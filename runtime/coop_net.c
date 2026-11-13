#include <enet/enet.h>
#include "coop_net.h"
#include "platform/platform.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NOTICE_CAP 256u
#define INTERVAL_NS 33333333ull
#define TIMEOUT_NS 5000000000ull

struct CoopNet {
    PlatMutex lock;
    PlatThread *thread;
    int stop;
    unsigned revision;
    CoopNetConfig config;
    CoopSample local;
    CoopNetSnapshot snapshot;
    char notices[NOTICE_CAP][96];
    unsigned notice_head, notice_count;
    uint64_t next_event;
};

static PlatOnce init_once = PLAT_ONCE_INIT;
static int enet_ok;
static void init_enet(void *arg) { (void)arg; enet_ok = enet_initialize() == 0; }

static int send_message(ENetPeer *peer, const CoopMessage *m, int reliable) {
    uint8_t bytes[COOP_WIRE_MAX];
    size_t n = coop_wire_encode(bytes, m);
    if (!n || !peer) return 0;
    if (enet_list_size(&peer->outgoingSendReliableCommands) + enet_list_size(&peer->sentReliableCommands) +
        enet_list_size(&peer->outgoingCommands) >= NOTICE_CAP) return 0;
    ENetPacket *p = enet_packet_create(bytes, n, reliable ? ENET_PACKET_FLAG_RELIABLE : 0);
    if (!p) return 0;
    if (enet_peer_send(peer, reliable ? 0 : 1, p)) { enet_packet_destroy(p); return 0; }
    return 1;
}

