// TotK 1.4.3 read-only adapter. Observation is separate from unverified actor and physics operations.
// Rotation/animation readers adapted from arnaldolima1/totk-recomp runtime/frame_rate.c
// game_player_quat and game_player_anim @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c.
// MIT, Copyright (c) 2026 Valiantsin Dzerakh; runtime/third_party/licenses/totk-recomp.txt.
#include "coop_adapter.h"
#include "coop.h"
#include "cfg.h"
#include "host.h"
#include "layout.h"
#include "platform/platform.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

// ---- Read-only PlayerLink inspection (1.4.3 PlayerLink root slot main+0x3969918)
enum { VERB_USE_BOW = 59, VERB_USE_SPECIAL_POWER = 61, VERB_DRAWN_BOW = 205, VERB_INVALID = 284 };

static int guest_readable(uint64_t p, uint64_t n) {
    return p >= 0x10000 && p < (1ull << 47) && !(p & 3) && mem_guest_readable(p, n);
}

static uint64_t guest_pointer(uint64_t at) {
    uint64_t v = 0;
    if (!plat_mem_read(at, &v, sizeof v)) return 0;
    return v;
}

static int32_t guest_s32(uint64_t at) {
    int32_t v = -1;
    if (!plat_mem_read(at, &v, sizeof v)) return -1;
    return v;
}

static float guest_f32(uint64_t at) {
    float v = NAN;
    if (!plat_mem_read(at, &v, sizeof v)) return NAN;
    return v;
}

// Resolves scene component 13, whose resident list is used by runtime/frame_rate.c:player_pos.
static uint64_t resident_component(void) {
    if (rt_game_version != 143) return 0;
    uint64_t mod_slot = MOD_MAIN_BASE + 0x3add238ull;
    if (!guest_readable(mod_slot, 8)) return 0;
    uint64_t module = guest_pointer(mod_slot);
    if (!guest_readable(module + 0x1e8ull, 8)) return 0;
    uint64_t scene = guest_pointer(module + 0x1e8ull);
    if (!guest_readable(scene + 0x50ull, 4)) return 0;
    int32_t comp_count = guest_s32(scene + 0x50ull);
    if (comp_count < 14 || comp_count > 256) return 0;
    if (!guest_readable(scene + 0x58ull, 8)) return 0;
    uint64_t comps = guest_pointer(scene + 0x58ull);
    if (!guest_readable(comps + 13ull * 8ull, 8)) return 0;
    uint64_t resident = guest_pointer(comps + 13ull * 8ull);
    return guest_readable(resident + 0x20ull, 16) ? resident : 0;
}

// Finds the named actor and its record in the resident list. The PlayerMgr pointer alone does not prove membership.
static uint64_t resident_player_proc(uint64_t expected_actor, uint64_t *record_out, uint64_t *data_out) {
    uint64_t resident = resident_component();
    if (!resident) return 0;
    int32_t count = guest_s32(resident + 0x20ull);
    uint64_t links = guest_pointer(resident + 0x28ull);
    if (count <= 0 || count > 64 || !guest_readable(links, (uint64_t)count * 0x70ull)) return 0;
    for (int32_t i = 0; i < count; i++) {
        uint64_t record = links + (uint64_t)i * 0x70ull;
        uint64_t data = guest_pointer(record + 8ull);
        if (!guest_readable(data + 0x40ull, 8)) continue;
        uint64_t actor = guest_pointer(data + 0x40ull);
        if (!guest_readable(actor, 0x300)) continue;
        if (expected_actor && actor != expected_actor) continue;
        uint64_t name = guest_pointer(actor + 0x218ull);
        char text[7];
        if (name && plat_mem_read(name, text, sizeof text) && !memcmp(text, "Player", sizeof text) &&
            (uint32_t)guest_s32(actor + 0x24) - 7u >= 5u) {
            if (record_out) *record_out = record;
            if (data_out) *data_out = data;
            return actor;
        }
    }
    return 0;
}

// Returns the validated PlayerLink ActorBase pointer (proc) on 1.4.3, or 0 when not spawned.
// Checks PlayerMgr first (main+0x3969918), then the scene resident list as a fallback.
static uint64_t player_proc(void) {
    if (rt_game_version != 143) return 0;
    uint64_t slot = MOD_MAIN_BASE + 0x3969918ull;
    if (guest_readable(slot, 8)) {
        uint64_t var = guest_pointer(slot);
        if (guest_readable(var, 8)) {
            uint64_t root = guest_pointer(var);
            if (guest_readable(root, 0x38)) {
                uint64_t link = root + 0x20, unit = guest_pointer(link + 8);
                int32_t id = guest_s32(link + 0x10);
                if (id != -1 && guest_readable(unit, 0x50) && guest_s32(unit + 0x48) == id) {
                    uint64_t proc = guest_pointer(unit + 0x40);
                    if (guest_readable(proc, 0x300)) {
                        uint64_t vt = guest_pointer(proc);
                        if (vt >= MOD_MAIN_BASE && vt < MOD_MAIN_BASE + 0x3adf000ull &&
                            (uint32_t)guest_s32(proc + 0x24) - 7u >= 5u) return proc;
                    }
                }
            }
        }
    }
    return resident_player_proc(0, NULL, NULL);
}

// Locate the manager's actor-reference slot without claiming that another actor may safely own it.
static uint64_t player_manager_link(void) {
    if (rt_game_version != 143 || !guest_readable(MOD_MAIN_BASE + 0x3969918ull, 8)) return 0;
    uint64_t var = guest_pointer(MOD_MAIN_BASE + 0x3969918ull);
    uint64_t root = guest_readable(var, 8) ? guest_pointer(var) : 0;
    return guest_readable(root, 0x38) ? root + 0x20ull : 0;
}

// Reads Link's exact 3D ActorBase position (proc+0x2b4), facing yaw (proc+0x2c0) and action verb (comps+0x158).
static uint64_t read_player_state(float pos_out[3], float *yaw_out, int *action_out) {
    *action_out = COOP_ACT_EXPLORING;
    uint64_t proc = player_proc();
    if (!proc) return 0;
    int got_pos = 0;
    float px = guest_f32(proc + 0x2b4ull);
    float py = guest_f32(proc + 0x2b8ull);
    float pz = guest_f32(proc + 0x2bcull);
    // Match frame_rate.c player_pos/world_clock's conservative title-screen exclusion. A render camera alone
    // never proves that a playable actor exists. This is still a heuristic, not a scene-lifecycle hook.
    if (isfinite(px) && isfinite(py) && isfinite(pz) && (fabsf(px) + fabsf(pz) >= 1.0f)) {
        pos_out[0] = px;
        pos_out[1] = py;
        pos_out[2] = pz;
        got_pos = 1;
        // Forward column (+Z of ActorBase::mRotation 3x3 at proc+0x2c0: m02 at +0x2c8, m22 at +0x2e0)
        float fx = guest_f32(proc + 0x2c8ull);
        float fz = guest_f32(proc + 0x2e0ull);
        if (isfinite(fx) && isfinite(fz) && (fx * fx + fz * fz > 1e-4f)) {
            *yaw_out = atan2f(fx, fz) * (180.0f / 3.14159265f);
        }
    }
    uint64_t comps = guest_pointer(proc + 0x228ull);
    if (guest_readable(comps, 0x160)) {
        uint64_t as = guest_pointer(comps + 0x158ull);
        if (guest_readable(as, 0x1f0 + 5 * 8)) {
            for (int i = 0; i < 5; i++) {
                uint64_t s = guest_pointer(as + 0x1f0 + 8ull * i);
                if (!guest_readable(s, 0x50)) continue;
                int32_t v = guest_s32(s + 0x28);
                if (v == VERB_INVALID) v = guest_s32(s + 0x4c);
                if (v == VERB_USE_SPECIAL_POWER) {
                    *action_out = COOP_ACT_ABILITY;
                    break;
                }
                if (v == VERB_USE_BOW || v == VERB_DRAWN_BOW) {
                    *action_out = COOP_ACT_BOW;
                    break;
                }
            }
        }
    }
    return got_pos ? proc : 0;
}


// Optional presentation state from the position observation's actor. Missing or changing model
// state leaves these fields absent without invalidating otherwise usable presence.
static void read_player_visual(uint64_t actor, CoopSample *sample) {
    float m[9], q[4];
    if (plat_mem_read(actor + 0x2c0, m, sizeof m)) {
        int valid = 1;
        for (int i = 0; i < 9; i++) if (!isfinite(m[i]) || fabsf(m[i]) > 1.02f) valid = 0;
        // Reject incomplete, scaled, reflected or sheared transforms before quaternion conversion.
        for (int i = 0; i < 3; i++) for (int j = i; j < 3; j++) {
            float dot = m[i] * m[j] + m[3 + i] * m[3 + j] + m[6 + i] * m[6 + j];
            if (fabsf(dot - (i == j ? 1 : 0)) > .03f) valid = 0;
        }
        float det = m[0] * (m[4] * m[8] - m[5] * m[7]) -
                    m[1] * (m[3] * m[8] - m[5] * m[6]) + m[2] * (m[3] * m[7] - m[4] * m[6]);
        if (valid && det > .95f && det < 1.05f) {
            float tr = m[0] + m[4] + m[8], s;
            if (tr > 0) {
                s = sqrtf(tr + 1) * 2;
                q[3] = .25f * s; q[0] = (m[7] - m[5]) / s;
                q[1] = (m[2] - m[6]) / s; q[2] = (m[3] - m[1]) / s;
            } else if (m[0] > m[4] && m[0] > m[8]) {
                s = sqrtf(1 + m[0] - m[4] - m[8]) * 2;
                q[3] = (m[7] - m[5]) / s; q[0] = .25f * s;
                q[1] = (m[1] + m[3]) / s; q[2] = (m[2] + m[6]) / s;
            } else if (m[4] > m[8]) {
                s = sqrtf(1 + m[4] - m[0] - m[8]) * 2;
                q[3] = (m[2] - m[6]) / s; q[0] = (m[1] + m[3]) / s;
                q[1] = .25f * s; q[2] = (m[5] + m[7]) / s;
            } else {
                s = sqrtf(1 + m[8] - m[0] - m[4]) * 2;
                q[3] = (m[3] - m[1]) / s; q[0] = (m[2] + m[6]) / s;
                q[1] = (m[5] + m[7]) / s; q[2] = .25f * s;
            }
            float norm = sqrtf(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3]);
            if (isfinite(norm) && norm > .5f && norm < 1.5f) {
                for (int i = 0; i < 4; i++) sample->rotation[i] = q[i] / norm;
                sample->flags |= COOP_SAMPLE_ROTATION;
            }
        }
    }
    uint64_t model = guest_pointer(actor + 0x238);
    uint64_t controller = model ? guest_pointer(model + 0xc8) : 0;
    uint64_t player = controller ? guest_pointer(controller + 0x118) : 0;
    uint64_t fska = player ? guest_pointer(player + 0x80) : 0;
    char magic[4];
    uint16_t length = 0;
    float frame = player ? guest_f32(player + 0x58) : NAN;
    if (!fska || !isfinite(frame) || frame < 0 || frame > 1000000 ||
        !plat_mem_read(fska, magic, sizeof magic) || memcmp(magic, "FSKA", 4)) return;
    uint64_t name = guest_pointer(fska + 8);
    char text[COOP_ANIMATION_MAX] = {0};
    if (!name || !plat_mem_read(name, &length, sizeof length) || !length || length >= sizeof text ||
        !plat_mem_read(name + 2, text, (size_t)length + 1) || text[length]) return;
    for (unsigned i = 0; i < length; i++) {
        unsigned char ch = (unsigned char)text[i];
        if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
              (ch >= '0' && ch <= '9') || ch == '_')) return;
    }
    // A clip/model switch must not combine two observations into one reported animation.
    if (guest_pointer(actor + 0x238) != model || guest_pointer(model + 0xc8) != controller ||
        guest_pointer(controller + 0x118) != player || guest_pointer(player + 0x80) != fska ||
        guest_pointer(fska + 8) != name) return;
    memcpy(sample->animation, text, sizeof text);
    sample->animation_frame = frame;
    sample->flags |= COOP_SAMPLE_ANIMATION;
}

