// Shared-world cooperative multiplayer (TOTK_COOP_MODE, TOTK_COOP_IP, TOTK_COOP_PORT).
//
// Reads the 3D camera uniform block (bank c4, size 0x940: rows 0-2 view matrix, rows 3-6 view-projection matrix)
// captured during scene draws in vk_exec_draw.c and the PlayerLink action component (main+0x3969918 on 1.4.3, as in
// mouse_direct.c). Exchanges 3D world coordinates, action verbs and shared world progression events over a
// non-blocking UDP socket, and projects the remote partner's 3D position into window coordinates for the ImGui
// background overlay.
#ifdef _WIN32
#include <windows.h>
#else
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "coop.h"
#include "host.h"
#include "layout.h"
#include "nvn_api.h"
#include "platform/platform.h"
#include "vk.h"

#define COOP_MAGIC 0x504F4F43u   // "COOP"
#define COOP_VERSION 1u
#define SEND_INTERVAL_NS 33333333ull   // 30 Hz state updates
#define PEER_TIMEOUT_NS 5000000000ull  // 5 s without packets marks peer disconnected
#define EVENT_SHOW_NS 6000000000ull    // 6 s banner display duration

enum {
    PKT_STATE = 1,
    PKT_WORLD_EVENT = 2,
};

typedef struct {
    uint32_t magic;
    uint8_t version;
    uint8_t kind;
    uint8_t action;
    uint8_t flags;
    uint32_t seq;
    uint32_t tx_ms;
    uint32_t echo_ms;
    float pos[3];
    float yaw;
    uint32_t world_syncs;
    char label[96];
} CoopPacket;

// ---- minimal dynamic Winsock loader on Windows (avoids adding -lws2_32 to existing build.ninja files)
#ifdef _WIN32
typedef uintptr_t CoopSock;
#define COOP_BAD_SOCK (~(uintptr_t)0)
#define COOP_AF_INET 2
#define COOP_SOCK_DGRAM 2
#define COOP_IPPROTO_UDP 17
#define COOP_FIONBIO 0x8004667Eu

typedef struct {
    int16_t sin_family;
    uint16_t sin_port;
    uint32_t sin_addr;
    char sin_zero[8];
} CoopSockAddrIn;

typedef struct {
    uint16_t wVersion;
    uint16_t wHighVersion;
    char szDescription[257];
    char szSystemStatus[129];
    uint16_t iMaxSockets;
    uint16_t iMaxUdpDg;
    char *lpVendorInfo;
} CoopWsaData;

static struct {
    int ready;
    int ok;
    int (WINAPI *startup)(uint16_t, CoopWsaData *);
    CoopSock (WINAPI *socket)(int, int, int);
    int (WINAPI *bind)(CoopSock, const CoopSockAddrIn *, int);
    int (WINAPI *sendto)(CoopSock, const char *, int, int, const CoopSockAddrIn *, int);
    int (WINAPI *recvfrom)(CoopSock, char *, int, int, CoopSockAddrIn *, int *);
    int (WINAPI *ioctlsocket)(CoopSock, long, unsigned long *);
    int (WINAPI *closesocket)(CoopSock);
    unsigned long (WINAPI *inet_addr)(const char *);
} W;

static int net_init(void) {
    if (W.ready) return W.ok;
    W.ready = 1;
    HMODULE m = LoadLibraryA("ws2_32.dll");
    if (!m) return 0;
    W.startup = (void *)GetProcAddress(m, "WSAStartup");
    W.socket = (void *)GetProcAddress(m, "socket");
    W.bind = (void *)GetProcAddress(m, "bind");
    W.sendto = (void *)GetProcAddress(m, "sendto");
    W.recvfrom = (void *)GetProcAddress(m, "recvfrom");
    W.ioctlsocket = (void *)GetProcAddress(m, "ioctlsocket");
    W.closesocket = (void *)GetProcAddress(m, "closesocket");
    W.inet_addr = (void *)GetProcAddress(m, "inet_addr");
    if (!W.startup || !W.socket || !W.bind || !W.sendto || !W.recvfrom || !W.ioctlsocket || !W.closesocket ||
        !W.inet_addr)
        return 0;
    CoopWsaData d;
    W.ok = W.startup(0x0202, &d) == 0;
    return W.ok;
}

