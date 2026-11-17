"""Check the bounded 1.4.3 pouch observer with authored guest memory, not game files."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include <assert.h>
#include "coop_equipment.c"
#include "coop_equipment_guest.c"
const int rt_game_version=143;
static uint64_t global;
static unsigned char manager[0x800], ints[4*64], names[4*144], strings[3][0x50];
static uint32_t imap[17][2], smap[17][2];
static int32_t indexes[3];
static int unstable, index_reads;
static unsigned reads;
static int range(uint64_t at,uint64_t n,const void *base,uint64_t size) {
    return n<=size && at>=(uintptr_t)base && at-(uintptr_t)base<=size-n;
}
int mem_guest_readable(uint64_t at,uint64_t n) {
    if(at==MOD_MAIN_BASE+0x3ad66b0ull && n==8) return 1;
    return range(at,n,manager,sizeof manager) || range(at,n,ints,sizeof ints) || range(at,n,names,sizeof names) ||
        range(at,n,strings,sizeof strings) || range(at,n,imap,sizeof imap) || range(at,n,smap,sizeof smap) ||
        range(at,n,indexes,sizeof indexes);
}
int plat_mem_read(uint64_t at,void *out,size_t n) {
    reads++;
    if(!mem_guest_readable(at,n)) return 0;
    if(at==MOD_MAIN_BASE+0x3ad66b0ull) { memcpy(out,&global,n); return 1; }
    if(at==(uintptr_t)indexes && unstable && ++index_reads==2) indexes[0]=-1;
    memcpy(out,(const void *)(uintptr_t)at,n); return 1;
}
static void ptr(void *out,uint64_t value) { memcpy(out,&value,8); }
static void u32(void *out,uint32_t value) { memcpy(out,&value,4); }
static void insert(uint32_t map[17][2],const char *name,uint32_t index) {
    uint32_t hash=name_hash(name), at=hash%17;
    while(map[at][1]) at=(at+1)%17;
    map[at][0]=hash; map[at][1]=index;
}
int main(void) {
    global=(uintptr_t)manager;
    ptr(manager+8,MOD_MAIN_BASE+0x39403d0ull);
    uint64_t it[5]={MOD_MAIN_BASE+0x100,4,(uintptr_t)ints,(uintptr_t)imap,17ull<<32};
    uint64_t st[5]={MOD_MAIN_BASE+0x200,4,(uintptr_t)names,(uintptr_t)smap,17ull<<32};
    memcpy(manager+8+3*0x60,it,sizeof it); memcpy(manager+8+17*0x60,st,sizeof st);
    const char *kinds[]={"Weapon","Shield","Bow"};
    const char *actors[]={"Weapon_Sword_101","Weapon_Shield_040","Weapon_Bow_001"};
    for(int k=0;k<3;k++) {
        char key[64]; snprintf(key,sizeof key,"Pouch.%s.EquipIndex",kinds[k]); insert(imap,key,k+1);
        snprintf(key,sizeof key,"Pouch.%s.Content.Name",kinds[k]); insert(smap,key,k+1);
        u32(ints+(k+1)*64+0x20,1); ptr(ints+(k+1)*64+0x28,(uintptr_t)(indexes+k));
        u32(names+(k+1)*144+0x70,1); ptr(names+(k+1)*144+0x78,(uintptr_t)strings[k]);
        strcpy((char *)strings[k]+12,actors[k]);
    }
    CoopEquipment out, prior;
    memset(&prior,0x55,sizeof prior); out=prior;
    unsigned char before[sizeof manager]; memcpy(before,manager,sizeof manager);
    assert(coop_equipment_observe(&out));
    for(int k=0;k<3;k++) assert(!strcmp(out.actor[k],actors[k]));
    assert(!memcmp(before,manager,sizeof manager));
    indexes[0]=-1; assert(coop_equipment_observe(&out) && !out.actor[0][0] && out.actor[1][0]);
    indexes[0]=1; out=prior; assert(!coop_equipment_observe(&out) && !memcmp(&out,&prior,sizeof out));
    indexes[0]=0; unstable=1; index_reads=0; assert(!coop_equipment_observe(&out)); unstable=0; indexes[0]=0;
    ptr(manager+8,MOD_MAIN_BASE+0x100); assert(!coop_equipment_observe(&out));
    ptr(manager+8,MOD_MAIN_BASE+0x39403d0ull);
    strings[0][12]='/'; assert(!coop_equipment_observe(&out)); strings[0][12]='W';
    memset(strings[0]+12,'a',64); assert(!coop_equipment_observe(&out)); strcpy((char *)strings[0]+12,actors[0]);
    ptr(names+144+0x78,UINT64_MAX-16); assert(!coop_equipment_observe(&out));
    ptr(names+144+0x78,(uintptr_t)strings[0]);
    for(unsigned k=0;k<17;k++) { imap[k][0]=0; imap[k][1]=1; }
    reads=0; assert(!coop_equipment_observe(&out) && reads<30); // no unbounded map scan
    puts("co-op equipment observer: stable pouch identities, unequip, invalid pointers, strings, map bounds and read-only capture passed");
}
'''

def main():
    out=ROOT/'build/tests'
    out.mkdir(parents=True,exist_ok=True)
    cc='C:/msys64/ucrt64/bin/clang.exe'
    with tempfile.TemporaryDirectory(prefix='equipment-',dir=out) as temporary:
        folder=Path(temporary)
        (folder/'layout.h').write_text('#define MOD_MAIN_BASE 0x7000000000ull\n#define MOD_MAIN_SIZE 0x3adf000ull\n')
        (folder/'check.c').write_text(HARNESS)
        exe=folder/'check.exe'
        env=dict(os.environ,PATH=str(Path(cc).parent)+os.pathsep+os.environ.get('PATH',''))
        subprocess.run([cc,'-std=gnu11','-O2','-Wall','-Wextra','-Werror','-I',str(folder),
                        '-I',str(ROOT/'runtime'),'-I','C:/msys64/ucrt64/include',str(folder/'check.c'),'-o',str(exe)],check=True,env=env)
        subprocess.run([str(exe)],check=True,env=env)

if __name__=='__main__': main()
