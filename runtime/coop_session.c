#include "coop_session.h"
#include <stdio.h>
#include <string.h>

static void update_state(CoopSession *s) {
    if (!s->negotiated) return;
    int native = (s->capabilities & COOP_REQUIRED_GAME_CAPS) == COOP_REQUIRED_GAME_CAPS &&
                 (s->peer_capabilities & COOP_REQUIRED_GAME_CAPS) == COOP_REQUIRED_GAME_CAPS;
    s->state = native && s->have_remote && (s->local.flags & COOP_SAMPLE_WORLD_READY) &&
               (s->remote.flags & COOP_SAMPLE_WORLD_READY) && s->local.scene == s->remote.scene
                   ? COOP_SESSION_READY : COOP_SESSION_LOADING;
}

void coop_session_init(CoopSession *s, int host, uint32_t version, const uint8_t content[32],
                       uint64_t player, uint64_t nonce, uint32_t challenge, uint32_t caps) {
    memset(s, 0, sizeof *s);
    s->host = host; s->state = host ? COOP_SESSION_WAITING : COOP_SESSION_CONNECTING;
    s->game_version = version; s->player = player; s->session = host ? nonce : 0;
    s->challenge = challenge; s->capabilities = caps;
    memcpy(s->content_id, content, 32);
}

void coop_session_hello(const CoopSession *s, CoopMessage *m) {
    *m = (CoopMessage){.kind = COOP_MSG_HELLO, .player = s->player, .seq = s->challenge,
                      .game_version = s->game_version, .capabilities = s->capabilities};
    memcpy(m->content_id, s->content_id, 32);
}

static int incompatible(CoopSession *s) {
    s->state = COOP_SESSION_INCOMPATIBLE; s->negotiated = s->have_remote = 0; s->rejected++;
    return COOP_RX_REJECT;
}

int coop_session_receive(CoopSession *s, const CoopMessage *m, CoopMessage *reply) {
    if (m->kind == COOP_MSG_HELLO || m->kind == COOP_MSG_WELCOME) {
        if ((s->host && m->kind != COOP_MSG_HELLO) || (!s->host && m->kind != COOP_MSG_WELCOME))
            return COOP_RX_IGNORE;
        if (s->negotiated && (m->player != s->peer_player || (!s->host && m->session != s->session)))
            return COOP_RX_IGNORE;
        if (!s->host && m->seq != s->challenge) return COOP_RX_IGNORE;
        if (s->host && s->negotiated && m->seq != s->peer_challenge) return COOP_RX_IGNORE;
        if (m->game_version != s->game_version || memcmp(m->content_id, s->content_id, 32) ||
            !(m->capabilities & COOP_CAP_PRESENCE) || m->player == s->player) return incompatible(s);
        s->peer_player = m->player; s->peer_capabilities = m->capabilities;
        if (s->host) s->peer_challenge = m->seq;
        if (!s->host) s->session = m->session;
        s->negotiated = 1;
        update_state(s);
        if (!s->host) return COOP_RX_ACCEPT;
        *reply = (CoopMessage){.kind = COOP_MSG_WELCOME, .session = s->session, .player = s->player,
                               .seq = m->seq, .game_version = s->game_version, .capabilities = s->capabilities};
        memcpy(reply->content_id, s->content_id, 32);
        return COOP_RX_REPLY;
    }
    if (!s->negotiated || m->session != s->session || m->player != s->peer_player) return COOP_RX_IGNORE;
    if (m->kind == COOP_MSG_STATE) {
        if (s->have_sequence && !coop_seq_newer(m->seq, s->rx_seq)) return COOP_RX_IGNORE;
        if (s->peer_generation && m->generation != s->peer_generation &&
            !coop_seq_newer(m->generation, s->peer_generation)) return COOP_RX_IGNORE;
        s->rx_seq = m->seq; s->have_sequence = 1; s->peer_generation = m->generation;
        s->remote = m->sample; s->have_remote = !!(m->sample.flags & COOP_SAMPLE_PLAYER);
        update_state(s);
        return COOP_RX_ACCEPT;
    }
    if (m->kind == COOP_MSG_NOTICE) {
        if (m->event_id <= s->last_event || m->generation != s->peer_generation) return COOP_RX_IGNORE;
        s->last_event = m->event_id; s->notices++;
        snprintf(s->notice, sizeof s->notice, "%s", m->label);
        return COOP_RX_ACCEPT;
    }
    return COOP_RX_IGNORE;
}

void coop_session_sample(CoopSession *s, const CoopSample *local) { s->local = *local; update_state(s); }

void coop_session_state_message(CoopSession *s, CoopMessage *m) {
    *m = (CoopMessage){.kind = COOP_MSG_STATE, .player = s->player, .session = s->session,
                      .seq = ++s->tx_seq, .generation = s->local.generation, .sample = s->local};
}

int coop_session_notice(CoopSession *s, uint64_t id, const char *text, CoopMessage *m) {
    if (!s->negotiated || !id || !text) return 0;
    *m = (CoopMessage){.kind = COOP_MSG_NOTICE, .session = s->session, .player = s->player,
                      .generation = s->local.generation, .event_id = id};
    snprintf(m->label, sizeof m->label, "%s", text);
    return 1;
}

void coop_session_disconnected(CoopSession *s) {
    s->negotiated = s->have_remote = s->have_sequence = 0;
    s->peer_generation = 0; s->last_event = 0; s->peer_player = 0;
    s->state = s->host ? COOP_SESSION_WAITING : COOP_SESSION_DISCONNECTED;
}
