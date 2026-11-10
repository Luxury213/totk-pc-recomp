// Pure session state machine, shared by the runtime worker and headless network tests.
#pragma once
#include "coop_wire.h"

enum { COOP_SESSION_OFF, COOP_SESSION_CONNECTING, COOP_SESSION_NEGOTIATING,
       COOP_SESSION_LOADING, COOP_SESSION_READY, COOP_SESSION_WAITING, COOP_SESSION_DISCONNECTED,
       COOP_SESSION_INCOMPATIBLE, COOP_SESSION_ERROR };
enum { COOP_RX_REJECT = -1, COOP_RX_IGNORE = 0, COOP_RX_ACCEPT = 1, COOP_RX_REPLY = 2 };

typedef struct {
    int host, state, negotiated, have_sequence;
    uint32_t game_version, capabilities, peer_capabilities, challenge, peer_challenge, tx_seq, rx_seq, peer_generation;
    uint64_t player, peer_player, session, last_event;
    uint8_t content_id[32];
    CoopSample local, remote;
    int have_remote;
    char notice[96];
    uint64_t notices;
    uint32_t rejected;
} CoopSession;

void coop_session_init(CoopSession *s, int host, uint32_t game_version, const uint8_t content[32],
                       uint64_t player, uint64_t nonce, uint32_t challenge, uint32_t capabilities);
void coop_session_hello(const CoopSession *s, CoopMessage *out);
int coop_session_receive(CoopSession *s, const CoopMessage *m, CoopMessage *reply);
void coop_session_sample(CoopSession *s, const CoopSample *local);
void coop_session_state_message(CoopSession *s, CoopMessage *out);
int coop_session_notice(CoopSession *s, uint64_t event_id, const char *text, CoopMessage *out);
void coop_session_disconnected(CoopSession *s);
