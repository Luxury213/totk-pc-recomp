// Co-op protocol v3. Fixed-width little-endian fields; never send native structs or guest pointers.
#pragma once
#include <stddef.h>
#include <stdint.h>

#define COOP_PROTOCOL 3u
#define COOP_ANIMATION_MAX 48u
#define COOP_WIRE_MAX 256u
#define COOP_CAP_PRESENCE 1u
#define COOP_CAP_NATIVE_ACTOR 2u
#define COOP_CAP_WORLD_CONTROL 4u
#define COOP_REQUIRED_GAME_CAPS (COOP_CAP_PRESENCE | COOP_CAP_NATIVE_ACTOR | COOP_CAP_WORLD_CONTROL)

enum { COOP_MSG_HELLO = 1, COOP_MSG_WELCOME, COOP_MSG_STATE, COOP_MSG_NOTICE };
enum { COOP_SAMPLE_PLAYER = 1, COOP_SAMPLE_WORLD_READY = 2,
       COOP_SAMPLE_ROTATION = 4, COOP_SAMPLE_ANIMATION = 8 };

typedef struct {
    uint32_t generation;    // sender observation epoch; not a shared checkpoint revision
    uint64_t scene;          // stable scene identity; zero until the engine adapter can establish it
    uint32_t flags;
    float pos[3], velocity[3], yaw;
    uint32_t action;
    uint64_t time_ns;
    float rotation[4];       // unit quaternion x/y/z/w; valid only with COOP_SAMPLE_ROTATION
    float animation_frame;   // native animation frame, not elapsed host time
    char animation[COOP_ANIMATION_MAX]; // FSKA name; valid only with COOP_SAMPLE_ANIMATION
} CoopSample;

typedef struct {
    uint8_t kind;
    uint64_t session, player;
    uint32_t generation, seq;
    uint32_t game_version, capabilities;
    uint8_t content_id[32];
    CoopSample sample;
    uint64_t event_id;
    char label[96];
} CoopMessage;

size_t coop_wire_encode(uint8_t out[COOP_WIRE_MAX], const CoopMessage *message);
int coop_wire_decode(CoopMessage *out, const uint8_t *bytes, size_t size);
int coop_seq_newer(uint32_t value, uint32_t previous);
