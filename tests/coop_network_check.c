// Two actual ENet workers with production platform threads/locks, without loading the game or renderer.
#include "coop_net.h"
#include "platform/platform.h"
#include <enet/enet.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void publish(CoopNet *h,CoopNet *c) {
    CoopSample a={.generation=1,.flags=COOP_SAMPLE_PLAYER,.pos={10,20,30},.time_ns=plat_now_ns()};
    a.flags |= COOP_SAMPLE_ROTATION | COOP_SAMPLE_ANIMATION;
    a.rotation[3]=1; strcpy(a.animation,"Nml_Wait"); a.animation_frame=7.5f;
    a.flags |= COOP_SAMPLE_BODY;
    for(unsigned i=0;i<COOP_BODY_BONES;i++) a.body.q[i][3]=1;
    a.body.t[0][0]=1.25f;
    a.flags |= COOP_SAMPLE_EQUIPMENT;
    strcpy(a.equipment.actor[0],"Weapon_Sword_101");
    strcpy(a.equipment.actor[1],"Weapon_Shield_040");
    coop_net_publish(h,&a);
    a.pos[0]=40; a.rotation[3]=0; a.rotation[0]=1;
    strcpy(a.equipment.actor[0],"Weapon_Spear_001");
    strcpy(a.animation,"Sword_Synthetic"); a.animation_frame=17.25f; coop_net_publish(c,&a);
}
static void connected(CoopNet *h,CoopNet *c) {
    uint64_t until=plat_now_ns()+7000000000ull;
    CoopNetSnapshot a,b;
    do {
        publish(h,c); coop_net_snapshot(h,&a); coop_net_snapshot(c,&b);
        if(a.negotiated && b.negotiated && a.has_remote && b.has_remote) {
            assert(a.session==b.session && a.remote.pos[0]==40 && b.remote.pos[0]==10);
            assert(!strcmp(a.remote.animation,"Sword_Synthetic") && a.remote.animation_frame==17.25f);
            assert(!strcmp(b.remote.animation,"Nml_Wait") && b.remote.animation_frame==7.5f);
            assert(a.remote.rotation[0]==1 && b.remote.rotation[3]==1);
            assert((a.remote.flags & b.remote.flags & COOP_SAMPLE_EQUIPMENT) &&
                   !strcmp(a.remote.equipment.actor[0],"Weapon_Spear_001") &&
                   !strcmp(b.remote.equipment.actor[0],"Weapon_Sword_101"));
            assert((a.remote.flags & b.remote.flags & COOP_SAMPLE_BODY) &&
                   a.remote.body.q[57][3]==1 && b.remote.body.t[0][0]==1.25f);
            assert(a.state==COOP_SESSION_LOADING && b.state==COOP_SESSION_LOADING);
            return;
        }
        plat_sleep_ms(10);
    }while(plat_now_ns()<until);
    fprintf(stderr,"connection timeout: host=%d %s client=%d %s\n",a.state,a.error,b.state,b.error);
    abort();
}
static void rejected(CoopNet *h,CoopNet *c) {
    uint64_t until=plat_now_ns()+5000000000ull;
    CoopNetSnapshot a,b;
    do {
        coop_net_snapshot(h,&a); coop_net_snapshot(c,&b);
        assert(!a.negotiated && !a.has_remote && !b.negotiated && !b.has_remote);
        if(a.state==COOP_SESSION_INCOMPATIBLE && b.state==COOP_SESSION_INCOMPATIBLE) break;
        plat_sleep_ms(10);
    }while(plat_now_ns()<until);
    if(a.state!=COOP_SESSION_INCOMPATIBLE || b.state!=COOP_SESSION_INCOMPATIBLE)
        fprintf(stderr,"content rejection timeout: host state=%d tx=%u rx=%u rejected=%u error=%s; client state=%d tx=%u rx=%u rejected=%u error=%s\n",
            a.state,a.packets_tx,a.packets_rx,a.rejected,a.error,b.state,b.packets_tx,b.packets_rx,b.rejected,b.error);
    assert(a.state==COOP_SESSION_INCOMPATIBLE && b.state==COOP_SESSION_INCOMPATIBLE);
    // A late transport completion must not erase the reason already published to either UI.
    until=plat_now_ns()+600000000ull;
    do {
        coop_net_snapshot(h,&a); coop_net_snapshot(c,&b);
        assert(a.state==COOP_SESSION_INCOMPATIBLE && b.state==COOP_SESSION_INCOMPATIBLE);
        assert(!a.negotiated && !a.has_remote && !b.negotiated && !b.has_remote);
        plat_sleep_ms(10);
    }while(plat_now_ns()<until);
}
static void rejected_protocol(CoopNet *h,uint16_t port) {
    ENetHost *legacy=enet_host_create(NULL,1,2,0,0); assert(legacy);
    ENetAddress address={.port=port}; assert(enet_address_set_host_ip(&address,"127.0.0.1")==0);
    assert(enet_host_connect(legacy,&address,2,COOP_PROTOCOL-1));
    uint64_t until=plat_now_ns()+5000000000ull;
    int disconnected=0; CoopNetSnapshot view;
    do {
        ENetEvent event;
        while(enet_host_service(legacy,&event,0)>0) {
            if(event.type==ENET_EVENT_TYPE_RECEIVE) { enet_packet_destroy(event.packet); assert(!"legacy peer received application state"); }
            if(event.type==ENET_EVENT_TYPE_DISCONNECT) { assert(event.data==2); disconnected=1; }
        }
        enet_host_flush(legacy); coop_net_snapshot(h,&view);
        if(view.state==COOP_SESSION_INCOMPATIBLE && disconnected) break;
        plat_sleep_ms(10);
    }while(plat_now_ns()<until);
    if(!disconnected || view.state!=COOP_SESSION_INCOMPATIBLE)
        fprintf(stderr,"protocol rejection timeout: state=%d rejected=%u disconnected=%d error=%s\n",
            view.state,view.rejected,disconnected,view.error);
    assert(disconnected && view.state==COOP_SESSION_INCOMPATIBLE && view.rejected && !view.has_remote);
    assert(strstr(view.error,"protocol")); enet_host_destroy(legacy);
}
int main(int argc,char **argv) {
    assert(argc==3 || argc==4 || argc==5); uint16_t port=(uint16_t)atoi(argv[1]);
    uint64_t id1=0,id2=0;
    assert(coop_net_player_id(argv[2],&id1)); assert(coop_net_player_id(argv[2],&id2)); assert(id1 && id1==id2);
    CoopNet *h=coop_net_create(),*c=coop_net_create(); assert(h && c);
    CoopNetConfig a={.mode=1,.port=port,.game_version=143,.player=11,.capabilities=COOP_CAP_PRESENCE};
    a.content_id[0]=99;
    CoopNetConfig b=a; b.mode=2; b.player=22; strcpy(b.ip,"127.0.0.1");
    if(argc>=4) b.port=(uint16_t)atoi(argv[3]);
    if(argc==5) {
        if(!strcmp(argv[4],"reject-protocol-loss")) {
            coop_net_configure(h,&a); plat_sleep_ms(100);
            rejected_protocol(h,b.port);
            coop_net_destroy(c); coop_net_destroy(h);
            puts("co-op ENet: old protocol rejection survives a lost disconnect passed");
            return 0;
        }
        assert(!strcmp(argv[4],"reject-loss"));
        b.content_id[0]^=1;
        coop_net_configure(h,&a); plat_sleep_ms(100); coop_net_configure(c,&b);
        rejected(h,c);
        b.content_id[0]^=1; coop_net_configure(c,&b);
        connected(h,c); // a valid connection can follow rejection on the still-running host
        coop_net_destroy(c); coop_net_destroy(h);
        puts("co-op ENet: both peers retain incompatibility after a lost disconnect, then reconnect passed");
        return 0;
    }
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
    rejected(h,c);
    coop_net_destroy(c); coop_net_destroy(h);
    // A previous protocol must fail visibly at connection, before any application state is accepted.
    h=coop_net_create(); assert(h); coop_net_configure(h,&a); plat_sleep_ms(100);
    rejected_protocol(h,b.port); coop_net_destroy(h);
    puts("co-op ENet: independent movement/rotation/animation, 50 reliable notices, stale observations, reconnect and incompatible content passed");
    return 0;
}
