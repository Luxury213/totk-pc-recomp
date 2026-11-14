// Isolated, opt-in creation experiment; this is not a companion gameplay API.
#pragma once
#include "cpu.h"

enum { COOP_NATIVE_PROBE_OFF, COOP_NATIVE_PROBE_CLONE, COOP_NATIVE_PROBE_OWNED, COOP_NATIVE_PROBE_NPC,
       COOP_NATIVE_PROBE_NPC_MOTION, COOP_NATIVE_PROBE_NPC_CONSUMER_MOTION };
void coop_native_probe_init(const char *profile, int timed_run, int mode);
void coop_native_probe_request(Cpu *cpu);
// Called only at the observed native actor-update entry, before its generated prologue.
void coop_native_probe_npc_update(Cpu *cpu);
void coop_native_probe_npc_consume(Cpu *cpu);
