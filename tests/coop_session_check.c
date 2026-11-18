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

static void visual_protocol_checks(void) {
    CoopMessage message={.kind=COOP_MSG_STATE,.session=10,.player=20,.generation=1,
        .sample={.generation=1,.flags=COOP_SAMPLE_PLAYER|COOP_SAMPLE_ROTATION|COOP_SAMPLE_ANIMATION,
                 .rotation={1,0,0,0},.animation="Sword_Synthetic",.animation_frame=12.25f}};
    CoopMessage decoded;
    uint8_t bytes[COOP_WIRE_MAX], mutated[COOP_WIRE_MAX], canonical[COOP_WIRE_MAX];
    size_t size=coop_wire_encode(bytes,&message);
    assert(size==152 && coop_wire_decode(&decoded,bytes,size));
    assert(decoded.sample.rotation[0]==1 && decoded.sample.animation_frame==12.25f);
    assert(!strcmp(decoded.sample.animation,"Sword_Synthetic"));
    assert(bytes[84]==0 && bytes[85]==0 && bytes[86]==128 && bytes[87]==63); // quaternion x = LE 1.0
    for(size_t n=0;n<size;n++) assert(!coop_wire_decode(&decoded,bytes,n));
    for(size_t i=0;i<size;i++) for(unsigned value=0;value<256;value++) {
        memcpy(mutated,bytes,size); mutated[i]=(uint8_t)value;
        if(coop_wire_decode(&decoded,mutated,size)) {
            assert(coop_wire_encode(canonical,&decoded)==size && !memcmp(mutated,canonical,size));
        }
    }
    message.sample.rotation[0]=0; assert(!coop_wire_encode(bytes,&message));
    message.sample.rotation[0]=NAN; assert(!coop_wire_encode(bytes,&message));
    message.sample.rotation[0]=2; assert(!coop_wire_encode(bytes,&message));
    message.sample.rotation[0]=1;
    message.sample.flags=COOP_SAMPLE_PLAYER|COOP_SAMPLE_ANIMATION;
    assert(!coop_wire_encode(bytes,&message)); // undeclared orientation
    message.sample.flags=COOP_SAMPLE_ROTATION|COOP_SAMPLE_ANIMATION;
    assert(!coop_wire_encode(bytes,&message)); // visual state without a player
    message.sample.flags|=COOP_SAMPLE_PLAYER;
    message.sample.animation_frame=INFINITY; assert(!coop_wire_encode(bytes,&message));
    message.sample.animation_frame=-1; assert(!coop_wire_encode(bytes,&message));
    message.sample.animation_frame=12.25f;
    message.sample.animation[0]='/'; assert(!coop_wire_encode(bytes,&message));
    message.sample.animation[0]='S';
    message.sample.animation[30]='x'; assert(!coop_wire_encode(bytes,&message)); // hidden suffix
    message.sample.animation[30]=0;
    memset(message.sample.animation,'a',sizeof message.sample.animation); assert(!coop_wire_encode(bytes,&message));

    CoopSample a={.generation=1,.flags=COOP_SAMPLE_PLAYER|COOP_SAMPLE_ROTATION|COOP_SAMPLE_ANIMATION,
                   .rotation={0,0,0,1},.animation="Synthetic_Walk",.animation_frame=10};
    CoopSample b=a, visual;
    b.rotation[3]=0; b.rotation[0]=1; b.animation_frame=20;
    CoopInterpolator history={0};
    coop_interp_push(&history,&a,1000000000); coop_interp_push(&history,&b,1100000000);
    assert(coop_interp_read(&history,1150000000,&visual));
    assert(fabsf(visual.rotation[0]-.7071068f)<.0001f && fabsf(visual.rotation[3]-.7071068f)<.0001f);
    assert(visual.animation_frame==15);
    b=a; b.rotation[3]=-1; // q and -q represent the same orientation, never a half turn
    history=(CoopInterpolator){0};
    coop_interp_push(&history,&a,1000000000); coop_interp_push(&history,&b,1100000000);
    coop_interp_read(&history,1150000000,&visual); assert(visual.rotation[3]==1);
    b.animation_frame=2; // loop restart: must not interpolate backwards
    history=(CoopInterpolator){0};
    coop_interp_push(&history,&a,1000000000); coop_interp_push(&history,&b,1100000000);
    coop_interp_read(&history,1150000000,&visual); assert(visual.animation_frame==10);
    coop_interp_read(&history,1200000000,&visual); assert(visual.animation_frame==2);
    strcpy(b.animation,"Synthetic_Attack"); b.animation_frame=20;
    history=(CoopInterpolator){0};
    coop_interp_push(&history,&a,1000000000); coop_interp_push(&history,&b,1100000000);
    coop_interp_read(&history,1150000000,&visual);
    assert(!strcmp(visual.animation,a.animation) && visual.animation_frame==10);
    b.generation=2; coop_interp_push(&history,&b,1200000000);
    assert(history.count==1); coop_interp_read(&history,1250000000,&visual);
    assert(!strcmp(visual.animation,b.animation) && visual.rotation[3]==-1);
}

