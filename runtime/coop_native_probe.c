// TotK 1.4.3 creation experiment at a real weapon-drop producer's native call boundary.
// ABI research: arnaldolima1/totk-recomp runtime/actor_spawn.c spawn, based on MacNativeGames research,
// @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c (MIT, Copyright (c) 2026 Valiantsin Dzerakh).
// Original license: runtime/third_party/licenses/totk-recomp.txt. The experiment and guards are ours.
#include "coop_native_probe.h"
#include "coop_adapter.h"
#include "host.h"
#include "layout.h"
#include "platform/platform.h"
#include <fenv.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static unsigned armed, attempted;
static _Thread_local int inside;

// Layouts adapted from the credited actor_spawn.c CreateArg and BlackboardInit. The pointer fields are
// deliberately initialized rather than copied from a live actor or a pouch request. Static one-shot storage
// stays valid through asynchronous initialization, rejection and cleanup; this probe never reuses it.
typedef struct {
    float position[3], rotation[9], scale[3];
    uint32_t pad_3c;
    const char *name;
    uint8_t b48[8], b50[4];
    uint32_t pad_54;
    void *blackboard, *blackboard_60, *parent, *dependent, *creator, *creator_rtti, *instance_heap;
    uint8_t transform_flags, pad_91[7];
} ProbeCreateArg;
typedef struct {
    int32_t size;
    uint32_t pad;
    void *params;
    int32_t count;
    uint32_t pad2;
    uint8_t buffer[32][0xc8];
} ProbeBlackboard;
_Static_assert(sizeof(ProbeCreateArg) == 0x98, "CreateArg size");
_Static_assert(offsetof(ProbeCreateArg, blackboard) == 0x58, "CreateArg blackboard");
_Static_assert(offsetof(ProbeCreateArg, transform_flags) == 0x90, "CreateArg flags");
_Static_assert(sizeof(ProbeBlackboard) == 0x1918, "BlackboardInit<32> size");
_Static_assert(offsetof(ProbeBlackboard, params) == 8, "BlackboardInit params");
_Static_assert(offsetof(ProbeBlackboard, count) == 0x10, "BlackboardInit count");
static ProbeCreateArg owned_arg;
static ProbeBlackboard owned_bb;
static const char *owned_name = "Weapon_Sword_101";

// Written only by the diagnostic runner after copying and verifying its isolated profile.
void coop_native_probe_init(const char *profile, int timed_run, int mode) {
    if (!mode) return;
    char path[PLAT_PATH_MAX * 3];
    const char *marker = mode == COOP_NATIVE_PROBE_NPC_MOTION ? "isolated-npc-velocity-v1\n" :
                         mode == COOP_NATIVE_PROBE_NPC ? "isolated-npc-road-001-v1\n" :
                         mode == COOP_NATIVE_PROBE_CLONE ? "isolated-physics-probe-v1\n" : "isolated-physics-owned-v1\n";
    char content[64] = {0};
    if (rt_game_version != 143 || !timed_run || !profile ||
        (mode != COOP_NATIVE_PROBE_CLONE && mode != COOP_NATIVE_PROBE_OWNED &&
         mode != COOP_NATIVE_PROBE_NPC && mode != COOP_NATIVE_PROBE_NPC_MOTION)) goto denied;
    int length = snprintf(path, sizeof path, "%s/coop-native-probe.txt", profile);
    if (length < 0 || (size_t)length >= sizeof path) goto denied;
    FILE *f = fopen(path, "rb");
    if (!f) goto denied;
    size_t n = fread(content, 1, sizeof content, f);
    fclose(f);
    if (n != strlen(marker) || memcmp(content, marker, n)) goto denied;
    owned_name = mode >= COOP_NATIVE_PROBE_NPC ? "Npc_Road_001" : "Weapon_Sword_101";
    __atomic_store_n(&armed, (unsigned)mode, __ATOMIC_RELEASE);
    rt_log("coop native spawn probe: armed for one authentic weapon drop in the isolated timed profile, arguments %s",
           mode == COOP_NATIVE_PROBE_CLONE ? "borrowed" : "owned");
    return;
denied:
    rt_log("coop native spawn probe: refused; needs game 1.4.3, a timed run and the diagnostic profile marker");
}

