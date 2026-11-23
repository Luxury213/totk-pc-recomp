// Bounded 1.4.3 retirement experiment, invoked only by the owned NPC's native update hook.
#pragma once
#include "cpu.h"

typedef struct {
    uint64_t actor, body;
    uint32_t generation;
    int32_t actor_id;
    unsigned attempted, accepted, refusals;
    int64_t rest_since_us, rest_last_us;
    unsigned rest_samples;
    float rest_pos[6];
} CoopRetirement;

// Refusal leaves guest state alone. An issued request is never retried; asynchronous cleanup is separate proof.
int coop_retirement_try(Cpu *cpu, CoopRetirement *request);
// Read-only verification of the original actor-update dispatch's current task/TLS/worker slot.
// Zero means the calling worker currently owns this actor; no creation/removal authority is implied.
int coop_actor_worker_context(const Cpu *cpu, uint64_t actor, unsigned *worker, uint32_t *tag);
