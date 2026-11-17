// Model name/palette layout and pointer-path research informed by arnaldolima1/totk-recomp
// runtime/anim_probe.c model_probe and runtime/game_gear.c named/place_of_n
// @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c (MIT).
// Copyright (c) 2026 Valiantsin Dzerakh; third_party/licenses/totk-recomp.txt.
// This bounded observer is ours. Reachability and name agreement are research
// evidence only, not proof that an object is exclusively owned by the player.
#include "coop_gear_probe.h"
#include "host.h"
#include "platform/platform.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { NODES=2048, SEEN=4096, DEPTH=6, PER_TICK=16, CANDIDATES=24, LOG_LIMIT=128, BRANCHES=130 };
typedef struct { uint64_t address; int parent; uint16_t offset; uint8_t depth, branch; } GearNode;
static struct {
    int armed, started, done, revoked;
    unsigned count, next, ncandidates, logs, poses, reference_poses, pruned, branch_count[BRANCHES];
    uint64_t actor, components, seen[SEEN];
    uint32_t actor_id, generation;
    int64_t next_pose_us;
    CoopEquipment wanted, current;
    char models[COOP_EQUIP_SLOTS][64];
    GearNode nodes[NODES];
    struct { unsigned node, slot; uint64_t resource, palette; } candidates[CANDIDATES];
} P;
enum { REFERENCES=64 };
enum { MODEL_NODES=64, MODEL_DEPTH=3 };
typedef struct { uint64_t address; int parent; uint16_t offset; uint8_t depth; } ModelNode;
static unsigned reference_enabled, reference_claimed;
static struct {
    uint64_t reference, alternate, actor, metadata, caller;
    int32_t id;
    unsigned slot, ready, logged, inspected;
    unsigned model_count, model_next, model_node, model_lost;
    int model_delta;
    ModelNode models[MODEL_NODES];
} references[REFERENCES];

static int rd(uint64_t at, void *out, size_t n) {
    return at>=0x10000 && at<(1ull<<47) && n<(1ull<<47)-at && mem_guest_readable(at,n) && plat_mem_read(at,out,n);
}
static uint64_t ptr(uint64_t at) { uint64_t v=0; return rd(at,&v,8) ? v : 0; }
static int32_t word(uint64_t at) { int32_t v=-1; return rd(at,&v,4) ? v : -1; }