// Observation and command diagnostics.
static PlatMutex adapter_lock = PLAT_MUTEX_INIT;
static CoopAdapterSnapshot observed;
static CoopGuestCommand commands[256];
static unsigned command_head, command_count;
static volatile int trace_enabled;
static uint64_t trace_actor_method, trace_actor;
static uint32_t trace_generation;
static unsigned trace_claimed, trace_consumed;
static unsigned local_sample_count;
static int64_t next_local_sample_us;
static unsigned trace_kind_claimed[3];
static const unsigned trace_kind_limits[3] = {32, 16, 16};
static const char *const trace_kind_names[3] = {"player_method", "physics_component", "matrix_holder"};
static struct {
    uint64_t address, caller, argument;
    uint32_t host_thread, generation, kind;
    unsigned ready;
} trace_entries[64];
enum { CONSTRUCTOR_TRACE_LIMIT = 16384 };
static unsigned constructor_claimed, constructor_consumed, constructor_summary_logged;
static _Thread_local uint64_t factory_caller, factory_request_caller, wrapper_request_caller;
static _Thread_local uint64_t pipeline_caller, request_pipeline_caller, wrapper_pipeline_caller;
static _Thread_local uint64_t dispatched_caller, dispatched_descriptor;
static _Thread_local uint64_t pipeline_descriptor, request_descriptor, wrapper_descriptor;
static _Thread_local uint64_t pipeline_actor, pipeline_allocator, pipeline_release_target;
static _Thread_local uint64_t pending_enqueue_descriptor;
static _Thread_local unsigned pending_enqueue_context;
static struct {
    uint64_t caller, actor, factory_caller, request_caller, pipeline_caller, task_descriptor;
    uint32_t host_thread;
    unsigned ready;
} constructor_entries[CONSTRUCTOR_TRACE_LIMIT];
enum { HOLDER_TRACE_LIMIT = 4096 };
static unsigned holder_claimed, holder_consumed;
static uint64_t matched_task_actor, matched_task_scene, matched_task_descriptor;
static struct {
    uint64_t address, caller, holder, actor;
    uint32_t mode, host_thread;
    unsigned ready;
} holder_entries[HOLDER_TRACE_LIMIT];
enum { INITIALIZER_TRACE_LIMIT = 8192 };
static unsigned initializer_claimed, initializer_consumed;
static struct {
    uint64_t address, caller, actor, context;
    uint32_t host_thread;
    unsigned ready;
} initializer_entries[INITIALIZER_TRACE_LIMIT];
enum { RESIDENT_INIT_TRACE_LIMIT = 4096 };
static unsigned resident_init_claimed, resident_init_consumed, resident_init_summary_logged;
static struct {
    uint64_t receiver, caller;
    uint32_t host_thread;
    unsigned ready;
} resident_init_entries[RESIDENT_INIT_TRACE_LIMIT];
enum { ACTOR_REQUEST_TRACE_LIMIT = 32 };
static _Thread_local unsigned active_request_index = ACTOR_REQUEST_TRACE_LIMIT;
static unsigned actor_request_total, actor_request_claimed, actor_request_consumed, actor_request_summary_logged;
static struct {
    uint64_t caller, watcher;
    char name[32];
    uint32_t host_thread;
    uint8_t manager_readable, arg_readable, transform_flags, watcher_readable;
    uint8_t extra_register_mask, stack_readable, stack_flag, stack_pointer_mask;
    uint64_t priority;
    unsigned ready, reference_captured;
} actor_request_entries[ACTOR_REQUEST_TRACE_LIMIT];
static unsigned reference_claimed, reference_consumed;
enum { REFERENCE_TRACE_LIMIT = 3 * ACTOR_REQUEST_TRACE_LIMIT };
static struct {
    uint64_t address, caller, value;
    unsigned request_index;
    uint32_t host_thread, publication, release, consumption, state;
    unsigned ready;
} reference_entries[REFERENCE_TRACE_LIMIT];
static unsigned request_context_claimed, request_context_consumed;
static struct {
    uint64_t descriptor, caller;
    unsigned request_index;
    uint32_t host_thread;
    unsigned ready;
} request_context_entries[ACTOR_REQUEST_TRACE_LIMIT];
static unsigned enqueue_claimed, enqueue_consumed;
static struct {
    uint64_t descriptor, caller, priority, handle, resource;
    unsigned request_index;
    uint32_t host_thread, handle_state;
    uint8_t handle_readable, handle_same, manager_readable;
    unsigned ready, dispatched;
} enqueue_entries[ACTOR_REQUEST_TRACE_LIMIT];
static _Thread_local unsigned pipeline_request_index = ACTOR_REQUEST_TRACE_LIMIT;
static struct {
    uint64_t actor, resource, address, caller, cleanup_caller;
    int32_t actor_id;
    uint32_t host_thread, cleanup_thread;
    unsigned claimed, ready, emitted, cleanup_claimed, cleanup_ready, cleanup_emitted, cleanup_same;
} resource_entries[ACTOR_REQUEST_TRACE_LIMIT];
static unsigned resident_bind_claimed, resident_bind_consumed;
static struct {
    uint64_t record, actor, metadata, caller;
    uint32_t host_thread, player_manager;
    unsigned ready;
} resident_bind_entries[ACTOR_REQUEST_TRACE_LIMIT];
static uint64_t known_player_manager_link;
static unsigned player_source_claimed, player_source_consumed;
static struct {
    uint64_t actor, metadata, source, caller;
    int32_t actor_id;
    uint32_t host_thread;
    unsigned ready;
} player_source_entries[ACTOR_REQUEST_TRACE_LIMIT];
enum { TEARDOWN_TARGET_LIMIT = 8, TEARDOWN_TRACE_LIMIT = 3 * TEARDOWN_TARGET_LIMIT };
static unsigned teardown_target_count, teardown_claimed, teardown_consumed;
static unsigned continuity_count;
static struct {
    uint64_t actor, metadata;
    int32_t id;
    uint32_t generation, last_observed_generation;
    unsigned ready, stages;
} teardown_targets[TEARDOWN_TARGET_LIMIT];
static struct {
    uint64_t address, caller;
    uint32_t generation, stage, reason, actor_state, pending, host_thread;
    unsigned ready;
} teardown_entries[TEARDOWN_TRACE_LIMIT];
enum { PROBE_LIMIT = 16, PROBE_TEARDOWN_LIMIT = 3 * PROBE_LIMIT };
static unsigned probe_requests, probe_claimed, probe_consumed, probe_teardown_claimed, probe_teardown_consumed;
static struct {
    uint64_t actor, metadata, address, caller;
    int32_t id;
    uint32_t generation, host_thread;
    unsigned request, ready, stages;
} probe_entries[PROBE_LIMIT];
// Only the isolated host-injected request is sampled here. Native calls supply a live receiver;
// retirement disables sampling before cleanup, and metadata/ID checks reject recycled storage.
static uint64_t probe_motion_actor;
static unsigned probe_motion_index, probe_motion_count;
static int64_t probe_motion_last_us;

// NPC-only snapshots at the Physics transform builder and a later actor update. The component's owner (+0x38) and
// controller-set field (+0x20) come from that entry's reads, not from the Player's component layout.
typedef struct {
    unsigned claimed, ready, emitted, probe, request, generation;
    uint32_t host_thread;
    int64_t world_us;
    uint64_t entry, caller;
    uint64_t node_address[12], body_flags;
    struct { uint64_t vtable, methods[8]; int readable; } node[12];
} NpcPhysicsSnapshot;
static NpcPhysicsSnapshot npc_physics, npc_late_physics;
static unsigned npc_receiver_claimed, npc_receiver_consumed;
static struct { uint64_t address, caller; int64_t world_us; uint32_t thread, kind; unsigned ready; } npc_receivers[64];
enum { NPC_VELOCITY_TRACE_LIMIT = 192 };
static unsigned npc_velocity_claimed, npc_velocity_consumed;
static struct {
    uint64_t entry, caller;
    int64_t world_us;
    uint32_t generation, flags, thread;
    float velocity[3];
    unsigned backend, ready;
} npc_velocity_entries[NPC_VELOCITY_TRACE_LIMIT];
static _Thread_local struct { uint64_t body_id; uint32_t generation, flags; int ready; } npc_velocity_scope;
static _Thread_local struct { uint64_t request; uint32_t generation; int ready; } npc_velocity_lock_scope;

static uint64_t main_relative(uint64_t address) {
    return address >= MOD_MAIN_BASE && address - MOD_MAIN_BASE < MOD_MAIN_SIZE ? address - MOD_MAIN_BASE : 0;
}

static int probe_identity_live(unsigned i, uint64_t actor) {
    if (i >= PROBE_LIMIT || !__atomic_load_n(&probe_entries[i].ready, __ATOMIC_ACQUIRE) ||
        __atomic_load_n(&probe_entries[i].stages, __ATOMIC_ACQUIRE) ||
        probe_entries[i].generation != __atomic_load_n(&trace_generation, __ATOMIC_ACQUIRE)) return 0;
    uint64_t meta = probe_entries[i].metadata;
    int32_t id = probe_entries[i].id;
    return actor == probe_entries[i].actor && guest_readable(actor, 0x1b0) && guest_readable(meta, 0x50) &&
           guest_pointer(actor + 0x1a8) == meta && guest_pointer(meta + 0x40) == actor &&
           guest_s32(actor + 0x10) == id && guest_s32(meta + 0x48) == id;
}

static void npc_physics_capture(NpcPhysicsSnapshot *snapshot, uint64_t entry, uint64_t caller, uint64_t component) {
    if (__atomic_load_n(&snapshot->ready, __ATOMIC_ACQUIRE)) return;
    uint64_t actor = __atomic_load_n(&probe_motion_actor, __ATOMIC_ACQUIRE);
    unsigned i = probe_motion_index;
    if (!actor || !probe_identity_live(i, actor)) return;
    unsigned request = probe_entries[i].request;
    if (request >= ACTOR_REQUEST_TRACE_LIMIT || strcmp(actor_request_entries[request].name, "Npc_Road_001") ||
        !guest_readable(component, 0x40) || guest_pointer(component + 0x38) != actor) return;
    uint64_t set = guest_pointer(component + 0x20);
    if (!guest_readable(set, 0x158)) return;
    unsigned zero = 0;
    if (!__atomic_compare_exchange_n(&snapshot->claimed, &zero, 1, 0, __ATOMIC_ACQ_REL, __ATOMIC_RELAXED)) return;
    uint64_t nodes[12] = {component, set, guest_pointer(set + 0x10), guest_pointer(set + 0x148)};
    // The set+0x10 branch of main+0xa10d28 dereferences +8, then +0x18 before reading body flags at +0x68.
    nodes[4] = guest_readable(nodes[2], 0x10) ? guest_pointer(nodes[2] + 8) : 0;
    nodes[5] = guest_readable(nodes[4], 0x20) ? guest_pointer(nodes[4] + 0x18) : 0;
    // This observed body's virtual +0x88 getter (main+0x298d8e0) returns an optional field at +0x158.
    uint64_t body_vtable = guest_readable(nodes[5], 8) ? guest_pointer(nodes[5]) : 0;
    if (guest_readable(body_vtable + 0x88, 8) && guest_pointer(body_vtable + 0x88) == MOD_MAIN_BASE + 0x298d8e0ull &&
        guest_readable(nodes[5], 0x160)) nodes[6] = guest_pointer(nodes[5] + 0x158);
    // The set+8 branch of main+0xa10d28 reads a second object at +0x20. Its role is not assumed here.
    nodes[7] = guest_pointer(set + 8);
    nodes[8] = guest_readable(nodes[7], 0x28) ? guest_pointer(nodes[7] + 0x20) : 0;
    // main+0xa0f6cc selects this body for the bounds path requested by the Physics transform builder.
    nodes[9] = guest_pointer(set + 0x150);
    // This CharacterMatterRigidBody's virtual +0x40 getter follows +0x1e0, then +0x28 before dispatch.
    if (guest_readable(body_vtable + 0x40, 8) && guest_pointer(body_vtable + 0x40) == MOD_MAIN_BASE + 0x298d890ull &&
        guest_readable(nodes[5], 0x1e8)) nodes[10] = guest_pointer(nodes[5] + 0x1e0);
    nodes[11] = guest_readable(nodes[10], 0x30) ? guest_pointer(nodes[10] + 0x28) : 0;
    snapshot->body_flags = guest_readable(nodes[5], 0x70) ? guest_pointer(nodes[5] + 0x68) : 0;
    for (unsigned n = 0; n < 12; n++) {
        snapshot->node[n].readable = guest_readable(nodes[n], 8);
        if (!snapshot->node[n].readable) continue;
        uint64_t vtable = guest_pointer(nodes[n]);
        snapshot->node[n].vtable = main_relative(vtable);
        if (!snapshot->node[n].vtable || !guest_readable(vtable, 8 * 8)) continue;
        for (unsigned m = 0; m < 8; m++) snapshot->node[n].methods[m] = main_relative(guest_pointer(vtable + m * 8));
    }
    if (!probe_identity_live(i, actor) || guest_pointer(component + 0x38) != actor ||
        guest_pointer(component + 0x20) != set || guest_pointer(set + 0x10) != nodes[2] ||
        (nodes[4] && guest_pointer(nodes[2] + 8) != nodes[4]) ||
        (nodes[5] && guest_pointer(nodes[4] + 0x18) != nodes[5]) ||
        guest_pointer(set + 8) != nodes[7] || guest_pointer(set + 0x150) != nodes[9] ||
        (nodes[8] && guest_pointer(nodes[7] + 0x20) != nodes[8])) {
        memset(snapshot->node, 0, sizeof snapshot->node);
        __atomic_store_n(&snapshot->claimed, 0, __ATOMIC_RELEASE);
        return;
    }
    snapshot->probe = i; snapshot->request = request; snapshot->entry = entry; snapshot->caller = caller;
    memcpy(snapshot->node_address, nodes, sizeof nodes);
    snapshot->generation = probe_entries[i].generation;
    snapshot->host_thread = plat_thread_id(); snapshot->world_us = frame_step_world_us();
    __atomic_store_n(&snapshot->ready, 1, __ATOMIC_RELEASE);
}

static void npc_physics_observe(uint64_t caller, uint64_t component) {
    npc_physics_capture(&npc_physics, MOD_MAIN_BASE + 0xa0f3f0ull, caller, component);
}

static void npc_physics_late_observe(uint64_t caller, uint64_t actor) {
    if (__atomic_load_n(&npc_late_physics.ready, __ATOMIC_ACQUIRE) ||
        !__atomic_load_n(&npc_physics.ready, __ATOMIC_ACQUIRE) || actor != probe_entries[npc_physics.probe].actor ||
        frame_step_world_us() < npc_physics.world_us + 1000000 ||
        !probe_identity_live(npc_physics.probe, actor)) return;
    npc_physics_capture(&npc_late_physics, MOD_MAIN_BASE + 0x2e27b0ull, caller, npc_physics.node_address[0]);
}

int coop_adapter_npc_probe_body(uint64_t actor, uint64_t *body, uint32_t *generation, int64_t *observed_us) {
    if (!body || !generation || !observed_us || rt_game_version != 143 ||
        !__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED) ||
        !__atomic_load_n(&npc_late_physics.ready, __ATOMIC_ACQUIRE)) return 0;
    NpcPhysicsSnapshot *s = &npc_late_physics;
    const uint64_t *n = s->node_address;
    if (s->generation != __atomic_load_n(&trace_generation, __ATOMIC_ACQUIRE) ||
        !probe_identity_live(s->probe, actor) || frame_step_world_us() < s->world_us ||
        strcmp(actor_request_entries[s->request].name, "Npc_Road_001") ||
        !guest_readable(n[0], 0x40) || guest_pointer(n[0] + 0x38) != actor || guest_pointer(n[0] + 0x20) != n[1] ||
        !guest_readable(n[1], 0x158) || guest_pointer(n[1] + 0x10) != n[2] || guest_pointer(n[1] + 0x150) != n[5] ||
        !guest_readable(n[2], 0x10) || guest_pointer(n[2] + 8) != n[4] ||
        !guest_readable(n[4], 0x20) || guest_pointer(n[4] + 0x18) != n[5] ||
        !guest_readable(n[5], 0x160) || guest_pointer(n[5]) != MOD_MAIN_BASE + 0x392af88ull) return 0;
    uint64_t flags = guest_pointer(n[5] + 0x68);
    // Only the observed dynamic body type; removal/static flags and a changed optional link reject it.
    if ((flags & 0x1c) != 4 || (flags & ((1ull << 8) | (1ull << 6))) ||
        guest_pointer(n[5] + 0x158) != n[6] || !probe_identity_live(s->probe, actor)) return 0;
    *body = n[5]; *generation = s->generation; *observed_us = s->world_us;
    return 1;
}

