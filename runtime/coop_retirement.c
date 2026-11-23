// Native paths independently inspected in the user's 1.4.3 modules. No generated game body is copied here.
#include "coop_retirement.h"
#include "coop_adapter.h"
#include "host.h"
#include "layout.h"
#include "platform/platform.h"
#include <fenv.h>
#include <math.h>
#include <string.h>

static int rd(uint64_t at,void *out,size_t n) {
    return at>=0x10000 && at<(1ull<<47) && n<=(1ull<<47)-at &&
        mem_guest_readable(at,n) && plat_mem_read(at,out,n);
}
static uint64_t ptr(uint64_t at) { uint64_t v=0; return rd(at,&v,8) ? v : 0; }
static uint32_t word(uint64_t at) { uint32_t v=UINT32_MAX; return rd(at,&v,4) ? v : UINT32_MAX; }
static int code(uint64_t at,size_t n,const uint8_t expected[32]) {
    uint8_t bytes[0x244],hash[32];
    if (n>sizeof bytes || !rd(at,bytes,n)) return 0;
    rt_sha256(bytes,n,hash); return !memcmp(hash,expected,sizeof hash);
}

// main+0x2f1554 records the current actor in its worker slot before dispatching the virtual +0x180 update.
// main+0x63baa8 recognizes this same task context. Read the SDK GetTlsValue ABI rather than calling a getter.
int coop_actor_worker_context(const Cpu *c,uint64_t actor,unsigned *worker,uint32_t *tag) {
    if (!c || !actor || !worker || !tag || rt_game_version!=143) return 1;
    *tag=UINT32_MAX;
    if (c->x[30]!=MOD_MAIN_BASE+0x2f1608ull || ptr(MOD_MAIN_BASE+0x398b0b0ull)!=MOD_SDK_BASE+0x143c60ull) return 1;
    uint64_t key_object=ptr(ptr(MOD_MAIN_BASE+0x396f7a8ull));
    uint32_t key=word(key_object+0x48);
    if (key>=64 || c->tpidrro<0x10000 || c->tpidrro>=(1ull<<47)-0x200) return 2;
    uint64_t thread=ptr(c->tpidrro+0x1f8),task=ptr(thread+0x80+key*8ull);
    uint64_t kind=ptr(MOD_MAIN_BASE+0x395eef8ull);
    *tag=word(task+0xd0);
    if (!task || !kind || ptr(ptr(task)+0x60)!=kind || *tag!=0x10) return 3;
    uint32_t index=word(task+0xa8);
    *worker=index;
    uint64_t manager=ptr(ptr(MOD_MAIN_BASE+0x395da68ull)),workers=ptr(manager+0x80);
    if (!workers || index==UINT32_MAX) return 4;
    for (unsigned i=0;i<3;i++) if (word(workers+0x20+i*4)==index && ptr(workers+0x30+i*8)==actor) {
        *worker=i; return 0;
    }
    return 5;
}

static int stationary(CoopRetirement *r,int64_t now) {
    float p[6],v[3];
    if (!rd(r->actor+0x2b4,p,12) || !rd(r->body+0xa4,p+3,4) ||
        !rd(r->body+0xb4,p+4,4) || !rd(r->body+0xc4,p+5,4) || !rd(r->body+0xf8,v,12)) {
        r->rest_samples=0; return 0;
    }
    for(unsigned k=0;k<6;k++) if(!isfinite(p[k]) || fabsf(p[k])>100000) { r->rest_samples=0; return 0; }
    for(unsigned k=0;k<3;k++) if(!isfinite(v[k]) || fabsf(v[k])>.05f) { r->rest_samples=0; return 0; }
    if (r->rest_samples && now==r->rest_last_us) return 0;
    int reset=!r->rest_samples || now<r->rest_last_us || now-r->rest_last_us>100000;
    for(unsigned k=0;k<6 && !reset;k++) reset=fabsf(p[k]-r->rest_pos[k])>.01f;
    if(reset) {
        memcpy(r->rest_pos,p,sizeof p); r->rest_since_us=now; r->rest_samples=1;
    } else r->rest_samples++;
    r->rest_last_us=now;
    return r->rest_samples>=12 && now-r->rest_since_us>=1000000;
}