void coop_gear_probe_reference(uint64_t reference, uint64_t actor, uint64_t caller) {
    if (!__atomic_load_n(&reference_enabled,__ATOMIC_ACQUIRE) || rt_game_version!=143 ||
        reference<0x10000 || reference>=(1ull<<47)-0x18 || actor<0x10000 || actor>=(1ull<<47)-0x240) return;
    uint64_t metadata=ptr(actor+0x1a8), name=ptr(actor+0x218);
    int32_t id=word(actor+0x10);
    if (metadata<0x10000 || metadata>=(1ull<<47)-0x50 || id==-1 || ptr(metadata+0x40)!=actor || word(metadata+0x48)!=id) return;
    unsigned slot=COOP_EQUIP_SLOTS;
    for (unsigned s=0;s<COOP_EQUIP_SLOTS;s++) {
        size_t n=strlen(P.wanted.actor[s])+1; char text[48];
        if (n>1 && rd(name,text,n) && !memcmp(text,P.wanted.actor[s],n)) { slot=s; break; }
    }
    if (slot==COOP_EQUIP_SLOTS) return;
    for (unsigned i=0;i<REFERENCES;i++) {
        if (!__atomic_load_n(&references[i].ready,__ATOMIC_ACQUIRE) || references[i].actor!=actor ||
            references[i].metadata!=metadata || references[i].id!=id || references[i].slot!=slot) continue;
        uint64_t previous=__atomic_exchange_n(&references[i].reference,reference,__ATOMIC_ACQ_REL);
        if (previous!=reference) __atomic_store_n(&references[i].alternate,previous,__ATOMIC_RELEASE);
        return;
    }
    unsigned index=__atomic_load_n(&reference_claimed,__ATOMIC_RELAXED);
    for (unsigned tries=0;tries<8;tries++) {
        if (index>=REFERENCES) return;
        if (__atomic_compare_exchange_n(&reference_claimed,&index,index+1,1,__ATOMIC_RELAXED,__ATOMIC_RELAXED)) {
            references[index].reference=reference; references[index].actor=actor;
            references[index].metadata=metadata; references[index].caller=caller;
            references[index].id=id; references[index].slot=slot;
            __atomic_store_n(&references[index].ready,1,__ATOMIC_RELEASE);
            return;
        }
    }
}
static int heap_object(uint64_t at) {
    const RtGuestLayout *l=mem_layout();
    return l && at>=l->heap.base && at-l->heap.base<l->heap.size && !(at&7) && mem_guest_readable(at,8);
}
static int seen_add(uint64_t at) {
    unsigned h=(unsigned)((at>>4)^(at>>19))&(SEEN-1);
    for (unsigned i=0;i<SEEN;i++,h=(h+1)&(SEEN-1)) {
        if (P.seen[h]==at) return 0;
        if (!P.seen[h]) { P.seen[h]=at; return 1; }
    }
    return 0;
}
static int name_matches(uint64_t model, unsigned slot) {
    char name[64]={0}; uint64_t at=ptr(model+0x90);
    size_t n=strlen(P.models[slot])+1;
    return n>1 && n<=sizeof name && rd(at,name,n) && !memcmp(name,P.models[slot],n);
}
static int palette(uint64_t model, uint64_t *res, uint64_t *pal, float first[12]) {
    *res=ptr(model+0x458); *pal=*res ? ptr(*res+8) : 0;
    if (!*pal || !rd(*pal,first,48)) return 0;
    for (int i=0;i<12;i++) if (!isfinite(first[i]) || fabsf(first[i])>100000) return 0;
    for (int j=0;j<3;j++) {
        float n=first[j]*first[j]+first[4+j]*first[4+j]+first[8+j]*first[8+j];
        if (n<.0001f || n>10000) return 0;
    }
    return 1;
}

