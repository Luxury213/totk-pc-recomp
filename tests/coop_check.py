"""Exercise the co-op guest observer, visual bot and bounded command rejection without game data.

Usage: python tests/coop_check.py --cc C:/msys64/ucrt64/bin/clang.exe --deps <dependency include directory>
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include <assert.h>
#include "coop_adapter.c"
#include "coop_interp.c"
#include "coop.c"

const int rt_game_version = 143;
volatile int g_fnprof;
GfxStats gfx_counters;
static unsigned config_version = 1;
static const char *mode = "bot";
static uint64_t now = 1000000000;
static float camera[28];
static uint64_t mgr;
static unsigned char root[0x38], unit[0x50], actor[0x400], other_actor[0x400];
static unsigned char vtable[0x220];
static unsigned char scene_module[0x1f0], scene[0x60], alternate_scene[0x60], components[14*8];
static unsigned char residents[0x30], resident_links[0xe0], resident_data[0x48], other_data[0x48];
static char actor_name[] = "Player";
static uint64_t request_name_ref;
static unsigned char request_arg[0x98];
static int fail_reads;
static unsigned guest_reads;
static int64_t world_us = -1;
static unsigned char probe_actor[0x400], probe_data[0x50], probe_descriptor[0x170], probe_context[0x18];
static char probe_name[] = "Weapon_Sword_Test";
static unsigned char request_stack[0x18], probe_owner[0x40], probe_heap[8], probe_heap_vtable[0x40];
static unsigned char probe_resource[0xe0];
static unsigned char player_source_ref[0x18];
static unsigned char visual_model[0xd0], visual_controller[0x120], visual_player[0x88], visual_clip[0x10];
static unsigned char visual_name[COOP_ANIMATION_MAX+2];
static int switch_visual_clip;

unsigned cfg_version(void) { return config_version; }
const char *cfg_value(const char *key) {
    return !strcmp(key, "TOTK_COOP_MODE") ? mode : "127.0.0.1";
}
int cfg_int(const char *key) { (void)key; return 7777; }
int cfg_bool(const char *key) { return !strcmp(key, "TOTK_COOP_TRACE_GUEST"); }
void plat_mutex_lock(PlatMutex *m) { (void)m; }
void plat_mutex_unlock(PlatMutex *m) { (void)m; }
uint64_t plat_now_ns(void) { return now; }
int64_t frame_step_world_us(void) { return world_us; }
uint32_t plat_thread_id(void) { return 17; }
void rt_log(const char *fmt, ...) { (void)fmt; }
const uint8_t *vk_usnap_bytes(uint64_t at, uint64_t n) {
    (void)at; assert(n == sizeof camera); return (const uint8_t *)camera;
}
static int in_range(uint64_t p, uint64_t n, const void *base, uint64_t size) {
    return n <= size && p >= (uintptr_t)base && p - (uintptr_t)base <= size - n;
}
int mem_guest_readable(uint64_t p, uint64_t n) {
    if (p == MOD_MAIN_BASE + 0x3969918ull && n <= 8) return 1;
    if (p == MOD_MAIN_BASE + 0x3add238ull && n <= 8) return 1;
    if (in_range(p,n,(const void *)(uintptr_t)(MOD_MAIN_BASE+0x100),sizeof vtable)) return 1;
    return in_range(p,n,&mgr,sizeof mgr) || in_range(p,n,root,sizeof root) ||
           in_range(p,n,unit,sizeof unit) || in_range(p,n,actor,sizeof actor) ||
           in_range(p,n,other_actor,sizeof other_actor) ||
           in_range(p,n,scene_module,sizeof scene_module) || in_range(p,n,scene,sizeof scene) ||
           in_range(p,n,alternate_scene,sizeof alternate_scene) ||
           in_range(p,n,components,sizeof components) || in_range(p,n,residents,sizeof residents) ||
           in_range(p,n,resident_links,sizeof resident_links) ||
           in_range(p,n,resident_data,sizeof resident_data) ||
           in_range(p,n,other_data,sizeof other_data) ||
           in_range(p,n,actor_name,sizeof actor_name) ||
           in_range(p,n,&request_name_ref,sizeof request_name_ref) ||
           in_range(p,n,request_arg,sizeof request_arg) ||
           in_range(p,n,probe_actor,sizeof probe_actor) || in_range(p,n,probe_data,sizeof probe_data) ||
           in_range(p,n,probe_descriptor,sizeof probe_descriptor) || in_range(p,n,probe_context,sizeof probe_context) ||
           in_range(p,n,probe_name,sizeof probe_name) || in_range(p,n,request_stack,sizeof request_stack) ||
           in_range(p,n,probe_owner,sizeof probe_owner) || in_range(p,n,probe_heap,sizeof probe_heap) ||
           in_range(p,n,probe_heap_vtable,sizeof probe_heap_vtable) || in_range(p,n,player_source_ref,sizeof player_source_ref) ||
           in_range(p,n,visual_model,sizeof visual_model) || in_range(p,n,visual_controller,sizeof visual_controller) ||
           in_range(p,n,visual_player,sizeof visual_player) || in_range(p,n,visual_clip,sizeof visual_clip) ||
           in_range(p,n,visual_name,sizeof visual_name);
}
int plat_mem_read(uint64_t p, void *out, size_t n) {
    guest_reads++;
    if (switch_visual_clip && p==(uintptr_t)visual_name+2) {
        memset(visual_player+0x80,0,8); switch_visual_clip=0;
    }
    if (fail_reads || !mem_guest_readable(p,n)) return 0;
    if (p == MOD_MAIN_BASE + 0x3969918ull) {
        uint64_t slot = (uintptr_t)&mgr; memcpy(out,&slot,n);
    } else if (p == MOD_MAIN_BASE + 0x3add238ull) {
        uint64_t slot = (uintptr_t)scene_module; memcpy(out,&slot,n);
    } else if (in_range(p,n,(const void *)(uintptr_t)(MOD_MAIN_BASE+0x100),sizeof vtable)) {
        memcpy(out,vtable+(p-(MOD_MAIN_BASE+0x100)),n);
    } else memcpy(out,(const void *)(uintptr_t)p,n);
    return 1;
}
static void ptr(void *p, uint64_t v) { memcpy(p,&v,8); }
static void scalar(void *p, float v) { memcpy(p,&v,4); }
static void player(float x, float y, float z) {
    mgr = (uintptr_t)root;
    ptr(root + 0x28,(uintptr_t)unit);
    int32_t id = 42; memcpy(root + 0x30,&id,4); memcpy(unit + 0x48,&id,4);
    memcpy(actor+0x10,&id,4);
    ptr(unit + 0x40,(uintptr_t)actor);
    ptr(actor,MOD_MAIN_BASE + 0x100);
    ptr(actor + 0x218,(uintptr_t)actor_name);
    ptr(vtable + 0x200,MOD_MAIN_BASE + 0x1000);
    ptr(scene_module + 0x1e8,(uintptr_t)scene);
    int32_t count = 14, two = 2;
    memcpy(scene + 0x50,&count,4);
    ptr(scene + 0x58,(uintptr_t)components);
    ptr(components + 13*8,(uintptr_t)residents);
    ptr(residents,MOD_MAIN_BASE + 0x500);
    memcpy(residents + 0x20,&two,4);
    ptr(residents + 0x28,(uintptr_t)resident_links);
    ptr(resident_links,MOD_MAIN_BASE + 0x600);
    ptr(resident_links + 8,(uintptr_t)other_data);
    ptr(resident_links + 0x70,MOD_MAIN_BASE + 0x600);
    ptr(resident_links + 0x78,(uintptr_t)resident_data);
    ptr(other_actor,MOD_MAIN_BASE + 0x100);
    ptr(other_actor + 0x218,(uintptr_t)actor_name);
    ptr(other_data + 0x40,(uintptr_t)other_actor);
    ptr(resident_data + 0x40,(uintptr_t)actor);
    scalar(actor + 0x2b4,x); scalar(actor + 0x2b8,y); scalar(actor + 0x2bc,z);
    scalar(actor + 0x2e0,1);
}
static CoopSnapshot tick(void) {
    CoopSnapshot s; now += 16666667; coop_guest_observe(NULL); coop_tick(1280,720,&s); return s;
}

CoopNet *coop_net_create(void) { return NULL; }
void coop_net_configure(CoopNet *n, const CoopNetConfig *c) { (void)n; (void)c; }
void coop_net_publish(CoopNet *n, const CoopSample *s) { (void)n; (void)s; }
void coop_net_snapshot(CoopNet *n, CoopNetSnapshot *s) { (void)n; memset(s,0,sizeof *s); }
int coop_net_notice(CoopNet *n, const char *s) { (void)n; (void)s; return 0; }
int coop_net_player_id(const char *s, uint64_t *id) { (void)s; *id=42; return 1; }
void rt_sha256(const void *p, size_t n, uint8_t out[32]) { (void)p; (void)n; memset(out,0,32); }
const RtFileHash rt_exefs_sha256[] = {{"main","synthetic"}};
const int rt_exefs_sha256_count = 1;
const RtConfig *rt_config(void) { static const RtConfig c = {.profile="build/tests/profile"}; return &c; }

static void visual_capture_checks(void) {
    memset(actor,0,sizeof actor);
    player(100,20,30);
    float identity[9]={1,0,0,0,1,0,0,0,1}; memcpy(actor+0x2c0,identity,sizeof identity);
    ptr(actor+0x238,(uintptr_t)visual_model); ptr(visual_model+0xc8,(uintptr_t)visual_controller);
    ptr(visual_controller+0x118,(uintptr_t)visual_player); ptr(visual_player+0x80,(uintptr_t)visual_clip);
    memcpy(visual_clip,"FSKA",4); ptr(visual_clip+8,(uintptr_t)visual_name);
    uint16_t length=14; memcpy(visual_name,&length,2); memcpy(visual_name+2,"Synthetic_Walk",15);
    scalar(visual_player+0x58,12.5f);
    CoopSample v={0}; read_player_visual((uintptr_t)actor,&v);
    assert(v.flags==(COOP_SAMPLE_ROTATION|COOP_SAMPLE_ANIMATION) && v.rotation[3]==1);
    assert(!strcmp(v.animation,"Synthetic_Walk") && v.animation_frame==12.5f);
    unsigned char before[sizeof actor]; memcpy(before,actor,sizeof actor);
    float turns[][9]={{1,0,0,0,-1,0,0,0,-1},{-1,0,0,0,1,0,0,0,-1},{-1,0,0,0,-1,0,0,0,1}};
    for(unsigned axis=0;axis<3;axis++) {
        memcpy(actor+0x2c0,turns[axis],sizeof turns[axis]); v=(CoopSample){0};
        read_player_visual((uintptr_t)actor,&v); assert(v.rotation[axis]==1 && v.rotation[3]==0);
    }
    memcpy(actor+0x2c0,identity,sizeof identity); scalar(actor+0x2c0,NAN);
    v=(CoopSample){0}; read_player_visual((uintptr_t)actor,&v); assert(v.flags==COOP_SAMPLE_ANIMATION);
    scalar(actor+0x2c0,-1); // a reflected transform cannot be a quaternion
    v=(CoopSample){0}; read_player_visual((uintptr_t)actor,&v); assert(v.flags==COOP_SAMPLE_ANIMATION);
    memcpy(actor+0x2c0,identity,sizeof identity);
    scalar(visual_player+0x58,NAN);
    v=(CoopSample){0}; read_player_visual((uintptr_t)actor,&v); assert(v.flags==COOP_SAMPLE_ROTATION);
    scalar(visual_player+0x58,12.5f); visual_name[2]='/';
    v=(CoopSample){0}; read_player_visual((uintptr_t)actor,&v); assert(v.flags==COOP_SAMPLE_ROTATION);
    visual_name[2]='S'; switch_visual_clip=1;
    v=(CoopSample){0}; read_player_visual((uintptr_t)actor,&v); assert(v.flags==COOP_SAMPLE_ROTATION);
    ptr(visual_player+0x80,(uintptr_t)visual_clip);
    coop_adapter_observe(NULL); CoopAdapterSnapshot snapshot; coop_adapter_snapshot(&snapshot);
    assert(snapshot.sample.flags & COOP_SAMPLE_ANIMATION);
    assert(!strcmp(snapshot.sample.animation,"Synthetic_Walk"));
    assert(!memcmp(before,actor,sizeof actor)); // capture never writes actor state
    ptr(actor+0x238,0); coop_adapter_observe(NULL); coop_adapter_snapshot(&snapshot);
    assert(!(snapshot.sample.flags & COOP_SAMPLE_ANIMATION) && !snapshot.sample.animation[0]);
    assert(snapshot.sample.animation_frame==0);
    fail_reads=1; coop_adapter_observe(NULL); coop_adapter_snapshot(&snapshot); fail_reads=0;
    assert(!snapshot.sample.flags && !snapshot.sample.animation[0] && snapshot.sample.animation_frame==0);
    for(int i=0;i<4;i++) assert(snapshot.sample.rotation[i]==0);
    memset(&observed,0,sizeof observed); memset(actor,0,sizeof actor); mgr=0;
}

int main(void) {
    g_fnprof=1; coop_adapter_trace_enable(1); assert(g_fnprof==3);
    coop_adapter_trace_enable(0); assert(g_fnprof==1); g_fnprof=0;
    assert(coop_active());
    camera[0] = camera[5] = camera[10] = 1;
    camera[12] = camera[17] = camera[22] = camera[27] = 1;
    coop_capture_camera(1);
    float replay_camera[28]; memcpy(replay_camera,camera,sizeof replay_camera);
    replay_camera[12]=2;
    gfx_counters.frames++;
    coop_capture_camera_values(replay_camera);
    assert(C.vp[0]==2 && camera[12]==1); // consume replay-local values without changing the guest snapshot
    replay_camera[12]=NAN;
    gfx_counters.frames++;
    coop_capture_camera_values(replay_camera);
    assert(C.vp[0]==2); // reject incomplete replay state without losing the last valid camera
    coop_capture_camera(1);
    assert(C.vp[0]==1);
    coop_adapter_trace_enable(1);
    Cpu request_cpu = {0};
    request_name_ref = (uintptr_t)actor_name;
    request_arg[0x90] = 7;
    request_cpu.x[0] = (uintptr_t)actor;
    request_cpu.x[1] = (uintptr_t)&request_name_ref;
    request_cpu.x[2] = (uintptr_t)request_arg;
    request_cpu.x[3] = (uintptr_t)(resident_links + 0x70 + 0x18);
    request_cpu.x[4] = 1;
    request_cpu.x[30] = MOD_MAIN_BASE+0x2348;
    Cpu request_before = request_cpu;
    request_cpu.x[1] = 0;
    coop_adapter_actor_request(&request_cpu);
    assert(actor_request_total==1 && !actor_request_claimed);
    request_cpu = request_before;
    coop_adapter_actor_request(&request_cpu);
    assert(!memcmp(&request_cpu,&request_before,sizeof request_cpu));
    assert(actor_request_total==2 && actor_request_claimed==1 &&
           actor_request_entries[0].arg_readable && actor_request_entries[0].transform_flags==7 &&
           actor_request_entries[0].watcher_readable && actor_request_entries[0].priority==1);
    ptr(request_arg + 0x10,request_cpu.x[3]);
    Cpu context_cpu = request_cpu;
    context_cpu.x[0] = (uintptr_t)actor + 0x18;
    context_cpu.x[1] = (uintptr_t)request_arg;
    coop_adapter_request_context(&context_cpu); // unrelated caller must not be associated
    assert(!request_context_claimed);
    context_cpu.x[30] = MOD_MAIN_BASE+0x599a90;
    Cpu context_before = context_cpu;
    coop_adapter_request_context(&context_cpu);
    coop_adapter_request_context(&context_cpu); // context copy is associated with only the active request
    assert(!memcmp(&context_cpu,&context_before,sizeof context_cpu));
    assert(request_context_claimed==1 && request_context_entries[0].descriptor==(uintptr_t)actor);
    ptr(resident_links + 0x88,(uintptr_t)(request_arg + 0x30));
    ptr(request_arg + 0x30,2);
    ptr(request_arg + 0x38,(uintptr_t)resident_data);
    ptr(actor + 0x98,(uintptr_t)(request_arg + 0x30));
    Cpu enqueue_cpu = {.x = {(uintptr_t)residents,(uintptr_t)actor,1}};
    coop_adapter_request_enqueue(&enqueue_cpu);
    assert(!enqueue_claimed); // only the inspected request's queue call is scoped
    enqueue_cpu.x[30] = MOD_MAIN_BASE+0x599cc0;
    Cpu enqueue_before = enqueue_cpu;
    coop_adapter_request_enqueue(&enqueue_cpu);
    assert(!memcmp(&enqueue_before,&enqueue_cpu,sizeof enqueue_cpu));
    coop_adapter_request_enqueue(&enqueue_cpu); // descriptor reuse cannot replay a consumed association
    assert(enqueue_claimed==1 && enqueue_entries[0].handle_same &&
           enqueue_entries[0].handle_state==2 && enqueue_entries[0].priority==1);
    coop_adapter_function(MOD_MAIN_BASE+0x2bb7a70,MOD_MAIN_BASE+0x54cf00,(uintptr_t)(request_arg+0x40));
    assert(!reference_claimed); // a pending reference must not appear ready
    ptr(request_arg + 0x30,3);
    ptr(request_arg + 0x38,(uintptr_t)actor);
    unsigned char reference_bytes[sizeof request_arg]; memcpy(reference_bytes,request_arg,sizeof request_arg);
    coop_adapter_function(MOD_MAIN_BASE+0x97df04,MOD_MAIN_BASE+0x2300,0);
    assert(!reference_claimed); // an unrelated slot cannot resolve a captured request
    coop_adapter_function(MOD_MAIN_BASE+0x2bb7a70,0,(uintptr_t)(request_arg+0x40));
    assert(!reference_claimed); // another unlock is not the observed publication site
    coop_adapter_function(MOD_MAIN_BASE+0x2bb7a70,MOD_MAIN_BASE+0x54cf00,(uintptr_t)(request_arg+0x40));
    coop_adapter_function(MOD_MAIN_BASE+0x2bb7a70,MOD_MAIN_BASE+0x54cf00,(uintptr_t)(request_arg+0x40));
    coop_adapter_function(MOD_MAIN_BASE+0x5559a0,MOD_MAIN_BASE+0x2300,(uintptr_t)(request_arg+0x30));
    coop_adapter_function(MOD_MAIN_BASE+0x97df04,MOD_MAIN_BASE+0x2300,request_cpu.x[3]);
    assert(reference_claimed==2 && reference_entries[0].value==(uintptr_t)actor && reference_entries[0].publication);
    assert(reference_entries[1].release && reference_entries[1].value==(uintptr_t)actor);
    coop_adapter_function(MOD_MAIN_BASE+0x50d6bc,MOD_MAIN_BASE+0xea5d28,(uintptr_t)(request_arg+0x30));
    coop_adapter_function(MOD_MAIN_BASE+0x50d6bc,MOD_MAIN_BASE+0xea5d28,(uintptr_t)(request_arg+0x30));
    coop_adapter_function(MOD_MAIN_BASE+0x5559a0,MOD_MAIN_BASE+0x2300,(uintptr_t)(request_arg+0x30));
    assert(reference_claimed==3 && reference_entries[2].consumption);
    assert(!memcmp(reference_bytes,request_arg,sizeof request_arg));
    ptr(actor + 0x1a8,(uintptr_t)resident_data);
    Cpu bind_cpu = {.x = {(uintptr_t)(resident_links+0x70),(uintptr_t)actor,0}};
    coop_adapter_actor_bind(&bind_cpu);
    assert(!resident_bind_claimed);
    bind_cpu.x[30] = MOD_MAIN_BASE+0xea5d70;
    Cpu bind_before = bind_cpu;
    coop_adapter_actor_bind(&bind_cpu);
    assert(!memcmp(&bind_cpu,&bind_before,sizeof bind_cpu));
    assert(resident_bind_claimed==1 && resident_bind_entries[0].metadata==(uintptr_t)resident_data);
    coop_adapter_function(MOD_MAIN_BASE+0xd30cf8,MOD_MAIN_BASE+0x2300,(uintptr_t)actor);
    assert(player_pipeline_claimed==1 && player_pipeline_entries[0].receiver_readable);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x2340,0,(uintptr_t)actor,0);
    coop_adapter_function(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x2340,77);
    coop_adapter_function(MOD_MAIN_BASE+0x3d40f0,MOD_MAIN_BASE+0x3d3e44,77);
    coop_adapter_function(MOD_MAIN_BASE+0x689894,MOD_MAIN_BASE+0x3d4114,77);
    coop_adapter_function(MOD_MAIN_BASE+0x6898dc,MOD_MAIN_BASE+0x6898cc,(uintptr_t)actor);
    coop_adapter_function(MOD_MAIN_BASE+0xc9a5a4,MOD_MAIN_BASE+0x2468,(uintptr_t)residents);
    assert(constructor_entries[0].factory_caller==MOD_MAIN_BASE+0x3d4114);
    assert(constructor_entries[0].request_caller==MOD_MAIN_BASE+0x3d3e44);
    assert(constructor_entries[0].pipeline_caller==MOD_MAIN_BASE+0x2340);
    assert(constructor_entries[0].task_descriptor==(uintptr_t)actor);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x1000,MOD_MAIN_BASE+0x3d4150,(uintptr_t)actor+0xf0,(uintptr_t)actor,1);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x20d530,MOD_MAIN_BASE+0x3d4264,(uintptr_t)actor,(uintptr_t)actor+0x18,0);
    coop_adapter_function(MOD_MAIN_BASE+0x6898dc,77,(uintptr_t)other_actor); // unrelated nested allocation
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x1000,MOD_MAIN_BASE+0x3d4488,(uintptr_t)actor,1,(uintptr_t)actor+0x18);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x1000,MOD_MAIN_BASE+0x3d3e88,(uintptr_t)actor+0xf0,0,0);
    ptr(actor + 0x160,(uintptr_t)residents);
    ptr(residents,MOD_MAIN_BASE+0x100);
    ptr(vtable + 0x38,MOD_MAIN_BASE+0x1000);
    coop_adapter_function(MOD_MAIN_BASE+0x3d3edc,MOD_MAIN_BASE+0x3d3e90,(uintptr_t)actor+0x18);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x1000,99,(uintptr_t)residents,(uintptr_t)actor,0);
    assert(lifecycle_claimed==4 && lifecycle_entries[3].stage==6);
    coop_adapter_function(MOD_MAIN_BASE+0x167e20,99,(uintptr_t)actor);
    assert(!pipeline_descriptor);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x1000,99,(uintptr_t)residents,(uintptr_t)actor,0);
    assert(lifecycle_claimed==4); // a repeated allocator dispatch cannot consume a stale task identity
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x1000,MOD_MAIN_BASE+0x3d4198,77,1234,0);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x20d530,MOD_MAIN_BASE+0x3d4264,1234,77,0);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x2340,0,99,0);
    coop_adapter_function(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x2344,77);
    coop_adapter_function(MOD_MAIN_BASE+0x3d40f0,MOD_MAIN_BASE+0x3d3e44,77);
    coop_adapter_function(MOD_MAIN_BASE+0x689894,MOD_MAIN_BASE+0x3d4114,77);
    coop_adapter_function(MOD_MAIN_BASE+0x6898dc,MOD_MAIN_BASE+0x6898cc,1234);
    assert(!constructor_entries[1].task_descriptor);
    // Reuse the same descriptor for another actor. Its cleanup must not be attributed to the local player.
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x2340,0,(uintptr_t)actor,0);
    coop_adapter_function(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x2340,77);
    coop_adapter_function(MOD_MAIN_BASE+0x3d40f0,MOD_MAIN_BASE+0x3d3e44,77);
    coop_adapter_function(MOD_MAIN_BASE+0x689894,MOD_MAIN_BASE+0x3d4114,77);
    coop_adapter_function(MOD_MAIN_BASE+0x6898dc,MOD_MAIN_BASE+0x6898cc,(uintptr_t)other_actor);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x1000,MOD_MAIN_BASE+0x3d4488,(uintptr_t)other_actor,1,(uintptr_t)actor+0x18);
    coop_adapter_function(MOD_MAIN_BASE+0x3d3edc,MOD_MAIN_BASE+0x3d3e90,(uintptr_t)actor+0x18);
    for(int i=0;i<100;i++) coop_adapter_function(MOD_MAIN_BASE+0xa11af0,99,77);
    CoopSnapshot s = tick();
    CoopAdapterSnapshot title; coop_adapter_snapshot(&title);
    assert(!title.native_trace_count && !title.native_constructor_trace_count);
    assert(s.has_camera && !s.has_local_pos && !s.connected && !s.has_peer_pos);
    player(0,144,0); s = tick(); assert(!s.has_local_pos); // title actor
    player(-686,144,839); s = tick();
    assert(s.has_local_pos && s.has_peer_pos && s.connected && fabsf(s.peer_dist - 4.5f) < .01f);
    coop_adapter_snapshot(&title);
    assert(title.native_constructor_trace_count==1 && title.native_holder_trace_count==1 &&
           title.native_initializer_trace_count==1 &&
           title.native_actor_request_trace_count==1 &&
           title.native_actor_request_resident_match_count==1 &&
           title.native_request_task_match_count==1 &&
           title.native_lifecycle_trace_count==4 &&
           title.native_ready_reference_trace_count==3 &&
           title.native_resident_bind_count==1 &&
           title.native_resident_reference_count==1 &&
           title.native_enqueue_trace_count==1 &&
           title.native_player_pipeline_trace_count==1 &&
           title.native_resident_match && title.native_resident_component_vtable_count==1 &&
           title.native_resident_init_trace_count==1 && title.native_resident_record_vtable_count==1);
    assert(matched_task_descriptor==(uintptr_t)actor && holder_entries[0].holder==matched_task_descriptor+0xf0);
    ptr(actor + 0x1a8,(uintptr_t)unit);
    bind_cpu.x[0] = (uintptr_t)(root + 0x20);
    bind_cpu.x[30] = MOD_MAIN_BASE+0x2550;
    bind_before = bind_cpu;
    coop_adapter_actor_bind(&bind_cpu);
    coop_adapter_observe(NULL); coop_adapter_snapshot(&title);
    assert(!memcmp(&bind_cpu,&bind_before,sizeof bind_cpu));
    assert(title.native_player_manager_bind_count==1 && title.native_resident_bind_count==1);
    ptr(player_source_ref+8,(uintptr_t)unit);
    int32_t source_id = 43;
    memcpy(player_source_ref+0x10,&source_id,4);
    Cpu source_cpu = {.x = {(uintptr_t)actor,(uintptr_t)player_source_ref}};
    source_cpu.x[30] = MOD_MAIN_BASE+0x2600;
    coop_adapter_player_reference_source(&source_cpu);
    assert(!player_source_claimed); // a copy into another reference cannot claim the player-manager destination
    source_cpu.x[0] = (uintptr_t)(root+0x20);
    coop_adapter_player_reference_source(&source_cpu);
    assert(!player_source_claimed); // a stale source ID cannot identify the manager's actor
    source_id = 42; memcpy(player_source_ref+0x10,&source_id,4);
    Cpu source_before = source_cpu;
    unsigned char root_before[sizeof root]; memcpy(root_before,root,sizeof root);
    coop_adapter_player_reference_source(&source_cpu);
    assert(player_source_claimed==1 && player_source_entries[0].actor==(uintptr_t)actor);
    assert(!memcmp(&source_cpu,&source_before,sizeof source_cpu) && !memcmp(root_before,root,sizeof root));
    coop_adapter_trace_enable(1);
    for(int i=0;i<100;i++) coop_adapter_function(MOD_MAIN_BASE+0xa11af0,99,77);
    for(int i=0;i<100;i++) coop_adapter_function(MOD_MAIN_BASE+0xa0f3f0,99,77);
    // Common physics entries must leave room for the observed player's own method.
    for(int i=0;i<100;i++) coop_adapter_function(MOD_MAIN_BASE+0x1000,99,123);
    coop_adapter_observe(NULL); coop_adapter_snapshot(&title);
    assert(title.native_trace_count==32 && !title.native_traces_by_kind[0]);
    for(int i=0;i<100;i++) coop_adapter_function(MOD_MAIN_BASE+0x1000,99,(uintptr_t)actor);
    coop_adapter_observe(NULL); coop_adapter_snapshot(&title);
    assert(title.native_trace_count==64 && title.native_traces_by_kind[0]==32 &&
           title.native_traces_by_kind[1]==16 && title.native_traces_by_kind[2]==16);
    unsigned prior_continuity = continuity_count;
    teardown_observe_player((uintptr_t)actor,title.sample.generation+1);
    teardown_observe_player((uintptr_t)actor,title.sample.generation+1);
    assert(continuity_count==prior_continuity+1); // the same identity in another scene is not a new actor
    Cpu removal_cpu = {.x = {(uintptr_t)other_actor,2}}, removal_before;
    removal_cpu.x[30] = MOD_MAIN_BASE+0x2500;
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x63baa8,&removal_cpu);
    assert(!teardown_claimed); // another Player-named actor cannot acquire the local teardown scope
    removal_cpu.x[0] = (uintptr_t)actor;
    int32_t changed_id = 43, local_id = 42;
    memcpy(unit+0x48,&changed_id,4);
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x63baa8,&removal_cpu);
    assert(!teardown_claimed); // the same pooled addresses with another metadata ID are a different actor
    memcpy(unit+0x48,&local_id,4);
    coop_adapter_trace_enable(0);
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x63baa8,&removal_cpu);
    assert(!teardown_claimed);
    coop_adapter_trace_enable(1);
    removal_before = removal_cpu;
    unsigned char teardown_bytes[sizeof actor]; memcpy(teardown_bytes,actor,sizeof actor);
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x63baa8,&removal_cpu);
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x63baa8,&removal_cpu);
    assert(teardown_claimed==1 && teardown_entries[0].reason==2 && !teardown_entries[0].pending);
    assert(!memcmp(&removal_cpu,&removal_before,sizeof removal_cpu));
    removal_cpu.x[1] = (uintptr_t)actor;
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x3d45e0,&removal_cpu);
    assert(teardown_claimed==1); // an unrelated queue caller is not a removal handoff
    removal_cpu.x[30] = MOD_MAIN_BASE+0x63bc40;
    removal_before = removal_cpu;
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x3d45e0,&removal_cpu);
    assert(teardown_claimed==2 && teardown_entries[1].stage==1);
    assert(!memcmp(&removal_cpu,&removal_before,sizeof removal_cpu));
    mgr = 0; memset(residents+0x20,0,4);
    coop_adapter_observe(NULL); // the native cleanup may arrive after PlayerMgr and the resident list disappear
    removal_cpu.x[0] = (uintptr_t)actor;
    removal_cpu.x[30] = MOD_MAIN_BASE+0x2550;
    removal_before = removal_cpu;
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0xa4a194,&removal_cpu);
    assert(teardown_claimed==3 && teardown_entries[2].generation==teardown_entries[0].generation);
    assert(!memcmp(&removal_cpu,&removal_before,sizeof removal_cpu));
    assert(!memcmp(teardown_bytes,actor,sizeof actor));
    unsigned reads_before_retired = guest_reads;
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0xa4a194,&removal_cpu);
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x63baa8,&removal_cpu);
    assert(teardown_claimed==3 && guest_reads==reads_before_retired); // no dereference after cleanup entry
    coop_adapter_observe(NULL); coop_adapter_snapshot(&title);
    assert(title.native_teardown_trace_count==3);
    player(-686,144,839);
    memcpy(unit+0x48,&changed_id,4); memcpy(root+0x30,&changed_id,4);
    coop_adapter_observe(NULL);
    removal_cpu.x[1] = 1;
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x63baa8,&removal_cpu);
    assert(teardown_claimed==4 && teardown_target_count==2); // a new metadata generation gets a new scope
    player(-686,144,839);
    coop_adapter_observe(NULL);
    coop_adapter_trace_enable(0);
    Cpu guest, preserved; memset(&guest,0x5a,sizeof guest); preserved=guest;
    coop_guest_observe(&guest); assert(!memcmp(&guest,&preserved,sizeof guest));
    assert(!s.packets_tx && !s.packets_rx); // local bot does not invent UDP traffic
    unsigned char original[sizeof actor]; memcpy(original,actor,sizeof actor);
    uint32_t events = C.world_syncs;
    coop_teleport_to_partner(); s = tick();
    assert(!memcmp(original,actor,sizeof actor) && C.world_syncs == events);
    assert(s.local_pos[0] == -686 && strstr(s.event_banner,"no disponible"));
    coop_toggle_bot_mode(); float fixed = C.peer_pos[0];
    player(-666,144,839); s = tick(); assert(s.peer_pos[0] == fixed && s.peer_speed == 0);
    coop_toggle_bot_mode(); s = tick(); assert(s.peer_speed > 0 && s.peer_pos[0] > fixed);
    coop_toggle_bot_mode();
    player(1000,200,1000); s = tick(); assert(fabsf(s.peer_dist - 4.5f) < .01f);
    mgr = 0; memset(residents + 0x20,0,4);
    s = tick(); assert(!s.has_local_pos && !s.has_peer_pos && !s.connected);
    player(1000,200,1000); s = tick(); assert(s.has_peer_pos);
    fail_reads = 1; s = tick(); assert(!s.has_local_pos && !s.has_peer_pos); fail_reads = 0;
    s = tick(); assert(s.has_local_pos);
    CoopAdapterSnapshot a; coop_adapter_snapshot(&a);
    assert(!(coop_adapter_capabilities() & COOP_CAP_NATIVE_ACTOR));
    CoopGuestCommand c = {.session=1,.entity=2,.request_id=3,.expires_ns=now+1000000000,
                          .generation=a.sample.generation,.kind=COOP_COMMAND_SPAWN};
    for (int i=0;i<256;i++) assert(coop_adapter_submit(&c));
    assert(!coop_adapter_submit(&c));
    memcpy(original,actor,sizeof actor); coop_adapter_observe(NULL);
    coop_adapter_snapshot(&a); assert(a.commands_rejected==256 && !a.queued);
    assert(!memcmp(original,actor,sizeof actor));
    c.expires_ns=now; assert(coop_adapter_submit(&c)); coop_adapter_observe(NULL);
    coop_adapter_snapshot(&a); assert(a.commands_stale==1);
    memcpy(alternate_scene,scene,sizeof scene);
    ptr(scene_module + 0x1e8,(uintptr_t)alternate_scene);
    coop_adapter_observe(NULL);
    assert(matched_task_scene==(uintptr_t)alternate_scene && !matched_task_descriptor);
    coop_adapter_trace_enable(1);
    request_name_ref = (uintptr_t)probe_name;
    Cpu probe_request = {.x = {(uintptr_t)actor,(uintptr_t)&request_name_ref,(uintptr_t)request_arg,0,1}};
    probe_request.x[30] = RT_RET_HOST;
    probe_request.sp = (uintptr_t)request_stack;
    probe_request.x[5] = 1; probe_request.x[7] = 2;
    request_stack[0] = 1; ptr(request_stack+16,0x1234);
    Cpu probe_preserved = probe_request;
    unsigned requests_before_probe = actor_request_claimed;
    world_us = 5000000;
    coop_adapter_actor_request(&probe_request);
    assert(actor_request_claimed==requests_before_probe); // startup weapon traffic cannot fill the probe sample
    world_us = 6000000;
    coop_adapter_actor_request(&probe_request);
    assert(actor_request_claimed==requests_before_probe+1 && !memcmp(&probe_request,&probe_preserved,sizeof probe_request));
    assert(!actor_request_entries[0].stack_readable); // an unreadable stack must remain unknown, not a verified zero
    assert(actor_request_entries[requests_before_probe].extra_register_mask==5 &&
           actor_request_entries[requests_before_probe].stack_readable &&
           actor_request_entries[requests_before_probe].stack_flag==1 &&
           actor_request_entries[requests_before_probe].stack_pointer_mask==2);
    Cpu probe_copy = {.x = {(uintptr_t)(probe_descriptor+0x18),(uintptr_t)probe_context}};
    probe_copy.x[30] = MOD_MAIN_BASE+0x599a90;
    coop_adapter_request_context(&probe_copy); // a fire-and-forget weapon request may have a null watcher
    Cpu probe_enqueue = {.x = {(uintptr_t)actor,(uintptr_t)probe_descriptor,1}};
    probe_enqueue.x[30] = MOD_MAIN_BASE+0x599cc0;
    ptr(probe_descriptor+0xf8,(uintptr_t)probe_resource);
    coop_adapter_request_enqueue(&probe_enqueue);
    ptr(probe_actor+0x1a8,(uintptr_t)probe_data);
    ptr(probe_actor+0x218,(uintptr_t)probe_name);
    ptr(probe_actor+8,(uintptr_t)probe_owner);
    ptr(probe_owner+0x38,(uintptr_t)probe_heap);
    ptr(probe_heap,(uintptr_t)probe_heap_vtable);
    ptr(probe_heap_vtable+0x38,MOD_MAIN_BASE+0x3900);
    ptr(probe_data+0x40,(uintptr_t)probe_actor);
    int32_t probe_id = 77;
    memcpy(probe_data+0x48,&probe_id,4);
    memcpy(probe_actor+0x10,&probe_id,4);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x108cad0,
                                0,(uintptr_t)probe_descriptor,0);
    coop_adapter_function(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x108cad0,0);
    assert(pipeline_descriptor==(uintptr_t)probe_descriptor && pipeline_request_index<ACTOR_REQUEST_TRACE_LIMIT);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3400,MOD_MAIN_BASE+0x3d4150,
                                (uintptr_t)(probe_descriptor+0xf0),(uintptr_t)probe_actor,1);
    assert(pipeline_actor==(uintptr_t)probe_actor); // scoped factory results cover a different actor allocator
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3400,MOD_MAIN_BASE+0x3d4150,
                                (uintptr_t)other_actor,(uintptr_t)other_actor,1);
    assert(pipeline_actor==(uintptr_t)probe_actor); // another holder cannot replace the scoped factory result
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3500,MOD_MAIN_BASE+0x3d4488,
                                (uintptr_t)probe_actor,0,(uintptr_t)(probe_descriptor+0x18));
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3500,MOD_MAIN_BASE+0x3d4488,
                                (uintptr_t)other_actor,1,(uintptr_t)(probe_descriptor+0x18));
    assert(!probe_claimed); // reject failed initialization and another actor in the same descriptor scope
    ptr(probe_actor+0x218,(uintptr_t)actor_name);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3500,MOD_MAIN_BASE+0x3d4488,
                                (uintptr_t)probe_actor,1,(uintptr_t)(probe_descriptor+0x18));
    assert(!probe_claimed); // a matching descriptor does not override the real actor name
    ptr(probe_actor+0x218,(uintptr_t)probe_name);
    ptr(probe_actor+0x370,(uintptr_t)other_data);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3500,MOD_MAIN_BASE+0x3d4488,
                                (uintptr_t)probe_actor,1,(uintptr_t)(probe_descriptor+0x18));
    assert(!resource_entries[requests_before_probe].ready); // another resource is not the queued holder's binding
    ptr(probe_actor+0x370,(uintptr_t)probe_resource);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3500,MOD_MAIN_BASE+0x3d4488,
                                (uintptr_t)probe_actor,1,(uintptr_t)(probe_descriptor+0x18));
    assert(probe_claimed==1 && probe_entries[0].request==requests_before_probe);
    assert(probe_motion_actor==(uintptr_t)probe_actor);
    coop_adapter_function(MOD_MAIN_BASE+0x3900,99,(uintptr_t)probe_actor);
    assert(probe_motion_count==1);
    coop_adapter_function(MOD_MAIN_BASE+0x3900,99,(uintptr_t)probe_actor);
    assert(probe_motion_count==1); // rate limited
    assert(resource_entries[requests_before_probe].ready && resource_entries[requests_before_probe].resource==(uintptr_t)probe_resource);
    Cpu probe_remove = {.x = {(uintptr_t)probe_actor,0}};
    probe_remove.x[30] = MOD_MAIN_BASE+0x3600;
    probe_preserved = probe_remove;
    unsigned char probe_bytes[sizeof probe_actor]; memcpy(probe_bytes,probe_actor,sizeof probe_bytes);
    int32_t reused_id = 78;
    memcpy(probe_data+0x48,&reused_id,4);
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x63baa8,&probe_remove);
    assert(!probe_teardown_claimed);
    memcpy(probe_data+0x48,&probe_id,4);
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x63baa8,&probe_remove);
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x63baa8,&probe_remove);
    assert(probe_teardown_claimed==1 && !memcmp(&probe_remove,&probe_preserved,sizeof probe_remove));
    world_us+=200000;
    unsigned reads_before_motion=guest_reads;
    coop_adapter_function(MOD_MAIN_BASE+0x3900,99,(uintptr_t)probe_actor);
    assert(probe_motion_count==1 && guest_reads==reads_before_motion); // no actor reads after retirement begins
    probe_remove.x[1] = (uintptr_t)probe_actor;
    probe_remove.x[30] = MOD_MAIN_BASE+0x63bc40;
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0x3d45e0,&probe_remove);
    assert(!memcmp(probe_bytes,probe_actor,sizeof probe_bytes));
    memset(probe_data+0x40,0,8); // native metadata may be invalidated before actor cleanup
    Cpu dispose_cpu = {.x = {0,(uintptr_t)probe_actor}};
    dispose_cpu.x[30] = MOD_MAIN_BASE+0x3800;
    Cpu dispose_preserved = dispose_cpu;
    coop_adapter_dispose_begin(&dispose_cpu);
    assert(!memcmp(&dispose_cpu,&dispose_preserved,sizeof dispose_cpu));
    probe_remove.x[30] = MOD_MAIN_BASE+0x992610;
    probe_remove.x[20] = (uintptr_t)probe_heap;
    memcpy(probe_actor+0x10,&reused_id,4);
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0xa4a194,&probe_remove);
    assert(probe_teardown_claimed==2); // cleanup cannot accept a reused actor ID just because metadata is gone
    assert(!resource_entries[requests_before_probe].cleanup_ready);
    memcpy(probe_actor+0x10,&probe_id,4);
    memcpy(probe_bytes,probe_actor,sizeof probe_bytes);
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0xa4a194,&probe_remove);
    assert(probe_teardown_claimed==3 && !probe_teardown_entries[2].metadata_live &&
           !memcmp(probe_bytes,probe_actor,sizeof probe_bytes));
    assert(resource_entries[requests_before_probe].cleanup_ready && resource_entries[requests_before_probe].cleanup_same);
    assert(dispose_scope.target==MOD_MAIN_BASE+0x3900 && dispose_scope.probe==0);
    unsigned probe_retired_reads = guest_reads;
    coop_adapter_actor_teardown(MOD_MAIN_BASE+0xa4a194,&probe_remove);
    assert(probe_teardown_claimed==3 && guest_reads==probe_retired_reads);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3900,MOD_MAIN_BASE+0x3800,0,(uintptr_t)probe_actor,0);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3900,MOD_MAIN_BASE+0x3800,(uintptr_t)probe_heap,(uintptr_t)other_actor,0);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3900,MOD_MAIN_BASE+0x3804,(uintptr_t)probe_heap,(uintptr_t)probe_actor,0);
    assert(!probe_allocator_claimed);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3900,MOD_MAIN_BASE+0x3800,(uintptr_t)probe_heap,(uintptr_t)probe_actor,0);
    assert(probe_allocator_claimed==1 && !dispose_scope.target && guest_reads==probe_retired_reads);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3900,MOD_MAIN_BASE+0x3800,(uintptr_t)probe_heap,(uintptr_t)probe_actor,0);
    assert(probe_allocator_claimed==1 && guest_reads==probe_retired_reads);
    dispose_scope.target = MOD_MAIN_BASE+0x3900;
    dispose_cpu.x[1] = (uintptr_t)other_actor;
    coop_adapter_dispose_begin(&dispose_cpu);
    assert(!dispose_scope.target); // another disposal invalidates an unfinished handoff identity
    enqueue_entries[pipeline_request_index].dispatched = 0; // model an old captured task abandoned before dispatch
    probe_enqueue.x[30] = MOD_MAIN_BASE+0x3700;
    coop_adapter_request_enqueue(&probe_enqueue); // an uncaptured producer reuses the physical descriptor
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x108cad0,
                                0,(uintptr_t)probe_descriptor,0);
    coop_adapter_function(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x108cad0,0);
    assert(pipeline_request_index==ACTOR_REQUEST_TRACE_LIMIT);
    world_us = -1;
    pipeline_actor = pipeline_descriptor = 0;
    mode = "off"; config_version++; assert(!coop_active()); s = tick();
    assert(s.mode == COOP_OFF && !s.has_peer_pos);
    mode = "bot"; config_version++; assert(coop_active());
    assert(!C.has_peer && !C.has_local && !C.has_camera && !C.last_rx_ns && !C.world_syncs);
    visual_capture_checks();
    puts("co-op: actor lifecycle, title exclusion, read failures, bot movement, disabled warp and bounded native command rejection passed");
    return 0;
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cc', required=True)
    ap.add_argument('--deps', required=True, type=Path)
    args = ap.parse_args()
    output = ROOT / 'build' / 'tests'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='coop-', dir=output) as tmp:
        folder = Path(tmp)
        (folder / 'layout.h').write_text('#define MOD_MAIN_BASE 0x1000000000ull\n', encoding='utf-8')
        source = folder / 'check.c'
        source.write_text(HARNESS, encoding='utf-8')
        exe = folder / ('check.exe' if os.name == 'nt' else 'check')
        subprocess.run([args.cc, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(folder),
                        '-I', str(ROOT / 'runtime'), '-I', str(args.deps), '-I', str(args.deps / 'vma'),
                        str(source), *([] if os.name == 'nt' else ['-lm']), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    main()
