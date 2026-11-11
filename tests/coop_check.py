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
static unsigned char root[0x38], unit[0x50], actor[0x400];
static unsigned char vtable[0x220];
static unsigned char scene_module[0x1f0], scene[0x60], alternate_scene[0x60], components[14*8];
static unsigned char residents[0x30], resident_links[0x70], resident_data[0x48];
static char actor_name[] = "Player";
static int fail_reads;

unsigned cfg_version(void) { return config_version; }
const char *cfg_value(const char *key) {
    return !strcmp(key, "TOTK_COOP_MODE") ? mode : "127.0.0.1";
}
int cfg_int(const char *key) { (void)key; return 7777; }
int cfg_bool(const char *key) { return !strcmp(key, "TOTK_COOP_TRACE_GUEST"); }
void plat_mutex_lock(PlatMutex *m) { (void)m; }
void plat_mutex_unlock(PlatMutex *m) { (void)m; }
uint64_t plat_now_ns(void) { return now; }
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
           in_range(p,n,scene_module,sizeof scene_module) || in_range(p,n,scene,sizeof scene) ||
           in_range(p,n,alternate_scene,sizeof alternate_scene) ||
           in_range(p,n,components,sizeof components) || in_range(p,n,residents,sizeof residents) ||
           in_range(p,n,resident_links,sizeof resident_links) ||
           in_range(p,n,resident_data,sizeof resident_data) ||
           in_range(p,n,actor_name,sizeof actor_name);
}
int plat_mem_read(uint64_t p, void *out, size_t n) {
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
    ptr(unit + 0x40,(uintptr_t)actor);
    ptr(actor,MOD_MAIN_BASE + 0x100);
    ptr(actor + 0x218,(uintptr_t)actor_name);
    ptr(vtable + 0x200,MOD_MAIN_BASE + 0x1000);
    ptr(scene_module + 0x1e8,(uintptr_t)scene);
    int32_t count = 14, one = 1;
    memcpy(scene + 0x50,&count,4);
    ptr(scene + 0x58,(uintptr_t)components);
    ptr(components + 13*8,(uintptr_t)residents);
    ptr(residents,MOD_MAIN_BASE + 0x500);
    memcpy(residents + 0x20,&one,4);
    ptr(residents + 0x28,(uintptr_t)resident_links);
    ptr(resident_links + 8,(uintptr_t)resident_data);
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

int main(void) {
    g_fnprof=1; coop_adapter_trace_enable(1); assert(g_fnprof==3);
    coop_adapter_trace_enable(0); assert(g_fnprof==1); g_fnprof=0;
    assert(coop_active());
    camera[0] = camera[5] = camera[10] = 1;
    camera[12] = camera[17] = camera[22] = camera[27] = 1;
    coop_capture_camera(1);
    coop_adapter_trace_enable(1);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x2340,0,88,0);
    coop_adapter_function(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x2340,77);
    coop_adapter_function(MOD_MAIN_BASE+0x3d40f0,MOD_MAIN_BASE+0x3d3e44,77);
    coop_adapter_function(MOD_MAIN_BASE+0x689894,MOD_MAIN_BASE+0x3d4114,77);
    coop_adapter_function(MOD_MAIN_BASE+0x6898dc,MOD_MAIN_BASE+0x6898cc,(uintptr_t)actor);
    coop_adapter_function(MOD_MAIN_BASE+0xc9a5a4,MOD_MAIN_BASE+0x2468,(uintptr_t)residents);
    assert(constructor_entries[0].factory_caller==MOD_MAIN_BASE+0x3d4114);
    assert(constructor_entries[0].request_caller==MOD_MAIN_BASE+0x3d3e44);
    assert(constructor_entries[0].pipeline_caller==MOD_MAIN_BASE+0x2340);
    assert(constructor_entries[0].task_descriptor==88);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x1000,MOD_MAIN_BASE+0x3d4150,88+0xf0,(uintptr_t)actor,1);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x20d530,MOD_MAIN_BASE+0x3d4264,(uintptr_t)actor,88+0x18,0);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x1000,MOD_MAIN_BASE+0x3d4198,77,1234,0);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x20d530,MOD_MAIN_BASE+0x3d4264,1234,77,0);
    coop_adapter_native_dispatch(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x2340,0,99,0);
    coop_adapter_function(MOD_MAIN_BASE+0x3d3dd0,MOD_MAIN_BASE+0x2344,77);
    coop_adapter_function(MOD_MAIN_BASE+0x3d40f0,MOD_MAIN_BASE+0x3d3e44,77);
    coop_adapter_function(MOD_MAIN_BASE+0x689894,MOD_MAIN_BASE+0x3d4114,77);
    coop_adapter_function(MOD_MAIN_BASE+0x6898dc,MOD_MAIN_BASE+0x6898cc,1234);
    assert(!constructor_entries[1].task_descriptor);
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
           title.native_resident_match && title.native_resident_component_vtable_count==1 &&
           title.native_resident_init_trace_count==1);
    assert(matched_task_descriptor==88 && holder_entries[0].holder==matched_task_descriptor+0xf0);
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
    mode = "off"; config_version++; assert(!coop_active()); s = tick();
    assert(s.mode == COOP_OFF && !s.has_peer_pos);
    mode = "bot"; config_version++; assert(coop_active());
    assert(!C.has_peer && !C.has_local && !C.has_camera && !C.last_rx_ns && !C.world_syncs);
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