static void equipment_protocol_checks(void) {
    CoopMessage m={.kind=COOP_MSG_STATE,.session=10,.player=20,.generation=1,
        .sample={.generation=1,.flags=COOP_SAMPLE_PLAYER|COOP_SAMPLE_EQUIPMENT}};
    strcpy(m.sample.equipment.actor[0],"Weapon_Sword_101");
    strcpy(m.sample.equipment.actor[1],"Weapon_Shield_040");
    strcpy(m.sample.equipment.actor[2],"Weapon_Bow_001");
    uint8_t bytes[COOP_WIRE_MAX]; CoopMessage out;
    size_t size=coop_wire_encode(bytes,&m);
    assert(size==296 && coop_wire_decode(&out,bytes,size));
    assert(!memcmp(&out.sample.equipment,&m.sample.equipment,sizeof m.sample.equipment));
    for(size_t n=0;n<size;n++) assert(!coop_wire_decode(&out,bytes,n));
    assert(!coop_wire_decode(&out,bytes,size+1));
    bytes[4]=4; assert(!coop_wire_decode(&out,bytes,size)); bytes[4]=COOP_PROTOCOL;
    m.sample.flags|=COOP_SAMPLE_BODY|COOP_SAMPLE_ROTATION; m.sample.rotation[3]=1;
    for(unsigned i=0;i<COOP_BODY_BONES;i++) m.sample.body.q[i][3]=1;
    assert(coop_wire_encode(bytes,&m)==772 && 772<=COOP_WIRE_MAX);
    assert(coop_wire_decode(&out,bytes,772));
    const char *bad[]={"../Weapon_Sword_101","Weapon_Bow_001","Weapon_Sword_","Weapon_Sword_a","Weapon_Sword_101/"};
    for(unsigned i=0;i<sizeof bad/sizeof *bad;i++) {
        memset(m.sample.equipment.actor[0],0,COOP_EQUIP_NAME);
        strcpy(m.sample.equipment.actor[0],bad[i]); assert(!coop_wire_encode(bytes,&m));
    }
    memset(m.sample.equipment.actor[0],'x',COOP_EQUIP_NAME); assert(!coop_wire_encode(bytes,&m));
    memset(m.sample.equipment.actor[0],0,COOP_EQUIP_NAME);
    strcpy(m.sample.equipment.actor[0],"Weapon_Sword_101");
    m.sample.equipment.actor[0][40]='x'; assert(!coop_wire_encode(bytes,&m));
    m.sample.equipment.actor[0][40]=0;
    CoopSample a=m.sample,b=a,visual; CoopInterpolator history={0};
    strcpy(b.equipment.actor[0],"Weapon_Spear_001");
    coop_interp_push(&history,&a,1000000000); coop_interp_push(&history,&b,1100000000);
    coop_interp_read(&history,1150000000,&visual); assert(!strcmp(visual.equipment.actor[0],"Weapon_Sword_101"));
    coop_interp_read(&history,1200000000,&visual); assert(!strcmp(visual.equipment.actor[0],"Weapon_Spear_001"));
    b.flags&=~COOP_SAMPLE_EQUIPMENT; memset(&b.equipment,0,sizeof b.equipment); history=(CoopInterpolator){0};
    coop_interp_push(&history,&a,1000000000); coop_interp_push(&history,&b,1100000000);
    coop_interp_read(&history,1150000000,&visual);
    assert(!(visual.flags&COOP_SAMPLE_EQUIPMENT) && !visual.equipment.actor[0][0]);
    m.sample.flags&=~COOP_SAMPLE_EQUIPMENT; assert(!coop_wire_encode(bytes,&m));
    memset(&m.sample.equipment,0,sizeof m.sample.equipment); assert(coop_wire_encode(bytes,&m)==628);
    m.sample.flags|=COOP_SAMPLE_EQUIPMENT; assert(coop_wire_encode(bytes,&m)==772);
    assert(coop_wire_decode(&out,bytes,772) && !out.sample.equipment.actor[1][0]); // explicitly unequipped
    puts("co-op equipment: bounded identities, slot validation, optional clearing, unequip and discrete changes passed");
}

