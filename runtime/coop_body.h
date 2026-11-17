// Copied presentation pose only; never contains guest pointers or native ownership.
// Palette selection adapted from arnaldolima1/totk-recomp runtime/link_figure.h
// LinkBody @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c (MIT).
// Copyright (c) 2026 Valiantsin Dzerakh; third_party/licenses/totk-recomp.txt.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum { COOP_BODY_BONES = 58, COOP_BODY_PALETTE = 89, COOP_BODY_BYTES = 476 };
typedef struct {
    float q[COOP_BODY_BONES][4]; // actor-space skinning rotations, x/y/z/w
    float t[2][3];              // Spine_1 and Waist skinning translations, metres
} CoopBody;

extern const uint8_t coop_body_entry[COOP_BODY_BONES];
int coop_body_valid(const CoopBody *body);
int coop_body_from_palette(const float *palette, unsigned count, CoopBody *out);
int coop_body_encode(uint8_t out[COOP_BODY_BYTES], const CoopBody *body);
int coop_body_decode(CoopBody *out, const uint8_t *bytes, size_t size);
void coop_body_lerp(const CoopBody *a, const CoopBody *b, float t, CoopBody *out);
#ifdef __cplusplus
}
#endif
