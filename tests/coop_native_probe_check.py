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
static Cpu original;
static int range(uint64_t p, uint64_t n, const void *base, size_t size) {
    return n <= size && p >= (uintptr_t)base && p - (uintptr_t)base <= size - n;
}
int mem_guest_readable(uint64_t p, uint64_t n) {
    return (p == MOD_MAIN_BASE+0x3ad7450ull && n == 8) ||
        (p == MOD_MAIN_BASE+0x599670ull && n == sizeof prologue) ||
        range(p,n,arg,sizeof arg) || range(p,n,name,sizeof name) || range(p,n,stack,sizeof stack) ||
        range(p,n,&manager,8) || range(p,n,&name_pointer,8) || range(p,n,&watcher,8);
}
int plat_mem_read(uint64_t p, void *dst, size_t n) {
    if (!mem_guest_readable(p,n)) return 0;
    if (p == MOD_MAIN_BASE+0x3ad7450ull) memcpy(dst,&manager,n);
    else if (p == MOD_MAIN_BASE+0x599670ull) memcpy(dst,prologue,n);
    else memcpy(dst,(const void *)(uintptr_t)p,n);
    return 1;
}
int64_t frame_step_world_us(void) { return 8000000; }
void rt_log(const char *fmt, ...) { (void)fmt; }
void rt_fatal(const char *fmt, ...) { (void)fmt; abort(); }
void rt_sha256(const void *p, size_t n, uint8_t out[32]) {
    (void)p; assert(n == 28);
    const uint8_t known[32] = {0xf8,0x23,0x0f,0xd5,0xeb,0xab,0x93,0x91,0x09,0xe4,0x71,0x48,0x55,0x34,0xa3,0x7b,
        0xbb,0xd8,0x60,0x51,0xeb,0xe1,0x80,0xd2,0x64,0x30,0x40,0x9e,0x88,0x31,0x63,0x49};
    memcpy(out,known,32); if (bad_hash) out[0] ^= 1;
}
uint64_t rt_call(Cpu *c, uint64_t fn, int n, ...) {
    assert(fn == MOD_MAIN_BASE+0x599670ull && n == 8);
    va_list ap; va_start(ap,n);
    uint64_t args[8];
    for (int i=0;i<n;i++) args[i]=va_arg(ap,uint64_t);
    va_end(ap);
    for (int i=0;i<n;i++) {
        if (armed >= COOP_NATIVE_PROBE_OWNED && (i==1 || i==2)) continue;
        assert(args[i] == (i == 3 ? 0 : original.x[i]));
    }
    if (armed >= COOP_NATIVE_PROBE_OWNED) {
        assert(args[1]==(uintptr_t)&owned_name && args[1]!=original.x[1]);
        assert(args[2]==(uintptr_t)&owned_arg && args[2]!=original.x[2]);
        assert(!strcmp(owned_name,armed == COOP_NATIVE_PROBE_NPC ? "Npc_Road_001" : "Weapon_Sword_101") && !strcmp(owned_arg.name,""));
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
    puts("native creation: guards, borrowed/owned request isolation and CPU/FP restoration passed");
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