static uint16_t net_htons(uint16_t v) { return (uint16_t)((v >> 8) | (v << 8)); }
#else
typedef int CoopSock;
#define COOP_BAD_SOCK (-1)
typedef struct sockaddr_in CoopSockAddrIn;
static int net_init(void) { return 1; }
static uint16_t net_htons(uint16_t v) { return htons(v); }
#endif

// ---- player action verb inspection (1.4.3 PlayerLink root slot main+0x3969918, matching mouse_direct.c)
enum { VERB_USE_BOW = 59, VERB_USE_SPECIAL_POWER = 61, VERB_DRAWN_BOW = 205, VERB_INVALID = 284 };

static int guest_readable(uint64_t p, uint64_t n) {
    return p >= 0x10000 && p < (1ull << 47) && !(p & 7) && mem_guest_readable(p, n);
}

static uint64_t guest_pointer(uint64_t at) {
    uint64_t v;
    memcpy(&v, (void *)(uintptr_t)at, sizeof v);
    return v;
}

static int32_t guest_s32(uint64_t at) {
    int32_t v;
    memcpy(&v, (void *)(uintptr_t)at, sizeof v);
    return v;
}

static int read_player_action(void) {
    if (rt_game_version != 143) return COOP_ACT_EXPLORING;
    uint64_t slot = MOD_MAIN_BASE + 0x3969918ull;
    if (!guest_readable(slot, 8)) return COOP_ACT_EXPLORING;
    uint64_t var = guest_pointer(slot);
    if (!guest_readable(var, 8)) return COOP_ACT_EXPLORING;
    uint64_t root = guest_pointer(var);
    if (!guest_readable(root, 0x38)) return COOP_ACT_EXPLORING;
    uint64_t link = root + 0x20, unit = guest_pointer(link + 8);
    int32_t id = guest_s32(link + 0x10);
    if (id == -1 || !guest_readable(unit, 0x50) || guest_s32(unit + 0x48) != id) return COOP_ACT_EXPLORING;
    uint64_t proc = guest_pointer(unit + 0x40);
    if (!guest_readable(proc, 0x230)) return COOP_ACT_EXPLORING;
    uint64_t vt = guest_pointer(proc);
    if (vt < MOD_MAIN_BASE || vt >= MOD_MAIN_BASE + 0x3adf000ull) return COOP_ACT_EXPLORING;
    if ((uint32_t)(guest_s32(proc + 0x24) - 7) < 5) return COOP_ACT_EXPLORING;
    uint64_t comps = guest_pointer(proc + 0x228);
    if (!guest_readable(comps, 0x160)) return COOP_ACT_EXPLORING;
    uint64_t as = guest_pointer(comps + 0x158);
    if (!guest_readable(as, 0x1f0 + 5 * 8)) return COOP_ACT_EXPLORING;
    for (int i = 0; i < 5; i++) {
        uint64_t s = guest_pointer(as + 0x1f0 + 8ull * i);
        if (!guest_readable(s, 0x50)) continue;
        int32_t v = guest_s32(s + 0x28);
        if (v == VERB_INVALID) v = guest_s32(s + 0x4c);
        if (v == VERB_USE_SPECIAL_POWER) return COOP_ACT_ABILITY;
        if (v == VERB_USE_BOW || v == VERB_DRAWN_BOW) return COOP_ACT_BOW;
    }
    return COOP_ACT_EXPLORING;
}

// ---- state protected by lock
static PlatMutex C_lock = PLAT_MUTEX_INIT;
static volatile int C_active_flag;

static struct {
    unsigned cfg_ver;
    int mode;
    char ip[64];
    int port;
    CoopSock sock;
    CoopSockAddrIn peer_addr;
    int have_peer_addr;

    // Camera & local player state from the render thread
    uint64_t cam_frame;
    int has_local;
    float local_pos[3];
    float local_fwd[3];
    float local_yaw;
    float vp[16];
    int local_action;

    // Remote partner state
    int has_peer;
    float peer_pos[3];
    float peer_target[3];
    float peer_yaw;
    int peer_action;
    uint64_t last_rx_ns;
    uint64_t last_tx_ns;
    uint32_t last_peer_tx_ms;
    uint32_t ping_ms;
    uint32_t seq;
    uint32_t packets_tx;
    uint32_t packets_rx;
    uint32_t world_syncs;

