// TotK 1.4.3 read-only adapter. Observation is separate from unverified actor and physics operations.
#include "coop_adapter.h"
#include "coop.h"
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

// Returns the validated PlayerLink ActorBase pointer (proc) on 1.4.3, or 0 when not spawned.
// Checks both the PlayerMgr singleton (main+0x3969918) and the Scene resident-actors list
// (main+0x3add238 -> +0x1e8 -> +0x58 -> comp[13], as in runtime/frame_rate.c:player_pos).
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
                            (uint32_t)guest_s32(proc + 0x24) - 7u >= 5u) {
                            return proc;
                        }
                    }
                }
            }
        }
    }
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
    if (!guest_readable(resident + 0x20ull, 16)) return 0;
    int32_t count = guest_s32(resident + 0x20ull);
    uint64_t links = guest_pointer(resident + 0x28ull);
    if (count <= 0 || count > 64 || !guest_readable(links, (uint64_t)count * 0x70ull)) return 0;
    for (int32_t i = 0; i < count; i++) {
        uint64_t data = guest_pointer(links + (uint64_t)i * 0x70ull + 8ull);
        if (!guest_readable(data + 0x40ull, 8)) continue;
        uint64_t actor = guest_pointer(data + 0x40ull);
        if (!guest_readable(actor, 0x300)) continue;
        uint64_t name = guest_pointer(actor + 0x218ull);
        char text[7];
        if (name && plat_mem_read(name, text, sizeof text) && !memcmp(text, "Player", sizeof text) &&
            (uint32_t)guest_s32(actor + 0x24) - 7u >= 5u) return actor;
    }
    return 0;
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


// Observation and command diagnostics.
static PlatMutex adapter_lock = PLAT_MUTEX_INIT;
static CoopAdapterSnapshot observed;
static CoopGuestCommand commands[256];
static unsigned command_head, command_count;
static volatile int trace_enabled;
static uint64_t trace_actor_method, trace_actor;
static uint32_t trace_generation;
static unsigned trace_claimed, trace_consumed;
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
static struct {
    uint64_t caller, actor;
    uint32_t host_thread;
    unsigned ready;
} constructor_entries[CONSTRUCTOR_TRACE_LIMIT];

void coop_adapter_trace_enable(int enable) {
    __atomic_store_n(&trace_enabled, enable, __ATOMIC_RELEASE);
    // Bit 0 belongs to resolution discovery. Disabling co-op tracing must not disable that observer.
    if (enable) __atomic_fetch_or(&g_fnprof, 2, __ATOMIC_RELAXED);
    else __atomic_fetch_and(&g_fnprof, ~2, __ATOMIC_RELAXED);
}

void coop_adapter_function(uint64_t address, uint64_t caller, uint64_t argument) {
    if (!__atomic_load_n(&trace_enabled, __ATOMIC_RELAXED)) return;
    // The GameActor constructor associated with the observed vtable runs before presence is ready.
    // Keep its separate bounded trace until actor observation can correlate an allocated object.
    if (address == MOD_MAIN_BASE + 0x6898dcull) {
        unsigned slot = __atomic_fetch_add(&constructor_claimed, 1, __ATOMIC_RELAXED);
        if (slot < CONSTRUCTOR_TRACE_LIMIT) {
            constructor_entries[slot].caller = caller;
            constructor_entries[slot].actor = argument;
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
    uint64_t scene = 0, module = rt_game_version == 143 ? guest_pointer(MOD_MAIN_BASE + 0x3add238ull) : 0;
    if (module) scene = guest_pointer(module + 0x1e8ull);
    uint64_t now = plat_now_ns();
    plat_mutex_lock(&adapter_lock);
    CoopSample previous = observed.sample;
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
    observed.actor = actor; observed.scene_address = scene; observed.observations++;
    if (actor) {
        if (!constructor_summary_logged) {
            rt_log("coop native constructor budget: %u entries before first playable actor, limit %u; observation only",
                   __atomic_load_n(&constructor_claimed, __ATOMIC_ACQUIRE), CONSTRUCTOR_TRACE_LIMIT);
            constructor_summary_logged = 1;
        }
        while (constructor_consumed < CONSTRUCTOR_TRACE_LIMIT &&
               __atomic_load_n(&constructor_entries[constructor_consumed].ready, __ATOMIC_ACQUIRE)) {
            unsigned i = constructor_consumed++;
            if (constructor_entries[i].actor == actor) {
                rt_log("coop native constructor: entry main+0x6898dc, caller %#llx, x0 %#llx, host thread %u, observed player same; observation only",
                       (unsigned long long)constructor_entries[i].caller,
                       (unsigned long long)constructor_entries[i].actor,
                       constructor_entries[i].host_thread);
                observed.native_constructor_trace_count++;
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
    observed.sample.flags = actor ? COOP_SAMPLE_PLAYER : 0;
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
