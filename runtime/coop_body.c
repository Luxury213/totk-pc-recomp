// Palette selection and rotation/blending math adapted from arnaldolima1/totk-recomp
// runtime/link_figure.c LF_BODY_ENTRY, quat_of, link_body_encode and link_body_lerp
// @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c (MIT).
// Copyright (c) 2026 Valiantsin Dzerakh; third_party/licenses/totk-recomp.txt.
// Binary encoding and validation are local: signed little-endian 16-bit values,
// with no base64, native structure layout, saturation or partial output on failure.
#include "coop_body.h"
#include <math.h>
#include <string.h>

const uint8_t coop_body_entry[COOP_BODY_BONES] = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
    20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33,
    65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80,
    81, 82, 83, 84, 85, 86, 87, 88
};

int coop_body_valid(const CoopBody *body) {
    if (!body) return 0;
    for (unsigned i = 0; i < COOP_BODY_BONES; i++) {
        float norm = 0;
        for (int k = 0; k < 4; k++) {
            float v = body->q[i][k];
            if (!isfinite(v) || fabsf(v) > 1.001f) return 0;
            norm += v * v;
        }
        if (fabsf(norm - 1) > .002f) return 0;
    }
    for (int i = 0; i < 2; i++) for (int k = 0; k < 3; k++)
        if (!isfinite(body->t[i][k]) || fabsf(body->t[i][k]) > 32.767f) return 0;
    return 1;
}

static int rotation(const float *m, float q[4]) {
    float r[9];
    for (int k = 0; k < 12; k++) if (!isfinite(m[k]) || fabsf(m[k]) > 100000) return 0;
    for (int j = 0; j < 3; j++) {
        float len = sqrtf(m[j]*m[j] + m[4+j]*m[4+j] + m[8+j]*m[8+j]);
        if (len < .01f || len > 100) return 0;
        for (int i = 0; i < 3; i++) r[3*i+j] = m[4*i+j] / len;
    }
    for (int i = 0; i < 3; i++) for (int j = i+1; j < 3; j++)
        if (fabsf(r[i]*r[j] + r[3+i]*r[3+j] + r[6+i]*r[6+j]) > .03f) return 0;
    float det = r[0]*(r[4]*r[8]-r[5]*r[7]) - r[1]*(r[3]*r[8]-r[5]*r[6]) + r[2]*(r[3]*r[7]-r[4]*r[6]);
    if (det < .95f || det > 1.05f) return 0;
    float tr = r[0] + r[4] + r[8], s;
    if (tr > 0) {
        s = sqrtf(tr + 1)*2;
        q[3]=s/4; q[0]=(r[7]-r[5])/s; q[1]=(r[2]-r[6])/s; q[2]=(r[3]-r[1])/s;
    } else if (r[0] > r[4] && r[0] > r[8]) {
        s = sqrtf(1+r[0]-r[4]-r[8])*2;
        q[3]=(r[7]-r[5])/s; q[0]=s/4; q[1]=(r[1]+r[3])/s; q[2]=(r[2]+r[6])/s;
    } else if (r[4] > r[8]) {
        s = sqrtf(1+r[4]-r[0]-r[8])*2;
        q[3]=(r[2]-r[6])/s; q[0]=(r[1]+r[3])/s; q[1]=s/4; q[2]=(r[5]+r[7])/s;
    } else {
        s = sqrtf(1+r[8]-r[0]-r[4])*2;
        q[3]=(r[3]-r[1])/s; q[0]=(r[2]+r[6])/s; q[1]=(r[5]+r[7])/s; q[2]=s/4;
    }
    float len = sqrtf(q[0]*q[0]+q[1]*q[1]+q[2]*q[2]+q[3]*q[3]);
    if (!isfinite(len) || len < .5f) return 0;
    if (q[3] < 0) len = -len;
    for (int i = 0; i < 4; i++) q[i] /= len;
    return 1;
}

int coop_body_from_palette(const float *pal, unsigned count, CoopBody *out) {
    if (!pal || !out || count < COOP_BODY_PALETTE || count > 128) return 0;
    CoopBody body = {0};
    for (unsigned i = 0; i < COOP_BODY_BONES; i++)
        if (!rotation(pal + 12*coop_body_entry[i], body.q[i])) return 0;
    for (int j = 0; j < 2; j++) for (int k = 0; k < 3; k++)
        body.t[j][k] = pal[12*(j ? 65 : 0) + 4*k+3];
    if (!coop_body_valid(&body)) return 0;
    *out = body;
    return 1;
}

static void put16(uint8_t *out, float value, float scale) {
    int v = (int)lrintf(value * scale);
    uint16_t bits = (uint16_t)v;
    out[0] = (uint8_t)bits; out[1] = (uint8_t)(bits >> 8);
}
static int get16(const uint8_t *in) {
    unsigned v = in[0] | (unsigned)in[1] << 8;
    return v < 32768 ? (int)v : (int)v - 65536;
}

int coop_body_encode(uint8_t out[COOP_BODY_BYTES], const CoopBody *body) {
    if (!out || !coop_body_valid(body)) return 0;
    for (unsigned i = 0; i < COOP_BODY_BONES; i++) {
        float norm = 0;
        for (int k = 0; k < 4; k++) norm += body->q[i][k]*body->q[i][k];
        norm = sqrtf(norm);
        for (int k = 0; k < 4; k++) put16(out + 8*i + 2*k, body->q[i][k]/norm, 32767);
    }
    for (int j = 0; j < 2; j++) for (int k = 0; k < 3; k++)
        put16(out + 8*COOP_BODY_BONES + 6*j + 2*k, body->t[j][k], 1000);
    return 1;
}

int coop_body_decode(CoopBody *out, const uint8_t *bytes, size_t size) {
    if (!out || !bytes || size != COOP_BODY_BYTES) return 0;
    CoopBody body = {0};
    for (unsigned i = 0; i < COOP_BODY_BONES; i++) for (int k = 0; k < 4; k++) {
        int v = get16(bytes + 8*i + 2*k);
        if (v == -32768) return 0;
        body.q[i][k] = v / 32767.0f;
    }
    for (int j = 0; j < 2; j++) for (int k = 0; k < 3; k++)
        body.t[j][k] = get16(bytes + 8*COOP_BODY_BONES + 6*j + 2*k) / 1000.0f;
    if (!coop_body_valid(&body)) return 0;
    for (unsigned i = 0; i < COOP_BODY_BONES; i++) {
        float len = 0;
        for (int k = 0; k < 4; k++) len += body.q[i][k]*body.q[i][k];
        for (int k = 0; k < 4; k++) body.q[i][k] /= sqrtf(len);
    }
    *out = body;
    return 1;
}

void coop_body_lerp(const CoopBody *a, const CoopBody *b, float t, CoopBody *out) {
    CoopBody body;
    for (unsigned i = 0; i < COOP_BODY_BONES; i++) {
        float dot = 0, norm = 0;
        for (int k = 0; k < 4; k++) dot += a->q[i][k]*b->q[i][k];
        for (int k = 0; k < 4; k++) {
            body.q[i][k] = a->q[i][k]*(1-t) + b->q[i][k]*(dot < 0 ? -t : t);
            norm += body.q[i][k]*body.q[i][k];
        }
        for (int k = 0; k < 4; k++) body.q[i][k] /= sqrtf(norm);
    }
    for (int j = 0; j < 2; j++) for (int k = 0; k < 3; k++)
        body.t[j][k] = a->t[j][k] + (b->t[j][k] - a->t[j][k])*t;
    *out = body;
}