    // Bot companion state
    int bot_spawned;
    double bot_angle;

    // Banner notification
    char event_banner[160];
    uint64_t event_until_ns;
} C = {.sock = COOP_BAD_SOCK};

static int parse_mode(const char *s) {
    if (!s || !strcmp(s, "off") || !strcmp(s, "0")) return COOP_OFF;
    if (!strcmp(s, "host")) return COOP_HOST;
    if (!strcmp(s, "client")) return COOP_CLIENT;
    if (!strcmp(s, "bot")) return COOP_BOT;
    return COOP_OFF;
}

static void close_sock(void) {
    if (C.sock == COOP_BAD_SOCK) return;
#ifdef _WIN32
    if (W.closesocket) W.closesocket(C.sock);
#else
    close(C.sock);
#endif
    C.sock = COOP_BAD_SOCK;
}

static void open_sock(void) {
    close_sock();
    C.have_peer_addr = 0;
    if (C.mode == COOP_OFF || !net_init()) return;
#ifdef _WIN32
    C.sock = W.socket(COOP_AF_INET, COOP_SOCK_DGRAM, COOP_IPPROTO_UDP);
    if (C.sock == COOP_BAD_SOCK) return;
    unsigned long nb = 1;
    W.ioctlsocket(C.sock, (long)COOP_FIONBIO, &nb);
    if (C.mode == COOP_HOST || C.mode == COOP_BOT) {
        CoopSockAddrIn bind_addr = {0};
        bind_addr.sin_family = COOP_AF_INET;
        bind_addr.sin_port = net_htons((uint16_t)(C.mode == COOP_BOT ? 0 : C.port));
        bind_addr.sin_addr = 0;   // INADDR_ANY
        if (W.bind(C.sock, &bind_addr, sizeof bind_addr) != 0 && C.mode == COOP_HOST) {
            rt_log("coop: failed to bind UDP port %d", C.port);
            close_sock();
            return;
        }
    }
    if (C.mode == COOP_CLIENT) {
        memset(&C.peer_addr, 0, sizeof C.peer_addr);
        C.peer_addr.sin_family = COOP_AF_INET;
        C.peer_addr.sin_port = net_htons((uint16_t)C.port);
        unsigned long a = W.inet_addr(C.ip);
        C.peer_addr.sin_addr = a == 0xFFFFFFFFul ? W.inet_addr("127.0.0.1") : (uint32_t)a;
        C.have_peer_addr = 1;
    }
#else
    C.sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (C.sock < 0) {
        C.sock = COOP_BAD_SOCK;
        return;
    }
    int flags = fcntl(C.sock, F_GETFL, 0);
    fcntl(C.sock, F_SETFL, flags | O_NONBLOCK);
    if (C.mode == COOP_HOST) {
        struct sockaddr_in b = {0};
        b.sin_family = AF_INET;
        b.sin_port = htons((uint16_t)C.port);
        b.sin_addr.s_addr = htonl(INADDR_ANY);
        if (bind(C.sock, (struct sockaddr *)&b, sizeof b) < 0) {
            close_sock();
            return;
        }
    } else if (C.mode == COOP_CLIENT) {
        memset(&C.peer_addr, 0, sizeof C.peer_addr);
        C.peer_addr.sin_family = AF_INET;
        C.peer_addr.sin_port = htons((uint16_t)C.port);
        C.peer_addr.sin_addr.s_addr = inet_addr(C.ip);
        C.have_peer_addr = 1;
    }
#endif
    rt_log("coop: started mode=%d ip=%s port=%d", C.mode, C.ip, C.port);
}

static void refresh_cfg_locked(void) {
    unsigned v = cfg_version();
    if (v == C.cfg_ver && C.cfg_ver != 0) return;
    C.cfg_ver = v ? v : 1;
    int m = parse_mode(cfg_value("TOTK_COOP_MODE"));
    const char *ip = cfg_value("TOTK_COOP_IP");
    int port = cfg_int("TOTK_COOP_PORT");
    if (port < 1024 || port > 65535) port = 7777;
    int changed = (m != C.mode) || (port != C.port) || strncmp(C.ip, ip ? ip : "127.0.0.1", sizeof C.ip - 1);
    C.mode = m;
    snprintf(C.ip, sizeof C.ip, "%s", ip && *ip ? ip : "127.0.0.1");
    C.port = port;
    __atomic_store_n(&C_active_flag, m != COOP_OFF, __ATOMIC_RELEASE);
    if (changed) {
        C.has_peer = 0;
        C.bot_spawned = 0;
        C.packets_rx = C.packets_tx = 0;
        open_sock();
    }
}