static void body_protocol_checks(void) {
    float palette[COOP_BODY_PALETTE*12]={0};
    for(unsigned i=0;i<COOP_BODY_PALETTE;i++) palette[12*i]=palette[12*i+5]=palette[12*i+10]=1;
    palette[3]=1.234f; palette[12*65+7]=-2.5f;
    CoopBody body, decoded, unchanged;
    memset(&unchanged,0x55,sizeof unchanged); decoded=unchanged;
    assert(!coop_body_from_palette(palette,COOP_BODY_PALETTE-1,&decoded));
    assert(!memcmp(&decoded,&unchanged,sizeof decoded));
    assert(coop_body_from_palette(palette,COOP_BODY_PALETTE,&body));
    uint8_t bytes[COOP_WIRE_MAX], bad[COOP_WIRE_MAX];
    assert(coop_body_encode(bytes,&body));
    assert(bytes[6]==255 && bytes[7]==127 && bytes[464]==0xd2 && bytes[465]==4);
    assert(coop_body_decode(&decoded,bytes,COOP_BODY_BYTES));
    assert(fabsf(decoded.t[0][0]-1.234f)<.0001f && decoded.q[57][3]==1);
    for(size_t n=0;n<COOP_BODY_BYTES;n++) assert(!coop_body_decode(&decoded,bytes,n));
    assert(!coop_body_decode(&decoded,bytes,COOP_BODY_BYTES+1));
    memcpy(bad,bytes,COOP_BODY_BYTES); memset(bad,0,8);
    decoded=unchanged; assert(!coop_body_decode(&decoded,bad,COOP_BODY_BYTES));
    assert(!memcmp(&decoded,&unchanged,sizeof decoded));
    memcpy(bad,bytes,COOP_BODY_BYTES); bad[0]=0; bad[1]=128;
    assert(!coop_body_decode(&decoded,bad,COOP_BODY_BYTES));
    body.q[0][0]=NAN; assert(!coop_body_encode(bytes,&body)); body.q[0][0]=0;
    body.t[0][0]=33; assert(!coop_body_encode(bytes,&body)); body.t[0][0]=1.234f;
    palette[0]=-1; assert(!coop_body_from_palette(palette,COOP_BODY_PALETTE,&decoded));
    palette[0]=1; palette[1]=.5f; assert(!coop_body_from_palette(palette,COOP_BODY_PALETTE,&decoded));
    palette[1]=0; palette[0]=NAN; assert(!coop_body_from_palette(palette,COOP_BODY_PALETTE,&decoded));

    CoopMessage m={.kind=COOP_MSG_STATE,.session=10,.player=20,.generation=1,
        .sample={.generation=1,.flags=COOP_SAMPLE_PLAYER|COOP_SAMPLE_ROTATION|COOP_SAMPLE_BODY,
                 .rotation={0,0,0,1},.body=body}}, received;
    size_t size=coop_wire_encode(bytes,&m); assert(size==628 && size<=COOP_WIRE_MAX);
    assert(coop_wire_decode(&received,bytes,size) && coop_body_valid(&received.sample.body));
    for(size_t n=0;n<size;n++) assert(!coop_wire_decode(&received,bytes,n));
    assert(!coop_wire_decode(&received,bytes,size+1));
    bytes[4]=3; assert(!coop_wire_decode(&received,bytes,size)); bytes[4]=COOP_PROTOCOL;
    m.sample.flags &= ~COOP_SAMPLE_BODY; assert(!coop_wire_encode(bad,&m));
    memset(&m.sample.body,0,sizeof m.sample.body); assert(coop_wire_encode(bad,&m)==152);
    assert(coop_wire_decode(&received,bad,152) && received.sample.body.q[0][3]==0);
    m.sample.body=body; m.sample.flags=COOP_SAMPLE_PLAYER|COOP_SAMPLE_BODY;
    assert(!coop_wire_encode(bad,&m)); // actor-space bones require actor orientation

    CoopSample a={.generation=1,.flags=COOP_SAMPLE_PLAYER|COOP_SAMPLE_BODY|COOP_SAMPLE_ROTATION,
                  .rotation={0,0,0,1},.body=body}, b=a, visual;
    b.body.q[1][3]=0; b.body.q[1][2]=1; b.body.t[0][0]=3.234f;
    CoopInterpolator history={0};
    coop_interp_push(&history,&a,1000000000); coop_interp_push(&history,&b,1100000000);
    coop_interp_read(&history,1150000000,&visual);
    assert(fabsf(visual.body.q[1][2]-.70710678f)<.0001f && fabsf(visual.body.t[0][0]-2.234f)<.0001f);
    b=a; for(int k=0;k<4;k++) b.body.q[0][k]=-a.body.q[0][k];
    coop_body_lerp(&a.body,&b.body,.5f,&decoded); assert(decoded.q[0][3]==1);
    b.flags &= ~COOP_SAMPLE_BODY; memset(&b.body,0,sizeof b.body);
    history=(CoopInterpolator){0};
    coop_interp_push(&history,&a,1000000000); coop_interp_push(&history,&b,1100000000);
    coop_interp_read(&history,1150000000,&visual);
    assert(!(visual.flags & COOP_SAMPLE_BODY) && visual.body.q[0][3]==0);
    b.generation=2; coop_interp_push(&history,&b,1200000000);
    assert(history.count==1); // old skeleton cannot cross local world generations
    printf("co-op body: bounded LE codec, malformed/truncated poses, protocol%u, interpolation and optional clearing passed\n",COOP_PROTOCOL);
}