static void worker(void *arg) {
    CoopNet *n = arg;
    ENetHost *host = NULL;
    ENetPeer *peer = NULL;
    CoopSession session = {0};
    CoopNetConfig config = {0};
    CoopNetSnapshot view = {0};
    unsigned revision = 0;
    uint64_t last_tx = 0, last_rx = 0, began = 0;
    uint32_t sent_generation = UINT32_MAX;
    plat_once(&init_once, init_enet, NULL);
    for (;;) {
        plat_mutex_lock(&n->lock);
        int stop = n->stop;
        unsigned pending = n->revision;
        CoopNetConfig next = n->config;
        CoopSample local = n->local;
        plat_mutex_unlock(&n->lock);
        if (stop) break;
        uint64_t now = plat_now_ns();
        if (revision != pending) {
            revision = pending; config = next;
            if (host) enet_host_destroy(host);
            host = NULL; peer = NULL; view = (CoopNetSnapshot){0}; session = (CoopSession){0};
            sent_generation = UINT32_MAX; last_tx = last_rx = 0; began = now;
            if (config.mode) {
                uint64_t nonce = 0; uint32_t challenge = 0;
                if (!enet_ok || !config.player || !plat_random(&nonce, sizeof nonce) || !nonce ||
                    !plat_random(&challenge, sizeof challenge)) {
                    session.state = COOP_SESSION_ERROR;
                    snprintf(view.error, sizeof view.error, "Network initialization or random identity failed");
                } else if (config.game_version != 143) {
                    session.state = COOP_SESSION_INCOMPATIBLE;
                    snprintf(view.error, sizeof view.error, "This adapter supports game 1.4.3 only");
                } else {
                    coop_session_init(&session, config.mode == 1, config.game_version, config.content_id,
                                      config.player, nonce, challenge, config.capabilities);
                    ENetAddress address = {.host = ENET_HOST_ANY, .port = config.port};
                    host = enet_host_create(config.mode == 1 ? &address : NULL, 1, 2, 0, 0);
                    if (!host) {
                        session.state = COOP_SESSION_ERROR;
                        snprintf(view.error, sizeof view.error, "Cannot open ENet socket (port may be in use)");
                    } else {
                        host->maximumPacketSize = COOP_WIRE_MAX;
                        host->maximumWaitingData = COOP_WIRE_MAX * NOTICE_CAP;
                        if (config.mode == 2) {
                            if (enet_address_set_host_ip(&address, config.ip) < 0 ||
                                !(peer = enet_host_connect(host, &address, 2, COOP_PROTOCOL))) {
                                session.state = COOP_SESSION_ERROR;
                                snprintf(view.error, sizeof view.error, "Invalid host IPv4 address or connection failure");
                                enet_host_destroy(host); host = NULL;
                            }
                        }
                    }
                }
            }
        }
        // Stop advertising a player if its observer stopped running during a load or a stalled presentation.
        if (!local.time_ns || now - local.time_ns > 1000000000ull) {
            local.flags = 0;
            memset(local.rotation, 0, sizeof local.rotation);
            memset(local.animation, 0, sizeof local.animation);
            local.animation_frame = 0;
        }
        coop_session_sample(&session, &local);
        if (host) {
            ENetEvent event;
            int serviced;
            unsigned budget = 64;
            while (budget-- && (serviced = enet_host_service(host, &event, 0)) > 0) {
                if (event.type == ENET_EVENT_TYPE_CONNECT) {
                    if (config.mode == 1 && event.data != COOP_PROTOCOL) {
                        enet_peer_disconnect_now(event.peer, 2);
                        peer = NULL; coop_session_disconnected(&session);
                        session.state = COOP_SESSION_INCOMPATIBLE; view.rejected++;
                        snprintf(view.error, sizeof view.error, "Incompatible co-op protocol; rebuild both players");
                        continue;
                    }
                    plat_mutex_lock(&n->lock); n->notice_head = n->notice_count = 0; plat_mutex_unlock(&n->lock);
                    view.error[0] = 0;
                    peer = event.peer; began = now; last_rx = now;
                    // Each transport connection gets a fresh epoch, including a reconnect to a still-running host.
                    uint64_t nonce = 0; uint32_t challenge = 0;
                    if (!plat_random(&nonce, sizeof nonce) || !nonce || !plat_random(&challenge, sizeof challenge)) {
                        enet_peer_disconnect_now(peer, 1); peer = NULL; session.state = COOP_SESSION_ERROR;
                        continue;
                    }
                    coop_session_init(&session, config.mode == 1, config.game_version, config.content_id,
                                      config.player, nonce, challenge, config.capabilities);
                    coop_session_sample(&session, &local);
                    session.state = COOP_SESSION_NEGOTIATING;
                    sent_generation = UINT32_MAX;
                    enet_peer_timeout(peer, 8, 3000, 5000);
                    if (config.mode == 2) {
                        CoopMessage hello; coop_session_hello(&session, &hello);
                        view.packets_tx += send_message(peer, &hello, 1);
                    }
                } else if (event.type == ENET_EVENT_TYPE_RECEIVE) {
                    CoopMessage m, reply;
                    int decoded = coop_wire_decode(&m, event.packet->data, event.packet->dataLength);
                    int reliable = !!(event.packet->flags & ENET_PACKET_FLAG_RELIABLE);
                    int channel_ok = decoded && ((m.kind == COOP_MSG_STATE &&
                        ((event.channelID == 0 && reliable) || (event.channelID == 1 && !reliable))) ||
                        (m.kind != COOP_MSG_STATE && event.channelID == 0 && reliable));
                    if (!channel_ok) view.rejected++;
                    else {
                        int result = coop_session_receive(&session, &m, &reply);
                        if (result > 0) { view.packets_rx++; last_rx = now; }
                        if (result > 0 && m.kind == COOP_MSG_STATE) view.state_received_ns = now;
                        if (result == COOP_RX_REPLY) view.packets_tx += send_message(peer, &reply, 1);
                        if (result == COOP_RX_REJECT) {
                            snprintf(view.error, sizeof view.error, "Incompatible game, content or capabilities");
                            enet_peer_disconnect_now(event.peer, 2); peer = NULL;
                        }
                    }
                    enet_packet_destroy(event.packet);
                } else if (event.type == ENET_EVENT_TYPE_DISCONNECT) {
                    peer = NULL; coop_session_disconnected(&session);
                    if (event.data == 2) {
                        session.state = COOP_SESSION_INCOMPATIBLE;
                        snprintf(view.error, sizeof view.error, "Peer rejected incompatible protocol, game or content");
                    }
                    plat_mutex_lock(&n->lock); n->notice_head = n->notice_count = 0; plat_mutex_unlock(&n->lock);
                }
            }
            if (peer && ((session.negotiated && now - last_rx > TIMEOUT_NS) ||
                         (!session.negotiated && now - began > TIMEOUT_NS))) {
                enet_peer_disconnect_now(peer, 3); peer = NULL; coop_session_disconnected(&session);
            }
            if (peer && session.negotiated) {
                int reliable = sent_generation != local.generation;
                if (reliable || now - last_tx >= INTERVAL_NS) {
                    CoopMessage m; coop_session_state_message(&session, &m);
                    if (send_message(peer, &m, reliable)) {
                        view.packets_tx++; last_tx = now; sent_generation = local.generation;
                    }
                }
                for (unsigned i = 0; i < 16; i++) {
                    char label[96]; uint64_t id;
                    plat_mutex_lock(&n->lock);
                    int have = n->notice_count != 0;
                    if (have) {
                        memcpy(label, n->notices[n->notice_head], sizeof label);
                        n->notice_head = (n->notice_head + 1) % NOTICE_CAP; n->notice_count--;
                    }
                    id = ++n->next_event;
                    plat_mutex_unlock(&n->lock);
                    if (!have) break;
                    CoopMessage m;
                    if (coop_session_notice(&session, id, label, &m)) {
                        if (!send_message(peer, &m, 1)) {
                            enet_peer_disconnect_now(peer, 4); peer = NULL; coop_session_disconnected(&session);
                            snprintf(view.error, sizeof view.error, "Reliable notification queue failed");
                            break;
                        }
                        view.packets_tx++;
                    }
                }
            }
            enet_host_flush(host);
        }
        view.state = session.state; view.negotiated = session.negotiated;
        view.has_remote = session.have_remote && session.negotiated;
        view.remote = session.remote; view.session = session.session; view.peer_player = session.peer_player;
        view.notices = session.notices; memcpy(view.notice, session.notice, sizeof view.notice);
        view.ping_ms = peer ? peer->roundTripTime : 0;
        plat_mutex_lock(&n->lock);
        n->snapshot = view;
        n->snapshot.rejected += session.rejected;
        if (!session.negotiated) n->notice_count = n->notice_head = 0;
        plat_mutex_unlock(&n->lock);
        plat_sleep_ms(5);
    }
    if (peer) enet_peer_disconnect_now(peer, 0);
    if (host) enet_host_destroy(host);
}