static int read_guest(uint64_t at, void *out, size_t size) {
    return at >= 0x10000 && at < (1ull << 47) && size <= (1ull << 47) - at &&
           mem_guest_readable(at, size) && plat_mem_read(at, out, size);
}

void coop_native_probe_request(Cpu *c) {
    if (!c || inside || !__atomic_load_n(&armed, __ATOMIC_ACQUIRE) ||
        __atomic_load_n(&attempted, __ATOMIC_RELAXED) || rt_game_version != 143 ||
        c->x[30] != MOD_MAIN_BASE + 0x20a57d8ull || frame_step_world_us() < 6000000) return;
    // Match the locally observed drop path, including all three stacked arguments. Never reuse the producer's
    // watcher or copy its actor dependencies. The owned mode uses this call boundary only as a scheduling trigger.
    uint64_t manager, name_at, stack[3];
    unsigned char flags, code[28], hash[32];
    const char name[] = "Weapon_Sword_101";
    char actual[sizeof name];
    if (!read_guest(MOD_MAIN_BASE + 0x3ad7450ull, &manager, sizeof manager) || manager != c->x[0] ||
        !read_guest(manager, stack, 8) || !read_guest(c->x[1], &name_at, 8) ||
        !read_guest(name_at, actual, sizeof actual) || memcmp(actual, name, sizeof name) ||
        !mem_guest_readable(c->x[2], 0x98) || !read_guest(c->x[2] + 0x90, &flags, 1) || flags != 3 || !c->x[3] ||
        !read_guest(c->x[3], stack, 8) || c->x[4] || c->x[5] || c->x[6] || c->x[7] ||
        (c->sp & 15) || !read_guest(c->sp, stack, sizeof stack) || (stack[0] & 255) || stack[1] || stack[2] ||
        !read_guest(MOD_MAIN_BASE + 0x599670ull, code, sizeof code)) return;
    // Hash the verified request prologue rather than publishing bytes derived from the game.
    static const unsigned char expected[32] = {
        0xf8,0x23,0x0f,0xd5,0xeb,0xab,0x93,0x91,0x09,0xe4,0x71,0x48,0x55,0x34,0xa3,0x7b,
        0xbb,0xd8,0x60,0x51,0xeb,0xe1,0x80,0xd2,0x64,0x30,0x40,0x9e,0x88,0x31,0x63,0x49
    };
    rt_sha256(code, sizeof code, hash);
    if (memcmp(hash, expected, sizeof hash)) return;
    unsigned mode = __atomic_load_n(&armed, __ATOMIC_ACQUIRE);
    float origin[3];
    if (mode != COOP_NATIVE_PROBE_CLONE) {
        if (!read_guest(c->x[2], origin, sizeof origin)) return;
        for (unsigned i = 0; i < 3; i++)
            if (!isfinite(origin[i]) || fabsf(origin[i]) > 100000) return;
    }
    unsigned zero = 0;
    if (!__atomic_compare_exchange_n(&attempted, &zero, 1, 0, __ATOMIC_ACQ_REL, __ATOMIC_RELAXED)) return;
    Cpu saved = *c;
    fenv_t fp;
    if (fegetenv(&fp)) {
        rt_log("coop native spawn probe: refused; cannot preserve host floating-point environment");
        return;
    }
    inside = 1;
    uint64_t name_ref = saved.x[1], create_arg = saved.x[2];
    if (mode != COOP_NATIVE_PROBE_CLONE) {
        memset(&owned_arg, 0, sizeof owned_arg);
        memset(&owned_bb, 0, sizeof owned_bb);
        owned_arg.position[0] = origin[0] + 2;
        owned_arg.position[1] = origin[1] + 2;
        owned_arg.position[2] = origin[2];
        owned_arg.rotation[0] = owned_arg.rotation[4] = owned_arg.rotation[8] = 1;
        owned_arg.scale[0] = owned_arg.scale[1] = owned_arg.scale[2] = 1;
        owned_arg.name = "";
        owned_bb.size = 32;
        owned_bb.params = owned_bb.buffer;
        owned_arg.blackboard = &owned_bb;
        owned_arg.transform_flags = 7;
        name_ref = (uintptr_t)&owned_name;
        create_arg = (uintptr_t)&owned_arg;
        rt_log("coop native spawn owned: pos %.6f %.6f %.6f, empty blackboard, actor dependencies absent; process-lifetime request storage",
               owned_arg.position[0], owned_arg.position[1], owned_arg.position[2]);
    }
    // Execute before the intercepted function caches registers or changes SP. Its existing stack arguments are
    // zero; the native callee owns its frame below SP and synchronously copies/acquires the original argument's
    // references. A null watcher requests the native fire-and-forget path, leaving the original watcher intact.
    uint64_t queued = rt_call(c, MOD_MAIN_BASE + 0x599670ull, 8,
                             saved.x[0], name_ref, create_arg, (uint64_t)0,
                             saved.x[4], saved.x[5], saved.x[6], saved.x[7]);
    *c = saved;
    if (fesetenv(&fp)) rt_fatal("coop native spawn probe: cannot restore host floating-point environment");
    inside = 0;
    rt_log("coop native spawn probe: queued %s, name %s, original CPU restored; actor initialization and physics require separate evidence",
           queued == 1 ? "yes" : "no", owned_name);
}