// Search only an identified equipment actor's ModelUnit. A model may be an
// embedded subobject, so locate its exact name field before interpreting +0x458.
// This is still discovery, not a verified ownership/accessor contract.
static uint64_t native_model(unsigned index, uint64_t actor, unsigned *budget) {
    uint64_t unit=ptr(actor+0x238);
    if (!heap_object(unit) || references[index].model_lost) return 0;
    unsigned slot=references[index].slot;
    if (!references[index].model_count) {
        references[index].models[0]=(ModelNode){unit,-1,0,0}; references[index].model_count=1;
    }
    if (references[index].models[0].address!=unit) { references[index].model_lost=1; return 0; }
    unsigned work=0;
    while (!references[index].model_node && references[index].model_next<references[index].model_count && *budget && work++<4) {
        unsigned node=references[index].model_next++;
        ModelNode current=references[index].models[node];
        uint64_t words[0x800/8]; (*budget)--;
        if (!rd(current.address,words,sizeof words)) continue;
        size_t length=strlen(P.models[slot])+1;
        for (unsigned k=0;k<sizeof words/sizeof *words;k++) {
            char text[64];
            if (length<=sizeof text && rd(words[k],text,length) && !memcmp(text,P.models[slot],length)) {
                int delta=(int)(k*8)-0x90;
                uint64_t model=current.address+(int64_t)delta, res,pal; float first[12];
                if (heap_object(model) && name_matches(model,slot) && palette(model,&res,&pal,first)) {
                    references[index].model_node=node+1; references[index].model_delta=delta;
                    rt_log("coop gear native model: slot %u, actor %#llx, model %#llx, depth %u, embedded delta %d; native entity, ownership unverified",
                        slot,(unsigned long long)actor,(unsigned long long)model,current.depth,delta);
                    break;
                }
            }
            if (current.depth>=MODEL_DEPTH || references[index].model_count>=MODEL_NODES || !heap_object(words[k])) continue;
            int seen=0;
            for (unsigned j=0;j<references[index].model_count;j++) seen|=references[index].models[j].address==words[k];
            if (seen) continue;
            unsigned next=references[index].model_count++;
            references[index].models[next]=(ModelNode){words[k],(int)node,(uint16_t)(k*8),(uint8_t)(current.depth+1)};
        }
    }
    if (!references[index].model_node) return 0;
    int node=(int)references[index].model_node-1, chain[MODEL_DEPTH], count=0;
    for (int i=node;i>0 && count<MODEL_DEPTH;i=references[index].models[i].parent) chain[count++]=i;
    uint64_t at=unit;
    while (count) {
        int i=chain[--count]; at=ptr(at+references[index].models[i].offset);
        if (at!=references[index].models[i].address) { references[index].model_lost=1; return 0; }
    }
    return at+(int64_t)references[index].model_delta;
}
static void path_text(unsigned node, char out[192]) {
    uint16_t offsets[DEPTH]; unsigned n=0;
    for (int i=(int)node;i>0 && n<DEPTH;i=P.nodes[i].parent) offsets[n++]=P.nodes[i].offset;
    size_t at=(size_t)snprintf(out,192,"actor");
    while (n && at<180) at+=(size_t)snprintf(out+at,192-at,"->%#x",offsets[--n]);
}
static unsigned add(uint64_t address, unsigned parent, unsigned offset, unsigned branch) {
    if (address==P.actor || P.count>=NODES || branch>=BRANCHES || P.nodes[parent].depth>=DEPTH || !heap_object(address)) return 0;
    unsigned quota=branch==0 ? 256 : branch==1 ? 1 : 12;
    if (P.branch_count[branch]>=quota) { P.pruned++; return 0; }
    if (!seen_add(address)) return 0;
    P.branch_count[branch]++;
    unsigned index=P.count++;
    P.nodes[index]=(GearNode){address,(int)parent,(uint16_t)offset,(uint8_t)(P.nodes[parent].depth+1),(uint8_t)branch};
    for (unsigned slot=0;slot<COOP_EQUIP_SLOTS;slot++) {
        if (!P.wanted.actor[slot][0] || strcmp(P.current.actor[slot],P.wanted.actor[slot]) || !name_matches(address,slot)) continue;
        uint64_t resource,pal; float first[12];
        if (!palette(address,&resource,&pal,first) || P.ncandidates>=CANDIDATES) continue;
        unsigned c=P.ncandidates++;
        P.candidates[c].node=index; P.candidates[c].slot=slot;
        P.candidates[c].resource=resource; P.candidates[c].palette=pal;
        char path[192]; path_text(index,path);
        if (P.logs++<LOG_LIMIT) rt_log("coop gear graph candidate: generation %u, slot %u, path %s, model %#llx, palette %#llx; reachability only",
            P.generation,slot,path,(unsigned long long)address,(unsigned long long)pal);
    }
    return index;
}

void coop_gear_probe_init(const char *profile, int timed) {
    __atomic_store_n(&reference_enabled,0,__ATOMIC_RELEASE);
    memset(&P,0,sizeof P);
    memset(references,0,sizeof references); reference_claimed=0;
    if (!profile || !timed || rt_game_version!=143) return;
    char path[1200]; snprintf(path,sizeof path,"%s/coop-gear-probe.tsv",profile);
    int64_t size=plat_file_size(path);
    if (size<1 || size>2048) return;
    uint64_t n=0; uint8_t *bytes=plat_file_read(path,&n);
    if (!bytes || n!=(uint64_t)size) { free(bytes); return; }
    char text[2049]; memcpy(text,bytes,(size_t)n); text[n]=0; free(bytes);
    if (memchr(text,0,(size_t)n)) return;
    char *line=strtok(text,"\n");
    if (!line || strcmp(line,"read-only-gear-graph-v1")) return;
    unsigned slots=0;
    while ((line=strtok(NULL,"\n"))!=NULL) {
        unsigned slot; char actor[48], model[64], extra;
        if (sscanf(line,"%u %47s %63s %c",&slot,actor,model,&extra)!=3 || slot>=COOP_EQUIP_SLOTS || (slots&(1u<<slot))) return;
        CoopEquipment check={0}; snprintf(check.actor[slot],48,"%s",actor);
        if (!coop_equipment_valid(&check)) return;
        for (const char *s=model;*s;s++) if (!((*s>='A'&&*s<='Z') || (*s>='a'&&*s<='z') || (*s>='0'&&*s<='9') || *s=='_' || *s=='.')) return;
        snprintf(P.wanted.actor[slot],48,"%s",actor); snprintf(P.models[slot],64,"%s",model); slots|=1u<<slot;
    }
    P.armed=slots!=0;
    __atomic_store_n(&reference_enabled,(unsigned)P.armed,__ATOMIC_RELEASE);
    if (P.armed) rt_log("coop gear graph: armed, node limit %u, depth limit %u, per tick %u; read-only diagnostic",NODES,DEPTH,PER_TICK);
}

