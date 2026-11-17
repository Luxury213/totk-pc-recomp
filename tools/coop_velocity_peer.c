// Synthetic ENet peer for a single copied-profile native NPC diagnostic. No game, renderer or guest pointers.
#include "coop_net.h"
#include "platform/platform.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Round-trip real captured poses through a separate ENet worker. Position is offset
// for inspection only; this tool never creates or controls a guest actor.
static int pose_echo(CoopNet *net) {
    uint64_t begin=plat_now_ns(), last_capture=0, session=0;
    uint32_t generation=0;
    unsigned samples=0, bodies=0, changed=0, equipment=0, equipped=0, equipment_changes=0;
    CoopBody previous={0};
    CoopEquipment previous_equipment={0};
    while (plat_now_ns()-begin < 90000000000ull) {
        CoopNetSnapshot view; coop_net_snapshot(net,&view);
        if (samples && (!view.negotiated || view.session!=session)) break;
        if (view.negotiated && view.has_remote &&
            (view.remote.time_ns!=last_capture || view.remote.generation!=generation)) {
            CoopSample sample=view.remote;
            session=view.session; last_capture=sample.time_ns; generation=sample.generation;
            samples++;
            if (sample.flags & COOP_SAMPLE_EQUIPMENT) {
                int different=memcmp(&previous_equipment,&sample.equipment,sizeof previous_equipment)!=0;
                if (equipment && different) equipment_changes++;
                if (!equipment || different) {
                    printf("peer: equipment echo: weapon %s, shield %s, bow %s\n",
                           sample.equipment.actor[0],sample.equipment.actor[1],sample.equipment.actor[2]);
                    fflush(stdout);
                }
                previous_equipment=sample.equipment; equipment++;
                equipped+=sample.equipment.actor[0][0] || sample.equipment.actor[1][0] || sample.equipment.actor[2][0];
            }
            if (sample.flags & COOP_SAMPLE_BODY) {
                if (bodies && memcmp(&previous,&sample.body,sizeof previous)) changed++;
                previous=sample.body; bodies++;
            }
            sample.pos[0]+=3; sample.time_ns=plat_now_ns();
            coop_net_publish(net,&sample);
            if (samples==1 || samples%30==0) {
                printf("peer: pose echo: samples %u, bodies %u, changed %u, animation %s\n",
                       samples,bodies,changed,sample.animation);
                fflush(stdout);
            }
        }
        plat_sleep_ms(10);
    }
    int ok=bodies>=10 && changed>0;
    printf("peer: pose echo %s: samples %u, bodies %u, changed %u\n",
           ok ? "completed" : "failed",samples,bodies,changed);
    printf("peer: equipment echo completed: samples %u, equipped %u, changes %u\n",equipment,equipped,equipment_changes);
    return ok ? 0 : 1;
}

int main(int argc, char **argv) {
    int echo=argc==5 && !strcmp(argv[4],"--pose-echo");
    if ((argc != 4 && !echo) || strlen(argv[2]) != 64) return 2;
    char *end;
    unsigned long port = strtoul(argv[1], &end, 10);
    if (*end || port < 1024 || port > 65535) return 2;
    CoopNetConfig config = {.mode=2,.port=(uint16_t)port,.game_version=143,.capabilities=COOP_CAP_PRESENCE};
    strcpy(config.ip,"127.0.0.1");
    for (unsigned i=0; i<32; i++) {
        char byte[3]={argv[2][i*2],argv[2][i*2+1],0};
        unsigned long value=strtoul(byte,&end,16);
        if (*end) return 2;
        config.content_id[i]=(uint8_t)value;
    }
    if (!coop_net_player_id(argv[3],&config.player)) return 2;
    CoopNet *net=coop_net_create();
    if (!net) return 2;
    coop_net_configure(net,&config);
    if (echo) {
        int result=pose_echo(net);
        coop_net_destroy(net);
        return result;
    }
    uint64_t begin=plat_now_ns(), pulse=0;
    unsigned last_phase=99;
    int success=0;
    while (plat_now_ns()-begin < 90000000000ull) {
        uint64_t now=plat_now_ns();
        CoopNetSnapshot view;
        coop_net_snapshot(net,&view);
        if (!pulse && view.negotiated && view.has_remote && !strcmp(view.notice,"npc-velocity-ready-v1")) {
            pulse=now;
            printf("peer: native diagnostic ready; negotiated session %llu\n",(unsigned long long)view.session);
            fflush(stdout);
        }
        double elapsed=pulse ? (double)(now-pulse)/1e9 : -1;
        unsigned phase=elapsed<0 ? 0 : elapsed<1.2 ? 1 : elapsed<2.1 ? 2 : elapsed<3.3 ? 3 :
                       elapsed<4.2 ? 4 : elapsed<5.4 ? 5 : 6;
        if (phase!=last_phase) {
            printf("peer: phase %u\n",phase); fflush(stdout); last_phase=phase;
        }
        // During each gap the worker remains connected and retransmits the same sample. That must not
        // renew the host's lease. The next publication resumes within the same session and generation.
        if (phase!=2 && phase!=4) {
            CoopSample sample={.generation=1,.flags=COOP_SAMPLE_PLAYER,.time_ns=now};
            sample.velocity[0]=phase==1 ? 2 : phase==3 ? -2 : phase==5 ? 1 : 0;
            sample.velocity[2]=phase==5 ? 1 : 0;
            coop_net_publish(net,&sample);
        }
        if (pulse && (!view.negotiated || !view.has_remote)) break;
        if (elapsed>=6.5) { success=1; break; }
        plat_sleep_ms(20);
    }
    coop_net_destroy(net);
    printf("peer: diagnostic sequence %s\n",success ? "completed" : "failed");
    return success ? 0 : 1;
}
