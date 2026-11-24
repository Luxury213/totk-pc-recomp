// Game-free diagnostic relay of copied poses. Native movement and sender generations remain independent.
#pragma once
#include "coop_net.h"
#include <string.h>

typedef struct {
    CoopSample sample;
    uint64_t session,player,received_ns;
    unsigned available;
} CoopPoseRelay;

static inline void coop_pose_relay_offer(CoopPoseRelay *relay,const CoopNetSnapshot *peer,uint64_t now) {
    int valid=peer->negotiated && peer->has_remote && peer->session && peer->peer_player &&
        (peer->remote.flags&COOP_SAMPLE_PLAYER) && peer->remote.generation && peer->remote.time_ns &&
        peer->state_received_ns && now>=peer->state_received_ns && now-peer->state_received_ns<=250000000ull;
    if (!valid) { relay->available=0; return; }
    int same=relay->session==peer->session && relay->player==peer->peer_player && relay->sample.generation==peer->remote.generation;
    if (same && (peer->remote.time_ns<=relay->sample.time_ns || peer->state_received_ns<=relay->received_ns)) return;
    relay->sample=peer->remote; relay->session=peer->session; relay->player=peer->peer_player;
    relay->received_ns=peer->state_received_ns; relay->available=1;
}

static inline int coop_pose_relay_apply(const CoopPoseRelay *relay,CoopSample *sample,uint64_t now) {
    const unsigned optional=COOP_SAMPLE_ROTATION|COOP_SAMPLE_ANIMATION|COOP_SAMPLE_BODY|COOP_SAMPLE_EQUIPMENT;
    sample->flags&=~optional;
    memset(sample->rotation,0,sizeof sample->rotation); memset(sample->animation,0,sizeof sample->animation);
    sample->animation_frame=0; memset(&sample->body,0,sizeof sample->body); memset(&sample->equipment,0,sizeof sample->equipment);
    sample->action=0; sample->yaw=0;
    if (!relay->available || now<relay->received_ns || now-relay->received_ns>250000000ull) return 0;
    sample->flags|=relay->sample.flags&optional;
    memcpy(sample->rotation,relay->sample.rotation,sizeof sample->rotation);
    memcpy(sample->animation,relay->sample.animation,sizeof sample->animation);
    sample->animation_frame=relay->sample.animation_frame;
    sample->action=relay->sample.action; sample->yaw=relay->sample.yaw;
    if (sample->flags&COOP_SAMPLE_BODY) {
        if (coop_body_valid(&relay->sample.body)) sample->body=relay->sample.body;
        else sample->flags&=~COOP_SAMPLE_BODY;
    }
    if (sample->flags&COOP_SAMPLE_EQUIPMENT) sample->equipment=relay->sample.equipment;
    return 1;
}