int coop_active(void) {
    static unsigned seen_ver;
    unsigned v = cfg_version();
    if (v != seen_ver || !seen_ver) {
        plat_mutex_lock(&C_lock);
        refresh_cfg_locked();
        seen_ver = C.cfg_ver;
        plat_mutex_unlock(&C_lock);
    }
    return __atomic_load_n(&C_active_flag, __ATOMIC_ACQUIRE);
}

// Called from vk_exec_draw.c when bank c4 (0x940 camera block) is bound on a scene depth draw.
void coop_capture_camera(uint64_t cam_addr) {
    if (!__atomic_load_n(&C_active_flag, __ATOMIC_RELAXED) || !cam_addr) return;
    uint64_t frame = __atomic_load_n(&gfx_counters.frames, __ATOMIC_RELAXED);
    if (frame == C.cam_frame && C.has_local) return;
    const float *f = (const float *)vk_usnap_bytes(cam_addr, 112);   // rows 0-2 (view) + rows 3-6 (view-projection)
    if (!f) return;
    // Row-major 3x4 view matrix V = [R | t] in f[0..11]: camera world position C = -R^T * t.
    float cx = -(f[0] * f[3] + f[4] * f[7] + f[8] * f[11]);
    float cy = -(f[1] * f[3] + f[5] * f[7] + f[9] * f[11]);
    float cz = -(f[2] * f[3] + f[6] * f[7] + f[10] * f[11]);
    if (!isfinite(cx) || !isfinite(cy) || !isfinite(cz)) return;
    if (fabsf(cx) < 1e-3f && fabsf(cy) < 1e-3f && fabsf(cz) < 1e-3f) return;
    // Camera forward vector (-row 2 of R)
    float fx = -f[8], fy = -f[9], fz = -f[10];
    float fh = sqrtf(fx * fx + fz * fz);
    float hfx = fh > 1e-4f ? fx / fh : 0.0f;
    float hfz = fh > 1e-4f ? fz / fh : 1.0f;
    // Link stands roughly 4.2 m in front of the third-person orbit camera
    float lx = cx + hfx * 4.2f;
    float ly = cy + fy * 4.2f - 0.5f;
    float lz = cz + hfz * 4.2f;

    plat_mutex_lock(&C_lock);
    C.cam_frame = frame;
    C.has_local = 1;
    C.local_pos[0] = lx;
    C.local_pos[1] = ly;
    C.local_pos[2] = lz;
    C.local_fwd[0] = fx;
    C.local_fwd[1] = fy;
    C.local_fwd[2] = fz;
    C.local_yaw = atan2f(hfx, hfz) * (180.0f / 3.14159265f);
    memcpy(C.vp, f + 12, 16 * sizeof(float));
    plat_mutex_unlock(&C_lock);
}

static void send_packet_locked(const CoopPacket *pkt) {
    if (C.sock == COOP_BAD_SOCK || !C.have_peer_addr) return;
#ifdef _WIN32
    int r = W.sendto(C.sock, (const char *)pkt, (int)sizeof *pkt, 0, &C.peer_addr, (int)sizeof C.peer_addr);
#else
    int r = (int)sendto(C.sock, pkt, sizeof *pkt, 0, (const struct sockaddr *)&C.peer_addr, sizeof C.peer_addr);
#endif
    if (r == (int)sizeof *pkt) C.packets_tx++;
}

