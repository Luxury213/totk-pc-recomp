"""Check native retirement against authored task/TLS memory, without game data or actual guest calls."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include <assert.h>
#include <stdarg.h>
#include <stdlib.h>
#include "coop_retirement.c"
const int rt_game_version=143;
static unsigned char actor[0x400],body[0x160],tlr[0x200],thread[0x100],task[0xd8],task_vtable[0x68];
static unsigned char manager[0x430],workers[0x50],key_object[0x50],actor_vtable[0x188];
static unsigned char request_code[0x244]={1},queue_code[28]={2},tls_code[20]={3},update_code[28]={4};
static uint64_t manager_ref,key_ref;
static struct { uint64_t at,value; } globals[5];
static struct { uint64_t at; unsigned char *bytes; size_t size; } regions[32];
static unsigned nregions,calls,reads,after_call;
static int valid_body=1,bad_hash;
static uint32_t live_generation=3;
static uint64_t native_result=1;
static int64_t world_us=24000000;
static CoopRetirement *active;
static Cpu original;
static void add(uint64_t at,void *bytes,size_t size) { regions[nregions++]=(typeof(*regions)){at,bytes,size}; }
static void put(void *base,unsigned off,uint64_t value,size_t size) { memcpy((unsigned char *)base+off,&value,size); }
int mem_guest_readable(uint64_t at,uint64_t n) {
    assert(!after_call);
    for(unsigned i=0;i<nregions;i++) if(n<=regions[i].size && at>=regions[i].at && at-regions[i].at<=regions[i].size-n) return 1;
    return 0;
}
int plat_mem_read(uint64_t at,void *out,size_t n) {
    assert(!after_call); reads++;
    for(unsigned i=0;i<nregions;i++) if(n<=regions[i].size && at>=regions[i].at && at-regions[i].at<=regions[i].size-n) {
        memcpy(out,regions[i].bytes+(at-regions[i].at),n); return 1;
    }
    return 0;
}
int coop_adapter_npc_probe_body(uint64_t a,uint64_t *b,uint32_t *g,int64_t *us) {
    assert(!after_call);
    if (!valid_body || a!=(uintptr_t)actor) return 0;
    *b=(uintptr_t)body; *g=live_generation; *us=1000000; return 1;
}
int64_t frame_step_world_us(void) { return world_us; }
void rt_log(const char *fmt,...) { (void)fmt; }
void rt_fatal(const char *fmt,...) { (void)fmt; abort(); }
void rt_sha256(const void *p,size_t n,uint8_t out[32]) {
    static const uint8_t hashes[4][32]={
        {0x24,0xde,0x58,0xb3,0x3b,0x20,0x83,0xc7,0x98,0xa9,0x38,0xca,0x94,0xb8,0x73,0xa2,0x01,0x4b,0xb7,0x46,0xb8,0x33,0xb9,0xa7,0xc1,0xb8,0x09,0x37,0x0b,0x57,0x54,0x6e},
        {0xfc,0x91,0x50,0x3f,0x93,0x7b,0x81,0xe3,0x86,0x24,0xad,0x34,0x90,0xc9,0x98,0xe4,0xad,0x61,0x0e,0x94,0x4e,0x5e,0x05,0x49,0x3f,0x9e,0xe8,0xd1,0xa8,0x8d,0xa3,0x52},
        {0xaf,0xbb,0x8e,0xce,0x9b,0x05,0x50,0x20,0x43,0x7c,0x5a,0xbe,0x71,0x07,0xf9,0xba,0xd1,0x0c,0xe6,0x12,0xe3,0xb4,0x03,0xaf,0xbc,0xdc,0x14,0xc4,0x36,0x2e,0x8a,0x86},
        {0x94,0x53,0x6d,0xb8,0x69,0xd0,0x79,0x8e,0x6a,0xd3,0xd9,0xf1,0xb3,0x6b,0x09,0x23,0x96,0xd0,0x0c,0xc7,0x31,0x4d,0xee,0x10,0x59,0x64,0x10,0xbd,0x7c,0xa5,0xa6,0x56}};
    unsigned tag=*(const uint8_t *)p; assert(tag>=1 && tag<=4);
    assert(n==(tag==1 ? 0x244u : tag==3 ? 20u : 28u));
    memcpy(out,hashes[tag-1],32); if(bad_hash==(int)tag) out[0]^=1;
}
uint64_t rt_call(Cpu *c,uint64_t fn,int n,...) {
    va_list args; va_start(args,n); uint64_t a=va_arg(args,uint64_t),reason=va_arg(args,uint64_t); va_end(args);
    assert(fn==MOD_MAIN_BASE+0x63baa8 && n==2 && a==(uintptr_t)actor && reason==0 && c->sp==original.sp);
    assert(active->attempted && !coop_retirement_try(c,active));
    calls++; memset(c,0x5a,sizeof *c); fesetround(FE_DOWNWARD); after_call=1;
    return native_result;
}
static void refused(Cpu *c,CoopRetirement *r) {
    Cpu before=*c; unsigned issued=calls;
    assert(!coop_retirement_try(c,r) && calls==issued && !r->attempted && !memcmp(&before,c,sizeof before));
}
static void rest(Cpu *c,CoopRetirement *r) {
    r->rest_samples=0;
    for(unsigned i=0;i<31;i++) { world_us+=33333; refused(c,r); }
    assert(r->rest_samples==31 && world_us-r->rest_since_us==999990);
    world_us+=33333;
}
int main(void) {
    add((uintptr_t)actor,actor,sizeof actor); add((uintptr_t)body,body,sizeof body);
    add((uintptr_t)tlr,tlr,sizeof tlr); add((uintptr_t)thread,thread,sizeof thread);
    add((uintptr_t)task,task,sizeof task); add((uintptr_t)task_vtable,task_vtable,sizeof task_vtable);
    add((uintptr_t)manager,manager,sizeof manager); add((uintptr_t)workers,workers,sizeof workers);
    add((uintptr_t)key_object,key_object,sizeof key_object); add((uintptr_t)&manager_ref,&manager_ref,8); add((uintptr_t)&key_ref,&key_ref,8);
    add(MOD_MAIN_BASE+0x3633078,actor_vtable,sizeof actor_vtable);
    add(MOD_MAIN_BASE+0x63baa8,request_code,sizeof request_code); add(MOD_MAIN_BASE+0x3d45e0,queue_code,sizeof queue_code);
    add(MOD_MAIN_BASE+0x2e27b0,update_code,sizeof update_code); add(MOD_SDK_BASE+0x143c60,tls_code,sizeof tls_code);
    manager_ref=(uintptr_t)manager; key_ref=(uintptr_t)key_object;
    globals[0]=(typeof(*globals)){MOD_MAIN_BASE+0x395da68,(uintptr_t)&manager_ref};
    globals[1]=(typeof(*globals)){MOD_MAIN_BASE+0x396f7a8,(uintptr_t)&key_ref};
    globals[2]=(typeof(*globals)){MOD_MAIN_BASE+0x395eef8,MOD_MAIN_BASE+0x500};
    globals[3]=(typeof(*globals)){MOD_MAIN_BASE+0x398b0b0,MOD_SDK_BASE+0x143c60};
    for(unsigned i=0;i<4;i++) add(globals[i].at,&globals[i].value,8);
    put(actor,0,MOD_MAIN_BASE+0x3633078,8); put(actor,0x10,17,4);
    put(actor_vtable,0xe0,MOD_MAIN_BASE+0xb2d470,8); put(actor_vtable,0x180,MOD_MAIN_BASE+0x2e27b0,8);
    put(key_object,0x48,3,4); put(tlr,0x1f8,(uintptr_t)thread,8); put(thread,0x80+3*8,(uintptr_t)task,8);
    put(task,0,(uintptr_t)task_vtable,8); put(task_vtable,0x60,MOD_MAIN_BASE+0x500,8);
    put(task,0xd0,16,4); put(task,0xa8,5,4); put(manager,0x80,(uintptr_t)workers,8);
    put(workers,0x20,5,4); put(workers,0x30,(uintptr_t)actor,8);
    unsigned char stack[512] __attribute__((aligned(16)));
    Cpu c; memset(&c,0xa5,sizeof c); c.x[0]=(uintptr_t)actor; c.x[30]=MOD_MAIN_BASE+0x2f1608;
    c.tpidrro=(uintptr_t)tlr; c.sp=(uintptr_t)(stack+sizeof stack);
    CoopRetirement request={.actor=(uintptr_t)actor,.body=(uintptr_t)body,.generation=3};
    c.x[0]++; refused(&c,&request); c.x[0]--;
    c.sp++; refused(&c,&request); c.sp--;
    c.x[30]++; refused(&c,&request); c.x[30]--;
    valid_body=0; refused(&c,&request); valid_body=1;
    live_generation=4; refused(&c,&request); live_generation=3;
    put(actor,0x28,0x20000,4); refused(&c,&request); put(actor,0x28,0,4);
    put(actor,0x24,11,4); refused(&c,&request); put(actor,0x24,0,4);
    put(task,0xd0,15,4); refused(&c,&request); put(task,0xd0,16,4);
    put(workers,0x30,(uintptr_t)body,8); refused(&c,&request); put(workers,0x30,(uintptr_t)actor,8);
    put(key_object,0x48,64,4); refused(&c,&request); put(key_object,0x48,3,4);
    for(bad_hash=1;bad_hash<=4;bad_hash++) refused(&c,&request); bad_hash=0;
    float moving=.1f; memcpy(body+0xf8,&moving,4); refused(&c,&request); assert(!request.rest_samples);
    memset(body+0xf8,0,4); refused(&c,&request); assert(request.rest_samples==1);
    refused(&c,&request); assert(request.rest_samples==1); // one world sample, even with repeated hooks
    world_us+=100001; refused(&c,&request); assert(request.rest_samples==1); // a gap restarts continuity
    moving=.02f; memcpy(actor+0x2b4,&moving,4); world_us+=33333; refused(&c,&request);
    assert(request.rest_samples==1); // drift invalidates the previous anchor
    moving=NAN; memcpy(body+0xa4,&moving,4); world_us+=33333; refused(&c,&request); assert(!request.rest_samples);
    memset(body+0xa4,0,4);
    rest(&c,&request);
    original=c; active=&request; fesetround(FE_UPWARD);
    assert(coop_retirement_try(&c,&request)==1 && calls==1 && request.accepted && request.actor_id==17);
    assert(!memcmp(&c,&original,sizeof c) && fegetround()==FE_UPWARD);
    unsigned before_reads=reads; assert(!coop_retirement_try(&c,&request) && reads==before_reads && calls==1);
    after_call=0; native_result=0; request=(CoopRetirement){.actor=(uintptr_t)actor,.body=(uintptr_t)body,.generation=3};
    rest(&c,&request);
    assert(coop_retirement_try(&c,&request)==-1 && calls==2 && request.attempted && !request.accepted);
    assert(!coop_retirement_try(&c,&request) && calls==2);
    puts("native retirement: owned task/TLS/type/code guards, single request, CPU/FP restore and no post-request guest reads passed");
}
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',default='C:/msys64/ucrt64/bin/clang.exe')
    args=parser.parse_args()
    output=ROOT/'build/tests'; output.mkdir(parents=True,exist_ok=True)
    cc=args.cc
    env=dict(os.environ,PATH=str(Path(cc).parent)+os.pathsep+os.environ.get('PATH',''))
    with tempfile.TemporaryDirectory(prefix='coop-retire-',dir=output) as temp:
        work=Path(temp); (work/'layout.h').write_text('#define MOD_MAIN_BASE 0x1000000000ull\n#define MOD_SDK_BASE 0x2000000000ull\n')
        (work/'check.c').write_text(HARNESS)
        subprocess.run([cc,'-std=gnu11','-O2','-Wall','-Wextra','-Werror','-I',str(work),'-I',str(ROOT/'runtime'),
            str(work/'check.c'),'-o',str(work/'check.exe')],check=True,env=env)
        subprocess.run([str(work/'check.exe')],check=True,env=env)

if __name__=='__main__': main()