// main+0x567750 consumes x0=RigidBody and x1=three floats, copies velocity into the body's change request
// and sets request flag 7 under its native lock. main+0x245030 uses this same request entry. The generated
// function, its consumers and observed body identity were inspected independently for 1.4.3.
static struct {
    uint64_t actor, body;
    uint32_t generation;
    int64_t started_us, last_us;
    unsigned calls, finished;
} npc_motion;
static unsigned npc_motion_busy;

static int probe_code_matches(uint64_t entry, const uint8_t expected[32]) {
    uint8_t bytes[28], hash[32];
    if (!read_guest(entry, bytes, sizeof bytes)) return 0;
    rt_sha256(bytes, sizeof bytes, hash);
    return !memcmp(hash, expected, sizeof hash);
}

static void npc_probe_update_locked(Cpu *c) {
    if (!c || inside || rt_game_version != 143 || npc_motion.finished ||
        __atomic_load_n(&armed, __ATOMIC_ACQUIRE) != COOP_NATIVE_PROBE_NPC_MOTION ||
        !__atomic_load_n(&attempted, __ATOMIC_ACQUIRE)) return;
    uint64_t body;
    uint32_t generation;
    int64_t observed_us, now = frame_step_world_us();
    if (!coop_adapter_npc_probe_body(c->x[0], &body, &generation, &observed_us)) return;
    if (now < observed_us + 2000000 || (npc_motion.calls && now < npc_motion.last_us + 30000)) return;
    if (npc_motion.calls && (c->x[0] != npc_motion.actor || body != npc_motion.body || generation != npc_motion.generation)) {
        npc_motion.finished = 1;
        rt_log("coop native npc velocity probe: aborted; target identity changed");
        return;
    }
    // Keep one call in reserve to stop the same live body if timing or the update budget is exceeded.
    int stop_early = npc_motion.calls >= 95 || (npc_motion.calls && now > npc_motion.last_us + 250000);
    const uint8_t velocity_hash[32] = {0x98,0x3c,0x1c,0xaf,0xee,0x3d,0xee,0x16,0x34,0xe0,0x57,0xa4,0x79,0x07,0xd9,0xcb,
        0x9e,0xf2,0x66,0x23,0x14,0x62,0xdb,0x66,0xd3,0x62,0x51,0x22,0x73,0x91,0x23,0xa9};
    const uint8_t update_hash[32] = {0x94,0x53,0x6d,0xb8,0x69,0xd0,0x79,0x8e,0x6a,0xd3,0xd9,0xf1,0xb3,0x6b,0x09,0x23,
        0x96,0xd0,0x0c,0xc7,0x31,0x4d,0xee,0x10,0x59,0x64,0x10,0xbd,0x7c,0xa5,0xa6,0x56};
    if (!probe_code_matches(MOD_MAIN_BASE + 0x567750ull, velocity_hash) ||
        !probe_code_matches(MOD_MAIN_BASE + 0x2e27b0ull, update_hash)) return;
    // Preserve native vertical motion; the experiment requests only bounded horizontal travel.
    float previous[3], velocity[3];
    if (!read_guest(body + 0xf8, previous, sizeof previous)) return;
    for (unsigned i = 0; i < 3; i++) if (!isfinite(previous[i]) || fabsf(previous[i]) > 50) return;
    // Read-only feedback distinguishes a queued request from native consumption or an overridden velocity.
    if (npc_motion.calls) {
        uint64_t request = 0;
        uint64_t body_flags = 0;
        float pending[3] = {NAN, NAN, NAN}, pos[3] = {NAN, NAN, NAN};
        uint32_t request_flags = 0;
        read_guest(body + 0x60, &request, sizeof request);
        read_guest(body + 0x68, &body_flags, sizeof body_flags);
        if (request) {
            read_guest(request + 0x44, pending, sizeof pending);
            read_guest(request + 0xd4, &request_flags, sizeof request_flags);
        }
        read_guest(body + 0xa4, &pos[0], 4); read_guest(body + 0xb4, &pos[1], 4); read_guest(body + 0xc4, &pos[2], 4);
        rt_log("coop native npc velocity feedback: step %u, cached %.6f %.6f %.6f, pending %.6f %.6f %.6f, request flags %#x, body flags %#llx, body pos %.6f %.6f %.6f; observation only",
               npc_motion.calls, previous[0], previous[1], previous[2], pending[0], pending[1], pending[2], request_flags,
               (unsigned long long)body_flags, pos[0], pos[1], pos[2]);
    }
    int64_t elapsed = npc_motion.calls ? now - npc_motion.started_us : 0;
    unsigned phase = stop_early ? 2 : elapsed < 1000000 ? 0 : elapsed < 2000000 ? 1 : 2;
    velocity[0] = phase == 0 ? 2.0f : phase == 1 ? -2.0f : 0.0f;
    velocity[1] = previous[1]; velocity[2] = 0;
    Cpu saved = *c;
    fenv_t fp;
    if (fegetenv(&fp)) return;
    if (!npc_motion.calls) {
        npc_motion.actor = c->x[0]; npc_motion.body = body; npc_motion.generation = generation; npc_motion.started_us = now;
    }
    inside = 1;
    rt_call(c, MOD_MAIN_BASE + 0x567750ull, 2, body, (uint64_t)(uintptr_t)velocity);
    *c = saved;
    if (fesetenv(&fp)) rt_fatal("coop native npc velocity probe: cannot restore host floating-point environment");
    inside = 0;
    uint64_t queued_request = 0;
    uint32_t queued_flags = 0;
    float queued_velocity[3] = {NAN, NAN, NAN};
    if (read_guest(body + 0x60, &queued_request, 8) && queued_request) {
        read_guest(queued_request + 0xd4, &queued_flags, 4);
        read_guest(queued_request + 0x44, queued_velocity, sizeof queued_velocity);
    }
    rt_log("coop native npc velocity queued: request %s, flags %#x, velocity %.6f %.6f %.6f; observation only",
           queued_request ? "present" : "absent", queued_flags, queued_velocity[0], queued_velocity[1], queued_velocity[2]);
    npc_motion.last_us = now; npc_motion.calls++;
    npc_motion.finished = phase == 2;
    if (stop_early) rt_log("coop native npc velocity probe: aborted; requested stop after update budget or continuity exceeded");
    rt_log("coop native npc velocity probe: step %u, phase %s, generation %u, world us %lld, velocity %.6f %.6f %.6f; native request, original CPU restored",
           npc_motion.calls, phase == 0 ? "forward" : phase == 1 ? "reverse" : "stop", generation,
           (long long)now, velocity[0], velocity[1], velocity[2]);
}

void coop_native_probe_npc_update(Cpu *c) {
    if (!c || inside || __atomic_load_n(&armed, __ATOMIC_ACQUIRE) != COOP_NATIVE_PROBE_NPC_MOTION) return;
    unsigned zero = 0;
    if (!__atomic_compare_exchange_n(&npc_motion_busy, &zero, 1, 0, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) return;
    npc_probe_update_locked(c);
    __atomic_store_n(&npc_motion_busy, 0, __ATOMIC_RELEASE);
}
