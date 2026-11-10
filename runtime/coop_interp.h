// Presentation-only history. Never feed interpolated poses back into native physics.
#pragma once
#include "coop_wire.h"
typedef struct {
    CoopSample samples[16];
    uint64_t received_ns[16];
    unsigned count;
} CoopInterpolator;
void coop_interp_push(CoopInterpolator *buffer, const CoopSample *sample, uint64_t received_ns);
int coop_interp_read(const CoopInterpolator *buffer, uint64_t now_ns, CoopSample *out);