void coop_gear_probe_observe(uint64_t actor, uint32_t actor_id, const CoopSample *s, int64_t world_us) {
    if (!P.armed || P.revoked || rt_game_version!=143) return;
    if (P.started && (world_us<0 || !(s->flags&COOP_SAMPLE_PLAYER) || !(s->flags&COOP_SAMPLE_EQUIPMENT) ||
        P.actor!=actor || P.actor_id!=actor_id || P.generation!=s->generation ||
        memcmp(&P.current,&s->equipment,sizeof P.current))) {
        P.revoked=1; __atomic_store_n(&reference_enabled,0,__ATOMIC_RELEASE);
        rt_log("coop gear graph: revoked after player/world/equipment identity changed; no attachment binding"); return;
    }
    if (world_us<1000000) return;
    if (!(s->flags&COOP_SAMPLE_PLAYER) || !(s->flags&COOP_SAMPLE_EQUIPMENT) || !actor || !s->generation) {
        return;
    }
    if (!P.started) {
        P.started=1; P.actor=actor; P.actor_id=actor_id; P.generation=s->generation; P.current=s->equipment;
        P.nodes[0]=(GearNode){actor,-1,0,0,0}; P.count=1; seen_add(actor);
        // ModelUnit gets its own budget. The component table's first128 words
        // seed separate branches, so one manager graph cannot starve all others.
        add(ptr(actor+0x238),0,0x238,0);
        P.components=ptr(actor+0x228);
        unsigned container=add(P.components,0,0x228,1);
        uint64_t components[128];
        if (container && rd(P.components,components,sizeof components))
            for (unsigned i=0;i<128;i++) add(components[i],container,i*8,i+2);
    }
    unsigned work=0;
    while (P.next<P.count && work++<PER_TICK) {
        unsigned index=P.next++; GearNode node=P.nodes[index];
        if (!index || node.address==P.components || node.depth>=DEPTH) continue;
        uint64_t object[0x800/8];
        if (!rd(node.address,object,sizeof object)) continue;
        for (unsigned i=0;i<sizeof object/sizeof *object;i++) add(object[i],index,i*8,node.branch);
    }
    if (!P.done && P.next==P.count) {
        P.done=1;
        rt_log("coop gear graph done: generation %u, nodes %u, candidates %u, capped %u; reachability only",
               P.generation,P.count,P.ncandidates,P.count==NODES || P.pruned!=0);
        rt_log("coop gear references: captured %u; original setter events only",
               __atomic_load_n(&reference_claimed,__ATOMIC_ACQUIRE));
    }
    if (world_us<P.next_pose_us || P.logs>=LOG_LIMIT) return;
    P.next_pose_us=world_us+500000;
    // The original game supplies these actor identities at its reference setter.
    // Revalidate the actor's metadata backlink and pool generation, and report
    // whether a recorded reference is still live. Temporary setters do not prove
    // exclusive ownership. No actor binding or native operation follows a pose.
    unsigned sampled_refs=0, model_work=PER_TICK;
    for (unsigned i=0;i<REFERENCES && P.logs<LOG_LIMIT;i++) {
        if (!__atomic_load_n(&references[i].ready,__ATOMIC_ACQUIRE)) continue;
        uint64_t a=references[i].actor, meta=references[i].metadata;
        uint64_t ref=__atomic_load_n(&references[i].reference,__ATOMIC_ACQUIRE);
        uint64_t alternate=__atomic_load_n(&references[i].alternate,__ATOMIC_ACQUIRE);
        unsigned slot=references[i].slot;
        if (sampled_refs&(1u<<slot) || strcmp(P.current.actor[slot],P.wanted.actor[slot]) ||
            ptr(a+0x1a8)!=meta ||
            ptr(meta+0x40)!=a || word(meta+0x48)!=references[i].id || word(a+0x10)!=references[i].id ||
            (uint32_t)word(a+0x24)-7u<5u) continue;
        uint64_t model_unit=ptr(a+0x238), model=native_model(i,a,&model_work);
        uint64_t res,pal; float first[12], pos[3];
        if (!references[i].inspected && P.logs<LOG_LIMIT) {
            references[i].inspected=1; P.logs++;
            char name[64]={0}; uint64_t np=model ? ptr(model+0x90) : 0;
            for (unsigned k=0;k<63;k++) {
                char ch;
                if (!rd(np+k,&ch,1) || !ch || ch<32 || ch>126) break;
                name[k]=ch;
            }
            rt_log("coop gear reference inspect: generation %u, slot %u, actor %#llx, model %#llx, name %s; native identity only",
                P.generation,slot,(unsigned long long)a,(unsigned long long)model,name);
        }
        if (!heap_object(model) || !name_matches(model,slot) || !palette(model,&res,&pal,first) ||
            !rd(a+0x2b4,pos,sizeof pos)) continue;
        float distance=0;
        for (int k=0;k<3;k++) distance+=(pos[k]-s->pos[k])*(pos[k]-s->pos[k]);
        if (!isfinite(distance) || distance>16) continue;
        if (ptr(a+0x1a8)!=meta ||
            ptr(meta+0x40)!=a || word(meta+0x48)!=references[i].id || word(a+0x10)!=references[i].id ||
            ptr(a+0x238)!=model_unit || native_model(i,a,&model_work)!=model || ptr(model+0x458)!=res || ptr(res+8)!=pal) continue;
        if (!references[i].logged) {
            references[i].logged=1;
            rt_log("coop gear reference candidate: generation %u, slot %u, actor %#llx, metadata id %d, caller %#llx; native identity, ownership unverified",
                P.generation,slot,(unsigned long long)a,references[i].id,(unsigned long long)references[i].caller);
        }
        unsigned reference_live=(ptr(ref+8)==meta && word(ref+0x10)==references[i].id) ||
            (ptr(alternate+8)==meta && word(alternate+0x10)==references[i].id);
        sampled_refs|=1u<<slot; P.logs++; P.reference_poses++;
        rt_log("coop gear reference pose: world us %lld, generation %u, slot %u, candidate %u, first %.6f %.6f %.6f; axes %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f %.6f; reference live %u; native model render origin",
            (long long)world_us,P.generation,slot,i,first[3],first[7],first[11],
            first[0],first[1],first[2],first[4],first[5],first[6],first[8],first[9],first[10],reference_live);
    }
    unsigned sampled=0;
    for (unsigned c=0;c<P.ncandidates && P.logs<LOG_LIMIT;c++) {
        unsigned index=P.candidates[c].node, slot=P.candidates[c].slot;
        if (sampled&(1u<<slot)) continue;
        int chain[DEPTH], count=0;
        for (int i=(int)index;i>0 && count<DEPTH;i=P.nodes[i].parent) chain[count++]=i;
        uint64_t at=actor;
        while (count) {
            int i=chain[--count]; at=ptr(at+P.nodes[i].offset);
            if (at!=P.nodes[i].address) { at=0; break; }
        }
        uint64_t resource,pal; float first[12];
        if (!at || !name_matches(at,slot) || !palette(at,&resource,&pal,first) ||
            resource!=P.candidates[c].resource || pal!=P.candidates[c].palette) continue;
        P.logs++; P.poses++;
        sampled|=1u<<slot;
        rt_log("coop gear graph pose: world us %lld, generation %u, candidate %u, slot %u, first %.6f %.6f %.6f; render origin, not actor space",
               (long long)world_us,P.generation,c,slot,first[3],first[7],first[11]);
    }
}
