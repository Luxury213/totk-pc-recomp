"""Exercise borrowed/owned request isolation and transparent CPU restoration with a stub guest callee."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include <assert.h>
#include <stdarg.h>
#include <stdlib.h>
#include "coop_native_probe.c"
const int rt_game_version = 143;
static unsigned char arg[0x98], prologue[28];
static uint64_t manager, name_pointer, watcher;
static const char name[] = "Weapon_Sword_101";
static uint64_t stack[3] __attribute__((aligned(16)));
static int calls, bad_hash;
static unsigned char npc_body[0x160], velocity_code[28] = {1}, update_code[28] = {2};
static unsigned char npc_request[0xd8], consumer_code[28] = {3}, parent_code[28] = {4};
static int target_valid, velocity_calls;
static uint32_t target_generation=3;
static int64_t world_us=8000000;
static float requested_velocity[3];
static Cpu original;
static int range(uint64_t p, uint64_t n, const void *base, size_t size) {
    return n <= size && p >= (uintptr_t)base && p - (uintptr_t)base <= size - n;
}
int mem_guest_readable(uint64_t p, uint64_t n) {
    return (p == MOD_MAIN_BASE+0x3ad7450ull && n == 8) ||
        (p == MOD_MAIN_BASE+0x599670ull && n == sizeof prologue) ||
        (p == MOD_MAIN_BASE+0x567750ull && n == 28) || (p == MOD_MAIN_BASE+0x2e27b0ull && n == 28) ||
        (p == MOD_MAIN_BASE+0x182eb0ull && n == 28) || (p == MOD_MAIN_BASE+0x182410ull && n == 28) ||
        range(p,n,npc_request,sizeof npc_request) ||
        range(p,n,npc_body,sizeof npc_body) ||
        range(p,n,arg,sizeof arg) || range(p,n,name,sizeof name) || range(p,n,stack,sizeof stack) ||
        range(p,n,&manager,8) || range(p,n,&name_pointer,8) || range(p,n,&watcher,8);
}
int plat_mem_read(uint64_t p, void *dst, size_t n) {
    if (!mem_guest_readable(p,n)) return 0;
    if (p == MOD_MAIN_BASE+0x3ad7450ull) memcpy(dst,&manager,n);
    else if (p == MOD_MAIN_BASE+0x599670ull) memcpy(dst,prologue,n);
    else if (p == MOD_MAIN_BASE+0x567750ull) memcpy(dst,velocity_code,n);
    else if (p == MOD_MAIN_BASE+0x2e27b0ull) memcpy(dst,update_code,n);
    else if (p == MOD_MAIN_BASE+0x182eb0ull) memcpy(dst,consumer_code,n);
    else if (p == MOD_MAIN_BASE+0x182410ull) memcpy(dst,parent_code,n);
    else memcpy(dst,(const void *)(uintptr_t)p,n);
    return 1;
}
int64_t frame_step_world_us(void) { return world_us; }
int coop_adapter_npc_probe_body(uint64_t actor, uint64_t *body, uint32_t *generation, int64_t *observed_us) {
    if (!target_valid || actor!=0xabc0) return 0;
    *body=(uintptr_t)npc_body; *generation=target_generation; *observed_us=8000000; return 1;
}
void rt_log(const char *fmt, ...) { (void)fmt; }
void rt_fatal(const char *fmt, ...) { (void)fmt; abort(); }
void rt_sha256(const void *p, size_t n, uint8_t out[32]) {
    (void)p; assert(n == 28);
    const uint8_t known[32] = {0xf8,0x23,0x0f,0xd5,0xeb,0xab,0x93,0x91,0x09,0xe4,0x71,0x48,0x55,0x34,0xa3,0x7b,
        0xbb,0xd8,0x60,0x51,0xeb,0xe1,0x80,0xd2,0x64,0x30,0x40,0x9e,0x88,0x31,0x63,0x49};
    const uint8_t velocity_hash[32]={0x98,0x3c,0x1c,0xaf,0xee,0x3d,0xee,0x16,0x34,0xe0,0x57,0xa4,0x79,0x07,0xd9,0xcb,
        0x9e,0xf2,0x66,0x23,0x14,0x62,0xdb,0x66,0xd3,0x62,0x51,0x22,0x73,0x91,0x23,0xa9};
    const uint8_t update_hash[32]={0x94,0x53,0x6d,0xb8,0x69,0xd0,0x79,0x8e,0x6a,0xd3,0xd9,0xf1,0xb3,0x6b,0x09,0x23,
        0x96,0xd0,0x0c,0xc7,0x31,0x4d,0xee,0x10,0x59,0x64,0x10,0xbd,0x7c,0xa5,0xa6,0x56};
    const uint8_t *code=p;
    const uint8_t consumer_hash[32]={0x9b,0x0d,0xc2,0xe4,0x50,0xcb,0xba,0x22,0x9b,0xa6,0xfc,0x43,0x13,0x76,0x6f,0x35,
        0xc5,0xd6,0x1f,0x9c,0x97,0x53,0x9c,0x5f,0x96,0x87,0xa0,0x59,0x78,0x98,0x66,0xed};
    const uint8_t parent_hash[32]={0xd3,0x2d,0x66,0x8a,0x58,0xff,0x87,0x78,0xb8,0x11,0xd6,0x46,0x5a,0x3c,0x33,0x9c,
        0x67,0x4b,0xe4,0x66,0x29,0x25,0xc6,0x68,0x65,0x91,0x4a,0x62,0xf6,0x2f,0x0c,0xec};
    memcpy(out,code[0]==1 ? velocity_hash : code[0]==2 ? update_hash :
               code[0]==3 ? consumer_hash : code[0]==4 ? parent_hash : known,32);
    if (bad_hash) out[0] ^= 1;
}
uint64_t rt_call(Cpu *c, uint64_t fn, int n, ...) {
    va_list ap; va_start(ap,n);
    uint64_t args[8];
    for (int i=0;i<n;i++) args[i]=va_arg(ap,uint64_t);
    va_end(ap);
    if (fn==MOD_MAIN_BASE+0x567750ull) {
        assert(n==2 && args[0]==(uintptr_t)npc_body && c->sp==original.sp);
        memcpy(requested_velocity,(const void *)(uintptr_t)args[1],sizeof requested_velocity);
        assert(requested_velocity[1]==-.5f && requested_velocity[2]==0);
        velocity_calls++;
        coop_native_probe_npc_update(c);
        coop_native_probe_npc_consume(c);
        if (armed==COOP_NATIVE_PROBE_NPC_CONSUMER_MOTION) memcpy(npc_request+0x44,requested_velocity,12);
        memset(c,0x5a,sizeof *c); fesetround(FE_DOWNWARD); return 0;
    }
    assert(fn == MOD_MAIN_BASE+0x599670ull && n == 8);
    for (int i=0;i<n;i++) {
        if (armed >= COOP_NATIVE_PROBE_OWNED && (i==1 || i==2)) continue;
        assert(args[i] == (i == 3 ? 0 : original.x[i]));
    }
    if (armed >= COOP_NATIVE_PROBE_OWNED) {
        assert(args[1]==(uintptr_t)&owned_name && args[1]!=original.x[1]);
        assert(args[2]==(uintptr_t)&owned_arg && args[2]!=original.x[2]);
        assert(!strcmp(owned_name,armed >= COOP_NATIVE_PROBE_NPC ? "Npc_Road_001" : "Weapon_Sword_101") && !strcmp(owned_arg.name,""));
        assert(owned_arg.position[0]==12 && owned_arg.position[1]==22 && owned_arg.position[2]==30);
        assert(owned_arg.rotation[0]==1 && owned_arg.rotation[4]==1 && owned_arg.rotation[8]==1);
        assert(owned_arg.scale[0]==1 && owned_arg.scale[1]==1 && owned_arg.scale[2]==1);
        assert(owned_arg.transform_flags==7 && owned_arg.blackboard==&owned_bb);
        assert(!owned_arg.blackboard_60 && !owned_arg.parent && !owned_arg.dependent && !owned_arg.creator &&
               !owned_arg.creator_rtti && !owned_arg.instance_heap);
        assert(owned_bb.size==32 && owned_bb.count==0 && owned_bb.params==owned_bb.buffer);
    }
    assert(c->sp == original.sp && stack[1] == 0 && stack[2] == 0);
    calls++;
    coop_native_probe_request(c); // reentry must not create a second request
    memset(c,0x5a,sizeof *c);
    fesetround(FE_DOWNWARD);
    return 1;
}
static void reset(Cpu *c) {
    attempted=0; calls=0; inside=0; bad_hash=0;
    memset(c,0xa5,sizeof *c); memset(arg,0,sizeof arg);
    manager=(uintptr_t)&manager; name_pointer=(uintptr_t)name; arg[0x90]=3;
    c->x[0]=manager; c->x[1]=(uintptr_t)&name_pointer; c->x[2]=(uintptr_t)arg;
    c->x[3]=(uintptr_t)&watcher; for (int i=4;i<8;i++) c->x[i]=0;
    c->x[30]=MOD_MAIN_BASE+0x20a57d8ull; c->sp=(uintptr_t)stack;
    memset(stack,0,sizeof stack);
    original=*c;
}
int main(int argc, char **argv) {
    assert(argc==2);
    Cpu c; reset(&c);
    coop_native_probe_init(argv[1],1,0); coop_native_probe_request(&c); assert(!calls && !armed);
    coop_native_probe_init(argv[1],0,1); assert(!armed);
    coop_native_probe_init(argv[1],1,1); assert(!armed); // missing marker
    char path[4096]; snprintf(path,sizeof path,"%s/coop-native-probe.txt",argv[1]);
    FILE *f=fopen(path,"wb"); assert(f); fputs("isolated-physics-probe-v1\nextra",f); fclose(f);
    coop_native_probe_init(argv[1],1,1); assert(!armed);
    f=fopen(path,"wb"); assert(f); fputs("isolated-physics-probe-v1\r\n",f); fclose(f);
    coop_native_probe_init(argv[1],1,1); assert(!armed); // the runner must write a canonical marker
    f=fopen(path,"wb"); assert(f); fputs("isolated-physics-probe-v1\n",f); fclose(f);
    coop_native_probe_init(argv[1],1,1); assert(armed);
    // An arbitrary/Player producer, stale name, nonzero extra argument, wrong manager or prologue cannot invoke it.
    for (int i=0;i<10;i++) {
        reset(&c);
        if(i==0) c.x[30]++;
        if(i==1) c.x[1]=0;
        if(i==2) arg[0x90]=1;
        if(i==3) c.x[3]=0;
        if(i==4) c.x[5]=1;
        if(i==5) stack[0]=1;
        if(i==6) stack[1]=123;
        if(i==7) stack[2]=123;
        if(i==8) c.x[0]=0;
        if(i==9) bad_hash=1;
        Cpu before=c;
        coop_native_probe_request(&c);
        assert(!calls && !attempted && !memcmp(&c,&before,sizeof c));
    }
    reset(&c);
    stack[0]=0x123400; // bytes above the ABI's one-byte stacked bool are padding
    fesetround(FE_UPWARD);
    coop_native_probe_request(&c);
    assert(calls==1 && attempted && !memcmp(&c,&original,sizeof c));
    assert(fegetround()==FE_UPWARD && arg[0x90]==3 && watcher==0 && stack[0]==0x123400);
    coop_native_probe_request(&c); assert(calls==1);
    armed=0;
    coop_native_probe_init(argv[1],1,COOP_NATIVE_PROBE_OWNED); assert(!armed); // a clone marker cannot arm owned mode
    f=fopen(path,"wb"); assert(f); fputs("isolated-physics-owned-v1\n",f); fclose(f);
    coop_native_probe_init(argv[1],1,99); assert(!armed);
    coop_native_probe_init(argv[1],1,COOP_NATIVE_PROBE_OWNED); assert(armed==COOP_NATIVE_PROBE_OWNED);
    reset(&c);
    float invalid[3]={NAN,20,30}; memcpy(arg,invalid,sizeof invalid);
    coop_native_probe_request(&c); assert(!attempted && !calls);
    float pos[3]={10,20,30}; memcpy(arg,pos,sizeof pos);
    memset(arg+0x58,0x5a,0x38); // source blackboard/dependency pointers must never be inherited
    unsigned char source_before[sizeof arg]; memcpy(source_before,arg,sizeof arg);
    coop_native_probe_request(&c);
    assert(calls==1 && attempted && !memcmp(&c,&original,sizeof c));
    assert(!memcmp(arg,source_before,sizeof arg) && fegetround()==FE_UPWARD);
    ProbeCreateArg retained_arg=owned_arg;
    ProbeBlackboard retained_bb=owned_bb;
    coop_native_probe_request(&c);
    assert(calls==1 && !memcmp(&retained_arg,&owned_arg,sizeof owned_arg) &&
           !memcmp(&retained_bb,&owned_bb,sizeof owned_bb));
    memset(arg,0,sizeof arg); // request data remains alive after the producer's storage is gone
    assert(owned_arg.position[0]==12 && owned_arg.blackboard==&owned_bb && owned_bb.params==owned_bb.buffer);
    armed=0;
    coop_native_probe_init(argv[1],1,COOP_NATIVE_PROBE_NPC); assert(!armed); // weapon markers cannot arm NPC creation
    f=fopen(path,"wb"); assert(f); fputs("isolated-npc-road-001-v1\n",f); fclose(f);
    coop_native_probe_init(argv[1],1,COOP_NATIVE_PROBE_OWNED); assert(!armed); // NPC marker cannot arm weapon mode
    coop_native_probe_init(argv[1],1,COOP_NATIVE_PROBE_NPC); assert(armed==COOP_NATIVE_PROBE_NPC);
    reset(&c); memcpy(arg,pos,sizeof pos);
    coop_native_probe_request(&c);
    assert(calls==1 && attempted && !memcmp(&c,&original,sizeof c) && !strcmp(owned_name,"Npc_Road_001"));
    assert(fegetround()==FE_UPWARD && owned_arg.blackboard==&owned_bb && !owned_arg.creator);
    coop_native_probe_request(&c); assert(calls==1);
    // A creation-only NPC marker cannot enable native movement.
    armed=0; coop_native_probe_init(argv[1],1,COOP_NATIVE_PROBE_NPC_MOTION); assert(!armed);
    f=fopen(path,"wb"); assert(f); fputs("isolated-npc-velocity-v1\n",f); fclose(f);
    coop_native_probe_init(argv[1],1,COOP_NATIVE_PROBE_NPC_MOTION); assert(armed==4);
    reset(&c); memcpy(arg,pos,sizeof pos);
    coop_native_probe_request(&c); assert(calls==1 && !strcmp(owned_name,"Npc_Road_001"));
    c.x[0]=0xabc0; original=c;
    float falling=-.5f; memcpy(npc_body+0xfc,&falling,4);
    world_us=10000000;
    coop_native_probe_npc_update(&c); assert(!velocity_calls); // no live scoped body
    target_valid=1; bad_hash=1;
    coop_native_probe_npc_update(&c); assert(!velocity_calls && !npc_motion.calls);
    bad_hash=0; world_us=9999999;
    coop_native_probe_npc_update(&c); assert(!velocity_calls); // allow settling first
    world_us=10000000; fesetround(FE_UPWARD);
    coop_native_probe_npc_update(&c);
    assert(velocity_calls==1 && requested_velocity[0]==2 && fegetround()==FE_UPWARD);
    assert(!memcmp(&c,&original,sizeof c));
    coop_native_probe_npc_update(&c); assert(velocity_calls==1); // bounded rate
    int saw_reverse=0;
    for (int i=0;i<70;i++) {
        world_us+=33334; coop_native_probe_npc_update(&c);
        if (requested_velocity[0]==-2) saw_reverse=1;
        assert(!memcmp(&c,&original,sizeof c) && fegetround()==FE_UPWARD);
    }
    assert(saw_reverse && npc_motion.finished && requested_velocity[0]==0 && velocity_calls<=96);
    int finished_calls=velocity_calls;
    world_us+=33334; coop_native_probe_npc_update(&c); assert(velocity_calls==finished_calls);
    memset(&npc_motion,0,sizeof npc_motion); world_us=10000000;
    coop_native_probe_npc_update(&c); target_generation++;
    world_us+=33334; finished_calls=velocity_calls; coop_native_probe_npc_update(&c);
    assert(npc_motion.finished && velocity_calls==finished_calls); // recycled world cannot resume the pulse
    memset(&npc_motion,0,sizeof npc_motion); world_us=10000000;
    coop_native_probe_npc_update(&c); world_us+=250001;
    coop_native_probe_npc_update(&c);
    assert(npc_motion.finished && requested_velocity[0]==0); // continuity failure stops the same live body
    armed=0; coop_native_probe_init(argv[1],1,COOP_NATIVE_PROBE_NPC_CONSUMER_MOTION); assert(!armed);
    f=fopen(path,"wb"); assert(f); fputs("isolated-npc-consumer-velocity-v1\n",f); fclose(f);
    coop_native_probe_init(argv[1],1,COOP_NATIVE_PROBE_NPC_CONSUMER_MOTION); assert(armed==5);
    reset(&c); memcpy(arg,pos,sizeof pos); coop_native_probe_request(&c); assert(calls==1);
    c.x[0]=0xabc0; original=c; memset(&npc_motion,0,sizeof npc_motion); world_us=10000000;
    uint64_t pending=(uintptr_t)npc_request; memcpy(npc_body+0x60,&pending,8);
    uint32_t pending_flags=0x80; memcpy(npc_request+0xd4,&pending_flags,4);
    coop_native_probe_npc_update(&c); assert(npc_motion.calls==1);
    memset(npc_request+0x44,0,12); // native preparation replaces the early request before consumption
    Cpu consumer=c; consumer.x[0]=pending; consumer.x[1]=(uintptr_t)npc_body; consumer.x[30]=MOD_MAIN_BASE+0x1824f8;
    Cpu consumer_before=consumer;
    int before_consume=velocity_calls;
    consumer.x[30]++; coop_native_probe_npc_consume(&consumer); assert(velocity_calls==before_consume);
    consumer=consumer_before; bad_hash=1;
    coop_native_probe_npc_consume(&consumer); assert(velocity_calls==before_consume);
    bad_hash=0; memset(npc_body+0x60,0,8);
    coop_native_probe_npc_consume(&consumer); assert(velocity_calls==before_consume);
    memcpy(npc_body+0x60,&pending,8); fesetround(FE_UPWARD);
    coop_native_probe_npc_consume(&consumer);
    assert(velocity_calls==before_consume+1 && npc_motion.consumer_calls==1 && !memcmp(&consumer,&consumer_before,sizeof consumer));
    float actual[3]; memcpy(actual,npc_request+0x44,sizeof actual);
    assert(actual[0]==2 && actual[1]==-.5f && fegetround()==FE_UPWARD);
    coop_native_probe_npc_consume(&consumer); assert(velocity_calls==before_consume+1);
    world_us+=100001; coop_native_probe_npc_consume(&consumer); assert(velocity_calls==before_consume+1); // stale command
    world_us=npc_motion.last_us+1; target_generation++;
    coop_native_probe_npc_consume(&consumer); assert(velocity_calls==before_consume+1); // another world
    target_generation--; npc_motion.consumer_calls=96;
    coop_native_probe_npc_consume(&consumer); assert(velocity_calls==before_consume+1); // consumer budget
    npc_motion.consumer_calls=1; npc_motion_busy=1;
    coop_native_probe_npc_consume(&consumer); assert(velocity_calls==before_consume+1); // busy guest phase
    npc_motion_busy=0;
    puts("native probes: scoped creation/velocity guards, bounded requests and CPU/FP restoration passed");
    return 0;
}
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cc', default='C:/msys64/ucrt64/bin/clang.exe')
    args = ap.parse_args()
    output = ROOT / 'build/tests'
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PATH=str(Path(args.cc).parent) + os.pathsep + os.environ.get('PATH', ''))
    with tempfile.TemporaryDirectory(prefix='coop-native-probe-', dir=output) as folder:
        work = Path(folder)
        (work / 'layout.h').write_text('#define MOD_MAIN_BASE 0x1000000000ull\n', encoding='utf-8')
        (work / 'check.c').write_text(HARNESS, encoding='utf-8')
        subprocess.run([args.cc, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-I', str(work), '-I', str(ROOT / 'runtime'), str(work / 'check.c'), '-o', str(work / 'check.exe')],
                       env=env, check=True)
        subprocess.run([str(work / 'check.exe'), str(work)], env=env, check=True)


if __name__ == '__main__':
    main()