int main(void) {
    equipment_protocol_checks();
    body_protocol_checks();
    visual_protocol_checks();
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
    assert(bytes[4]==COOP_PROTOCOL && bytes[5]==0 && bytes[6]==COOP_MSG_HELLO && bytes[7]==0);
    assert(bytes[16]==22 && bytes[32]==143);
    assert(coop_wire_decode(&decoded,bytes,n) && decoded.player==22);
    for(size_t i=0;i<n;i++) assert(!coop_wire_decode(&decoded,bytes,i));
    assert(!coop_wire_decode(&decoded,bytes,n+1));
    bytes[4]=1; assert(!coop_wire_decode(&decoded,bytes,n));
    bytes[4]=2; assert(!coop_wire_decode(&decoded,bytes,n)); bytes[4]=COOP_PROTOCOL;
    bytes[7]=1; assert(!coop_wire_decode(&decoded,bytes,n)); bytes[7]=0;

    CoopSample sample={.generation=1,.flags=COOP_SAMPLE_PLAYER,.pos={1.25f,-4,300},.velocity={1,0,0},
                       .yaw=-45,.time_ns=1000000000};
    coop_session_sample(&c,&sample); coop_session_state_message(&c,&m);
    n=coop_wire_encode(bytes,&m); assert(n==152 && coop_wire_decode(&decoded,bytes,n));
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
    coop_session_disconnected(&h);
    assert(h.state==COOP_SESSION_INCOMPATIBLE && !h.negotiated && !h.have_remote && !h.peer_player);
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