CoopNet *coop_net_create(void) {
    CoopNet *n = calloc(1, sizeof *n);
    if (!n) return NULL;
    n->thread = plat_thread_new(worker, n, "coop-network");
    if (!n->thread) { free(n); return NULL; }
    return n;
}
void coop_net_destroy(CoopNet *n) {
    if (!n) return;
    plat_mutex_lock(&n->lock); n->stop = 1; plat_mutex_unlock(&n->lock);
    plat_thread_join(n->thread); free(n);
}
void coop_net_configure(CoopNet *n, const CoopNetConfig *config) {
    if (!n) return;
    plat_mutex_lock(&n->lock);
    n->config = *config; n->revision++; n->notice_head = n->notice_count = 0;
    n->snapshot = (CoopNetSnapshot){.state = config->mode == 1 ? COOP_SESSION_WAITING :
                                          config->mode == 2 ? COOP_SESSION_CONNECTING : COOP_SESSION_OFF};
    plat_mutex_unlock(&n->lock);
}
void coop_net_publish(CoopNet *n, const CoopSample *s) {
    if (!n) return;
    plat_mutex_lock(&n->lock); n->local = *s; plat_mutex_unlock(&n->lock);
}
void coop_net_snapshot(CoopNet *n, CoopNetSnapshot *out) {
    *out = (CoopNetSnapshot){0};
    if (!n) return;
    plat_mutex_lock(&n->lock); *out = n->snapshot; plat_mutex_unlock(&n->lock);
}
int coop_net_notice(CoopNet *n, const char *text) {
    if (!n || !text) return 0;
    plat_mutex_lock(&n->lock);
    int ok = n->snapshot.negotiated && n->notice_count < NOTICE_CAP;
    if (ok) {
        unsigned at = (n->notice_head + n->notice_count++) % NOTICE_CAP;
        snprintf(n->notices[at], sizeof n->notices[at], "%s", text);
    }
    plat_mutex_unlock(&n->lock);
    return ok;
}

int coop_net_player_id(const char *profile, uint64_t *out) {
    if (!profile || !*profile) return 0;
    char path[4096];
    if (snprintf(path, sizeof path, "%s/coop-player-id.bin", profile) >= (int)sizeof path) return 0;
    uint64_t size = 0; uint8_t *data = plat_file_read(path, &size);
    if (data) {
        int valid = size == sizeof *out;
        if (valid) memcpy(out, data, sizeof *out);
        free(data);
        return valid && *out;
    }
    // A corrupt existing identity must not silently create a different player in the host's roster.
    if (plat_file_exists(path) || !plat_random(out, sizeof *out) || !*out) return 0;
    plat_file_mkdir_p(profile);
    return plat_file_write_atomic(path, out, sizeof *out);
}