static void npc_velocity_capture(uint64_t entry, uint64_t caller, uint32_t generation,
                                 uint32_t flags, const float velocity[3], int backend) {
    unsigned slot = __atomic_fetch_add(&npc_velocity_claimed, 1, __ATOMIC_RELAXED);
    if (slot >= NPC_VELOCITY_TRACE_LIMIT) return;
    npc_velocity_entries[slot].entry = entry; npc_velocity_entries[slot].caller = caller;
    npc_velocity_entries[slot].generation = generation; npc_velocity_entries[slot].flags = flags;
    npc_velocity_entries[slot].thread = plat_thread_id(); npc_velocity_entries[slot].world_us = frame_step_world_us();
    memcpy(npc_velocity_entries[slot].velocity, velocity, sizeof npc_velocity_entries[slot].velocity);
    npc_velocity_entries[slot].backend = backend;
    __atomic_store_n(&npc_velocity_entries[slot].ready, 1, __ATOMIC_RELEASE);
}

void coop_adapter_npc_velocity_consume(const Cpu *cpu) {
    // Every native request consumer invalidates this thread's preceding handoff, including other actors.
    npc_velocity_scope.ready = 0;
    if (!cpu || !__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED) ||
        !__atomic_load_n(&npc_late_physics.ready, __ATOMIC_ACQUIRE) ||
        __atomic_load_n(&npc_velocity_claimed, __ATOMIC_RELAXED) >= NPC_VELOCITY_TRACE_LIMIT ||
        cpu->x[1] != npc_late_physics.node_address[5]) return;
    uint64_t body; uint32_t generation; int64_t observed_us;
    if (!coop_adapter_npc_probe_body(probe_entries[npc_late_physics.probe].actor, &body, &generation, &observed_us) ||
        body != cpu->x[1] || !guest_readable(cpu->x[0], 0xd8)) return;
    uint32_t flags = (uint32_t)guest_s32(cpu->x[0] + 0xd4);
    float velocity[3];
    // The consumer owns its request argument even after the native queue clears body+0x60.
    if (!(flags & 0x80) || !plat_mem_read(cpu->x[0] + 0x44, velocity, sizeof velocity)) return;
    for (unsigned i = 0; i < 3; i++) if (!isfinite(velocity[i])) return;
    uint64_t sdk = guest_pointer(body + 0x70);
    if (!guest_readable(sdk, 0x10)) return;
    npc_velocity_scope.body_id = guest_pointer(sdk + 8);
    npc_velocity_scope.generation = generation; npc_velocity_scope.flags = flags; npc_velocity_scope.ready = 1;
    npc_velocity_capture(MOD_MAIN_BASE + 0x182eb0ull, cpu->x[30], generation, flags, velocity, 0);
}

static void npc_velocity_backend_observe(uint64_t entry, uint64_t caller, uint64_t body_id, uint64_t vector) {
    if (!npc_velocity_scope.ready || (caller != MOD_MAIN_BASE + 0x183078ull &&
        caller != MOD_MAIN_BASE + 0x183518ull && caller != MOD_MAIN_BASE + 0x1843b0ull) ||
        body_id != npc_velocity_scope.body_id || !__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED) ||
        npc_velocity_scope.generation != __atomic_load_n(&trace_generation, __ATOMIC_ACQUIRE) ||
        __atomic_load_n(&npc_velocity_claimed, __ATOMIC_RELAXED) >= NPC_VELOCITY_TRACE_LIMIT || !main_relative(entry)) return;
    uint64_t body; uint32_t generation; int64_t observed_us;
    if (!coop_adapter_npc_probe_body(probe_entries[npc_late_physics.probe].actor, &body, &generation, &observed_us)) return;
    uint64_t sdk = guest_pointer(body + 0x70);
    float velocity[3];
    if (!guest_readable(sdk, 0x10) || guest_pointer(sdk + 8) != body_id ||
        !guest_readable(vector, sizeof velocity) || !plat_mem_read(vector, velocity, sizeof velocity)) return;
    for (unsigned i = 0; i < 3; i++) if (!isfinite(velocity[i])) return;
    npc_velocity_capture(entry, caller, generation, npc_velocity_scope.flags, velocity, 1);
    npc_velocity_scope.ready = 0;
}

static void npc_velocity_lock_observe(uint64_t entry, uint64_t caller, uint64_t mutex) {
    int unlock = entry == MOD_MAIN_BASE + 0x2bb7a70ull;
    if ((!unlock && entry != MOD_MAIN_BASE + 0x2bb7a60ull) ||
        !__atomic_load_n(&npc_late_physics.ready, __ATOMIC_ACQUIRE) ||
        mutex != npc_late_physics.node_address[5] + 0x78 ||
        __atomic_load_n(&npc_velocity_claimed, __ATOMIC_RELAXED) >= NPC_VELOCITY_TRACE_LIMIT ||
        (unlock && !npc_velocity_lock_scope.ready)) return;
    uint64_t body; uint32_t generation; int64_t observed_us;
    if (!coop_adapter_npc_probe_body(probe_entries[npc_late_physics.probe].actor, &body, &generation, &observed_us)) return;
    uint64_t request = guest_pointer(body + 0x60);
    float velocity[3];
    if (!guest_readable(request, 0xd8) || !plat_mem_read(request + 0x44, velocity, sizeof velocity)) return;
    for (unsigned i = 0; i < 3; i++) if (!isfinite(velocity[i])) return;
    uint32_t flags = (uint32_t)guest_s32(request + 0xd4);
    if (!unlock) {
        npc_velocity_lock_scope.ready = 0;
        if (!(flags & 0x80) || (fabsf(velocity[0]) < .001f && fabsf(velocity[1]) < .001f && fabsf(velocity[2]) < .001f)) return;
        npc_velocity_lock_scope.request = request; npc_velocity_lock_scope.generation = generation;
        npc_velocity_lock_scope.ready = 1;
    } else {
        npc_velocity_lock_scope.ready = 0;
        if (request != npc_velocity_lock_scope.request || generation != npc_velocity_lock_scope.generation) return;
    }
    npc_velocity_capture(entry, caller, generation, flags, velocity, unlock ? 3 : 2);
}

static void npc_receiver_observe(uint64_t address, uint64_t caller, uint64_t argument) {
    if (!argument || !__atomic_load_n(&npc_physics.ready, __ATOMIC_ACQUIRE) || !main_relative(address)) return;
    NpcPhysicsSnapshot *snapshot = __atomic_load_n(&npc_late_physics.ready, __ATOMIC_ACQUIRE) ? &npc_late_physics : &npc_physics;
    unsigned kind = argument == snapshot->node_address[0] ? 8 : argument == snapshot->node_address[1] ? 9 :
                    argument == snapshot->node_address[11] ? 7 : argument == snapshot->node_address[10] ? 6 :
                    argument == snapshot->node_address[9] ? 5 : argument == snapshot->node_address[6] ? 2 : argument == snapshot->node_address[5] ? 1 :
                    argument == snapshot->node_address[7] ? 3 : argument == snapshot->node_address[8] ? 4 : 0;
    if (!kind && argument != snapshot->node_address[2]) return;
    unsigned count = __atomic_load_n(&npc_receiver_claimed, __ATOMIC_ACQUIRE);
    for (unsigned j = 0; j < count && j < 64; j++)
        if (__atomic_load_n(&npc_receivers[j].ready, __ATOMIC_ACQUIRE) &&
            npc_receivers[j].address == address && npc_receivers[j].kind == kind) return;
    if (count >= 64 || !probe_identity_live(snapshot->probe, probe_entries[snapshot->probe].actor)) return;
    const uint64_t *nodes = snapshot->node_address;
    if (!guest_readable(nodes[0], 0x40) || !guest_readable(nodes[1], 0x18) ||
        guest_pointer(nodes[0] + 0x38) != probe_entries[snapshot->probe].actor ||
        guest_pointer(nodes[0] + 0x20) != nodes[1] || guest_pointer(nodes[1] + 0x10) != nodes[2]) return;
    if ((kind == 1 || kind == 2 || kind == 6 || kind == 7) && (!guest_readable(nodes[2], 0x10) || !guest_readable(nodes[4], 0x20) ||
                 guest_pointer(nodes[2] + 8) != nodes[4] || guest_pointer(nodes[4] + 0x18) != nodes[5])) return;
    if (kind == 2 && (!guest_readable(nodes[5], 0x160) || guest_pointer(nodes[5] + 0x158) != argument)) return;
    if ((kind == 3 || kind == 4) && guest_pointer(nodes[1] + 8) != nodes[7]) return;
    if (kind == 4 && (!guest_readable(nodes[7], 0x28) || guest_pointer(nodes[7] + 0x20) != argument)) return;
    if (kind == 5 && (!guest_readable(nodes[1], 0x158) || guest_pointer(nodes[1] + 0x150) != argument)) return;
    if ((kind == 6 || kind == 7) && (!guest_readable(nodes[5], 0x1e8) || guest_pointer(nodes[5] + 0x1e0) != nodes[10])) return;
    if (kind == 7 && (!guest_readable(nodes[10], 0x30) || guest_pointer(nodes[10] + 0x28) != argument)) return;
    unsigned slot = __atomic_fetch_add(&npc_receiver_claimed, 1, __ATOMIC_RELAXED);
    if (slot >= 64) return;
    npc_receivers[slot].address = address; npc_receivers[slot].caller = caller;
    npc_receivers[slot].world_us = frame_step_world_us(); npc_receivers[slot].thread = plat_thread_id();
    npc_receivers[slot].kind = kind;
    __atomic_store_n(&npc_receivers[slot].ready, 1, __ATOMIC_RELEASE);
}
static struct {
    uint64_t address, caller;
    uint32_t stage, reason, actor_state, pending, host_thread, metadata_live;
    unsigned probe, ready;
} probe_teardown_entries[PROBE_TEARDOWN_LIMIT];
static _Thread_local struct {
    uint64_t actor, caller, allocator, target;
    unsigned probe;
} dispose_scope;
static unsigned probe_allocator_claimed, probe_allocator_consumed;
static struct {
    uint64_t address, caller;
    uint32_t host_thread;
    unsigned probe, ready;
} probe_allocator_entries[PROBE_LIMIT];
enum { PLAYER_PIPELINE_TRACE_LIMIT = 32 };
static unsigned player_pipeline_claimed, player_pipeline_consumed;
static struct {
    uint64_t caller;
    uint32_t host_thread;
    uint8_t receiver_readable;
    unsigned ready;
} player_pipeline_entries[PLAYER_PIPELINE_TRACE_LIMIT];
enum { LIFECYCLE_TRACE_LIMIT = 8192 };
static unsigned lifecycle_claimed, lifecycle_consumed;
static const char *const lifecycle_stages[] = {
    "initialize_result", "release_140", "release_110", "release_f0", "context_cleanup", "task_free", "allocator_release"
};
static struct {
    uint64_t address, caller, descriptor, actor, owner_actor;
    uint32_t stage, result, host_thread;
    unsigned ready;
} lifecycle_entries[LIFECYCLE_TRACE_LIMIT];

static void ready_reference_capture(uint64_t address, uint64_t caller, unsigned request,
                                    uint64_t value, uint32_t state, int operation) {
    unsigned bit = operation == 3 ? 4u : operation == 2 ? 2u : 1u;
    if ((!value && operation != 2) ||
        (__atomic_fetch_or(&actor_request_entries[request].reference_captured, bit, __ATOMIC_RELAXED) & bit)) return;
    unsigned slot = __atomic_fetch_add(&reference_claimed, 1, __ATOMIC_RELAXED);
    if (slot >= REFERENCE_TRACE_LIMIT) return;
    reference_entries[slot].address = address;
    reference_entries[slot].caller = caller;
    reference_entries[slot].value = value;
    reference_entries[slot].request_index = request;
    reference_entries[slot].publication = operation == 1;
    reference_entries[slot].release = operation == 2;
    reference_entries[slot].consumption = operation == 3;
    reference_entries[slot].state = state;
    reference_entries[slot].host_thread = plat_thread_id();
    __atomic_store_n(&reference_entries[slot].ready, 1, __ATOMIC_RELEASE);
}

static void lifecycle_capture(uint64_t address, uint64_t caller, uint64_t descriptor,
                              uint64_t actor, unsigned stage, uint32_t result) {
    if (!pipeline_actor || descriptor != pipeline_descriptor) return;
    unsigned slot = __atomic_fetch_add(&lifecycle_claimed, 1, __ATOMIC_RELAXED);
    if (slot >= LIFECYCLE_TRACE_LIMIT) return;
    lifecycle_entries[slot].address = address;
    lifecycle_entries[slot].caller = caller;
    lifecycle_entries[slot].descriptor = descriptor;
    lifecycle_entries[slot].actor = actor;
    lifecycle_entries[slot].owner_actor = pipeline_actor;
    lifecycle_entries[slot].stage = stage;
    lifecycle_entries[slot].result = result;
    lifecycle_entries[slot].host_thread = plat_thread_id();
    __atomic_store_n(&lifecycle_entries[slot].ready, 1, __ATOMIC_RELEASE);
}

void coop_adapter_trace_enable(int enable) {
    __atomic_store_n(&trace_enabled, enable, __ATOMIC_RELEASE);
    // Bit 0 belongs to resolution discovery. Disabling co-op tracing must not disable that observer.
    if (enable) __atomic_fetch_or(&g_fnprof, 2, __ATOMIC_RELAXED);
    else __atomic_fetch_and(&g_fnprof, ~2, __ATOMIC_RELAXED);
}