static void poll_socket_locked(uint64_t now_ns) {
    if (C.sock == COOP_BAD_SOCK) return;
    for (int i = 0; i < 16; i++) {
        CoopPacket pkt;
        CoopSockAddrIn from = {0};
#ifdef _WIN32
        int from_len = sizeof from;
        int n = W.recvfrom(C.sock, (char *)&pkt, (int)sizeof pkt, 0, &from, &from_len);
#else
        socklen_t from_len = sizeof from;
        int n = (int)recvfrom(C.sock, &pkt, sizeof pkt, 0, (struct sockaddr *)&from, &from_len);
#endif
        if (n <= 0) break;
        if (n < (int)sizeof(CoopPacket) || pkt.magic != COOP_MAGIC || pkt.version != COOP_VERSION) continue;
        if (C.mode == COOP_HOST) {
            C.peer_addr = from;
            C.have_peer_addr = 1;
        }
        C.packets_rx++;
        C.last_rx_ns = now_ns;
        C.last_peer_tx_ms = pkt.tx_ms;
        uint32_t now_ms = (uint32_t)(now_ns / 1000000ull);
        if (pkt.echo_ms && now_ms >= pkt.echo_ms && now_ms - pkt.echo_ms < 10000)
            C.ping_ms = now_ms - pkt.echo_ms;
        if (pkt.kind == PKT_STATE) {
            if (isfinite(pkt.pos[0]) && isfinite(pkt.pos[1]) && isfinite(pkt.pos[2])) {
                if (!C.has_peer) {
                    memcpy(C.peer_pos, pkt.pos, sizeof C.peer_pos);
                }
                memcpy(C.peer_target, pkt.pos, sizeof C.peer_target);
                C.peer_yaw = pkt.yaw;
                C.peer_action = pkt.action;
                C.has_peer = 1;
            }
        } else if (pkt.kind == PKT_WORLD_EVENT) {
            C.world_syncs = pkt.world_syncs > C.world_syncs ? pkt.world_syncs : C.world_syncs + 1;
            pkt.label[sizeof pkt.label - 1] = 0;
            snprintf(C.event_banner, sizeof C.event_banner, "%s", pkt.label);
            C.event_until_ns = now_ns + EVENT_SHOW_NS;
            rt_log("coop: received shared world event #%u: %s", C.world_syncs, C.event_banner);
        }
    }
}

static void tick_bot_locked(uint64_t now_ns, double dt) {
    C.last_rx_ns = now_ns;
    C.ping_ms = 1;
    if (!C.has_local) return;
    float lx = C.local_pos[0], ly = C.local_pos[1], lz = C.local_pos[2];
    if (!C.bot_spawned) {
        float fx = C.local_fwd[0], fz = C.local_fwd[2];
        float fh = sqrtf(fx * fx + fz * fz);
        float hfx = fh > 1e-4f ? fx / fh : 0.0f;
        float hfz = fh > 1e-4f ? fz / fh : 1.0f;
        C.peer_pos[0] = C.peer_target[0] = lx + hfx * 6.0f;
        C.peer_pos[1] = C.peer_target[1] = ly;
        C.peer_pos[2] = C.peer_target[2] = lz + hfz * 6.0f;
        C.bot_spawned = 1;
        C.has_peer = 1;
        snprintf(C.event_banner, sizeof C.event_banner,
                 "Compañero de prueba conectado en el mundo compartido (6 m frente a Link)");
        C.event_until_ns = now_ns + EVENT_SHOW_NS;
    }
    C.bot_angle += dt * 0.65;
    // Target point orbits gently 5.5 m around Link's vicinity and follows if Link walks away
    float desired_x = lx + (float)cos(C.bot_angle) * 5.5f;
    float desired_y = ly + (float)sin(C.bot_angle * 2.0) * 0.15f;
    float desired_z = lz + (float)sin(C.bot_angle) * 5.5f;
    float rate = (float)fmin(1.0, dt * 3.5);
    C.peer_pos[0] += (desired_x - C.peer_pos[0]) * rate;
    C.peer_pos[1] += (desired_y - C.peer_pos[1]) * rate;
    C.peer_pos[2] += (desired_z - C.peer_pos[2]) * rate;
    C.peer_yaw = (float)fmod(C.bot_angle * (180.0 / 3.14159265) + 90.0, 360.0);
    int phase = (int)(now_ns / 4000000000ull) % 3;
    C.peer_action = phase == 0 ? COOP_ACT_EXPLORING : phase == 1 ? COOP_ACT_BOW : COOP_ACT_ABILITY;
    C.packets_rx = (uint32_t)(now_ns / 33333333ull);
    C.packets_tx = C.packets_rx;
}

