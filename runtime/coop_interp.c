#include "coop_interp.h"
#include <math.h>
#include <string.h>

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
            return 1;
        }
        *out = b->samples[i];
    }
    return 1;   // hold the last pose rather than extrapolating into unavailable terrain
}