// Observe Player requests and bounded Weapon samples; the isolated NPC mode admits only its injected identity.
// These observations do not establish an external creation ABI.
void coop_adapter_actor_request(const Cpu *cpu) {
    if (!cpu || rt_game_version != 143 || !__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED)) return;
    pending_enqueue_descriptor = 0; // every new request invalidates an unfinished association on this thread
    active_request_index = ACTOR_REQUEST_TRACE_LIMIT;
    __atomic_fetch_add(&actor_request_total, 1, __ATOMIC_RELAXED);
    if (!guest_readable(cpu->x[1], 8)) return;
    uint64_t name_at = guest_pointer(cpu->x[1]);
    char prefix[6];
    if (!name_at || !plat_mem_read(name_at, prefix, sizeof prefix)) return;
    int npc = !memcmp(prefix, "Npc_Ro", sizeof prefix) && cpu->x[30] == RT_RET_HOST &&
              (cfg_int("TOTK_COOP_NATIVE_PROBE") >= 3 && cfg_int("TOTK_COOP_NATIVE_PROBE") <= 5);
    int probe = !memcmp(prefix, "Weapon", sizeof prefix) || npc;
    if (memcmp(prefix, "Player", sizeof prefix) && !probe) return;
    if (probe && (frame_step_world_us() < 6000000 ||
                  __atomic_load_n(&probe_requests, __ATOMIC_RELAXED) >= PROBE_LIMIT)) return;
    char name[32] = {0};
    int complete = 0;
    for (unsigned i = 0; i + 1 < sizeof name; i++) {
        unsigned char ch = 0;
        if (!plat_mem_read(name_at + i, &ch, 1)) return;
        if (!ch) { complete = 1; break; }
        if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
              (ch >= '0' && ch <= '9') || ch == '_')) return;
        name[i] = (char)ch;
    }
    if (!complete) return;
    if (npc && strcmp(name, "Npc_Road_001")) return;
    if (probe && __atomic_fetch_add(&probe_requests, 1, __ATOMIC_RELAXED) >= PROBE_LIMIT) return;
    unsigned slot = __atomic_fetch_add(&actor_request_claimed, 1, __ATOMIC_RELAXED);
    if (slot >= ACTOR_REQUEST_TRACE_LIMIT) return;
    actor_request_entries[slot].caller = cpu->x[30];
    actor_request_entries[slot].watcher = cpu->x[3];
    memcpy(actor_request_entries[slot].name, name, sizeof name);
    actor_request_entries[slot].host_thread = plat_thread_id();
    actor_request_entries[slot].manager_readable = guest_readable(cpu->x[0], 8);
    actor_request_entries[slot].arg_readable = guest_readable(cpu->x[2], 0x98);
    actor_request_entries[slot].watcher_readable = guest_readable(cpu->x[3], 8);
    actor_request_entries[slot].priority = cpu->x[4];
    for (unsigned i = 0; i < 3; i++)
        if (cpu->x[5 + i]) actor_request_entries[slot].extra_register_mask |= 1u << i;
    uint8_t stack[0x18];
    if (guest_readable(cpu->sp, sizeof stack) && plat_mem_read(cpu->sp, stack, sizeof stack)) {
        uint64_t first, second;
        memcpy(&first, stack + 8, sizeof first);
        memcpy(&second, stack + 16, sizeof second);
        actor_request_entries[slot].stack_readable = 1;
        actor_request_entries[slot].stack_flag = stack[0];
        actor_request_entries[slot].stack_pointer_mask = (first != 0) | ((second != 0) << 1);
    }
    if (actor_request_entries[slot].arg_readable)
        plat_mem_read(cpu->x[2] + 0x90, &actor_request_entries[slot].transform_flags, 1);
    __atomic_store_n(&actor_request_entries[slot].ready, 1, __ATOMIC_RELEASE);
    active_request_index = slot;
}

// The observed request copies its context into descriptor+0x18. Correlate only previously captured requests;
// the destination is not read or modified, and equality alone does not establish its lifetime contract.
void coop_adapter_request_context(const Cpu *cpu) {
    if (!cpu || rt_game_version != 143 || !__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED) ||
        cpu->x[30] != MOD_MAIN_BASE + 0x599a90ull) return;
    unsigned i = active_request_index;
    active_request_index = ACTOR_REQUEST_TRACE_LIMIT;
    if (i >= ACTOR_REQUEST_TRACE_LIMIT || cpu->x[0] < 0x18ull ||
        !guest_readable(cpu->x[1], 0x18) || !guest_readable(cpu->x[0], 0x18)) return;
    uint64_t watcher = guest_pointer(cpu->x[1] + 0x10ull);
    uint32_t host_thread = plat_thread_id();
    if (!__atomic_load_n(&actor_request_entries[i].ready, __ATOMIC_ACQUIRE)) return;
    if (!watcher && !memcmp(actor_request_entries[i].name, "Player", 6)) return;
    if (actor_request_entries[i].watcher != watcher ||
        actor_request_entries[i].host_thread != host_thread) return;
    unsigned slot = __atomic_fetch_add(&request_context_claimed, 1, __ATOMIC_RELAXED);
    if (slot >= ACTOR_REQUEST_TRACE_LIMIT) return;
    request_context_entries[slot].descriptor = cpu->x[0] - 0x18ull;
    request_context_entries[slot].caller = cpu->x[30];
    request_context_entries[slot].request_index = i;
    request_context_entries[slot].host_thread = host_thread;
    __atomic_store_n(&request_context_entries[slot].ready, 1, __ATOMIC_RELEASE);
    pending_enqueue_context = slot;
    pending_enqueue_descriptor = request_context_entries[slot].descriptor;
    return;
}

// Observe the request's queue submission, including the handle prepared after its context copy.
void coop_adapter_request_enqueue(const Cpu *cpu) {
    if (!cpu || rt_game_version != 143 || !__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED)) return;
    // Every queue submission invalidates an older identity at this descriptor, including uncaptured actor requests.
    for (unsigned i = 0; i < ACTOR_REQUEST_TRACE_LIMIT; i++)
        if (__atomic_load_n(&enqueue_entries[i].ready, __ATOMIC_ACQUIRE) && enqueue_entries[i].descriptor == cpu->x[1])
            __atomic_store_n(&enqueue_entries[i].dispatched, 1, __ATOMIC_RELEASE);
    if (cpu->x[30] != MOD_MAIN_BASE + 0x599cc0ull) return;
    uint64_t pending = pending_enqueue_descriptor;
    pending_enqueue_descriptor = 0; // a reused descriptor must never pick up an older request's context
    if (!pending || pending != cpu->x[1] || !guest_readable(cpu->x[1], 0xa0)) return;
    uint32_t thread = plat_thread_id();
    unsigned i = pending_enqueue_context;
    if (i >= ACTOR_REQUEST_TRACE_LIMIT ||
        !__atomic_load_n(&request_context_entries[i].ready, __ATOMIC_ACQUIRE) ||
        request_context_entries[i].host_thread != thread) return;
    unsigned slot = __atomic_fetch_add(&enqueue_claimed, 1, __ATOMIC_RELAXED);
    if (slot >= ACTOR_REQUEST_TRACE_LIMIT) return;
    unsigned request = request_context_entries[i].request_index;
    uint64_t handle = guest_pointer(cpu->x[1] + 0x98ull);
    enqueue_entries[slot].handle = handle;
    enqueue_entries[slot].resource = guest_readable(cpu->x[1] + 0xf8ull, 8) ? guest_pointer(cpu->x[1] + 0xf8ull) : 0;
    enqueue_entries[slot].descriptor = cpu->x[1];
    enqueue_entries[slot].caller = cpu->x[30];
    enqueue_entries[slot].priority = cpu->x[2];
    enqueue_entries[slot].request_index = request;
    enqueue_entries[slot].host_thread = thread;
    enqueue_entries[slot].manager_readable = guest_readable(cpu->x[0], 8);
    enqueue_entries[slot].handle_readable = guest_readable(handle, 0x10);
    enqueue_entries[slot].handle_state = enqueue_entries[slot].handle_readable ?
        (uint32_t)guest_s32(handle) & 0xffffu : 0xffffu;
    enqueue_entries[slot].handle_same = handle &&
        handle == guest_pointer(actor_request_entries[request].watcher);
    __atomic_store_n(&enqueue_entries[slot].ready, 1, __ATOMIC_RELEASE);
    return;
}

// Observe the resident bind after handle consumption, and assignments to the known local-player manager link.
void coop_adapter_actor_bind(const Cpu *cpu) {
    if (!cpu || rt_game_version != 143 || !__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED) ||
        !guest_readable(cpu->x[0], 0x18) ||
        !guest_readable(cpu->x[1], 0x1b0)) return;
    int player_manager = cpu->x[0] == player_manager_link();
    if (!player_manager && cpu->x[30] != MOD_MAIN_BASE + 0xea5d70ull) return;
    for (unsigned i = 0; i < ACTOR_REQUEST_TRACE_LIMIT; i++) {
        if (!player_manager && (!__atomic_load_n(&actor_request_entries[i].ready, __ATOMIC_ACQUIRE) ||
            actor_request_entries[i].watcher != cpu->x[0] + 0x18ull)) continue;
        unsigned slot = __atomic_fetch_add(&resident_bind_claimed, 1, __ATOMIC_RELAXED);
        if (slot >= ACTOR_REQUEST_TRACE_LIMIT) return;
        resident_bind_entries[slot].record = cpu->x[0];
        resident_bind_entries[slot].actor = cpu->x[1];
        resident_bind_entries[slot].metadata = guest_pointer(cpu->x[1] + 0x1a8ull);
        resident_bind_entries[slot].caller = cpu->x[30];
        resident_bind_entries[slot].host_thread = plat_thread_id();
        resident_bind_entries[slot].player_manager = player_manager;
        __atomic_store_n(&resident_bind_entries[slot].ready, 1, __ATOMIC_RELEASE);
        return;
    }
}

// Observe the caller and source of a copy into the known local-player reference, without changing either link.
void coop_adapter_player_reference_source(const Cpu *cpu) {
    if (!cpu || rt_game_version != 143 || !__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED)) return;
    uint64_t link = __atomic_load_n(&known_player_manager_link, __ATOMIC_ACQUIRE);
    if (!link) {
        link = player_manager_link();
        __atomic_store_n(&known_player_manager_link, link, __ATOMIC_RELEASE);
    }
    if (!link || cpu->x[0] != link || link != player_manager_link() || !guest_readable(cpu->x[1], 0x18)) return;
    uint64_t metadata = guest_pointer(cpu->x[1] + 8ull);
    int32_t id = guest_s32(cpu->x[1] + 0x10ull);
    if (id == -1 || !guest_readable(metadata, 0x50) || guest_s32(metadata + 0x48ull) != id) return;
    uint64_t actor = guest_pointer(metadata + 0x40ull);
    if (!guest_readable(actor, 0x1b0) || guest_s32(actor + 0x10ull) != id) return;
    unsigned i = __atomic_fetch_add(&player_source_claimed, 1, __ATOMIC_RELAXED);
    if (i >= ACTOR_REQUEST_TRACE_LIMIT) return;
    player_source_entries[i].actor = actor;
    player_source_entries[i].metadata = metadata;
    player_source_entries[i].actor_id = id;
    player_source_entries[i].source = cpu->x[1];
    player_source_entries[i].caller = cpu->x[30];
    player_source_entries[i].host_thread = plat_thread_id();
    __atomic_store_n(&player_source_entries[i].ready, 1, __ATOMIC_RELEASE);
}

// Retain only an independently observed actor identity. Metadata IDs distinguish reuse of pooled addresses.
// Targets survive observation loss so the game's later teardown can be seen; cleanup retires them before reuse.
static void teardown_observe_player(uint64_t actor, uint32_t generation) {
    uint64_t metadata = guest_pointer(actor + 0x1a8ull);
    if (!guest_readable(metadata, 0x50) || guest_pointer(metadata + 0x40ull) != actor) return;
    int32_t id = guest_s32(metadata + 0x48ull);
    if (id == -1) return;
    for (unsigned i = 0; i < teardown_target_count; i++)
        if (teardown_targets[i].actor == actor && teardown_targets[i].metadata == metadata &&
            teardown_targets[i].id == id) {
            if (teardown_targets[i].last_observed_generation != generation && continuity_count < TEARDOWN_TARGET_LIMIT &&
                !(__atomic_load_n(&teardown_targets[i].stages, __ATOMIC_RELAXED) & 4u)) {
                rt_log("coop native player continuity: generation %u, original generation %u, actor metadata id same, constructor entries %u, limit %u; observation only",
                       generation, teardown_targets[i].generation,
                       __atomic_load_n(&constructor_claimed, __ATOMIC_ACQUIRE), CONSTRUCTOR_TRACE_LIMIT);
                continuity_count++;
            }
            teardown_targets[i].last_observed_generation = generation;
            return;
        }
    if (teardown_target_count == TEARDOWN_TARGET_LIMIT) return;
    unsigned i = teardown_target_count++;
    teardown_targets[i].actor = actor;
    teardown_targets[i].metadata = metadata;
    teardown_targets[i].id = id;
    teardown_targets[i].generation = generation;
    teardown_targets[i].last_observed_generation = generation;
    __atomic_store_n(&teardown_targets[i].ready, 1, __ATOMIC_RELEASE);
    rt_log("coop native teardown scope: generation %u, actor metadata backlink same, metadata id valid; observation only", generation);
}

// The native initialization-result callback receives the factory's exact actor and descriptor context.
// Bind only a captured diagnostic identity with the same request and live metadata backlink.
static void probe_initialized(uint64_t address, uint64_t caller, uint64_t actor, uint64_t context, uint64_t result) {
    if (!__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED) || result != 1 || !pipeline_actor ||
        actor != pipeline_actor || context < 0x18ull || context - 0x18ull != pipeline_descriptor) return;
    {
        unsigned e = pipeline_request_index;
        if (e >= ACTOR_REQUEST_TRACE_LIMIT || !__atomic_load_n(&enqueue_entries[e].ready, __ATOMIC_ACQUIRE) ||
            enqueue_entries[e].descriptor != pipeline_descriptor) return;
        unsigned request = enqueue_entries[e].request_index;
        const char *requested_name = actor_request_entries[request].name;
        int npc = actor_request_entries[request].caller == RT_RET_HOST && !strcmp(requested_name, "Npc_Road_001");
        if ((memcmp(requested_name, "Weapon", 6) && !npc) || !guest_readable(actor, 0x1b0)) return;
        uint64_t metadata = guest_pointer(actor + 0x1a8ull);
        if (!guest_readable(metadata, 0x50) || guest_pointer(metadata + 0x40ull) != actor) return;
        int32_t id = guest_s32(metadata + 0x48ull);
        if (id == -1 || guest_s32(actor + 0x10ull) != id) return;
        uint64_t name = guest_pointer(actor + 0x218ull);
        for (unsigned j = 0; j < sizeof actor_request_entries[request].name; j++) {
            char ch;
            if (!name || !plat_mem_read(name + j, &ch, 1) || ch != actor_request_entries[request].name[j]) return;
            if (!ch) break;
        }
        for (unsigned j = 0; j < PROBE_LIMIT; j++)
            if (__atomic_load_n(&probe_entries[j].ready, __ATOMIC_ACQUIRE) &&
                probe_entries[j].actor == actor && probe_entries[j].metadata == metadata && probe_entries[j].id == id) return;
        unsigned i = __atomic_fetch_add(&probe_claimed, 1, __ATOMIC_RELAXED);
        if (i >= PROBE_LIMIT) return;
        probe_entries[i].actor = actor;
        probe_entries[i].metadata = metadata;
        probe_entries[i].id = id;
        probe_entries[i].request = request;
        probe_entries[i].address = address;
        probe_entries[i].caller = caller;
        probe_entries[i].generation = __atomic_load_n(&trace_generation, __ATOMIC_ACQUIRE);
        probe_entries[i].host_thread = plat_thread_id();
        __atomic_store_n(&probe_entries[i].ready, 1, __ATOMIC_RELEASE);
        if (actor_request_entries[request].caller == RT_RET_HOST) {
            probe_motion_index = i;
            __atomic_store_n(&probe_motion_actor, actor, __ATOMIC_RELEASE);
        }
        return;
    }
}

