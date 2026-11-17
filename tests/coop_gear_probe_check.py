"""Check bounded model-graph observation against authored memory and a private opt-in marker."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include <assert.h>
#include "coop_equipment.c"
#include "coop_gear_probe.c"
const int rt_game_version=143;
static unsigned char heap[0x6000];
static const char model_name[]="Weapon_Sword_101.Weapon_Sword_101";
static const char actor_name[]="Weapon_Sword_101";
static const char marker[]="read-only-gear-graph-v1\n0\tWeapon_Sword_101\tWeapon_Sword_101.Weapon_Sword_101\n";
static int files=1;
static unsigned reads,file_reads;
static int range(uint64_t at,uint64_t n,const void *base,uint64_t size) {
    return n<=size && at>=(uintptr_t)base && at-(uintptr_t)base<=size-n;
}
const RtGuestLayout *mem_layout(void) {
    static RtGuestLayout layout; layout.heap=(RtRange){(uintptr_t)heap,sizeof heap}; return &layout;
}
int mem_guest_readable(uint64_t at,uint64_t n) {
    return range(at,n,heap,sizeof heap) || range(at,n,model_name,sizeof model_name) || range(at,n,actor_name,sizeof actor_name);
}
int plat_mem_read(uint64_t at,void *out,size_t n) {
    reads++; if(!mem_guest_readable(at,n)) return 0;
    memcpy(out,(const void *)(uintptr_t)at,n); return 1;
}
int64_t plat_file_size(const char *path) { (void)path; file_reads++; return files ? sizeof marker-1 : -1; }
uint8_t *plat_file_read(const char *path,uint64_t *size) {
    (void)path; file_reads++; *size=sizeof marker-1; uint8_t *p=malloc(*size); memcpy(p,marker,*size); return p;
}
void rt_log(const char *fmt,...) { (void)fmt; }
static void pointer(unsigned at,uint64_t p) { memcpy(heap+at,&p,8); }
int main(void) {
    CoopSample sample={.generation=1,.flags=COOP_SAMPLE_PLAYER|COOP_SAMPLE_EQUIPMENT};
    strcpy(sample.equipment.actor[0],"Weapon_Sword_101");
    coop_gear_probe_init("synthetic",0); assert(!P.armed && !file_reads);
    coop_gear_probe_observe((uintptr_t)heap,10,&sample,1000000); assert(!reads);
    files=0; coop_gear_probe_init("synthetic",1); assert(!P.armed); files=1;
    coop_gear_probe_init("synthetic",1); assert(P.armed);
    pointer(0x238,(uintptr_t)heap+0x1000); pointer(0x1000+0x3e0,(uintptr_t)heap+0x2000);
    pointer(0x1000,(uintptr_t)heap+0x1000); // cycle must not grow the frontier
    pointer(0x2000+0x90,(uintptr_t)model_name); pointer(0x2000+0x458,(uintptr_t)heap+0x3000);
    pointer(0x3008,(uintptr_t)heap+0x4000);
    float mat[12]={1,0,0,1,0,1,0,2,0,0,1,3}; memcpy(heap+0x4000,mat,sizeof mat);
    unsigned char before[sizeof heap]; memcpy(before,heap,sizeof heap);
    coop_gear_probe_observe((uintptr_t)heap,10,&sample,999999); assert(!P.started);
    coop_gear_probe_observe((uintptr_t)heap,10,&sample,1000000);
    assert(P.started && P.done && P.count<10 && P.ncandidates==1 && P.poses==1);
    assert(!memcmp(before,heap,sizeof heap));
    char path[192]; path_text(P.candidates[0].node,path); assert(!strcmp(path,"actor->0x238->0x3e0"));
    unsigned was=P.poses; pointer(0x1000+0x3e0,0);
    coop_gear_probe_observe((uintptr_t)heap,10,&sample,1250000); assert(P.poses==was); // stale edge
    sample.generation=2; coop_gear_probe_observe((uintptr_t)heap,10,&sample,1500000); assert(P.revoked);
    unsigned previous_reads=reads; coop_gear_probe_observe((uintptr_t)heap,10,&sample,1750000); assert(reads==previous_reads);
    coop_gear_probe_init("synthetic",1); sample.generation=1;
    pointer(0x1000+0x3e0,(uintptr_t)heap+0x2000);
    coop_gear_probe_observe((uintptr_t)heap,10,&sample,1000000);
    memset(&sample.equipment,0,sizeof sample.equipment);
    coop_gear_probe_observe((uintptr_t)heap,10,&sample,1250000); assert(P.revoked);
    // Observe an original reference setter, then the native actor's own ModelUnit.
    coop_gear_probe_init("synthetic",1); sample.generation=1;
    strcpy(sample.equipment.actor[0],"Weapon_Sword_101");
    uint64_t item=(uintptr_t)heap+0x5000, meta=(uintptr_t)heap+0x5700, ref=(uintptr_t)heap+0x5800;
    pointer(0x5000+0x1a8,meta); pointer(0x5000+0x218,(uintptr_t)actor_name);
    pointer(0x5000+0x238,(uintptr_t)heap+0x1000); pointer(0x5700+0x40,item); pointer(0x5808,meta);
    int32_t id=17; memcpy(heap+0x5010,&id,4); memcpy(heap+0x5748,&id,4); memcpy(heap+0x5810,&id,4);
    coop_gear_probe_reference(ref,item,1234); assert(reference_claimed==1);
    for(int n=0;n<100;n++) coop_gear_probe_reference(ref,item,1234);
    assert(reference_claimed==1); // repeated setters cannot exhaust the distinct-identity ring
    memcpy(before,heap,sizeof heap);
    coop_gear_probe_observe((uintptr_t)heap,10,&sample,1000000);
    assert(P.reference_poses==1 && !memcmp(before,heap,sizeof heap));
    id=18; memcpy(heap+0x5010,&id,4); memcpy(heap+0x5748,&id,4); memcpy(heap+0x5810,&id,4);
    coop_gear_probe_observe((uintptr_t)heap,10,&sample,1500000); assert(P.reference_poses==1); // pooled reuse rejected
    // The model can be embedded rather than the object's apparent base address.
    coop_gear_probe_init("synthetic",1); id=17;
    memcpy(heap+0x5010,&id,4); memcpy(heap+0x5748,&id,4); memcpy(heap+0x5810,&id,4);
    pointer(0x1000+0xb0,(uintptr_t)model_name); pointer(0x1000+0x478,(uintptr_t)heap+0x3000);
    coop_gear_probe_reference(ref,item,1234);
    coop_gear_probe_observe((uintptr_t)heap,10,&sample,1000000);
    assert(P.reference_poses==1 && references[0].model_node==1 && references[0].model_delta==0x20);
    pointer(0x5000+0x238,(uintptr_t)heap+0x1800);
    coop_gear_probe_observe((uintptr_t)heap,10,&sample,1500000);
    assert(P.reference_poses==1 && references[0].model_lost);
    puts("co-op gear graph: timed opt-in, bounded traversal, cycles, stale paths, identity revocation and read-only memory passed");
}
'''

def main():
    output=ROOT/'build/tests'; output.mkdir(parents=True,exist_ok=True)
    compiler='C:/msys64/ucrt64/bin/clang.exe'
    with tempfile.TemporaryDirectory(prefix='gear-probe-',dir=output) as temporary:
        folder=Path(temporary); (folder/'check.c').write_text(HARNESS)
        exe=folder/'check.exe'
        env=dict(os.environ,PATH=str(Path(compiler).parent)+os.pathsep+os.environ.get('PATH',''))
        subprocess.run([compiler,'-std=gnu11','-O2','-Wall','-Wextra','-Werror','-I',str(ROOT/'runtime'),
                        '-I','C:/msys64/ucrt64/include',str(folder/'check.c'),'-o',str(exe)],check=True,env=env)
        subprocess.run([str(exe)],check=True,env=env)

if __name__=='__main__': main()
