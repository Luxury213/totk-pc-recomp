// Two actual ENet workers with production platform threads/locks, without loading the game or renderer.
#include "coop_net.h"
#include "platform/platform.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void publish(CoopNet *h,CoopNet *c) {
    CoopSample a={.generation=1,.flags=COOP_SAMPLE_PLAYER,.pos={10,20,30},.time_ns=plat_now_ns()};
    coop_net_publish(h,&a); a.pos[0]=40; coop_net_publish(c,&a);
}
static void connected(CoopNet *h,CoopNet *c) {
    uint64_t until=plat_now_ns()+7000000000ull;
    CoopNetSnapshot a,b;
    do {
        publish(h,c); coop_net_snapshot(h,&a); coop_net_snapshot(c,&b);
        if(a.negotiated && b.negotiated && a.has_remote && b.has_remote) {
            assert(a.session==b.session && a.remote.pos[0]==40 && b.remote.pos[0]==10);
            assert(a.state==COOP_SESSION_LOADING && b.state==COOP_SESSION_LOADING);
            return;
        }
        plat_sleep_ms(10);
    }while(plat_now_ns()<until);
    fprintf(stderr,"connection timeout: host=%d %s client=%d %s\n",a.state,a.error,b.state,b.error);
    abort();
}
int main(int argc,char **argv) {
    assert(argc==3 || argc==4); uint16_t port=(uint16_t)atoi(argv[1]);
    uint64_t id1=0,id2=0;
    assert(coop_net_player_id(argv[2],&id1)); assert(coop_net_player_id(argv[2],&id2)); assert(id1 && id1==id2);
    CoopNet *h=coop_net_create(),*c=coop_net_create(); assert(h && c);
    CoopNetConfig a={.mode=1,.port=port,.game_version=143,.player=11,.capabilities=COOP_CAP_PRESENCE};
    a.content_id[0]=99;
    CoopNetConfig b=a; b.mode=2; b.player=22; strcpy(b.ip,"127.0.0.1");
    if(argc==4) b.port=(uint16_t)atoi(argv[3]);
    coop_net_configure(h,&a); plat_sleep_ms(100); coop_net_configure(c,&b);
    connected(h,c); CoopNetSnapshot before; coop_net_snapshot(h,&before);
    for(unsigned i=0;i<50;i++) {
        char text[96]; snprintf(text,sizeof text,"Reliable notice %u",i);
        assert(coop_net_notice(c,text));
    }
    uint64_t until=plat_now_ns()+5000000000ull;
    CoopNetSnapshot view;
    do {
        publish(h,c); coop_net_snapshot(h,&view);
        if(view.notices==50) break;
        plat_sleep_ms(10);
    }while(plat_now_ns()<until);
    assert(view.notices==50 && !strcmp(view.notice,"Reliable notice 49"));
    // No UI/render tick is called anywhere in this program. Transport and reliable delivery are autonomous.
    plat_sleep_ms(1700); coop_net_snapshot(h,&view); assert(view.negotiated && !view.has_remote);
    connected(h,c);
    b.mode=0; coop_net_configure(c,&b);
    until=plat_now_ns()+7000000000ull;
    do { coop_net_snapshot(h,&view); if(!view.negotiated) break; plat_sleep_ms(10); }while(plat_now_ns()<until);
    assert(!view.negotiated && !view.has_remote && view.state==COOP_SESSION_WAITING);
    b.mode=2; coop_net_configure(c,&b); connected(h,c); coop_net_snapshot(h,&view);
    assert(view.session!=before.session && !view.notices);
    coop_net_destroy(c); coop_net_destroy(h);
    char identity[4096]; snprintf(identity,sizeof identity,"%s/coop-player-id.bin",argv[2]);
    assert(plat_file_write_atomic(identity,"bad",3));
    assert(!coop_net_player_id(argv[2],&id1) && plat_file_size(identity)==3);

    h=coop_net_create(); c=coop_net_create(); assert(h && c);
    b.content_id[0]^=1;
    coop_net_configure(h,&a); plat_sleep_ms(100); coop_net_configure(c,&b);
    until=plat_now_ns()+5000000000ull;
    do { coop_net_snapshot(h,&view); if(view.state==COOP_SESSION_INCOMPATIBLE) break; plat_sleep_ms(10); }while(plat_now_ns()<until);
    assert(view.state==COOP_SESSION_INCOMPATIBLE && !view.has_remote);
    coop_net_destroy(c); coop_net_destroy(h);
    puts("co-op ENet: two workers, independent movement, 50 reliable notices, stale observations, disconnect/reconnect, new epochs and incompatible content passed");
    return 0;
}