// Follow the queued holder's resource into the initialized actor without acquiring or releasing it.
static void resource_initialized(uint64_t address, uint64_t caller, uint64_t actor, uint64_t context, uint64_t result) {
    if (!__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED) || result != 1 || !pipeline_actor || actor != pipeline_actor ||
        context < 0x18ull || context - 0x18ull != pipeline_descriptor || pipeline_request_index >= ACTOR_REQUEST_TRACE_LIMIT) return;
    unsigned e = pipeline_request_index;
    if (!__atomic_load_n(&enqueue_entries[e].ready, __ATOMIC_ACQUIRE) ||
        enqueue_entries[e].descriptor != pipeline_descriptor || !enqueue_entries[e].resource ||
        !guest_readable(pipeline_descriptor + 0xf8ull, 8) ||
        guest_pointer(pipeline_descriptor + 0xf8ull) != enqueue_entries[e].resource || !guest_readable(actor, 0x378)) return;
    uint64_t resource = guest_pointer(actor + 0x370ull), metadata = guest_pointer(actor + 0x1a8ull);
    int32_t id = guest_s32(actor + 0x10ull);
    if (resource != enqueue_entries[e].resource || id == -1 || !guest_readable(metadata, 0x50) ||
        guest_pointer(metadata + 0x40ull) != actor || guest_s32(metadata + 0x48ull) != id) return;
    unsigned request = enqueue_entries[e].request_index;
    if (__atomic_exchange_n(&resource_entries[request].claimed, 1, __ATOMIC_ACQ_REL)) return;
    resource_entries[request].actor = actor;
    resource_entries[request].resource = resource;
    resource_entries[request].actor_id = id;
    resource_entries[request].address = address;
    resource_entries[request].caller = caller;
    resource_entries[request].host_thread = plat_thread_id();
    __atomic_store_n(&resource_entries[request].ready, 1, __ATOMIC_RELEASE);
}

static void resource_before_cleanup(uint64_t actor, uint64_t caller) {
    for (unsigned i = 0; i < ACTOR_REQUEST_TRACE_LIMIT; i++) {
        if (!__atomic_load_n(&resource_entries[i].ready, __ATOMIC_ACQUIRE) || resource_entries[i].actor != actor ||
            __atomic_load_n(&resource_entries[i].cleanup_claimed, __ATOMIC_RELAXED)) continue;
        if (!guest_readable(actor, 0x378) || guest_s32(actor + 0x10ull) != resource_entries[i].actor_id) continue;
        if (__atomic_exchange_n(&resource_entries[i].cleanup_claimed, 1, __ATOMIC_ACQ_REL)) continue;
        resource_entries[i].cleanup_same = guest_pointer(actor + 0x370ull) == resource_entries[i].resource;
        resource_entries[i].cleanup_caller = caller;
        resource_entries[i].cleanup_thread = plat_thread_id();
        __atomic_store_n(&resource_entries[i].cleanup_ready, 1, __ATOMIC_RELEASE);
    }
}

void coop_adapter_dispose_begin(const Cpu *cpu) {
    memset(&dispose_scope, 0, sizeof dispose_scope);
    if (!cpu || rt_game_version != 143 || !__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED)) return;
    dispose_scope.actor = cpu->x[1];
    dispose_scope.caller = cpu->x[30];
}

static void probe_teardown(uint64_t address, uint64_t caller, uint64_t actor, unsigned stage, uint32_t reason,
                           const Cpu *cpu) {
    for (unsigned n = PROBE_LIMIT; n; n--) {
        unsigned i = n - 1;
        if (!__atomic_load_n(&probe_entries[i].ready, __ATOMIC_ACQUIRE) || probe_entries[i].actor != actor ||
            (__atomic_load_n(&probe_entries[i].stages, __ATOMIC_RELAXED) & 4u)) continue;
        if (!guest_readable(actor, 0x1b0) || guest_s32(actor + 0x10ull) != probe_entries[i].id) continue;
        uint64_t metadata = guest_pointer(actor + 0x1a8ull);
        int live = metadata == probe_entries[i].metadata && guest_readable(metadata, 0x50) &&
                   guest_pointer(metadata + 0x40ull) == actor && guest_s32(metadata + 0x48ull) == probe_entries[i].id;
        // Cleanup can follow metadata invalidation. The actor's own ID must still equal the ID captured at creation.
        if (!live && (stage != 2 || (metadata && metadata != probe_entries[i].metadata))) continue;
        if (__atomic_fetch_or(&probe_entries[i].stages, 1u << stage, __ATOMIC_RELAXED) & (1u << stage)) return;
        unsigned slot = __atomic_fetch_add(&probe_teardown_claimed, 1, __ATOMIC_RELAXED);
        if (slot >= PROBE_TEARDOWN_LIMIT) return;
        probe_teardown_entries[slot].address = address;
        probe_teardown_entries[slot].caller = caller;
        probe_teardown_entries[slot].probe = i;
        probe_teardown_entries[slot].stage = stage;
        probe_teardown_entries[slot].reason = reason;
        probe_teardown_entries[slot].actor_state = (uint32_t)guest_s32(actor + 0x24ull);
        probe_teardown_entries[slot].pending = ((uint32_t)guest_s32(actor + 0x28ull) >> 17) & 1u;
        probe_teardown_entries[slot].host_thread = plat_thread_id();
        probe_teardown_entries[slot].metadata_live = live;
        // The disposal dispatcher loaded its allocator before this virtual cleanup. Retain identities only;
        // the actor must never be dereferenced by the later allocator observer.
        if (stage == 2 && caller == MOD_MAIN_BASE + 0x992610ull && dispose_scope.actor == actor) {
            uint64_t owner = guest_pointer(actor + 8ull);
            uint64_t allocator = guest_readable(owner + 0x38ull, 8) ? guest_pointer(owner + 0x38ull) : 0;
            uint64_t table = guest_readable(allocator, 8) ? guest_pointer(allocator) : 0;
            uint64_t target = guest_readable(table + 0x38ull, 8) ? guest_pointer(table + 0x38ull) : 0;
            if (allocator && allocator == cpu->x[20] && target >= MOD_MAIN_BASE &&
                target < MOD_MAIN_BASE + 0x3adf000ull && !(target & 3ull)) {
                dispose_scope.allocator = allocator;
                dispose_scope.target = target;
                dispose_scope.probe = i;
            }
        }
        __atomic_store_n(&probe_teardown_entries[slot].ready, 1, __ATOMIC_RELEASE);
        return;
    }
}

// Observe the game's removal request, its specific queue handoff and cleanup entry; never call them ourselves.
void coop_adapter_actor_teardown(uint64_t address, const Cpu *cpu) {
    if (!cpu || rt_game_version != 143 || !__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED)) return;
    unsigned stage;
    uint64_t actor;
    if (address == MOD_MAIN_BASE + 0x63baa8ull) { stage = 0; actor = cpu->x[0]; }
    else if (address == MOD_MAIN_BASE + 0x3d45e0ull &&
             (cpu->x[30] == MOD_MAIN_BASE + 0x63bc40ull || cpu->x[30] == MOD_MAIN_BASE + 0x63bcb0ull)) {
        stage = 1; actor = cpu->x[1];
    } else if (address == MOD_MAIN_BASE + 0xa4a194ull) { stage = 2; actor = cpu->x[0]; }
    else return;
    if (stage == 2) resource_before_cleanup(actor, cpu->x[30]);
    probe_teardown(address, cpu->x[30], actor, stage, stage == 0 ? (uint32_t)cpu->x[1] : 0, cpu);
    for (unsigned n = TEARDOWN_TARGET_LIMIT; n; n--) {
        unsigned i = n - 1;
        if (!__atomic_load_n(&teardown_targets[i].ready, __ATOMIC_ACQUIRE) ||
            teardown_targets[i].actor != actor ||
            (__atomic_load_n(&teardown_targets[i].stages, __ATOMIC_RELAXED) & 4u)) continue;
        if (!guest_readable(actor, 0x1b0) || guest_pointer(actor + 0x1a8ull) != teardown_targets[i].metadata ||
            !guest_readable(teardown_targets[i].metadata, 0x50) ||
            guest_pointer(teardown_targets[i].metadata + 0x40ull) != actor ||
            guest_s32(teardown_targets[i].metadata + 0x48ull) != teardown_targets[i].id) continue;
        if (__atomic_fetch_or(&teardown_targets[i].stages, 1u << stage, __ATOMIC_RELAXED) & (1u << stage)) return;
        unsigned slot = __atomic_fetch_add(&teardown_claimed, 1, __ATOMIC_RELAXED);
        if (slot >= TEARDOWN_TRACE_LIMIT) return;
        teardown_entries[slot].address = address;
        teardown_entries[slot].caller = cpu->x[30];
        teardown_entries[slot].generation = teardown_targets[i].generation;
        teardown_entries[slot].stage = stage;
        teardown_entries[slot].reason = stage == 0 ? (uint32_t)cpu->x[1] : 0;
        teardown_entries[slot].actor_state = (uint32_t)guest_s32(actor + 0x24ull);
        teardown_entries[slot].pending = ((uint32_t)guest_s32(actor + 0x28ull) >> 17) & 1u;
        teardown_entries[slot].host_thread = plat_thread_id();
        __atomic_store_n(&teardown_entries[slot].ready, 1, __ATOMIC_RELEASE);
        return;
    }
}

// Capture the task descriptor, holder call and actor initializer dispatches before their targets run.
// Return sites identify the observed call path; neither call is made by the adapter.
void coop_adapter_native_dispatch(uint64_t address, uint64_t caller, uint64_t x0,
                                  uint64_t x1, uint64_t x2) {
    if (rt_game_version != 143) return;
    npc_velocity_backend_observe(address, caller, x1, x2);
    if (__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED) && dispose_scope.target &&
        address == dispose_scope.target && caller == dispose_scope.caller &&
        x0 == dispose_scope.allocator && x1 == dispose_scope.actor) {
        unsigned probe = dispose_scope.probe;
        memset(&dispose_scope, 0, sizeof dispose_scope);
        if (!(__atomic_fetch_or(&probe_entries[probe].stages, 8u, __ATOMIC_RELAXED) & 8u)) {
            unsigned slot = __atomic_fetch_add(&probe_allocator_claimed, 1, __ATOMIC_RELAXED);
            if (slot < PROBE_LIMIT) {
                probe_allocator_entries[slot].address = address;
                probe_allocator_entries[slot].caller = caller;
                probe_allocator_entries[slot].probe = probe;
                probe_allocator_entries[slot].host_thread = plat_thread_id();
                __atomic_store_n(&probe_allocator_entries[slot].ready, 1, __ATOMIC_RELEASE);
            }
        }
    }
    if (pipeline_allocator && address == pipeline_release_target && x0 == pipeline_allocator &&
        x1 == pipeline_descriptor) {
        lifecycle_capture(address, caller, pipeline_descriptor, 0, 6, 0);
        pipeline_descriptor = pipeline_actor = pipeline_allocator = pipeline_release_target = 0;
    }
    if (caller == MOD_MAIN_BASE + 0x3d4488ull && x2 >= 0x18ull) {
        probe_initialized(address, caller, x0, x2, x1);
        resource_initialized(address, caller, x0, x2, x1);
        lifecycle_capture(address, caller, x2 - 0x18ull, x0, 0, (uint32_t)x1);
    }
    const uint64_t release_callers[] = {0x3d3e64ull, 0x3d3e74ull, 0x3d3e88ull};
    const uint64_t release_offsets[] = {0x140ull, 0x110ull, 0xf0ull};
    for (unsigned i = 0; i < 3; i++)
        if (caller == MOD_MAIN_BASE + release_callers[i] && x0 >= release_offsets[i])
            lifecycle_capture(address, caller, x0 - release_offsets[i], 0, i + 1, 0);
    if (address == MOD_MAIN_BASE + 0x3d3dd0ull) {
        dispatched_caller = caller;
        dispatched_descriptor = x1;
    }
    if ((caller == MOD_MAIN_BASE + 0x3d4150ull || caller == MOD_MAIN_BASE + 0x3d4198ull) && x1) {
        // The scoped holder receives the factory result even for actor types with another allocator wrapper.
        if (pipeline_descriptor && x0 == pipeline_descriptor + 0xf0ull) pipeline_actor = x1;
        unsigned slot = __atomic_fetch_add(&holder_claimed, 1, __ATOMIC_RELAXED);
        if (slot < HOLDER_TRACE_LIMIT) {
            holder_entries[slot].address = address;
            holder_entries[slot].caller = caller;
            holder_entries[slot].holder = x0;
            holder_entries[slot].actor = x1;
            holder_entries[slot].mode = (uint32_t)x2;
            holder_entries[slot].host_thread = plat_thread_id();
            __atomic_store_n(&holder_entries[slot].ready, 1, __ATOMIC_RELEASE);
        }
    }
    if ((caller == MOD_MAIN_BASE + 0x3d4264ull || caller == MOD_MAIN_BASE + 0x3d4284ull ||
         caller == MOD_MAIN_BASE + 0x3d42a0ull) && x0) {
        unsigned slot = __atomic_fetch_add(&initializer_claimed, 1, __ATOMIC_RELAXED);
        if (slot < INITIALIZER_TRACE_LIMIT) {
            initializer_entries[slot].address = address;
            initializer_entries[slot].caller = caller;
            initializer_entries[slot].actor = x0;
            initializer_entries[slot].context = x1;
            initializer_entries[slot].host_thread = plat_thread_id();
            __atomic_store_n(&initializer_entries[slot].ready, 1, __ATOMIC_RELEASE);
        }
    }
}

