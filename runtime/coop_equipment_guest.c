// Read-only pouch array layouts and MurmurHash3 adapted from arnaldolima1/totk-recomp
// runtime/game_flags.c mmh3, number_of, game_int_array_get and game_str_array_get,
// and runtime/game_gear.c game_player_gear @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c.
// MIT, Copyright (c) 2026 Valiantsin Dzerakh; third_party/licenses/totk-recomp.txt.
// No flags watcher, heap search, inventory writes, file I/O or allocation. All
// references and values are reread before publishing an optional copied snapshot.
#include "coop_equipment.h"
#include "host.h"
#include "layout.h"
#include "platform/platform.h"
#include <stdio.h>
#include <string.h>

static int rd(uint64_t at, void *out, size_t size) {
    return at>=0x10000 && at<(1ull<<47) && size<(1ull<<47)-at &&
           mem_guest_readable(at,size) && plat_mem_read(at,out,size);
}
static uint32_t name_hash(const char *s) {
    uint32_t h=0, n=(uint32_t)strlen(s), k;
    const uint8_t *p=(const uint8_t *)s;
    for (uint32_t i=0;i+4<=n;i+=4) {
        k=(uint32_t)p[i] | (uint32_t)p[i+1]<<8 | (uint32_t)p[i+2]<<16 | (uint32_t)p[i+3]<<24;
        k*=0xcc9e2d51u; k=k<<15|k>>17; k*=0x1b873593u;
        h^=k; h=h<<13|h>>19; h=h*5+0xe6546b64u;
    }
    k=0;
    for (uint32_t i=n&~3u, shift=0;i<n;i++,shift+=8) k|=(uint32_t)p[i]<<shift;
    if (n&3) { k*=0xcc9e2d51u; k=k<<15|k>>17; k*=0x1b873593u; h^=k; }
    h^=n; h^=h>>16; h*=0x85ebca6bu; h^=h>>13; h*=0xc2b2ae35u; h^=h>>16;
    return h;
}
typedef struct { uint64_t words[5], address; uint32_t count, cap, stride; } EquipTable;
static int table(uint64_t address, uint32_t stride, EquipTable *out) {
    EquipTable t={.address=address,.stride=stride};
    if (!rd(address,t.words,sizeof t.words)) return 0;
    t.count=(uint32_t)t.words[1]; t.cap=(uint32_t)(t.words[4]>>32);
    if (t.words[0]<MOD_MAIN_BASE || t.words[0]>=MOD_MAIN_BASE+MOD_MAIN_SIZE ||
        !t.count || t.count>200000 || t.cap<t.count || t.cap>800000 ||
        t.words[2]<0x10000 || t.words[2]>=(1ull<<47)-(uint64_t)t.count*stride ||
        t.words[3]<0x10000 || t.words[3]>=(1ull<<47)-8ull*t.cap) return 0;
    *out=t; return 1;
}
static uint64_t entry(const EquipTable *t, uint32_t hash) {
    // Valid maps normally need only a few probes. Corrupt/collision-heavy maps
    // cannot turn one observation into an unbounded walk through guest memory.
    uint32_t at=hash%t->cap;
    for (unsigned tries=0;tries<64 && tries<t->cap;tries++,at=at+1==t->cap ? 0 : at+1) {
        uint32_t pair[2];
        if (!rd(t->words[3]+8ull*at,pair,sizeof pair) || !pair[1]) return 0;
        if (pair[0]==hash) return pair[1]<t->count ? t->words[2]+(uint64_t)t->stride*pair[1] : 0;
    }
    return 0;
}
static int equipped(const EquipTable *ints, const EquipTable *names, CoopEquipment *out) {
    static const char *const kinds[]={"Weapon","Shield","Bow"};
    for (int slot=0;slot<COOP_EQUIP_SLOTS;slot++) {
        char key[64];
        snprintf(key,sizeof key,"Pouch.%s.EquipIndex",kinds[slot]);
        uint64_t e=entry(ints,name_hash(key)), values=0;
        uint32_t count=0;
        int32_t index=-2;
        if (!e || !rd(e+0x20,&count,4) || !count || count>4096 ||
            !rd(e+0x28,&values,8) || !rd(values,&index,4) || index < -1 || index>=4096) return 0;
        if (index==-1) continue;
        snprintf(key,sizeof key,"Pouch.%s.Content.Name",kinds[slot]);
        e=entry(names,name_hash(key));
        if (!e || !rd(e+0x70,&count,4) || !count || count>4096 || (uint32_t)index>=count ||
            !rd(e+0x78,&values,8) || values<0x10000 || values>=(1ull<<47)-0x50ull*count) return 0;
        char text[64];
        if (!rd(values+0x50ull*(uint32_t)index+0xc,text,sizeof text)) return 0;
        const char *end=memchr(text,0,sizeof text);
        if (!end || end==text || (size_t)(end-text)>=COOP_EQUIP_NAME) return 0;
        memcpy(out->actor[slot],text,(size_t)(end-text));
    }
    return coop_equipment_valid(out);
}
int coop_equipment_observe(CoopEquipment *out) {
    if (rt_game_version!=143 || !out) return 0;
    uint64_t manager=0, vtable=0, after=0;
    uint64_t root=MOD_MAIN_BASE+0x3ad66b0ull;
    if (!rd(root,&manager,8) || !manager || !rd(manager+8,&vtable,8) ||
        vtable!=MOD_MAIN_BASE+0x39403d0ull) return 0;
    EquipTable ints, names;
    if (!table(manager+8+3*0x60,64,&ints) || !table(manager+8+17*0x60,144,&names)) return 0;
    CoopEquipment first={0}, second={0};
    uint64_t ia[5], sa[5];
    if (!equipped(&ints,&names,&first) || !equipped(&ints,&names,&second) ||
        memcmp(&first,&second,sizeof first) || !rd(root,&after,8) || after!=manager ||
        !rd(manager+8,&after,8) || after!=vtable ||
        !rd(ints.address,ia,sizeof ia) || memcmp(ia,ints.words,sizeof ia) ||
        !rd(names.address,sa,sizeof sa) || memcmp(sa,names.words,sizeof sa)) return 0;
    *out=first; return 1;
}