// Projects a 3D world point (x, y, z) through the row-major 4x4 View-Projection matrix vp[0..15] to 2D window pixels.
static int project_3d(const float vp[16], const float p[3], float w, float h, float out[2]) {
    float x = p[0], y = p[1], z = p[2];
    float cx = vp[0] * x + vp[1] * y + vp[2] * z + vp[3];
    float cy = vp[4] * x + vp[5] * y + vp[6] * z + vp[7];
    float cw = vp[12] * x + vp[13] * y + vp[14] * z + vp[15];
    if (cw > 0.1f) {
        float ndc_x = cx / cw;
        float ndc_y = cy / cw;
        out[0] = (ndc_x * 0.5f + 0.5f) * w;
        out[1] = (0.5f - ndc_y * 0.5f) * h;
        if (out[0] >= 24.0f && out[0] <= w - 24.0f && out[1] >= 24.0f && out[1] <= h - 24.0f) return 1;
    }
    // Behind camera or off-screen: clamp to screen border so the player always knows which direction their partner is
    float dir_x = cw > 0.0f ? cx : -cx;
    float dir_y = cw > 0.0f ? -cy : cy;
    float len = sqrtf(dir_x * dir_x + dir_y * dir_y);
    if (len < 1e-4f) {
        dir_x = 0.0f;
        dir_y = -1.0f;
    } else {
        dir_x /= len;
        dir_y /= len;
    }
    float pad = 48.0f;
    float rx = (w * 0.5f - pad) * dir_x + w * 0.5f;
    float ry = (h * 0.5f - pad) * dir_y + h * 0.5f;
    out[0] = fmaxf(pad, fminf(w - pad, rx));
    out[1] = fmaxf(pad, fminf(h - pad, ry));
    return 0;
}

void coop_tick(uint32_t width, uint32_t height, CoopSnapshot *out) {
    memset(out, 0, sizeof *out);
    uint64_t now = plat_now_ns();
    static uint64_t last_tick_ns;
    double dt = last_tick_ns ? (double)(now - last_tick_ns) / 1e9 : 1.0 / 60.0;
    if (dt < 0.0001 || dt > 0.25) dt = 1.0 / 60.0;
    last_tick_ns = now;

    int act = __atomic_load_n(&C_active_flag, __ATOMIC_RELAXED) ? read_player_action() : COOP_ACT_EXPLORING;

    plat_mutex_lock(&C_lock);
    refresh_cfg_locked();
    C.local_action = act;
    if (C.mode == COOP_OFF) {
        plat_mutex_unlock(&C_lock);
        return;
    }

    if (C.mode == COOP_BOT) {
        tick_bot_locked(now, dt);
    } else {
        poll_socket_locked(now);
        if (C.has_peer) {
            float rate = (float)fmin(1.0, dt * 12.0);
            for (int k = 0; k < 3; k++) C.peer_pos[k] += (C.peer_target[k] - C.peer_pos[k]) * rate;
        }
        if (now - C.last_tx_ns >= SEND_INTERVAL_NS && C.have_peer_addr) {
            C.last_tx_ns = now;
            CoopPacket pkt = {
                .magic = COOP_MAGIC,
                .version = COOP_VERSION,
                .kind = PKT_STATE,
                .action = (uint8_t)C.local_action,
                .flags = (uint8_t)C.has_local,
                .seq = ++C.seq,
                .tx_ms = (uint32_t)(now / 1000000ull),
                .echo_ms = C.last_peer_tx_ms,
                .pos = {C.local_pos[0], C.local_pos[1], C.local_pos[2]},
                .yaw = C.local_yaw,
                .world_syncs = C.world_syncs,
            };
            send_packet_locked(&pkt);
        }
    }

    int connected = C.last_rx_ns && (now - C.last_rx_ns < PEER_TIMEOUT_NS);
    out->mode = C.mode;
    out->connected = connected;
    out->ping_ms = C.ping_ms;
    out->packets_tx = C.packets_tx;
    out->packets_rx = C.packets_rx;
    out->world_syncs = C.world_syncs;
    out->has_local_pos = C.has_local;
    memcpy(out->local_pos, C.local_pos, sizeof out->local_pos);
    memcpy(out->local_fwd, C.local_fwd, sizeof out->local_fwd);
    out->local_action = C.local_action;
    out->has_peer_pos = connected && C.has_peer;
    if (out->has_peer_pos) {
        memcpy(out->peer_pos, C.peer_pos, sizeof out->peer_pos);
        out->peer_yaw = C.peer_yaw;
        out->peer_action = C.peer_action;
        float dx = C.peer_pos[0] - C.local_pos[0];
        float dy = C.peer_pos[1] - C.local_pos[1];
        float dz = C.peer_pos[2] - C.local_pos[2];
        out->peer_dist = sqrtf(dx * dx + dy * dy + dz * dz);
        if (C.has_local && width > 0 && height > 0) {
            float head[3] = {C.peer_pos[0], C.peer_pos[1] + 1.9f, C.peer_pos[2]};
            out->peer_on_screen = project_3d(C.vp, head, (float)width, (float)height, out->peer_screen);
            project_3d(C.vp, C.peer_pos, (float)width, (float)height, out->peer_foot_screen);
        }
    }

    if (C.mode == COOP_BOT) {
        snprintf(out->status_text, sizeof out->status_text, "Bot activo · %.1f m · Mundo compartido", out->peer_dist);
    } else if (connected) {
        snprintf(out->status_text, sizeof out->status_text, "Conectado (%s:%d) · %u ms · %.1f m", C.ip, C.port,
                 out->ping_ms, out->peer_dist);
    } else if (C.mode == COOP_HOST) {
        snprintf(out->status_text, sizeof out->status_text, "Esperando jugador en UDP :%d...", C.port);
    } else {
        snprintf(out->status_text, sizeof out->status_text, "Conectando a %s:%d...", C.ip, C.port);
    }

    if (now < C.event_until_ns && C.event_banner[0]) {
        snprintf(out->event_banner, sizeof out->event_banner, "%s", C.event_banner);
        double rem = (double)(C.event_until_ns - now) / 1e9;
        out->event_alpha = rem < 1.0 ? (float)rem : 1.0f;
    }
    plat_mutex_unlock(&C_lock);
}

