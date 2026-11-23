// Isolated TotK 1.4.3 creation experiments at verified inventory and actor-update boundaries.
// ABI research: arnaldolima1/totk-recomp runtime/actor_spawn.c spawn, based on MacNativeGames research,
// @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c (MIT, Copyright (c) 2026 Valiantsin Dzerakh).
// Original license: runtime/third_party/licenses/totk-recomp.txt. The experiment and guards are ours.
#include "coop_native_probe.h"
#include "coop_adapter.h"
#include "coop_retirement.h"
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
// Two bounded cycles retain separate storage until process exit. Neither slot is ever reused.
static ProbeCreateArg second_arg;
static ProbeBlackboard second_bb;
static const char *owned_name = "Weapon_Sword_101";
static unsigned cycle_claim(void);
static void cycle_release(void);
static const unsigned char request_hash[32] = {
    0xf8,0x23,0x0f,0xd5,0xeb,0xab,0x93,0x91,0x09,0xe4,0x71,0x48,0x55,0x34,0xa3,0x7b,
    0xbb,0xd8,0x60,0x51,0xeb,0xe1,0x80,0xd2,0x64,0x30,0x40,0x9e,0x88,0x31,0x63,0x49
};

static void prepare_owned(ProbeCreateArg *arg,ProbeBlackboard *bb,const float origin[3]) {
    memset(arg,0,sizeof *arg); memset(bb,0,sizeof *bb);
    arg->position[0]=origin[0]+2; arg->position[1]=origin[1]+2; arg->position[2]=origin[2];
    arg->rotation[0]=arg->rotation[4]=arg->rotation[8]=1;
    arg->scale[0]=arg->scale[1]=arg->scale[2]=1;
    arg->name=""; bb->size=32; bb->params=bb->buffer;
    arg->blackboard=bb; arg->transform_flags=7;
    rt_log("coop native spawn owned: pos %.6f %.6f %.6f, empty blackboard, actor dependencies absent; process-lifetime request storage",
           arg->position[0],arg->position[1],arg->position[2]);
}

// Written only by the diagnostic runner after copying and verifying its isolated profile.
void coop_native_probe_init(const char *profile, int timed_run, int mode) {
    if (!mode) return;
    char path[PLAT_PATH_MAX * 3];
    const char *marker = mode == COOP_NATIVE_PROBE_NPC_RECONNECT ? "isolated-npc-session-reconnect-v1\n" :
                         mode == COOP_NATIVE_PROBE_NPC_SESSION ? "isolated-npc-session-create-v1\n" :
                         mode == COOP_NATIVE_PROBE_NPC_CYCLES ? "isolated-npc-two-cycles-v1\n" :
                         mode == COOP_NATIVE_PROBE_NPC_RETIREMENT ? "isolated-npc-native-retirement-v1\n" :
                         mode == COOP_NATIVE_PROBE_NPC_VISIBILITY ? "isolated-npc-native-visibility-v1\n" :
                         mode == COOP_NATIVE_PROBE_NPC_FIGURE ? "isolated-npc-body-figure-v1\n" :
                         mode == COOP_NATIVE_PROBE_NPC_PEER_MOTION ? "isolated-npc-enet-velocity-v1\n" :
                         mode == COOP_NATIVE_PROBE_NPC_CONSUMER_MOTION ? "isolated-npc-consumer-velocity-v1\n" :
                         mode == COOP_NATIVE_PROBE_NPC_MOTION ? "isolated-npc-velocity-v1\n" :
                         mode == COOP_NATIVE_PROBE_NPC ? "isolated-npc-road-001-v1\n" :
                         mode == COOP_NATIVE_PROBE_CLONE ? "isolated-physics-probe-v1\n" : "isolated-physics-owned-v1\n";
    char content[64] = {0};
    if (rt_game_version != 143 || !timed_run || !profile ||
        (mode != COOP_NATIVE_PROBE_CLONE && mode != COOP_NATIVE_PROBE_OWNED &&
         mode != COOP_NATIVE_PROBE_NPC && mode != COOP_NATIVE_PROBE_NPC_MOTION &&
         mode != COOP_NATIVE_PROBE_NPC_CONSUMER_MOTION && mode != COOP_NATIVE_PROBE_NPC_PEER_MOTION &&
         mode != COOP_NATIVE_PROBE_NPC_FIGURE && mode != COOP_NATIVE_PROBE_NPC_VISIBILITY &&
         mode != COOP_NATIVE_PROBE_NPC_RETIREMENT && mode != COOP_NATIVE_PROBE_NPC_CYCLES &&
         mode != COOP_NATIVE_PROBE_NPC_SESSION && mode != COOP_NATIVE_PROBE_NPC_RECONNECT)) goto denied;
    int length = snprintf(path, sizeof path, "%s/coop-native-probe.txt", profile);
    if (length < 0 || (size_t)length >= sizeof path) goto denied;
    FILE *f = fopen(path, "rb");
    if (!f) goto denied;
    size_t n = fread(content, 1, sizeof content, f);
    fclose(f);
    if (n != strlen(marker) || memcmp(content, marker, n)) goto denied;
    owned_name = mode >= COOP_NATIVE_PROBE_NPC ? "Npc_Road_001" : "Weapon_Sword_101";
    __atomic_store_n(&armed, (unsigned)mode, __ATOMIC_RELEASE);
    rt_log("coop native spawn probe: armed for %s in the isolated timed profile, arguments %s",
           mode==COOP_NATIVE_PROBE_NPC_RECONNECT ? "two session-driven creations" :
           mode==COOP_NATIVE_PROBE_NPC_SESSION ? "one session-driven creation" :
           mode==COOP_NATIVE_PROBE_NPC_CYCLES ? "two authentic weapon drops" : "one authentic weapon drop",
           mode == COOP_NATIVE_PROBE_CLONE ? "borrowed" : "owned");
    return;
denied:
    rt_log("coop native spawn probe: refused; needs game 1.4.3, a timed run and the diagnostic profile marker");
}

