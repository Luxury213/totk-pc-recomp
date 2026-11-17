// Diagnostic-only, read-only reachability search. No attachment ownership capability.
#pragma once
#include "coop_wire.h"
// Cold startup: timed copied-profile runs require an exact opt-in mapping file.
void coop_gear_probe_init(const char *profile, int timed);
// Guest observer only. Work and logging are bounded; no guest calls or writes.
void coop_gear_probe_observe(uint64_t actor, uint32_t actor_id, const CoopSample *sample, int64_t world_us);
// Verified original actor-reference setter boundary: record only bounded copied identities.
void coop_gear_probe_reference(uint64_t reference, uint64_t actor, uint64_t caller);
