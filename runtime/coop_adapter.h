// Version-specific guest observations. Native mutation capabilities remain zero until independently verified.
#pragma once
#include "coop_wire.h"
#include "cpu.h"

typedef struct {
    CoopSample sample;
    uint64_t actor, scene_address, observations;
    uint32_t commands_rejected, commands_stale, queued;
    uint32_t native_trace_count;
    uint32_t native_traces_by_kind[3]; // player method, physics component, matrix holder
    uint32_t native_constructor_trace_count;
    uint32_t native_holder_trace_count;
    uint32_t native_initializer_trace_count;
    uint32_t native_resident_match;
    char reason[128];
} CoopAdapterSnapshot;

enum { COOP_COMMAND_SPAWN = 1, COOP_COMMAND_MOVE, COOP_COMMAND_DESPAWN };
typedef struct {
    uint64_t session, entity, request_id, expires_ns;
    uint32_t generation, kind;
    float pos[3];
} CoopGuestCommand;

// Called before NVN_BLOCKING in nvnQueuePresentTexture. This is an observer, not a verified mutation phase.
void coop_adapter_observe(const Cpu *cpu);
void coop_adapter_snapshot(CoopAdapterSnapshot *out);
int coop_adapter_submit(const CoopGuestCommand *command);
uint32_t coop_adapter_capabilities(void);
void coop_adapter_trace_enable(int enable);
void coop_adapter_function(uint64_t address, uint64_t caller, uint64_t argument);
void coop_adapter_native_dispatch(uint64_t address, uint64_t caller, uint64_t x0,
                                  uint64_t x1, uint64_t x2);
