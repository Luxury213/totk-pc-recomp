#include "coop_wire.h"
#include <math.h>
#include <string.h>

#define MAGIC 0x504f4f43u
#define HEADER 32u

static void put(uint8_t *p, uint64_t v, unsigned n) {
    for (unsigned i = 0; i < n; i++) p[i] = (uint8_t)(v >> (8 * i));
}
static uint64_t get(const uint8_t *p, unsigned n) {
    uint64_t v = 0;
    for (unsigned i = 0; i < n; i++) v |= (uint64_t)p[i] << (8 * i);
    return v;
}
static void put_float(uint8_t *p, float f) { uint32_t v; memcpy(&v, &f, 4); put(p, v, 4); }
static float get_float(const uint8_t *p) { uint32_t v = (uint32_t)get(p, 4); float f; memcpy(&f, &v, 4); return f; }

int coop_seq_newer(uint32_t v, uint32_t previous) {
    uint32_t delta = v - previous;
    return delta && delta < 0x80000000u;
}

static int valid(const CoopMessage *m) {
    if (!m->player || m->kind < COOP_MSG_HELLO || m->kind > COOP_MSG_NOTICE) return 0;
    if (m->kind == COOP_MSG_HELLO) return m->session == 0 && m->generation == 0;
    if (!m->session) return 0;
    if (m->kind == COOP_MSG_STATE) {
        const CoopSample *s = &m->sample;
        if (m->generation != s->generation || (s->flags & ~15u) || s->action > 2 ||
            !isfinite(s->yaw) || fabsf(s->yaw) > 360) return 0;
        if ((s->flags & COOP_SAMPLE_PLAYER) && !s->generation) return 0;
        if ((s->flags & (COOP_SAMPLE_ROTATION | COOP_SAMPLE_ANIMATION)) && !(s->flags & COOP_SAMPLE_PLAYER)) return 0;
        if ((s->flags & COOP_SAMPLE_WORLD_READY) && (!(s->flags & COOP_SAMPLE_PLAYER) || !s->scene)) return 0;
        for (int i = 0; i < 3; i++)
            if (!isfinite(s->pos[i]) || fabsf(s->pos[i]) > 1000000 ||
                !isfinite(s->velocity[i]) || fabsf(s->velocity[i]) > 10000) return 0;
        float norm = 0;
        for (int i = 0; i < 4; i++) {
            if (!isfinite(s->rotation[i]) || fabsf(s->rotation[i]) > 1.001f) return 0;
            if (!(s->flags & COOP_SAMPLE_ROTATION) && s->rotation[i] != 0) return 0;
            norm += s->rotation[i] * s->rotation[i];
        }
        if ((s->flags & COOP_SAMPLE_ROTATION) && fabsf(norm - 1) > .002f) return 0;
        if (!isfinite(s->animation_frame) || s->animation_frame < 0 || s->animation_frame > 1000000) return 0;
        if (!(s->flags & COOP_SAMPLE_ANIMATION) && s->animation_frame != 0) return 0;
        int ended = 0;
        for (unsigned i = 0; i < sizeof s->animation; i++) {
            unsigned char ch = (unsigned char)s->animation[i];
            if (!ch) ended = 1;
            else if (ended || !(s->flags & COOP_SAMPLE_ANIMATION) ||
                     !((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
                       (ch >= '0' && ch <= '9') || ch == '_')) return 0;
        }
        if (!ended || ((s->flags & COOP_SAMPLE_ANIMATION) && !s->animation[0])) return 0;
    }
    if (m->kind == COOP_MSG_NOTICE && (!m->event_id || !memchr(m->label, 0, sizeof m->label))) return 0;
    return 1;
}

size_t coop_wire_encode(uint8_t out[COOP_WIRE_MAX], const CoopMessage *m) {
    if (!valid(m)) return 0;
    memset(out, 0, COOP_WIRE_MAX);
    put(out, MAGIC, 4); put(out + 4, COOP_PROTOCOL, 2); out[6] = m->kind;
    put(out + 8, m->session, 8); put(out + 16, m->player, 8);
    put(out + 24, m->generation, 4); put(out + 28, m->seq, 4);
    uint8_t *p = out + HEADER;
    if (m->kind == COOP_MSG_HELLO || m->kind == COOP_MSG_WELCOME) {
        put(p, m->game_version, 4); put(p + 4, m->capabilities, 4); memcpy(p + 8, m->content_id, 32);
        return HEADER + 40;
    }
    if (m->kind == COOP_MSG_STATE) {
        put(p, m->sample.scene, 8); put(p + 8, m->sample.flags, 4);
        for (int i = 0; i < 3; i++) {
            put_float(p + 12 + i * 4, m->sample.pos[i]);
            put_float(p + 24 + i * 4, m->sample.velocity[i]);
        }
        put_float(p + 36, m->sample.yaw); put(p + 40, m->sample.action, 4); put(p + 44, m->sample.time_ns, 8);
        for (int i = 0; i < 4; i++) put_float(p + 52 + i * 4, m->sample.rotation[i]);
        put_float(p + 68, m->sample.animation_frame);
        memcpy(p + 72, m->sample.animation, sizeof m->sample.animation);
        return HEADER + 120;
    }
    size_t n = strlen(m->label);
    put(p, m->event_id, 8); put(p + 8, n, 2); memcpy(p + 10, m->label, n);
    return HEADER + 10 + n;
}

int coop_wire_decode(CoopMessage *m, const uint8_t *b, size_t n) {
    if (!b || n < HEADER || n > COOP_WIRE_MAX || get(b, 4) != MAGIC ||
        get(b + 4, 2) != COOP_PROTOCOL || b[7]) return 0;
    CoopMessage v = {0};
    v.kind = b[6]; v.session = get(b + 8, 8); v.player = get(b + 16, 8);
    v.generation = (uint32_t)get(b + 24, 4); v.seq = (uint32_t)get(b + 28, 4);
    const uint8_t *p = b + HEADER;
    if (v.kind == COOP_MSG_HELLO || v.kind == COOP_MSG_WELCOME) {
        if (n != HEADER + 40) return 0;
        v.game_version = (uint32_t)get(p, 4); v.capabilities = (uint32_t)get(p + 4, 4);
        memcpy(v.content_id, p + 8, 32);
    } else if (v.kind == COOP_MSG_STATE) {
        if (n != HEADER + 120) return 0;
        v.sample.generation = v.generation; v.sample.scene = get(p, 8); v.sample.flags = (uint32_t)get(p + 8, 4);
        for (int i = 0; i < 3; i++) {
            v.sample.pos[i] = get_float(p + 12 + i * 4); v.sample.velocity[i] = get_float(p + 24 + i * 4);
        }
        v.sample.yaw = get_float(p + 36); v.sample.action = (uint32_t)get(p + 40, 4);
        v.sample.time_ns = get(p + 44, 8);
        for (int i = 0; i < 4; i++) v.sample.rotation[i] = get_float(p + 52 + i * 4);
        v.sample.animation_frame = get_float(p + 68);
        memcpy(v.sample.animation, p + 72, sizeof v.sample.animation);
    } else if (v.kind == COOP_MSG_NOTICE) {
        if (n < HEADER + 10) return 0;
        size_t len = (size_t)get(p + 8, 2);
        if (len >= sizeof v.label || n != HEADER + 10 + len || memchr(p + 10, 0, len)) return 0;
        v.event_id = get(p, 8); memcpy(v.label, p + 10, len);
    } else return 0;
    if (!valid(&v)) return 0;
    *m = v;
    return 1;
}
