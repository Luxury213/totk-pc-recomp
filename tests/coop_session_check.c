// No game data: production wire/session code is exercised with synthetic identities and world samples.
#include "coop_session.h"
#include "coop_interp.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static const uint8_t content[32] = {1,2,3};
static void negotiate(CoopSession *host, CoopSession *client, uint64_t nonce, uint32_t caps) {
    coop_session_init(host,1,143,content,11,nonce,7,caps);
    coop_session_init(client,0,143,content,22,0,123,caps);
    CoopMessage hello, welcome, empty;
    coop_session_hello(client,&hello);
    assert(coop_session_receive(host,&hello,&welcome)==COOP_RX_REPLY);
    assert(coop_session_receive(client,&welcome,&empty)==COOP_RX_ACCEPT);
    assert(host->session==client->session && host->session==nonce);
}

int main(void) {
    CoopSession h,c;
    CoopInterpolator buffer={0}; CoopSample frame={.generation=1,.flags=COOP_SAMPLE_PLAYER,.yaw=170};
    CoopSample visual;
    assert(!coop_interp_read(&buffer,1000000000,&visual));
    coop_interp_push(&buffer,&frame,1000000000);
    frame.pos[0]=10; frame.yaw=-170; coop_interp_push(&buffer,&frame,1100000000);
    assert(coop_interp_read(&buffer,1150000000,&visual));
    assert(fabsf(visual.pos[0]-5)<.001f && fabsf(visual.yaw-180)<.001f);
    assert(coop_interp_read(&buffer,5000000000,&visual) && visual.pos[0]==10);
    frame.generation=2; frame.pos[0]=100; coop_interp_push(&buffer,&frame,1200000000);
    assert(buffer.count==1 && coop_interp_read(&buffer,1250000000,&visual) && visual.pos[0]==100);
    negotiate(&h,&c,12345,COOP_CAP_PRESENCE);
    CoopMessage m,decoded,reply; uint8_t bytes[COOP_WIRE_MAX];
    CoopMessage stale_welcome={.kind=COOP_MSG_WELCOME,.player=11,.session=44,.seq=1,.game_version=121};
    assert(coop_session_receive(&c,&stale_welcome,&reply)==COOP_RX_IGNORE && c.negotiated);
    coop_session_hello(&c,&m); m.seq++; m.game_version=121;
    assert(coop_session_receive(&h,&m,&reply)==COOP_RX_IGNORE && h.negotiated);
    coop_session_hello(&c,&m);
    size_t n=coop_wire_encode(bytes,&m); assert(n==72);
    assert(bytes[0]=='C' && bytes[1]=='O' && bytes[2]=='O' && bytes[3]=='P');
    assert(bytes[4]==2 && bytes[5]==0 && bytes[6]==COOP_MSG_HELLO && bytes[7]==0);
    assert(bytes[16]==22 && bytes[32]==143);
    assert(coop_wire_decode(&decoded,bytes,n) && decoded.player==22);
    for(size_t i=0;i<n;i++) assert(!coop_wire_decode(&decoded,bytes,i));
    assert(!coop_wire_decode(&decoded,bytes,n+1));
    bytes[4]=1; assert(!coop_wire_decode(&decoded,bytes,n)); bytes[4]=2;
    bytes[7]=1; assert(!coop_wire_decode(&decoded,bytes,n)); bytes[7]=0;

    CoopSample sample={.generation=1,.flags=COOP_SAMPLE_PLAYER,.pos={1.25f,-4,300},.velocity={1,0,0},
                       .yaw=-45,.time_ns=1000000000};
    coop_session_sample(&c,&sample); coop_session_state_message(&c,&m);
    n=coop_wire_encode(bytes,&m); assert(n==84 && coop_wire_decode(&decoded,bytes,n));
    assert(!memcmp(&decoded.sample.pos,&sample.pos,sizeof sample.pos));
    assert(coop_session_receive(&h,&decoded,&reply)==COOP_RX_ACCEPT && h.have_remote);
    assert(coop_session_receive(&h,&decoded,&reply)==COOP_RX_IGNORE);
    m.seq=0; assert(coop_session_receive(&h,&m,&reply)==COOP_RX_IGNORE);
    assert(coop_seq_newer(1,0xfffffffeu) && !coop_seq_newer(0xfffffffeu,1));
    m.sample.pos[0]=NAN; assert(!coop_wire_encode(bytes,&m)); m.sample.pos[0]=1;
    m.sample.yaw=10000; assert(!coop_wire_encode(bytes,&m)); m.sample.yaw=-45;
    m.sample.velocity[0]=INFINITY; assert(!coop_wire_encode(bytes,&m)); m.sample.velocity[0]=0;
    m.sample.flags=COOP_SAMPLE_WORLD_READY; assert(!coop_wire_encode(bytes,&m));
    m.sample.flags=COOP_SAMPLE_PLAYER;
    m.generation=m.sample.generation=2; m.seq=3;
    assert(coop_session_receive(&h,&m,&reply)==COOP_RX_ACCEPT);
    m.generation=m.sample.generation=1; m.seq=4;
    assert(coop_session_receive(&h,&m,&reply)==COOP_RX_IGNORE);
    sample.generation=2; coop_session_sample(&c,&sample);
    assert(coop_session_notice(&c,1,"Checkpoint notification only",&m));
    n=coop_wire_encode(bytes,&m); assert(coop_wire_decode(&decoded,bytes,n));
    assert(coop_session_receive(&h,&decoded,&reply)==COOP_RX_ACCEPT && h.notices==1);
    assert(coop_session_receive(&h,&decoded,&reply)==COOP_RX_IGNORE && h.notices==1);
    m.generation=1; m.event_id=2; assert(coop_session_receive(&h,&m,&reply)==COOP_RX_IGNORE);
    m.session++; assert(coop_session_receive(&h,&m,&reply)==COOP_RX_IGNORE);
    CoopMessage old=decoded;
    negotiate(&h,&c,98765,COOP_CAP_PRESENCE);
    assert(coop_session_receive(&h,&old,&reply)==COOP_RX_IGNORE);

    coop_session_hello(&c,&m); m.game_version=121;
    assert(coop_session_receive(&h,&m,&reply)==COOP_RX_REJECT && h.state==COOP_SESSION_INCOMPATIBLE);
    negotiate(&h,&c,555,COOP_CAP_PRESENCE);
    coop_session_hello(&c,&m); m.content_id[0]^=1;
    assert(coop_session_receive(&h,&m,&reply)==COOP_RX_REJECT);
    negotiate(&h,&c,666,COOP_CAP_PRESENCE);
    coop_session_sample(&h,&sample); coop_session_sample(&c,&sample);
    coop_session_state_message(&c,&m); assert(coop_session_receive(&h,&m,&reply)==COOP_RX_ACCEPT);
    assert(h.state==COOP_SESSION_LOADING); // Presence cannot enable gameplay, even with a loaded actor.

    negotiate(&h,&c,777,COOP_REQUIRED_GAME_CAPS);
    sample.flags=COOP_SAMPLE_PLAYER|COOP_SAMPLE_WORLD_READY; sample.scene=55;
    coop_session_sample(&h,&sample); coop_session_sample(&c,&sample);
    coop_session_state_message(&c,&m); assert(coop_session_receive(&h,&m,&reply)==COOP_RX_ACCEPT);
    assert(h.state==COOP_SESSION_READY);
    sample.scene=56; coop_session_sample(&c,&sample); coop_session_state_message(&c,&m);
    assert(coop_session_receive(&h,&m,&reply)==COOP_RX_ACCEPT && h.state==COOP_SESSION_LOADING);
    sample.flags=0; coop_session_sample(&c,&sample); coop_session_state_message(&c,&m);
    assert(coop_session_receive(&h,&m,&reply)==COOP_RX_ACCEPT && !h.have_remote);
    coop_session_disconnected(&h); assert(h.state==COOP_SESSION_WAITING && !h.have_remote);

    // Feed every possible byte into every offset of a valid packet and re-encode accepted inputs.
    // Decoders must also survive arbitrary short buffers; accepted messages must have a canonical round trip.
    coop_session_hello(&c,&m); n=coop_wire_encode(bytes,&m);
    uint8_t mutated[COOP_WIRE_MAX],canonical[COOP_WIRE_MAX];
    for(size_t i=0;i<n;i++) for(unsigned value=0;value<256;value++) {
        memcpy(mutated,bytes,n); mutated[i]=(uint8_t)value;
        if(coop_wire_decode(&decoded,mutated,n)) {
            size_t size=coop_wire_encode(canonical,&decoded); assert(size==n);
            assert(!memcmp(mutated,canonical,n));
        }
    }
    puts("co-op protocol: serialization, malformed input, compatibility, replay, generations, deduplication and readiness passed");
    return 0;
}
