// Synthetic ENet peer for a single copied-profile native NPC diagnostic. No game, renderer or guest pointers.
#include "coop_net.h"
#include "platform/platform.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc != 4 || strlen(argv[2]) != 64) return 2;
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