void coop_notify_world_event(const char *label) {
    if (!coop_active()) return;
    uint64_t now = plat_now_ns();
    plat_mutex_lock(&C_lock);
    C.world_syncs++;
    snprintf(C.event_banner, sizeof C.event_banner, "%s (Evento #%u)",
             label && *label ? label : "Mundo compartido sincronizado", C.world_syncs);
    C.event_until_ns = now + EVENT_SHOW_NS;
    if (C.mode == COOP_HOST || C.mode == COOP_CLIENT) {
        CoopPacket pkt = {
            .magic = COOP_MAGIC,
            .version = COOP_VERSION,
            .kind = PKT_WORLD_EVENT,
            .seq = ++C.seq,
            .tx_ms = (uint32_t)(now / 1000000ull),
            .echo_ms = C.last_peer_tx_ms,
            .pos = {C.local_pos[0], C.local_pos[1], C.local_pos[2]},
            .yaw = C.local_yaw,
            .world_syncs = C.world_syncs,
        };
        snprintf(pkt.label, sizeof pkt.label, "%s", C.event_banner);
        send_packet_locked(&pkt);
    }
    rt_log("coop: world event #%u broadcast: %s", C.world_syncs, C.event_banner);
    plat_mutex_unlock(&C_lock);
}

void coop_on_save_commit(int changed_files) {
    if (!__atomic_load_n(&C_active_flag, __ATOMIC_RELAXED) || changed_files <= 0) return;
    char msg[128];
    snprintf(msg, sizeof msg, "Mundo compartido: progreso guardado (%d archivos sincronizados)", changed_files);
    coop_notify_world_event(msg);
}

void coop_summon_partner(void) {
    if (!coop_active()) return;
    plat_mutex_lock(&C_lock);
    if (C.has_local) {
        float fx = C.local_fwd[0], fz = C.local_fwd[2];
        float fh = sqrtf(fx * fx + fz * fz);
        float hfx = fh > 1e-4f ? fx / fh : 0.0f;
        float hfz = fh > 1e-4f ? fz / fh : 1.0f;
        C.peer_pos[0] = C.peer_target[0] = C.local_pos[0] + hfx * 4.5f;
        C.peer_pos[1] = C.peer_target[1] = C.local_pos[1];
        C.peer_pos[2] = C.peer_target[2] = C.local_pos[2] + hfz * 4.5f;
        C.has_peer = 1;
        C.bot_spawned = 1;
    }
    plat_mutex_unlock(&C_lock);
    coop_notify_world_event("Mundo compartido: baliza de misión y posición sincronizadas");
}
