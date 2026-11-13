#include "coop_interp.h"
#include <math.h>
#include <string.h>

// Shortest-path normalized quaternion blend, adapted from arnaldolima1/totk-recomp
// runtime/net_mp.c place_on @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c (MIT).
// Copyright (c) 2026 Valiantsin Dzerakh; runtime/third_party/licenses/totk-recomp.txt.
static void blend_visual(const CoopSample *a, const CoopSample *b, float t, CoopSample *out) {
    if ((a->flags & b->flags & COOP_SAMPLE_ROTATION)) {
        float dot = 0, norm = 0;
        for (int i = 0; i < 4; i++) dot += a->rotation[i] * b->rotation[i];
        float sign = dot < 0 ? -1 : 1;
        for (int i = 0; i < 4; i++) {
            out->rotation[i] = a->rotation[i] + (sign * b->rotation[i] - a->rotation[i]) * t;
            norm += out->rotation[i] * out->rotation[i];
        }
        norm = sqrtf(norm);
        for (int i = 0; i < 4; i++) out->rotation[i] = norm > 1e-6f ? out->rotation[i] / norm : (i == 3);
    }
    // A new clip or a loop restart is a discrete boundary. Its duration is not known here;
    // hold the earlier frame until that sample arrives instead of playing the clip backwards.
    if ((a->flags & b->flags & COOP_SAMPLE_ANIMATION) && !strcmp(a->animation, b->animation) &&
        b->animation_frame >= a->animation_frame)
        out->animation_frame = a->animation_frame + (b->animation_frame - a->animation_frame) * t;
}

void coop_interp_push(CoopInterpolator *b, const CoopSample *s, uint64_t received) {
    if (!received || !(s->flags & COOP_SAMPLE_PLAYER)) return;
    if (b->count && b->samples[b->count - 1].generation != s->generation) b->count = 0;
    if (b->count && received <= b->received_ns[b->count - 1]) return;
    if (b->count == 16) {
        memmove(b->samples, b->samples + 1, 15 * sizeof b->samples[0]);
        memmove(b->received_ns, b->received_ns + 1, 15 * sizeof b->received_ns[0]);
        b->count--;
    }
    b->samples[b->count] = *s; b->received_ns[b->count++] = received;
}

int coop_interp_read(const CoopInterpolator *b, uint64_t now, CoopSample *out) {
    if (!b->count) return 0;
    uint64_t time = now > 100000000ull ? now - 100000000ull : 0;
    *out = b->samples[0];
    for (unsigned i = 1; i < b->count; i++) {
        if (time < b->received_ns[i]) {
            if (time <= b->received_ns[i - 1]) return 1;
            const CoopSample *a = &b->samples[i - 1], *z = &b->samples[i];
            float t = (float)((double)(time - b->received_ns[i - 1]) / (b->received_ns[i] - b->received_ns[i - 1]));
            *out = *a;
            for (int k = 0; k < 3; k++) {
                out->pos[k] = a->pos[k] + (z->pos[k] - a->pos[k]) * t;
                out->velocity[k] = a->velocity[k] + (z->velocity[k] - a->velocity[k]) * t;
            }
            float delta = remainderf(z->yaw - a->yaw, 360.0f);
            out->yaw = a->yaw + delta * t;
            blend_visual(a, z, t, out);
            return 1;
        }
        *out = b->samples[i];
    }
    return 1;   // hold the last pose rather than extrapolating into unavailable terrain
}
