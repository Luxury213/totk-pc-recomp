// ENet belongs exclusively to the worker. Other threads exchange copies through this interface.
#pragma once
#include "coop_session.h"

typedef struct CoopNet CoopNet;
typedef struct {
    int mode;                // 0 off, 1 host, 2 client
    uint16_t port;
    char ip[64];
    uint32_t game_version, capabilities;
    uint64_t player;
    uint8_t content_id[32];
} CoopNetConfig;

typedef struct {
    int state, negotiated, has_remote;
    uint32_t packets_tx, packets_rx, rejected, ping_ms; // application messages; excludes ENet ACKs/retransmissions
    uint64_t session, peer_player, notices;
    uint64_t state_received_ns;
    CoopSample remote;
    char notice[96], error[96];
} CoopNetSnapshot;

CoopNet *coop_net_create(void);
void coop_net_destroy(CoopNet *net);
void coop_net_configure(CoopNet *net, const CoopNetConfig *config);
void coop_net_publish(CoopNet *net, const CoopSample *sample);
void coop_net_snapshot(CoopNet *net, CoopNetSnapshot *out);
int coop_net_notice(CoopNet *net, const char *label);
// A persistent random identity in this isolated profile, independent of the transport session nonce.
int coop_net_player_id(const char *profile, uint64_t *out);