int coop_retirement_try(Cpu *c,CoopRetirement *r) {
    if (!c || !r || r->attempted || rt_game_version!=143 || !r->actor || c->x[0]!=r->actor || !r->generation || (c->sp&15)) return 0;
    uint64_t body; uint32_t generation; int64_t observed_us;
    if (!coop_adapter_npc_probe_body(r->actor,&body,&generation,&observed_us) || body!=r->body || generation!=r->generation ||
        ptr(r->actor)!=MOD_MAIN_BASE+0x3633078ull ||
        ptr(MOD_MAIN_BASE+0x3633078ull+0xe0)!=MOD_MAIN_BASE+0xb2d470ull ||
        ptr(MOD_MAIN_BASE+0x3633078ull+0x180)!=MOD_MAIN_BASE+0x2e27b0ull ||
        (word(r->actor+0x24)-7u)<5u || (word(r->actor+0x28)&0x20000u)) return 0;
    unsigned worker=0; uint32_t tag; int context=coop_actor_worker_context(c,r->actor,&worker,&tag);
    if (context) {
        if (!(r->refusals&(1u<<context))) rt_log("coop native npc retirement context: refused %d, task kind %u, worker index %u; no request issued",context,tag,worker);
        r->refusals|=1u<<context; return 0;
    }
    static const uint8_t request_hash[32]={0x24,0xde,0x58,0xb3,0x3b,0x20,0x83,0xc7,0x98,0xa9,0x38,0xca,0x94,0xb8,0x73,0xa2,
        0x01,0x4b,0xb7,0x46,0xb8,0x33,0xb9,0xa7,0xc1,0xb8,0x09,0x37,0x0b,0x57,0x54,0x6e};
    static const uint8_t queue_hash[32]={0xfc,0x91,0x50,0x3f,0x93,0x7b,0x81,0xe3,0x86,0x24,0xad,0x34,0x90,0xc9,0x98,0xe4,
        0xad,0x61,0x0e,0x94,0x4e,0x5e,0x05,0x49,0x3f,0x9e,0xe8,0xd1,0xa8,0x8d,0xa3,0x52};
    static const uint8_t tls_hash[32]={0xaf,0xbb,0x8e,0xce,0x9b,0x05,0x50,0x20,0x43,0x7c,0x5a,0xbe,0x71,0x07,0xf9,0xba,
        0xd1,0x0c,0xe6,0x12,0xe3,0xb4,0x03,0xaf,0xbc,0xdc,0x14,0xc4,0x36,0x2e,0x8a,0x86};
    static const uint8_t update_hash[32]={0x94,0x53,0x6d,0xb8,0x69,0xd0,0x79,0x8e,0x6a,0xd3,0xd9,0xf1,0xb3,0x6b,0x09,0x23,
        0x96,0xd0,0x0c,0xc7,0x31,0x4d,0xee,0x10,0x59,0x64,0x10,0xbd,0x7c,0xa5,0xa6,0x56};
    if (!code(MOD_MAIN_BASE+0x63baa8ull,0x244,request_hash) || !code(MOD_MAIN_BASE+0x3d45e0ull,28,queue_hash) ||
        !code(MOD_SDK_BASE+0x143c60ull,20,tls_hash) || !code(MOD_MAIN_BASE+0x2e27b0ull,28,update_hash)) return 0;
    uint32_t id=word(r->actor+0x10);
    if (id==UINT32_MAX || !coop_adapter_npc_probe_body(r->actor,&body,&generation,&observed_us) ||
        body!=r->body || generation!=r->generation || coop_actor_worker_context(c,r->actor,&worker,&tag)) return 0;
    int64_t now=frame_step_world_us();
    if (!stationary(r,now) || !coop_adapter_npc_probe_body(r->actor,&body,&generation,&observed_us) ||
        body!=r->body || generation!=r->generation) return 0;
    Cpu saved=*c; fenv_t fp;
    if (fegetenv(&fp)) return 0;
    r->attempted=1; r->actor_id=(int32_t)id;
    uint64_t result=rt_call(c,MOD_MAIN_BASE+0x63baa8ull,2,r->actor,(uint64_t)0);
    *c=saved;
    if (fesetenv(&fp)) rt_fatal("coop native npc retirement: cannot restore host floating-point environment");
    // The request may invalidate actor/body ownership immediately. Never read them after this call.
    r->accepted=result==1;
    rt_log("coop native npc retirement request: generation %u, actor id %d, world us %lld, result %llu, worker %u, rest samples %u, rest us %lld; original CPU restored, asynchronous cleanup required",
        r->generation,r->actor_id,(long long)now,(unsigned long long)result,worker,
        r->rest_samples,(long long)(now-r->rest_since_us));
    return r->accepted ? 1 : -1;
}