void coop_adapter_function(uint64_t address, uint64_t caller, uint64_t argument) {
    if (!__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED)) return;
    npc_velocity_lock_observe(address, caller, argument);
    if (address == MOD_MAIN_BASE + 0xa0f3f0ull) npc_physics_observe(caller, argument);
    if (address == MOD_MAIN_BASE + 0x2e27b0ull) npc_physics_late_observe(caller, argument);
    npc_receiver_observe(address, caller, argument);
    if (argument && argument == __atomic_load_n(&probe_motion_actor, __ATOMIC_ACQUIRE)) {
        unsigned i = probe_motion_index;
        int64_t now = frame_step_world_us();
        int64_t last = __atomic_load_n(&probe_motion_last_us, __ATOMIC_RELAXED);
        if (i < PROBE_LIMIT && !__atomic_load_n(&probe_entries[i].stages, __ATOMIC_ACQUIRE) &&
            now >= last + 100000 && __atomic_load_n(&probe_motion_count, __ATOMIC_RELAXED) < 128 &&
            __atomic_compare_exchange_n(&probe_motion_last_us, &last, now, 0, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {
            uint64_t meta = probe_entries[i].metadata;
            int32_t id = probe_entries[i].id;
            float pos[3];
            if (guest_readable(argument, 0x2c0) && guest_readable(meta, 0x50) &&
                guest_pointer(argument + 0x1a8) == meta && guest_pointer(meta + 0x40) == argument &&
                guest_s32(meta + 0x48) == id && guest_s32(argument + 0x10) == id &&
                plat_mem_read(argument + 0x2b4, pos, sizeof pos) &&
                isfinite(pos[0]) && isfinite(pos[1]) && isfinite(pos[2]) &&
                !__atomic_load_n(&probe_entries[i].stages, __ATOMIC_ACQUIRE)) {
                __atomic_fetch_add(&probe_motion_count, 1, __ATOMIC_RELAXED);
                rt_log("coop native spawn motion: probe %u, request %u, world us %lld, pos %.6f %.6f %.6f, entry main+%#llx; native receiver observation only",
                       i, probe_entries[i].request, (long long)now, pos[0], pos[1], pos[2],
                       (unsigned long long)(address - MOD_MAIN_BASE));
            }
        }
    }
    // Observe publication before the native mutex unlock, or the common handle-release entry before it clears the value.
    int publication = address == MOD_MAIN_BASE + 0x2bb7a70ull && caller == MOD_MAIN_BASE + 0x54cf00ull;
    int consumption = address == MOD_MAIN_BASE + 0x50d6bcull && caller == MOD_MAIN_BASE + 0xea5d28ull;
    if (rt_game_version == 143 && ((publication && argument >= 0x10ull) ||
                                  consumption ||
                                  address == MOD_MAIN_BASE + 0x5559a0ull)) {
        uint64_t handle = publication ? argument - 0x10ull : argument;
        if (!guest_readable(handle, 0x10)) return;
        uint32_t state = (uint32_t)guest_s32(handle) & 0xffffu;
        if ((publication || consumption) && state != 3) return;
        uint64_t value = guest_pointer(handle + 8ull);
        for (unsigned n = ACTOR_REQUEST_TRACE_LIMIT; n; n--) {
            unsigned i = n - 1;
            if (!__atomic_load_n(&enqueue_entries[i].ready, __ATOMIC_ACQUIRE) ||
                enqueue_entries[i].handle != handle) continue;
            unsigned request = enqueue_entries[i].request_index;
            if (__atomic_load_n(&actor_request_entries[request].reference_captured, __ATOMIC_RELAXED) & 4u) return;
            ready_reference_capture(address, caller, request, value, state, publication ? 1 : consumption ? 3 : 2);
            return;
        }
        return;
    }
    // Capture a ready handle before the native slot-release routine clears it. This does not request actor removal.
    if (rt_game_version == 143 && address == MOD_MAIN_BASE + 0x97df04ull) {
        for (unsigned n = ACTOR_REQUEST_TRACE_LIMIT; n; n--) {
            unsigned i = n - 1;
            if (!__atomic_load_n(&actor_request_entries[i].ready, __ATOMIC_ACQUIRE) ||
                actor_request_entries[i].watcher != argument) continue;
            uint64_t handle = guest_readable(argument, 8) ? guest_pointer(argument) : 0;
            if (!guest_readable(handle, 0x10) || ((uint32_t)guest_s32(handle) & 0xffffu) != 3) return;
            uint64_t value = guest_pointer(handle + 8ull);
            ready_reference_capture(address, caller, i, value, 3, 2);
            return;
        }
        return;
    }
    // Follow only the descriptor carried by this thread's observed task dispatch. Never dereference it after free.
    if (rt_game_version == 143 && pipeline_descriptor) {
        if (address == MOD_MAIN_BASE + 0x3d3edcull && argument == pipeline_descriptor + 0x18ull) {
            lifecycle_capture(address, caller, pipeline_descriptor, 0, 4, 0);
            // The cleanup context is still live here; retain only identities for the later allocator dispatch.
            pipeline_allocator = guest_pointer(pipeline_descriptor + 0x160ull);
            uint64_t table = guest_readable(pipeline_allocator, 8) ? guest_pointer(pipeline_allocator) : 0;
            pipeline_release_target = guest_readable(table + 0x38ull, 8) ? guest_pointer(table + 0x38ull) : 0;
        }
        if (address == MOD_MAIN_BASE + 0x167e20ull && argument == pipeline_descriptor) {
            lifecycle_capture(address, caller, pipeline_descriptor, 0, 5, 0);
            pipeline_descriptor = pipeline_actor = pipeline_allocator = pipeline_release_target = 0;
        }
    }
    if (address == MOD_MAIN_BASE + 0xd30cf8ull) {
        unsigned slot = __atomic_fetch_add(&player_pipeline_claimed, 1, __ATOMIC_RELAXED);
        if (slot < PLAYER_PIPELINE_TRACE_LIMIT) {
            player_pipeline_entries[slot].caller = caller;
            player_pipeline_entries[slot].host_thread = plat_thread_id();
            player_pipeline_entries[slot].receiver_readable = guest_readable(argument, 8);
            __atomic_store_n(&player_pipeline_entries[slot].ready, 1, __ATOMIC_RELEASE);
        }
        return;
    }
    if (address == MOD_MAIN_BASE + 0xc9a5a4ull) {
        unsigned slot = __atomic_fetch_add(&resident_init_claimed, 1, __ATOMIC_RELAXED);
        if (slot < RESIDENT_INIT_TRACE_LIMIT) {
            resident_init_entries[slot].receiver = argument;
            resident_init_entries[slot].caller = caller;
            resident_init_entries[slot].host_thread = plat_thread_id();
            __atomic_store_n(&resident_init_entries[slot].ready, 1, __ATOMIC_RELEASE);
        }
        return;
    }
    if (address == MOD_MAIN_BASE + 0x3d3dd0ull) {
        pipeline_caller = caller;
        pipeline_descriptor = caller == dispatched_caller ? dispatched_descriptor : 0;
        pipeline_actor = pipeline_allocator = pipeline_release_target = 0;
        pipeline_request_index = ACTOR_REQUEST_TRACE_LIMIT;
        for (unsigned n = ACTOR_REQUEST_TRACE_LIMIT; pipeline_descriptor && n; n--) {
            unsigned i = n - 1;
            if (!__atomic_load_n(&enqueue_entries[i].ready, __ATOMIC_ACQUIRE) ||
                enqueue_entries[i].descriptor != pipeline_descriptor) continue;
            if (!__atomic_exchange_n(&enqueue_entries[i].dispatched, 1, __ATOMIC_ACQ_REL)) pipeline_request_index = i;
            break;
        }
        dispatched_caller = dispatched_descriptor = 0;
        return;
    }
    if (address == MOD_MAIN_BASE + 0x3d40f0ull) {
        factory_request_caller = caller; // the caller requested a factory-created object
        request_pipeline_caller = caller == MOD_MAIN_BASE + 0x3d3e44ull ? pipeline_caller : 0;
        request_descriptor = request_pipeline_caller ? pipeline_descriptor : 0;
        return;
    }
    if (address == MOD_MAIN_BASE + 0x689894ull) {
        factory_caller = caller; // this wrapper allocates before calling the GameActor constructor
        wrapper_request_caller = caller == MOD_MAIN_BASE + 0x3d4114ull ? factory_request_caller : 0;
        wrapper_pipeline_caller = caller == MOD_MAIN_BASE + 0x3d4114ull ? request_pipeline_caller : 0;
        wrapper_descriptor = caller == MOD_MAIN_BASE + 0x3d4114ull ? request_descriptor : 0;
        return;
    }
    // The GameActor constructor associated with the observed vtable runs before presence is ready.
    // Keep its separate bounded trace until actor observation can correlate an allocated object.
    if (address == MOD_MAIN_BASE + 0x6898dcull) {
        uint64_t outer_caller = caller == MOD_MAIN_BASE + 0x6898ccull ? factory_caller : 0;
        uint64_t request_caller = outer_caller == MOD_MAIN_BASE + 0x3d4114ull ? wrapper_request_caller : 0;
        uint64_t upstream_caller = request_caller == MOD_MAIN_BASE + 0x3d3e44ull ? wrapper_pipeline_caller : 0;
        uint64_t task_descriptor = upstream_caller ? wrapper_descriptor : 0;
        if (task_descriptor) pipeline_actor = argument;
        factory_caller = 0;
        wrapper_request_caller = 0;
        wrapper_pipeline_caller = 0;
        wrapper_descriptor = 0;
        unsigned slot = __atomic_fetch_add(&constructor_claimed, 1, __ATOMIC_RELAXED);
        if (slot < CONSTRUCTOR_TRACE_LIMIT) {
            constructor_entries[slot].caller = caller;
            constructor_entries[slot].actor = argument;
            constructor_entries[slot].factory_caller = outer_caller;
            constructor_entries[slot].request_caller = request_caller;
            constructor_entries[slot].pipeline_caller = upstream_caller;
            constructor_entries[slot].task_descriptor = task_descriptor;
            constructor_entries[slot].host_thread = plat_thread_id();
            __atomic_store_n(&constructor_entries[slot].ready, 1, __ATOMIC_RELEASE);
        }
        return;
    }
    uint32_t generation = __atomic_load_n(&trace_generation, __ATOMIC_ACQUIRE);
    if (!generation) return;   // title/loading observations must not consume the gameplay trace budget
    uint64_t actor = __atomic_load_n(&trace_actor, __ATOMIC_RELAXED);
    uint64_t method = __atomic_load_n(&trace_actor_method, __ATOMIC_RELAXED);
    unsigned kind;
    if (address == method && argument == actor) kind = 0;
    else if (address == MOD_MAIN_BASE + 0xa0f3f0ull) kind = 1;
    else if (address == MOD_MAIN_BASE + 0xa11af0ull) kind = 2;
    else return;
    if (generation != __atomic_load_n(&trace_generation, __ATOMIC_ACQUIRE)) return;
    unsigned used = __atomic_load_n(&trace_kind_claimed[kind], __ATOMIC_RELAXED);
    for (;;) {
        if (used >= trace_kind_limits[kind]) return;
        if (__atomic_compare_exchange_n(&trace_kind_claimed[kind], &used, used + 1, 1,
                                        __ATOMIC_RELAXED, __ATOMIC_RELAXED)) break;
    }
    unsigned slot = __atomic_fetch_add(&trace_claimed, 1, __ATOMIC_RELAXED);
    if (slot >= 64) return;
    trace_entries[slot].address = address; trace_entries[slot].caller = caller; trace_entries[slot].argument = argument;
    trace_entries[slot].host_thread = plat_thread_id();
    trace_entries[slot].generation = generation; trace_entries[slot].kind = kind;
    __atomic_store_n(&trace_entries[slot].ready, 1, __ATOMIC_RELEASE);
}

uint32_t coop_adapter_capabilities(void) { return COOP_CAP_PRESENCE; }

void coop_adapter_observe(const Cpu *cpu) {
    float pos[3] = {0}, yaw = 0;
    int action = COOP_ACT_EXPLORING;
    uint64_t actor = read_player_state(pos, &yaw, &action);
    CoopSample visual = {0};
    uint32_t actor_id = actor ? (uint32_t)guest_s32(actor + 0x10) : 0;
    if (actor) {
        read_player_visual(actor, &visual);
        if (player_proc() != actor || (uint32_t)guest_s32(actor + 0x10) != actor_id)
            memset(&visual, 0, sizeof visual);
    }
    uint64_t resident_record = 0, resident_data = 0;
    uint64_t resident_actor = actor && __atomic_load_n(&trace_enabled, __ATOMIC_RELAXED) ?
                              resident_player_proc(actor, &resident_record, &resident_data) : 0;
    uint64_t scene = 0, module = rt_game_version == 143 ? guest_pointer(MOD_MAIN_BASE + 0x3add238ull) : 0;
    if (module) scene = guest_pointer(module + 0x1e8ull);
    uint64_t now = plat_now_ns();
    if (__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED))
        __atomic_store_n(&known_player_manager_link, player_manager_link(), __ATOMIC_RELEASE);
    plat_mutex_lock(&adapter_lock);
    CoopSample previous = observed.sample;
    uint32_t resident_match = actor && resident_actor == actor;
    float displacement = hypotf(hypotf(pos[0] - previous.pos[0], pos[2] - previous.pos[2]),
                                pos[1] - previous.pos[1]);
    int changed = !observed.observations || actor != observed.actor || scene != observed.scene_address ||
                  (actor && displacement > 128);
    if (changed) {
        if (!++observed.sample.generation) ++observed.sample.generation;
        rt_log("coop adapter: generation %u, player %s, scene observation %s; native actor/control unverified (guest lr %#llx, host thread %u)",
               observed.sample.generation, actor ? "observed" : "absent", scene ? "present" : "absent",
               (unsigned long long)(cpu ? cpu->x[30] : 0), plat_thread_id());
    }
    if (actor && __atomic_load_n(&trace_enabled, __ATOMIC_RELAXED) && local_sample_count < 64) {
        int64_t world_us = frame_step_world_us();
        if (world_us >= next_local_sample_us) {
            rt_log("coop native local sample: world ms %.1f, generation %u, pos %.6f %.6f %.6f, yaw %.6f, action %d; observation only",
                   world_us / 1000.0, observed.sample.generation, pos[0], pos[1], pos[2], yaw, action);
            local_sample_count++;
            rt_log("coop visual sample: world ms %.1f, generation %u, rotation %s, animation %s, frame %.6f; observation only",
                   world_us / 1000.0, observed.sample.generation,
                   (visual.flags & COOP_SAMPLE_ROTATION) ? "observed" : "absent",
                   (visual.flags & COOP_SAMPLE_ANIMATION) ? visual.animation : "unavailable", visual.animation_frame);
            next_local_sample_us = world_us + 250000;
        }
    }
    if (actor && __atomic_load_n(&trace_enabled, __ATOMIC_RELAXED))
        teardown_observe_player(actor, observed.sample.generation);
    while (probe_consumed < PROBE_LIMIT && __atomic_load_n(&probe_entries[probe_consumed].ready, __ATOMIC_ACQUIRE)) {
        unsigned i = probe_consumed++;
        rt_log("coop native probe actor: entry main+%#llx, caller %#llx, probe %u, name %s, request task same, metadata backlink same, generation %u, host thread %u, request %u; observation only",
               (unsigned long long)(probe_entries[i].address - MOD_MAIN_BASE),
               (unsigned long long)probe_entries[i].caller, i, actor_request_entries[probe_entries[i].request].name,
               probe_entries[i].generation, probe_entries[i].host_thread, probe_entries[i].request);
    }
    for (unsigned phase = 0; phase < 2; phase++) {
        NpcPhysicsSnapshot *snapshot = phase ? &npc_late_physics : &npc_physics;
        if (!__atomic_load_n(&snapshot->ready, __ATOMIC_ACQUIRE) || snapshot->emitted) continue;
        static const char *const names[] = {"component", "set", "set10", "set148", "set10_8", "set10_8_18", "body158", "set8", "set8_20", "set150", "body1e0", "body1e0_28"};
        rt_log("coop native npc physics: probe %u, request %u, entry main+%#llx, caller %#llx, generation %u, world us %lld, host thread %u, phase %s; owner and metadata matched, observation only",
               snapshot->probe, snapshot->request, (unsigned long long)main_relative(snapshot->entry), (unsigned long long)snapshot->caller,
               snapshot->generation, (long long)snapshot->world_us, snapshot->host_thread, phase ? "later-actor-update" : "transform-builder");
        for (unsigned n = 0; n < 12; n++)
            rt_log("coop native npc node: kind %s, readable %s, vtable main+%#llx, methods %#llx %#llx %#llx %#llx %#llx %#llx %#llx %#llx; observation only",
                   names[n], snapshot->node[n].readable ? "yes" : "no", (unsigned long long)snapshot->node[n].vtable,
                   (unsigned long long)snapshot->node[n].methods[0], (unsigned long long)snapshot->node[n].methods[1],
                   (unsigned long long)snapshot->node[n].methods[2], (unsigned long long)snapshot->node[n].methods[3],
                   (unsigned long long)snapshot->node[n].methods[4], (unsigned long long)snapshot->node[n].methods[5],
                   (unsigned long long)snapshot->node[n].methods[6], (unsigned long long)snapshot->node[n].methods[7]);
        rt_log("coop native npc body flags: %#llx; read from the native transform-builder's body path, observation only",
               (unsigned long long)snapshot->body_flags);
        snapshot->emitted = 1;
    }
    while (npc_receiver_consumed < 64 && __atomic_load_n(&npc_receivers[npc_receiver_consumed].ready, __ATOMIC_ACQUIRE)) {
        unsigned i = npc_receiver_consumed++;
        rt_log("coop native npc receiver: kind %s, entry main+%#llx, caller %#llx, world us %lld, host thread %u; observation only",
               npc_receivers[i].kind == 9 ? "set" : npc_receivers[i].kind == 8 ? "component" :
               npc_receivers[i].kind == 7 ? "body1e0_28" : npc_receivers[i].kind == 6 ? "body1e0" :
               npc_receivers[i].kind == 5 ? "set150" : npc_receivers[i].kind == 4 ? "set8_20" : npc_receivers[i].kind == 3 ? "set8" :
               npc_receivers[i].kind == 2 ? "body158" : npc_receivers[i].kind ? "body" : "set10", (unsigned long long)main_relative(npc_receivers[i].address),
               (unsigned long long)npc_receivers[i].caller, (long long)npc_receivers[i].world_us, npc_receivers[i].thread);
    }
    while (npc_velocity_consumed < NPC_VELOCITY_TRACE_LIMIT &&
           __atomic_load_n(&npc_velocity_entries[npc_velocity_consumed].ready, __ATOMIC_ACQUIRE)) {
        unsigned i = npc_velocity_consumed++;
        rt_log("coop native npc velocity path: stage %s, entry main+%#llx, caller %#llx, generation %u, world us %lld, request flags %#x, velocity %.6f %.6f %.6f, host thread %u; observation only",
               npc_velocity_entries[i].backend == 3 ? "body-unlock-entry" : npc_velocity_entries[i].backend == 2 ? "body-lock-entry" :
               npc_velocity_entries[i].backend ? "backend-dispatch" : "request-consumer",
               (unsigned long long)main_relative(npc_velocity_entries[i].entry), (unsigned long long)npc_velocity_entries[i].caller,
               npc_velocity_entries[i].generation, (long long)npc_velocity_entries[i].world_us, npc_velocity_entries[i].flags,
               npc_velocity_entries[i].velocity[0], npc_velocity_entries[i].velocity[1], npc_velocity_entries[i].velocity[2],
               npc_velocity_entries[i].thread);
    }
    for (unsigned i = 0; i < ACTOR_REQUEST_TRACE_LIMIT; i++) {
        if (__atomic_load_n(&resource_entries[i].ready, __ATOMIC_ACQUIRE) && !resource_entries[i].emitted) {
            rt_log("coop native resource binding: entry main+%#llx, caller %#llx, request %u, name %s, task resource same, actor resource same, actor id same, host thread %u; observation only",
                   (unsigned long long)(resource_entries[i].address - MOD_MAIN_BASE),
                   (unsigned long long)resource_entries[i].caller, i, actor_request_entries[i].name,
                   resource_entries[i].host_thread);
            resource_entries[i].emitted = 1;
        }
        if (__atomic_load_n(&resource_entries[i].cleanup_ready, __ATOMIC_ACQUIRE) && !resource_entries[i].cleanup_emitted) {
            rt_log("coop native resource cleanup: entry main+0xa4a194, caller %#llx, request %u, name %s, actor id same, actor resource %s, host thread %u; observation only",
                   (unsigned long long)resource_entries[i].cleanup_caller, i, actor_request_entries[i].name,
                   resource_entries[i].cleanup_same ? "same" : "different", resource_entries[i].cleanup_thread);
            resource_entries[i].cleanup_emitted = 1;
        }
    }
    while (probe_teardown_consumed < PROBE_TEARDOWN_LIMIT &&
           __atomic_load_n(&probe_teardown_entries[probe_teardown_consumed].ready, __ATOMIC_ACQUIRE)) {
        unsigned i = probe_teardown_consumed++;
        unsigned probe = probe_teardown_entries[i].probe;
        const char *stages[] = {"request", "queue", "cleanup"};
        rt_log("coop native probe teardown: entry main+%#llx, caller %#llx, probe %u, name %s, stage %s, actor id same, reason %u, actor state %u, removal pending %s, host thread %u, metadata live %s; observation only",
               (unsigned long long)(probe_teardown_entries[i].address - MOD_MAIN_BASE),
               (unsigned long long)probe_teardown_entries[i].caller, probe,
               actor_request_entries[probe_entries[probe].request].name, stages[probe_teardown_entries[i].stage],
               probe_teardown_entries[i].reason, probe_teardown_entries[i].actor_state,
               probe_teardown_entries[i].pending ? "yes" : "no", probe_teardown_entries[i].host_thread,
               probe_teardown_entries[i].metadata_live ? "yes" : "no");
    }
    while (probe_allocator_consumed < PROBE_LIMIT &&
           __atomic_load_n(&probe_allocator_entries[probe_allocator_consumed].ready, __ATOMIC_ACQUIRE)) {
        unsigned i = probe_allocator_consumed++;
        unsigned probe = probe_allocator_entries[i].probe;
        rt_log("coop native probe allocator: entry main+%#llx, caller %#llx, probe %u, name %s, cleanup scope same, actor argument same, host thread %u; observation only",
               (unsigned long long)(probe_allocator_entries[i].address - MOD_MAIN_BASE),
               (unsigned long long)probe_allocator_entries[i].caller, probe,
               actor_request_entries[probe_entries[probe].request].name, probe_allocator_entries[i].host_thread);
    }
    while (teardown_consumed < TEARDOWN_TRACE_LIMIT &&
           __atomic_load_n(&teardown_entries[teardown_consumed].ready, __ATOMIC_ACQUIRE)) {
        unsigned i = teardown_consumed++;
        const char *stages[] = {"request", "queue", "cleanup"};
        rt_log("coop native actor teardown: entry main+%#llx, caller %#llx, stage %s, observed player same, generation %u, reason %u, actor state %u, removal pending %s, host thread %u; observation only",
               (unsigned long long)(teardown_entries[i].address - MOD_MAIN_BASE),
               (unsigned long long)teardown_entries[i].caller, stages[teardown_entries[i].stage],
               teardown_entries[i].generation, teardown_entries[i].reason, teardown_entries[i].actor_state,
               teardown_entries[i].pending ? "yes" : "no", teardown_entries[i].host_thread);
        observed.native_teardown_trace_count++;
    }
    if (actor && (changed || resident_match != observed.native_resident_match))
        rt_log("coop native scene resident: player %s; observation only",
               resident_match ? "matched" : "unmatched");
    if (actor && resident_match && __atomic_load_n(&trace_enabled, __ATOMIC_RELAXED)) {
        uint64_t resident = resident_component();
        uint64_t vtable = resident ? guest_pointer(resident) : 0;
        if (changed && vtable >= MOD_MAIN_BASE && vtable < MOD_MAIN_BASE + 0x3adf000ull && !(vtable & 7ull)) {
            rt_log("coop native resident component: vtable main+%#llx, list count %d; observation only",
                   (unsigned long long)(vtable - MOD_MAIN_BASE), guest_s32(resident + 0x20ull));
            observed.native_resident_component_vtable_count++;
        }
        if (changed && resident_record && resident_data) {
            uint64_t handle = guest_pointer(resident_record + 0x18ull);
            int handle_readable = guest_readable(handle, 0x10);
            uint32_t handle_state = handle_readable ? (uint32_t)guest_s32(handle) & 0xffffu : 0xffffu;
            uint64_t value = handle_readable ? guest_pointer(handle + 8ull) : 0;
            rt_log("coop native resident reference: handle present %s, handle readable %s, state %u, value actor %s, value resident data %s; observation only",
                   handle ? "yes" : "no", handle_readable ? "yes" : "no", handle_state,
                   !handle_readable ? "unknown" : value == actor ? "same" : "different",
                   !handle_readable ? "unknown" : value == resident_data ? "same" : "different");
            observed.native_resident_reference_count++;
            uint64_t record_vtable = guest_pointer(resident_record);
            uint64_t data_vtable = guest_pointer(resident_data);
            if (record_vtable >= MOD_MAIN_BASE && record_vtable < MOD_MAIN_BASE + 0x3adf000ull &&
                !(record_vtable & 7ull)) {
                int data_vtable_in_main = data_vtable >= MOD_MAIN_BASE &&
                    data_vtable < MOD_MAIN_BASE + 0x3adf000ull && !(data_vtable & 7ull);
                rt_log("coop native resident record: vtable main+%#llx, data first word main vtable %s; observation only",
                       (unsigned long long)(record_vtable - MOD_MAIN_BASE),
                       data_vtable_in_main ? "yes" : "no");
                observed.native_resident_record_vtable_count++;
            }
        }
        if (!resident_init_summary_logged) {
            rt_log("coop native resident init budget: %u entries before first playable actor, limit %u; observation only",
                   __atomic_load_n(&resident_init_claimed, __ATOMIC_ACQUIRE), RESIDENT_INIT_TRACE_LIMIT);
            resident_init_summary_logged = 1;
        }
        while (resident_init_consumed < RESIDENT_INIT_TRACE_LIMIT &&
               __atomic_load_n(&resident_init_entries[resident_init_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = resident_init_consumed++;
            if (resident_init_entries[i].receiver == resident) {
                rt_log("coop native resident init: entry main+0xc9a5a4, caller %#llx, x0 resident same, host thread %u; observation only",
                       (unsigned long long)resident_init_entries[i].caller,
                       resident_init_entries[i].host_thread);
                observed.native_resident_init_trace_count++;
            }
        }
    }
    observed.native_resident_match = resident_match;
    observed.actor = actor; observed.scene_address = scene; observed.observations++;
    if (actor != matched_task_actor || scene != matched_task_scene) {
        matched_task_actor = actor;
        matched_task_scene = scene;
        matched_task_descriptor = 0;
    }
    if (actor) {
        while (player_pipeline_consumed < PLAYER_PIPELINE_TRACE_LIMIT &&
               __atomic_load_n(&player_pipeline_entries[player_pipeline_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = player_pipeline_consumed++;
            rt_log("coop native player pipeline: entry main+0xd30cf8, caller %#llx, x0 readable %s, host thread %u; observation only",
                   (unsigned long long)player_pipeline_entries[i].caller,
                   player_pipeline_entries[i].receiver_readable ? "yes" : "no",
                   player_pipeline_entries[i].host_thread);
            observed.native_player_pipeline_trace_count++;
        }
        if (!actor_request_summary_logged) {
            rt_log("coop native actor request budget: %u calls, %u Player candidates before first playable actor, limit %u; observation only",
                   __atomic_load_n(&actor_request_total, __ATOMIC_ACQUIRE),
                   __atomic_load_n(&actor_request_claimed, __ATOMIC_ACQUIRE), ACTOR_REQUEST_TRACE_LIMIT);
            actor_request_summary_logged = 1;
        }
        while (actor_request_consumed < ACTOR_REQUEST_TRACE_LIMIT &&
               __atomic_load_n(&actor_request_entries[actor_request_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = actor_request_consumed++;
            unsigned watcher_group = actor_request_entries[i].watcher ? i + 1 : 0;
            for (unsigned j = 0; j < i && watcher_group; j++)
                if (actor_request_entries[j].watcher == actor_request_entries[i].watcher) {
                    watcher_group = j + 1;
                    break;
                }
            int watcher_resident_slot = resident_record &&
                !strcmp(actor_request_entries[i].name, "Player") &&
                actor_request_entries[i].watcher == resident_record + 0x18ull;
            rt_log("coop native actor request: entry main+0x599670, caller %#llx, name %s, manager readable %s, create arg readable %s, transform flags %u, watcher readable %s, watcher group %u, watcher resident slot %s, priority %llu, host thread %u; observation only",
                   (unsigned long long)actor_request_entries[i].caller, actor_request_entries[i].name,
                   actor_request_entries[i].manager_readable ? "yes" : "no",
                   actor_request_entries[i].arg_readable ? "yes" : "no",
                   actor_request_entries[i].transform_flags,
                   actor_request_entries[i].watcher_readable ? "yes" : "no",
                   watcher_group,
                   resident_record ? (watcher_resident_slot ? "yes" : "no") : "unknown",
                   (unsigned long long)actor_request_entries[i].priority,
                   actor_request_entries[i].host_thread);
            observed.native_actor_request_trace_count++;
            if (actor_request_entries[i].caller == RT_RET_HOST)
                rt_log("coop native spawn request: request %u, name %s, watcher %s; isolated experiment",
                       i, actor_request_entries[i].name, actor_request_entries[i].watcher ? "present" : "absent");
            rt_log("coop native request abi: entry main+0x599670, caller %#llx, name %s, extra registers nonzero mask %u, stack readable %s, stack flag %u, stack pointers nonzero mask %u, host thread %u; observation only",
                   (unsigned long long)actor_request_entries[i].caller, actor_request_entries[i].name,
                   actor_request_entries[i].extra_register_mask, actor_request_entries[i].stack_readable ? "yes" : "no",
                   actor_request_entries[i].stack_flag, actor_request_entries[i].stack_pointer_mask,
                   actor_request_entries[i].host_thread);
            observed.native_actor_request_resident_match_count += watcher_resident_slot;
        }
        if (!constructor_summary_logged) {
            rt_log("coop native constructor budget: %u entries before first playable actor, limit %u; observation only",
                   __atomic_load_n(&constructor_claimed, __ATOMIC_ACQUIRE), CONSTRUCTOR_TRACE_LIMIT);
            constructor_summary_logged = 1;
        }
        while (constructor_consumed < CONSTRUCTOR_TRACE_LIMIT &&
               __atomic_load_n(&constructor_entries[constructor_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = constructor_consumed++;
            if (constructor_entries[i].actor == actor) {
                matched_task_descriptor = constructor_entries[i].task_descriptor;
                rt_log("coop native constructor: entry main+0x6898dc, caller %#llx, x0 %#llx, host thread %u, factory caller %#llx, request caller %#llx, pipeline caller %#llx, task descriptor %#llx, observed player same; observation only",
                       (unsigned long long)constructor_entries[i].caller,
                       (unsigned long long)constructor_entries[i].actor,
                       constructor_entries[i].host_thread,
                       (unsigned long long)constructor_entries[i].factory_caller,
                       (unsigned long long)constructor_entries[i].request_caller,
                       (unsigned long long)constructor_entries[i].pipeline_caller,
                       (unsigned long long)constructor_entries[i].task_descriptor);
                observed.native_constructor_trace_count++;
            }
        }
        while (request_context_consumed < ACTOR_REQUEST_TRACE_LIMIT &&
               __atomic_load_n(&request_context_entries[request_context_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = request_context_consumed++;
            unsigned request = request_context_entries[i].request_index;
            int task_same = matched_task_descriptor &&
                request_context_entries[i].descriptor == matched_task_descriptor;
            rt_log("coop native request context: entry main+0x59a138, caller %#llx, name %s, constructor task %s, host thread %u; observation only",
                   (unsigned long long)request_context_entries[i].caller,
                   actor_request_entries[request].name,
                   !matched_task_descriptor ? "unknown" : task_same ? "same" : "different",
                   request_context_entries[i].host_thread);
            observed.native_request_task_match_count += task_same;
        }
        while (enqueue_consumed < ACTOR_REQUEST_TRACE_LIMIT &&
               __atomic_load_n(&enqueue_entries[enqueue_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = enqueue_consumed++;
            unsigned request = enqueue_entries[i].request_index;
            rt_log("coop native request enqueue: entry main+0x59a380, caller %#llx, name %s, priority %llu, manager readable %s, handle readable %s, handle state %u, watcher handle same %s, host thread %u; observation only",
                   (unsigned long long)enqueue_entries[i].caller, actor_request_entries[request].name,
                   (unsigned long long)enqueue_entries[i].priority,
                   enqueue_entries[i].manager_readable ? "yes" : "no",
                   enqueue_entries[i].handle_readable ? "yes" : "no", enqueue_entries[i].handle_state,
                   enqueue_entries[i].handle_same ? "yes" : "no", enqueue_entries[i].host_thread);
            observed.native_enqueue_trace_count++;
        }
        while (reference_consumed < REFERENCE_TRACE_LIMIT &&
               __atomic_load_n(&reference_entries[reference_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = reference_consumed++;
            unsigned request = reference_entries[i].request_index;
            rt_log("coop native reference event: entry main+%#llx, caller %#llx, name %s, state %u, resident slot %s, value actor %s, value resident data %s, host thread %u, publication %s, release %s, consumption %s; observation only",
                   (unsigned long long)(reference_entries[i].address - MOD_MAIN_BASE),
                   (unsigned long long)reference_entries[i].caller, actor_request_entries[request].name,
                   reference_entries[i].state,
                   !resident_record ? "unknown" : actor_request_entries[request].watcher == resident_record + 0x18ull ? "yes" : "no",
                   !reference_entries[i].value ? "unknown" : reference_entries[i].value == actor ? "same" : "different",
                   !resident_data || !reference_entries[i].value ? "unknown" : reference_entries[i].value == resident_data ? "same" : "different",
                   reference_entries[i].host_thread, reference_entries[i].publication ? "yes" : "no",
                   reference_entries[i].release ? "yes" : "no", reference_entries[i].consumption ? "yes" : "no");
            observed.native_ready_reference_trace_count++;
        }
        while (resident_bind_consumed < ACTOR_REQUEST_TRACE_LIMIT &&
               __atomic_load_n(&resident_bind_entries[resident_bind_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = resident_bind_consumed++;
            if (resident_bind_entries[i].player_manager) {
                uint64_t link = player_manager_link();
                if (resident_bind_entries[i].actor == actor && resident_bind_entries[i].record == link) {
                    rt_log("coop native player manager bind: entry main+0x14f334, caller %#llx, source actor same, metadata manager data %s, host thread %u; observation only",
                           (unsigned long long)resident_bind_entries[i].caller,
                           resident_bind_entries[i].metadata && resident_bind_entries[i].metadata == guest_pointer(link + 8ull) ? "same" : "different",
                           resident_bind_entries[i].host_thread);
                    observed.native_player_manager_bind_count++;
                }
                continue;
            }
            if (resident_bind_entries[i].actor != actor || resident_bind_entries[i].record != resident_record) continue;
            rt_log("coop native resident bind: entry main+0x14f334, caller %#llx, target local record same, source actor same, metadata resident data %s, host thread %u; observation only",
                   (unsigned long long)resident_bind_entries[i].caller,
                   resident_bind_entries[i].metadata && resident_bind_entries[i].metadata == resident_data ? "same" : "different",
                   resident_bind_entries[i].host_thread);
            observed.native_resident_bind_count++;
        }
        while (player_source_consumed < ACTOR_REQUEST_TRACE_LIMIT &&
               __atomic_load_n(&player_source_entries[player_source_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = player_source_consumed++;
            if (player_source_entries[i].actor != actor || guest_s32(actor + 0x10ull) != player_source_entries[i].actor_id) continue;
            uint64_t link = player_manager_link();
            rt_log("coop native player reference source: entry main+0x1b0614, caller %#llx, source resident record %s, actor local same, metadata manager data %s, host thread %u; observation only",
                   (unsigned long long)player_source_entries[i].caller,
                   !resident_record ? "unknown" : player_source_entries[i].source == resident_record ? "same" : "different",
                   link && guest_pointer(link + 8ull) == player_source_entries[i].metadata ? "same" : "different",
                   player_source_entries[i].host_thread);
        }
        while (lifecycle_consumed < LIFECYCLE_TRACE_LIMIT &&
               __atomic_load_n(&lifecycle_entries[lifecycle_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = lifecycle_consumed++;
            if (!matched_task_descriptor || lifecycle_entries[i].descriptor != matched_task_descriptor ||
                lifecycle_entries[i].owner_actor != actor) continue;
            rt_log("coop native lifecycle: entry main+%#llx, caller %#llx, stage %s, constructor task same, actor %s, result %u, host thread %u; observation only",
                   (unsigned long long)(lifecycle_entries[i].address - MOD_MAIN_BASE),
                   (unsigned long long)lifecycle_entries[i].caller,
                   lifecycle_stages[lifecycle_entries[i].stage],
                   !lifecycle_entries[i].actor ? "unscoped" : lifecycle_entries[i].actor == actor ? "same" : "different",
                   lifecycle_entries[i].result, lifecycle_entries[i].host_thread);
            observed.native_lifecycle_trace_count++;
        }
        while (holder_consumed < HOLDER_TRACE_LIMIT &&
               __atomic_load_n(&holder_entries[holder_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = holder_consumed++;
            if (holder_entries[i].actor == actor) {
                const char *inline_task = !matched_task_descriptor ? "unknown" :
                    holder_entries[i].holder == matched_task_descriptor + 0xf0ull ? "yes" : "no";
                rt_log("coop native holder: target %#llx, caller %#llx, x0 %#llx, x1 player same, x2 %u, host thread %u, inline task holder %s; observation only",
                       (unsigned long long)holder_entries[i].address,
                       (unsigned long long)holder_entries[i].caller,
                       (unsigned long long)holder_entries[i].holder,
                       holder_entries[i].mode, holder_entries[i].host_thread, inline_task);
                observed.native_holder_trace_count++;
            }
        }
        while (initializer_consumed < INITIALIZER_TRACE_LIMIT &&
               __atomic_load_n(&initializer_entries[initializer_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = initializer_consumed++;
            if (initializer_entries[i].actor == actor) {
                const char *inline_task = !matched_task_descriptor ? "unknown" :
                    initializer_entries[i].context == matched_task_descriptor + 0x18ull ? "yes" : "no";
                rt_log("coop native initializer: target %#llx, caller %#llx, x0 player same, x1 task+0x18 %s, host thread %u; observation only",
                       (unsigned long long)initializer_entries[i].address,
                       (unsigned long long)initializer_entries[i].caller,
                       inline_task, initializer_entries[i].host_thread);
                observed.native_initializer_trace_count++;
            }
        }
    }
    uint64_t vtable = actor ? guest_pointer(actor) : 0;
    uint64_t method = vtable ? guest_pointer(vtable + 0x200) : 0;
    if (method < MOD_MAIN_BASE || method >= MOD_MAIN_BASE + 0x3adf000ull || (method & 3)) method = 0;
    if (changed && actor && vtable >= MOD_MAIN_BASE && vtable < MOD_MAIN_BASE + 0x3adf000ull)
        rt_log("coop native vtable: player main+%#llx, generation %u; observation only",
               (unsigned long long)(vtable - MOD_MAIN_BASE), observed.sample.generation);
    if (changed && method)
        rt_log("coop native candidate: player vtable+0x200 -> main+%#llx, generation %u; observation only",
               (unsigned long long)(method - MOD_MAIN_BASE), observed.sample.generation);
    __atomic_store_n(&trace_generation, 0, __ATOMIC_RELEASE);
    __atomic_store_n(&trace_actor, actor, __ATOMIC_RELAXED);
    __atomic_store_n(&trace_actor_method, method, __ATOMIC_RELAXED);
    __atomic_store_n(&trace_generation, actor ? observed.sample.generation : 0, __ATOMIC_RELEASE);
    while (trace_consumed < 64 && __atomic_load_n(&trace_entries[trace_consumed].ready, __ATOMIC_ACQUIRE)) {
        unsigned i = trace_consumed++;
        rt_log("coop native trace: entry main+%#llx, caller %#llx, x0 %#llx, host thread %u, generation %u, kind %s; observation only",
               (unsigned long long)(trace_entries[i].address - MOD_MAIN_BASE),
               (unsigned long long)trace_entries[i].caller, (unsigned long long)trace_entries[i].argument,
               trace_entries[i].host_thread, trace_entries[i].generation, trace_kind_names[trace_entries[i].kind]);
        observed.native_trace_count++;
        observed.native_traces_by_kind[trace_entries[i].kind]++;
    }
    observed.sample.flags = actor ? COOP_SAMPLE_PLAYER | visual.flags : 0;
    memcpy(observed.sample.rotation, visual.rotation, sizeof visual.rotation);
    memcpy(observed.sample.animation, visual.animation, sizeof visual.animation);
    observed.sample.animation_frame = visual.animation_frame;
    observed.sample.scene = 0;   // A guest scene address is not a stable network scene identity.
    observed.sample.time_ns = now;
    observed.sample.yaw = yaw; observed.sample.action = (uint32_t)action;
    memcpy(observed.sample.pos, pos, sizeof pos);
    memset(observed.sample.velocity, 0, sizeof observed.sample.velocity);
    double dt = previous.time_ns ? (double)(now - previous.time_ns) / 1e9 : 0;
    if (actor && !changed && dt > .001 && dt < .25)
        for (int i = 0; i < 3; i++) {
            float v = (float)((pos[i] - previous.pos[i]) / dt);
            if (isfinite(v) && fabsf(v) <= 1000) observed.sample.velocity[i] = v;
        }
    snprintf(observed.reason, sizeof observed.reason, "%s", rt_game_version != 143 ?
             "Unsupported game version; native operations disabled" :
             "Native actor lifecycle, world update phase and pause control are not verified");
    while (command_count) {
        const CoopGuestCommand *c = &commands[command_head];
        if (c->generation != observed.sample.generation || c->expires_ns <= now) observed.commands_stale++;
        else observed.commands_rejected++;
        // No guest functions or memory stores: presentation is not a verified world mutation phase.
        command_head = (command_head + 1) % 256; command_count--;
    }
    observed.queued = command_count;
    plat_mutex_unlock(&adapter_lock);
}

void coop_adapter_snapshot(CoopAdapterSnapshot *out) {
    plat_mutex_lock(&adapter_lock); *out = observed; plat_mutex_unlock(&adapter_lock);
}

int coop_adapter_submit(const CoopGuestCommand *c) {
    if (!c || !c->session || !c->entity || !c->request_id || c->kind < COOP_COMMAND_SPAWN ||
        c->kind > COOP_COMMAND_DESPAWN) return 0;
    for (int i = 0; i < 3; i++) if (!isfinite(c->pos[i]) || fabsf(c->pos[i]) > 1000000) return 0;
    plat_mutex_lock(&adapter_lock);
    int accepted = command_count < 256;
    if (accepted) commands[(command_head + command_count++) % 256] = *c;
    observed.queued = command_count;
    plat_mutex_unlock(&adapter_lock);
    return accepted;
}