static int read_guest(uint64_t at, void *out, size_t size) {
    return at >= 0x10000 && at < (1ull << 47) && size <= (1ull << 47) - at &&
           mem_guest_readable(at, size) && plat_mem_read(at, out, size);
}

static int drop_name_matches(uint64_t at,int cycles) {
    const char expected[]="Weapon_Sword_101";
    if (!cycles) { char actual[sizeof expected]; return read_guest(at,actual,sizeof actual) && !memcmp(actual,expected,sizeof actual); }
    // The same verified inventory producer drops other weapon slots after the first item is removed.
    // This name only authenticates the trigger; the injected actor name remains Npc_Road_001.
    char name[32];
    for (unsigned i=0;i<sizeof name;i++) {
        if (!read_guest(at+i,&name[i],1)) return 0;
        if (!name[i]) return i>7 && !memcmp(name,"Weapon_",7);
        if (!((name[i]>='A' && name[i]<='Z') || (name[i]>='a' && name[i]<='z') ||
              (name[i]>='0' && name[i]<='9') || name[i]=='_')) return 0;
    }
    return 0;
}

void coop_native_probe_request(Cpu *c) {
    unsigned mode = __atomic_load_n(&armed, __ATOMIC_ACQUIRE);
    int cycles = mode == COOP_NATIVE_PROBE_NPC_CYCLES;
    if (!c || inside || !mode || mode==COOP_NATIVE_PROBE_NPC_SESSION || mode==COOP_NATIVE_PROBE_NPC_RECONNECT ||
        (__atomic_load_n(&attempted, __ATOMIC_RELAXED) && !cycles) || rt_game_version != 143 ||
        c->x[30] != MOD_MAIN_BASE + 0x20a57d8ull || frame_step_world_us() < 6000000) return;
    // Match the locally observed drop path, including all three stacked arguments. Never reuse the producer's
    // watcher or copy its actor dependencies. The owned mode uses this call boundary only as a scheduling trigger.
    uint64_t manager, name_at, stack[3];
    unsigned char flags, code[28], hash[32];
    if (!read_guest(MOD_MAIN_BASE + 0x3ad7450ull, &manager, sizeof manager) || manager != c->x[0] ||
        !read_guest(manager, stack, 8) || !read_guest(c->x[1], &name_at, 8) ||
        !drop_name_matches(name_at,cycles) ||
        !mem_guest_readable(c->x[2], 0x98) || !read_guest(c->x[2] + 0x90, &flags, 1) || flags != 3 || !c->x[3] ||
        !read_guest(c->x[3], stack, 8) || c->x[4] || c->x[5] || c->x[6] || c->x[7] ||
        (c->sp & 15) || !read_guest(c->sp, stack, sizeof stack) || (stack[0] & 255) || stack[1] || stack[2] ||
        !read_guest(MOD_MAIN_BASE + 0x599670ull, code, sizeof code)) return;
    // Hash the verified request prologue rather than publishing bytes derived from the game.
    rt_sha256(code, sizeof code, hash);
    if (memcmp(hash, request_hash, sizeof hash)) return;
    float origin[3];
    if (mode != COOP_NATIVE_PROBE_CLONE) {
        if (!read_guest(c->x[2], origin, sizeof origin)) return;
        for (unsigned i = 0; i < 3; i++)
            if (!isfinite(origin[i]) || fabsf(origin[i]) > 100000) return;
    }
    unsigned zero = 0;
    unsigned cycle=0;
    if (cycles) { if (!(cycle=cycle_claim())) return; }
    else if (!__atomic_compare_exchange_n(&attempted, &zero, 1, 0, __ATOMIC_ACQ_REL, __ATOMIC_RELAXED)) return;
    Cpu saved = *c;
    fenv_t fp;
    if (fegetenv(&fp)) {
        rt_log("coop native spawn probe: refused; cannot preserve host floating-point environment");
        if (cycles) cycle_release();
        return;
    }
    inside = 1;
    uint64_t name_ref = saved.x[1], create_arg = saved.x[2];
    if (mode != COOP_NATIVE_PROBE_CLONE) {
        ProbeCreateArg *arg=cycle==2 ? &second_arg : &owned_arg;
        ProbeBlackboard *bb=cycle==2 ? &second_bb : &owned_bb;
        prepare_owned(arg,bb,origin);
        name_ref = (uintptr_t)&owned_name;
        create_arg = (uintptr_t)arg;
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
    if (cycles) cycle_release();
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
    int64_t last_consumer_us;
    float target_velocity[3];
    unsigned calls, consumer_calls, finished, stop_pending;
} npc_motion;
static unsigned npc_motion_busy;
static struct {
    uint64_t session, player, received_ns, sender_ns;
    uint32_t generation;
    float horizontal[2];
    unsigned bound, valid, revoked, notified;
} npc_peer;
static struct {
    uint64_t publication_ns, controller;
    uint32_t generation;
    int32_t actor_id;
    unsigned calls, hidden, done;
} npc_visibility;
static CoopRetirement npc_retirement;
static int32_t cycle_actor_id=-1;
// A single copied join candidate. The observer never invokes native code or puts guest pointers here.
typedef struct {
    uint64_t session,player,received_ns,sender_ns;
    uint32_t local_generation,remote_generation;
    unsigned present,issued,revoked,cleaned;
} NpcSession;
static NpcSession npc_session,npc_next_session;
static uint64_t npc_previous_session;

static int session_mode(void) {
    unsigned mode=__atomic_load_n(&armed,__ATOMIC_ACQUIRE);
    return mode==COOP_NATIVE_PROBE_NPC_SESSION || mode==COOP_NATIVE_PROBE_NPC_RECONNECT;
}

static void session_candidate(NpcSession *candidate,const CoopNetSnapshot *peer,uint32_t generation) {
    int same=candidate->session==peer->session && candidate->player==peer->peer_player &&
        candidate->local_generation==generation && candidate->remote_generation==peer->remote.generation;
    if (same && (peer->remote.time_ns<=candidate->sender_ns || peer->state_received_ns<=candidate->received_ns)) return;
    candidate->session=peer->session; candidate->player=peer->peer_player;
    candidate->local_generation=generation; candidate->remote_generation=peer->remote.generation;
    candidate->received_ns=peer->state_received_ns; candidate->sender_ns=peer->remote.time_ns;
    candidate->present=1;
}

static void session_offer_locked(const CoopNetSnapshot *peer,uint32_t generation,uint64_t now) {
    int valid=peer->negotiated && peer->has_remote && peer->session && peer->peer_player && generation &&
        peer->remote.generation && (peer->remote.flags&COOP_SAMPLE_PLAYER) && peer->remote.time_ns &&
        peer->state_received_ns && now>=peer->state_received_ns && now-peer->state_received_ns<=200000000ull;
    if (npc_session.issued) {
        if (!valid || peer->session!=npc_session.session || peer->peer_player!=npc_session.player ||
            generation!=npc_session.local_generation || peer->remote.generation!=npc_session.remote_generation) {
            // Missing/stale motion is handled by the lease; only ownership changes/disconnection revoke a binding.
            if (!peer->negotiated || peer->session!=npc_session.session || peer->peer_player!=npc_session.player ||
                generation!=npc_session.local_generation ||
                (peer->has_remote && peer->remote.generation!=npc_session.remote_generation)) {
                npc_session.revoked=1; npc_peer.valid=0; npc_peer.revoked=1;
            }
        }
        if (__atomic_load_n(&armed,__ATOMIC_RELAXED)==COOP_NATIVE_PROBE_NPC_RECONNECT && npc_session.revoked &&
            __atomic_load_n(&attempted,__ATOMIC_RELAXED)==1) {
            if (valid && generation==npc_session.local_generation && peer->session!=npc_session.session)
                session_candidate(&npc_next_session,peer,generation);
            else npc_next_session.present=0;
        }
        return;
    }
    if (!valid) { npc_session.present=0; return; }
    // Worker retransmissions of one old sender sample cannot keep a pending creation alive either.
    session_candidate(&npc_session,peer,generation);
}

static unsigned cycle_start_locked(unsigned count,int previous) {
    rt_log("coop native npc cycle begin: cycle %u, world us %lld, prior actor id %d, prior retired %u; distinct retained request slot",
        count+1,(long long)frame_step_world_us(),count ? npc_retirement.actor_id : -1,previous);
    memset(&npc_motion,0,sizeof npc_motion); memset(&npc_peer,0,sizeof npc_peer);
    memset(&npc_visibility,0,sizeof npc_visibility); memset(&npc_retirement,0,sizeof npc_retirement);
    cycle_actor_id=-1;
    __atomic_store_n(&attempted,count+1,__ATOMIC_RELEASE);
    return count+1;
}
static unsigned cycle_claim(void) {
    unsigned zero=0;
    if (!__atomic_compare_exchange_n(&npc_motion_busy,&zero,1,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)) return 0;
    unsigned count=__atomic_load_n(&attempted,__ATOMIC_RELAXED);
    int previous=count==1 && npc_retirement.accepted &&
        coop_adapter_npc_probe_retired(npc_retirement.actor,npc_retirement.generation,npc_retirement.actor_id);
    if (count>=2 || (count && !previous)) { cycle_release(); return 0; }
    return cycle_start_locked(count,previous);
}
static void cycle_release(void) { __atomic_store_n(&npc_motion_busy,0,__ATOMIC_RELEASE); }
static const uint8_t npc_velocity_hash[32] = {0x98,0x3c,0x1c,0xaf,0xee,0x3d,0xee,0x16,0x34,0xe0,0x57,0xa4,0x79,0x07,0xd9,0xcb,
    0x9e,0xf2,0x66,0x23,0x14,0x62,0xdb,0x66,0xd3,0x62,0x51,0x22,0x73,0x91,0x23,0xa9};
static const uint8_t npc_update_hash[32] = {0x94,0x53,0x6d,0xb8,0x69,0xd0,0x79,0x8e,0x6a,0xd3,0xd9,0xf1,0xb3,0x6b,0x09,0x23,
    0x96,0xd0,0x0c,0xc7,0x31,0x4d,0xee,0x10,0x59,0x64,0x10,0xbd,0x7c,0xa5,0xa6,0x56};

static int npc_peer_offer_locked(const CoopNetSnapshot *peer, uint32_t generation, uint64_t now) {
    if (!npc_motion.body || npc_motion.finished || npc_peer.revoked) return 0;
    if (generation != npc_motion.generation || (npc_peer.bound && (!peer->negotiated ||
        peer->session != npc_peer.session || peer->peer_player != npc_peer.player ||
        (peer->has_remote && peer->remote.generation != npc_peer.generation)))) {
        npc_peer.valid = 0; npc_peer.revoked = 1;
        return 0;
    }
    int notify = peer->negotiated && !npc_peer.notified;
    if (notify) npc_peer.notified = 1;
    if (!peer->negotiated || !peer->has_remote || !peer->session || !peer->peer_player ||
        !(peer->remote.flags & COOP_SAMPLE_PLAYER) || !peer->remote.generation || !peer->remote.time_ns ||
        !peer->state_received_ns || peer->state_received_ns > now) {
        npc_peer.valid = 0;
        return notify;
    }
    for (unsigned i = 0; i < 3; i++) if (!isfinite(peer->remote.velocity[i])) {
        npc_peer.valid = 0;
        return notify;
    }
    float x = peer->remote.velocity[0], z = peer->remote.velocity[2];
    if (x*x + z*z > 4.0001f) { npc_peer.valid = 0; return notify; }
    // A retransmitted state with the same sender timestamp must not renew the receive-time lease.
    // Sender clocks are never compared with our clock; only their ordering is used.
    if (peer->state_received_ns <= npc_peer.received_ns || peer->remote.time_ns <= npc_peer.sender_ns) return notify;
    if (!npc_peer.bound)
        rt_log("coop native npc peer binding: session %llu, player %llu, remote generation %u, local generation %u; diagnostic velocity only",
               (unsigned long long)peer->session, (unsigned long long)peer->peer_player, peer->remote.generation, generation);
    npc_peer.session = peer->session; npc_peer.player = peer->peer_player;
    npc_peer.generation = peer->remote.generation; npc_peer.bound = npc_peer.valid = 1;
    npc_peer.received_ns = peer->state_received_ns; npc_peer.sender_ns = peer->remote.time_ns;
    npc_peer.horizontal[0] = x; npc_peer.horizontal[1] = z;
    return notify;
}

int coop_native_probe_peer_enabled(void) {
    unsigned mode=__atomic_load_n(&armed, __ATOMIC_ACQUIRE);
    return mode==COOP_NATIVE_PROBE_NPC_PEER_MOTION || mode==COOP_NATIVE_PROBE_NPC_FIGURE ||
           mode==COOP_NATIVE_PROBE_NPC_VISIBILITY || mode==COOP_NATIVE_PROBE_NPC_RETIREMENT ||
           session_mode();
}

int coop_native_probe_figure_enabled(void) {
    unsigned mode=__atomic_load_n(&armed, __ATOMIC_ACQUIRE);
    return mode==COOP_NATIVE_PROBE_NPC_FIGURE || mode==COOP_NATIVE_PROBE_NPC_VISIBILITY ||
           mode==COOP_NATIVE_PROBE_NPC_RETIREMENT || session_mode();
}

static int native_visibility_enabled(void) {
    unsigned mode=__atomic_load_n(&armed,__ATOMIC_ACQUIRE);
    return mode==COOP_NATIVE_PROBE_NPC_VISIBILITY || mode==COOP_NATIVE_PROBE_NPC_RETIREMENT ||
           session_mode();
}

void coop_native_probe_figure_publish(uint32_t generation, int32_t actor_id, uint64_t sample_ns) {
    if (!native_visibility_enabled()) return;
    unsigned zero=0;
    if (!__atomic_compare_exchange_n(&npc_motion_busy,&zero,1,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)) return;
    if (__atomic_load_n(&armed,__ATOMIC_RELAXED)==COOP_NATIVE_PROBE_NPC_RECONNECT && sample_ns &&
        (!npc_motion.calls || generation!=npc_motion.generation || actor_id!=cycle_actor_id)) {
        cycle_release(); return; // a delayed render acknowledgement cannot restore/hide another native actor
    }
    npc_visibility.publication_ns=sample_ns;
    npc_visibility.generation=generation; npc_visibility.actor_id=actor_id;
    __atomic_store_n(&npc_motion_busy,0,__ATOMIC_RELEASE);
}

int coop_native_probe_peer_matches(uint64_t session, uint64_t player, uint32_t remote_generation,
                                   uint32_t local_generation) {
    if (!coop_native_probe_figure_enabled()) return 0;
    unsigned zero=0;
    if (!__atomic_compare_exchange_n(&npc_motion_busy,&zero,1,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)) return -1;
    int matches=!npc_retirement.attempted && npc_peer.bound && !npc_peer.revoked && session && player && remote_generation &&
        npc_peer.session==session && npc_peer.player==player && npc_peer.generation==remote_generation &&
        npc_motion.generation==local_generation;
    __atomic_store_n(&npc_motion_busy,0,__ATOMIC_RELEASE);
    return matches;
}

int coop_native_probe_peer_offer(const CoopNetSnapshot *peer, uint32_t generation, uint64_t now) {
    if (!peer || !coop_native_probe_peer_enabled()) return 0;
    unsigned zero = 0;
    if (!__atomic_compare_exchange_n(&npc_motion_busy, &zero, 1, 0, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) return 0;
    if (__atomic_load_n(&armed,__ATOMIC_RELAXED)==COOP_NATIVE_PROBE_NPC_RECONNECT &&
        npc_previous_session && peer->session==npc_previous_session) { cycle_release(); return 0; }
    if (session_mode())
        session_offer_locked(peer,generation,now);
    int notify = npc_peer_offer_locked(peer, generation, now);
    __atomic_store_n(&npc_motion_busy, 0, __ATOMIC_RELEASE);
    return notify;
}

static const char *npc_peer_velocity(uint64_t now, float velocity[3]) {
    velocity[0] = velocity[2] = 0;
    if (npc_motion.finished) return "finished";
    if (npc_peer.revoked) return "revoked";
    if (!npc_peer.valid) return "waiting";
    if (now < npc_peer.received_ns || now - npc_peer.received_ns > 200000000ull) return "expired";
    velocity[0] = npc_peer.horizontal[0]; velocity[2] = npc_peer.horizontal[1];
    return "fresh";
}

static int probe_code_matches(uint64_t entry, const uint8_t expected[32]) {
    uint8_t bytes[28], hash[32];
    if (!read_guest(entry, bytes, sizeof bytes)) return 0;
    rt_sha256(bytes, sizeof bytes, hash);
    return !memcmp(hash, expected, sizeof hash);
}

static int visibility_code_matches(uint64_t entry, size_t size, const uint8_t expected[32]) {
    uint8_t bytes[0xb4], hash[32];
    if (size>sizeof bytes || !read_guest(entry,bytes,size)) return 0;
    rt_sha256(bytes,size,hash);
    return !memcmp(hash,expected,sizeof hash);
}

static void session_create_locked(Cpu *c) {
    if (!session_mode() || frame_step_world_us()<6000000) return;
    unsigned count=__atomic_load_n(&attempted,__ATOMIC_RELAXED);
    int reconnect=__atomic_load_n(&armed,__ATOMIC_RELAXED)==COOP_NATIVE_PROBE_NPC_RECONNECT;
    if (reconnect && npc_session.issued && npc_session.revoked && !npc_session.cleaned && npc_retirement.accepted &&
        coop_adapter_npc_probe_retired(npc_retirement.actor,npc_retirement.generation,npc_retirement.actor_id)) {
        npc_session.cleaned=1;
        rt_log("coop native session retired: cycle %u, session %llu, generation %u, actor id %d, world us %lld; correlated cleanup and allocator handoff",
            count,(unsigned long long)npc_session.session,npc_retirement.generation,npc_retirement.actor_id,(long long)frame_step_world_us());
    }
    if (count>=(reconnect ? 2u : 1u)) return;
    NpcSession *candidate=&npc_session;
    if (count) {
        if (!reconnect || !npc_session.cleaned || !npc_session.revoked) return;
        candidate=&npc_next_session;
        if (candidate->local_generation!=npc_session.local_generation || candidate->session==npc_session.session) return;
    }
    if (!candidate->present || candidate->issued || candidate->revoked) return;
    uint64_t now=plat_now_ns();
    if (now<candidate->received_ns || now-candidate->received_ns>200000000ull) return;
    float position[3]; uint32_t generation;
    if (!coop_adapter_local_actor(c->x[0],&generation,position) || generation!=candidate->local_generation) return;
    unsigned worker=0; uint32_t tag;
    if (coop_actor_worker_context(c,c->x[0],&worker,&tag)) return;
    uint64_t vtable,method,manager;
    if (!read_guest(c->x[0],&vtable,8) || vtable!=MOD_MAIN_BASE+0x3633078ull ||
        !read_guest(vtable+0x180,&method,8) || method!=MOD_MAIN_BASE+0x2e27b0ull ||
        !read_guest(MOD_MAIN_BASE+0x3ad7450ull,&manager,8) || !mem_guest_readable(manager,0xe2)) return;
    // The original worker has installed its current actor, before the virtual update's prologue/locks.
    // Bind that complete dispatch and the TLS getter, not only a matching return address.
    static const uint8_t dispatch_hash[32]={0x57,0x6b,0xe9,0x8a,0x75,0xa2,0xaf,0x64,0x38,0xc6,0x1c,0xa4,0xac,0x2a,0x01,0x0d,
        0xe6,0xd8,0xcc,0x68,0xb6,0x2c,0x54,0xb5,0x47,0xc6,0xaf,0xea,0xe9,0xeb,0x57,0x31};
    static const uint8_t tls_hash[32]={0xaf,0xbb,0x8e,0xce,0x9b,0x05,0x50,0x20,0x43,0x7c,0x5a,0xbe,0x71,0x07,0xf9,0xba,
        0xd1,0x0c,0xe6,0x12,0xe3,0xb4,0x03,0xaf,0xbc,0xdc,0x14,0xc4,0x36,0x2e,0x8a,0x86};
    if (!probe_code_matches(MOD_MAIN_BASE+0x599670ull,request_hash) ||
        !probe_code_matches(MOD_MAIN_BASE+0x2e27b0ull,npc_update_hash) ||
        !visibility_code_matches(MOD_MAIN_BASE+0x2f1554ull,0xb4,dispatch_hash) ||
        !visibility_code_matches(MOD_SDK_BASE+0x143c60ull,20,tls_hash)) return;
    // AAPCS64 has no red zone. Reserve a private aligned outgoing-argument area below the current SP,
    // inside its mapped writable Stack region, retaining 64 KiB of committed native call headroom.
    RtMemoryInfo region;
    if ((c->sp&15) || c->sp<0x20000 || mem_query(c->sp-0x10020,&region) || region.state!=0xb ||
        region.perm!=3 || region.base>c->sp-0x10020 || region.size>UINT64_MAX-region.base ||
        c->sp>region.base+region.size || !mem_guest_readable(c->sp-0x10020,0x10020)) return;
    if (!coop_adapter_local_actor(c->x[0],&generation,position) || generation!=candidate->local_generation ||
        coop_actor_worker_context(c,c->x[0],&worker,&tag)) return;
    Cpu saved=*c; fenv_t fp;
    if (fegetenv(&fp)) return;
    uint8_t stack_saved[32]; memcpy(stack_saved,(const void *)(uintptr_t)(c->sp-32),sizeof stack_saved);
    if (reconnect) {
        if (count) { npc_previous_session=npc_session.session; npc_session=*candidate; memset(&npc_next_session,0,sizeof npc_next_session); }
        cycle_start_locked(count,count!=0);
    } else __atomic_store_n(&attempted,1,__ATOMIC_RELEASE);
    npc_session.issued=1;
    ProbeCreateArg *arg=count ? &second_arg : &owned_arg;
    ProbeBlackboard *bb=count ? &second_bb : &owned_bb;
    prepare_owned(arg,bb,position);
    c->sp-=32; memset((void *)(uintptr_t)c->sp,0,32);
    inside=1;
    uint64_t queued=rt_call(c,MOD_MAIN_BASE+0x599670ull,8,manager,(uint64_t)(uintptr_t)&owned_name,
        (uint64_t)(uintptr_t)arg,(uint64_t)0,(uint64_t)0,(uint64_t)0,(uint64_t)0,(uint64_t)0);
    memcpy((void *)(uintptr_t)(saved.sp-32),stack_saved,sizeof stack_saved); *c=saved;
    if (fesetenv(&fp)) rt_fatal("coop native session creation: cannot restore host floating-point environment");
    inside=0;
    rt_log("coop native session creation: session %llu, player %llu, local generation %u, remote generation %u, world us %lld, worker %u, queued %u; local actor update, owned stack arguments, original CPU restored",
        (unsigned long long)npc_session.session,(unsigned long long)npc_session.player,generation,npc_session.remote_generation,
        (long long)frame_step_world_us(),worker,queued==1);
    rt_log("coop native spawn probe: queued %s, name %s, original CPU restored; actor initialization and physics require separate evidence",
        queued==1 ? "yes" : "no",owned_name);
}

static void npc_visibility_update_locked(Cpu *c) {
    if (!native_visibility_enabled() ||
        npc_visibility.done || npc_visibility.calls>=2 || !npc_motion.actor || c->x[0]!=npc_motion.actor) return;
    uint64_t now=plat_now_ns();
    int wanted=npc_peer.bound && !npc_peer.revoked && npc_visibility.publication_ns &&
        now>=npc_visibility.publication_ns && now-npc_visibility.publication_ns<=250000000ull &&
        npc_visibility.generation==npc_motion.generation && !npc_motion.finished;
    if (!npc_visibility.hidden && !wanted) return;
    uint64_t controller; uint32_t generation;
    if (!coop_adapter_npc_probe_model(npc_motion.actor,&controller,&generation) || generation!=npc_motion.generation ||
        (npc_visibility.controller && controller!=npc_visibility.controller)) {
        if (npc_visibility.hidden) {
            npc_visibility.done=1;
            rt_log("coop native model visibility: aborted; controller/body identity changed, no stale restore");
        }
        return;
    }
    int32_t id; uint8_t visible;
    if (!read_guest(npc_motion.actor+0x10,&id,sizeof id) ||
        !read_guest(controller+0x9c,&visible,sizeof visible) || visible>1) return;
    if (wanted && id!=npc_visibility.actor_id) wanted=0;
    if (!npc_visibility.hidden && !wanted) return;
    if ((!npc_visibility.hidden && !visible) || (npc_visibility.hidden && visible)) {
        npc_visibility.done=1;
        rt_log("coop native model visibility: aborted; original visibility changed, no ownership takeover");
        return;
    }
    if (npc_visibility.hidden && wanted) return;
    // OneShotSetOnlyModelVisible calls this exact setter with the controller returned by main+0x1b9ce0.
    // It changes only the model visibility byte/dirty request. Body motion uses its separate native API.
    static const uint8_t setter_hash[32]={0x57,0x68,0x56,0xdc,0xf0,0x7a,0x2c,0xc0,0x6f,0x32,0xc5,0x55,0x49,0x23,0xd3,0xb8,
        0x41,0xf0,0xf9,0x12,0x41,0x5e,0x30,0x89,0xec,0xea,0xd2,0xeb,0x00,0x79,0x38,0x9a};
    static const uint8_t getter_hash[32]={0xa4,0x0b,0x1d,0xc1,0x46,0xb2,0x83,0x7e,0x9d,0x5d,0xd9,0x20,0x11,0x27,0x01,0x3c,
        0x89,0x77,0xc8,0xb3,0x79,0x03,0x53,0x4f,0x41,0x89,0x97,0xd1,0x05,0xe4,0x6f,0x69};
    if (!probe_code_matches(MOD_MAIN_BASE+0x2e27b0ull,npc_update_hash) ||
        !visibility_code_matches(MOD_MAIN_BASE+0x1b87b50ull,36,setter_hash) ||
        !visibility_code_matches(MOD_MAIN_BASE+0x1b9ce0ull,24,getter_hash)) return;
    Cpu saved=*c; fenv_t fp;
    if (fegetenv(&fp)) return;
    unsigned target=wanted ? 0 : 1;
    inside=1;
    rt_call(c,MOD_MAIN_BASE+0x1b87b50ull,2,controller,(uint64_t)target);
    *c=saved;
    if (fesetenv(&fp)) rt_fatal("coop native model visibility: cannot restore host floating-point environment");
    inside=0;
    uint8_t after=255;
    uint64_t rechecked; uint32_t same_generation;
    int matched=coop_adapter_npc_probe_model(npc_motion.actor,&rechecked,&same_generation) && rechecked==controller &&
        same_generation==generation && read_guest(controller+0x9c,&after,1) && after==target;
    npc_visibility.calls++; npc_visibility.controller=controller;
    npc_visibility.hidden=target==0; npc_visibility.done=target!=0 || !matched;
    rt_log("coop native model visibility: call %u, phase %s, generation %u, actor id %d, world us %lld, before %u, requested %u, after %u, owner matched %u; native API, original CPU restored",
        npc_visibility.calls,target ? "restore" : "hide",generation,id,(long long)frame_step_world_us(),
        visible,target,after,matched);
}

static void npc_probe_update_locked(Cpu *c) {
    unsigned mode = __atomic_load_n(&armed, __ATOMIC_ACQUIRE);
    int peer_mode = coop_native_probe_peer_enabled();
    if (!c || inside || rt_game_version != 143 || npc_motion.finished ||
        (mode != COOP_NATIVE_PROBE_NPC_MOTION && mode != COOP_NATIVE_PROBE_NPC_CONSUMER_MOTION &&
         mode != COOP_NATIVE_PROBE_NPC_CYCLES && !peer_mode) ||
        !__atomic_load_n(&attempted, __ATOMIC_ACQUIRE)) return;
    uint64_t body;
    uint32_t generation;
    int64_t observed_us, now = frame_step_world_us();
    if (!coop_adapter_npc_probe_body(c->x[0], &body, &generation, &observed_us)) return;
    if (session_mode() && generation!=npc_session.local_generation) return;
    if (now < observed_us + 2000000 || (npc_motion.calls && now < npc_motion.last_us + 30000)) return;
    if (npc_motion.calls && (c->x[0] != npc_motion.actor || body != npc_motion.body || generation != npc_motion.generation)) {
        npc_motion.finished = 1;
        rt_log("coop native npc velocity probe: aborted; target identity changed");
        return;
    }
    // Keep one call in reserve to stop the same live body if timing or the update budget is exceeded.
    int stop_early = npc_motion.calls >= (peer_mode ? 255u : 95u) || (npc_motion.calls && now > npc_motion.last_us + 250000);
    if (!probe_code_matches(MOD_MAIN_BASE + 0x567750ull, npc_velocity_hash) ||
        !probe_code_matches(MOD_MAIN_BASE + 0x2e27b0ull, npc_update_hash)) return;
    if ((mode==COOP_NATIVE_PROBE_NPC_CYCLES || mode==COOP_NATIVE_PROBE_NPC_RECONNECT) && !npc_motion.calls &&
        (!read_guest(c->x[0]+0x10,&cycle_actor_id,sizeof cycle_actor_id) || cycle_actor_id==-1)) return;
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
    const char *peer_reason = NULL;
    if (peer_mode) {
        phase = stop_early || elapsed >= 8000000 ? 2 : 3;
        peer_reason = npc_peer_velocity(plat_now_ns(), velocity);
        if (phase == 2) { velocity[0] = velocity[2] = 0; peer_reason = "finished"; }
    }
    Cpu saved = *c;
    fenv_t fp;
    if (fegetenv(&fp)) return;
    if (!npc_motion.calls) {
        npc_motion.actor = c->x[0]; npc_motion.body = body; npc_motion.generation = generation; npc_motion.started_us = now;
        if (mode==COOP_NATIVE_PROBE_NPC_CYCLES || mode==COOP_NATIVE_PROBE_NPC_RECONNECT)
            rt_log("coop native npc cycle binding: cycle %u, generation %u, actor id %d, world us %lld; scoped live body",
                __atomic_load_n(&attempted,__ATOMIC_RELAXED),generation,cycle_actor_id,(long long)now);
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
    memcpy(npc_motion.target_velocity, velocity, sizeof velocity);
    npc_motion.finished = phase == 2;
    if (peer_mode) npc_motion.stop_pending = npc_motion.finished;
    if (stop_early) rt_log("coop native npc velocity probe: aborted; requested stop after update budget or continuity exceeded");
    if (peer_mode)
        rt_log("coop native npc peer velocity: step %u, reason %s, generation %u, world us %lld, velocity %.6f %.6f %.6f; leased native request, original CPU restored",
               npc_motion.calls, peer_reason, generation, (long long)now, velocity[0], velocity[1], velocity[2]);
    else rt_log("coop native npc velocity probe: step %u, phase %s, generation %u, world us %lld, velocity %.6f %.6f %.6f; native request, original CPU restored",
           npc_motion.calls, phase == 0 ? "forward" : phase == 1 ? "reverse" : "stop", generation,
           (long long)now, velocity[0], velocity[1], velocity[2]);
}

void coop_native_probe_npc_update(Cpu *c) {
    if (!c || inside || (__atomic_load_n(&armed, __ATOMIC_ACQUIRE) != COOP_NATIVE_PROBE_NPC_MOTION &&
                        __atomic_load_n(&armed, __ATOMIC_ACQUIRE) != COOP_NATIVE_PROBE_NPC_CONSUMER_MOTION &&
                        __atomic_load_n(&armed, __ATOMIC_ACQUIRE) != COOP_NATIVE_PROBE_NPC_CYCLES &&
                        !coop_native_probe_peer_enabled())) return;
    unsigned zero = 0;
    if (!__atomic_compare_exchange_n(&npc_motion_busy, &zero, 1, 0, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) return;
    session_create_locked(c);
    npc_visibility_update_locked(c);
    unsigned mode=__atomic_load_n(&armed,__ATOMIC_ACQUIRE);
    int retire=(mode==COOP_NATIVE_PROBE_NPC_RETIREMENT || session_mode()) && npc_visibility.done && !npc_visibility.hidden &&
        npc_visibility.calls==2 && frame_step_world_us()>=npc_motion.started_us+9000000;
    if (session_mode() && !npc_visibility.calls && !npc_visibility.hidden)
        retire=npc_motion.calls && frame_step_world_us()>=npc_motion.started_us+9000000;
    if (mode==COOP_NATIVE_PROBE_NPC_RECONNECT && !npc_session.revoked) retire=0;
    if (mode==COOP_NATIVE_PROBE_NPC_CYCLES)
        retire=npc_motion.calls && frame_step_world_us()>=npc_motion.started_us+3000000;
    if (npc_motion.finished && retire) {
        if (!npc_retirement.actor) npc_retirement=(CoopRetirement){.actor=npc_motion.actor,.body=npc_motion.body,
            .generation=npc_motion.generation};
        coop_retirement_try(c,&npc_retirement);
    }
    npc_probe_update_locked(c);
    __atomic_store_n(&npc_motion_busy, 0, __ATOMIC_RELEASE);
}

static void npc_probe_consume_locked(Cpu *c) {
    if (npc_retirement.attempted) return;
    int peer_mode = coop_native_probe_peer_enabled();
    if (!npc_motion.calls || (npc_motion.finished && (!peer_mode || !npc_motion.stop_pending)) ||
        npc_motion.consumer_calls >= (peer_mode ? 256u : 96u) ||
        c->x[30] != MOD_MAIN_BASE + 0x1824f8ull || c->x[1] != npc_motion.body) return;
    int64_t now = frame_step_world_us(), observed_us;
    if (now < npc_motion.last_us || (!peer_mode && now > npc_motion.last_us + 100000) || now <= npc_motion.last_consumer_us) return;
    uint64_t body, pending; uint32_t generation, flags;
    if (!coop_adapter_npc_probe_body(npc_motion.actor, &body, &generation, &observed_us) ||
        body != npc_motion.body || generation != npc_motion.generation ||
        !read_guest(body + 0x60, &pending, 8) || pending != c->x[0] ||
        !read_guest(pending + 0xd4, &flags, 4) || !(flags & 0x80)) return;
    const uint8_t consumer_hash[32] = {0x9b,0x0d,0xc2,0xe4,0x50,0xcb,0xba,0x22,0x9b,0xa6,0xfc,0x43,0x13,0x76,0x6f,0x35,
        0xc5,0xd6,0x1f,0x9c,0x97,0x53,0x9c,0x5f,0x96,0x87,0xa0,0x59,0x78,0x98,0x66,0xed};
    const uint8_t parent_hash[32] = {0xd3,0x2d,0x66,0x8a,0x58,0xff,0x87,0x78,0xb8,0x11,0xd6,0x46,0x5a,0x3c,0x33,0x9c,
        0x67,0x4b,0xe4,0x66,0x29,0x25,0xc6,0x68,0x65,0x91,0x4a,0x62,0xf6,0x2f,0x0c,0xec};
    if (!probe_code_matches(MOD_MAIN_BASE + 0x567750ull, npc_velocity_hash) ||
        !probe_code_matches(MOD_MAIN_BASE + 0x182eb0ull, consumer_hash) ||
        !probe_code_matches(MOD_MAIN_BASE + 0x182410ull, parent_hash)) return;
    float velocity[3];
    memcpy(velocity, npc_motion.target_velocity, sizeof velocity);
    if (peer_mode) {
        // Preserve this consumer's native vertical request, including gravity/ground response. Cached body
        // velocity precedes native preparation and feeding it back can accumulate an artificial ascent.
        if (!read_guest(pending + 0x44, velocity, sizeof velocity)) return;
        for (unsigned i = 0; i < 3; i++) if (!isfinite(velocity[i]) || fabsf(velocity[i]) > 50) return;
        npc_peer_velocity(plat_now_ns(), velocity);
        if (now > npc_motion.last_us + 100000 || now >= npc_motion.started_us + 8000000 || npc_motion.consumer_calls >= 255) {
            velocity[0] = velocity[2] = 0;
            // Duration alone leaves the actor-update hook its final stop/report opportunity. A missing
            // actor update or exhausted consumer budget terminates the experiment without rebinding.
            if (now > npc_motion.last_us + 100000 || npc_motion.consumer_calls >= 255) {
                npc_motion.finished = 1;
                rt_log("coop native npc peer consumer stop: reason %s, generation %u, world us %lld; requested zero horizontal velocity",
                       npc_motion.consumer_calls >= 255 ? "budget" : "actor-update-stale", generation, (long long)now);
            }
        }
    }
    // main+0x182410 has popped this exact live request but has not acquired body+0x78 here. Its normal
    // consumer call precedes the native request cleanup and lock. Reapply via the verified request API,
    // never by changing the consumer's arguments or directly storing into the request/body.
    Cpu saved = *c;
    fenv_t fp;
    if (fegetenv(&fp)) return;
    inside = 1;
    rt_call(c, MOD_MAIN_BASE + 0x567750ull, 2, body, (uint64_t)(uintptr_t)velocity);
    *c = saved;
    if (fesetenv(&fp)) rt_fatal("coop native npc velocity consumer: cannot restore host floating-point environment");
    inside = 0;
    npc_motion.consumer_calls++; npc_motion.last_consumer_us = now;
    if (peer_mode && npc_motion.finished) npc_motion.stop_pending = 0;
    rt_log("coop native npc velocity consumer reapply: correction %u, generation %u, world us %lld; same live pending request, original CPU restored",
           npc_motion.consumer_calls, generation, (long long)now);
}

void coop_native_probe_npc_consume(Cpu *c) {
    if (!c || inside || rt_game_version != 143 ||
        (__atomic_load_n(&armed, __ATOMIC_ACQUIRE) != COOP_NATIVE_PROBE_NPC_CONSUMER_MOTION &&
         __atomic_load_n(&armed, __ATOMIC_ACQUIRE) != COOP_NATIVE_PROBE_NPC_CYCLES &&
         !coop_native_probe_peer_enabled())) return;
    unsigned zero = 0;
    if (!__atomic_compare_exchange_n(&npc_motion_busy, &zero, 1, 0, __ATOMIC_ACQUIRE, __ATOMIC_RELAXED)) return;
    npc_probe_consume_locked(c);
    __atomic_store_n(&npc_motion_busy, 0, __ATOMIC_RELEASE);
}
