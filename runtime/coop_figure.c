// Feed copied session state into the diagnostic 3D figure. Never reads or writes guest actors.
#include "figure.h"
#include "link_figure.h"
#include "host.h"
#include "coop_native_probe.h"
#include "platform/platform.h"
#include <math.h>
#include <string.h>

void coop_figure_publish(const CoopSnapshot *snapshot) {
    static uint64_t previous_ms;
    static float fallback_frame;
    static int previous_animation = -1;
    if (!snapshot->has_peer_pos || !snapshot->has_local_pos || !gfx_figures_wanted()) {
        gfx_figures_set(NULL, 0);
        coop_native_probe_figure_publish(0,0,0);
        previous_ms = 0; previous_animation = -1;
        return;
    }
    const LinkFigure *model = link_figure();
    uint64_t now = plat_now_ms();
    float elapsed = previous_ms && now >= previous_ms ? fminf(.25f, (now - previous_ms) / 1000.0f) : 0;
    previous_ms = now;
    // Near-black sRGB preserves the hair texture's shading while distinguishing the companion.
    GfxFigure figure = {.blend = 1, .fig = model, .hair = {.06f, .055f, .05f}};
    memcpy(figure.feet, snapshot->peer_pos, sizeof figure.feet);
    int animation = (snapshot->peer_visual_flags & COOP_SAMPLE_ANIMATION) ?
                     link_figure_find(model, snapshot->peer_animation) : -1;
    if (animation >= 0) {
        figure.anim = animation;
        figure.frame = snapshot->peer_animation_frame;
    } else {
        figure.anim = snapshot->peer_speed > 6 ? LF_DASH : snapshot->peer_speed > 3 ? LF_RUN :
                      snapshot->peer_speed > .15f ? LF_WALK : LF_WAIT;
        if (figure.anim >= model->nanims) figure.anim = 0;
        float speed = model->anims[figure.anim].speed;
        figure.fps = figure.anim != LF_WAIT && speed > .01f ? 30 * snapshot->peer_speed / speed : 30;
        fallback_frame = previous_animation == figure.anim ? fallback_frame + elapsed * figure.fps : 0;
        fallback_frame = fmodf(fallback_frame, (float)model->anims[figure.anim].frames);
        figure.frame = fallback_frame;
    }
    previous_animation = figure.anim;
    figure.has_body = (snapshot->peer_visual_flags & COOP_SAMPLE_BODY) && model->npalm && model->parent &&
                      figure.anim>=0 && figure.anim<model->nanims && !model->anims[figure.anim].mats &&
                      coop_body_valid(&snapshot->peer_body);
    if (figure.has_body) figure.body = snapshot->peer_body;
    float q[4];
    if (snapshot->peer_visual_flags & COOP_SAMPLE_ROTATION) memcpy(q, snapshot->peer_rotation, sizeof q);
    else {
        float angle = snapshot->peer_yaw * (3.14159265359f / 360);
        q[0] = q[2] = 0; q[1] = sinf(angle); q[3] = cosf(angle);
    }
    link_figure_orient(q, figure.has_body ? 0 : link_figure_root_yaw(model, figure.anim, figure.frame), figure.rot);
    gfx_figures_set(&figure, 1);
    coop_native_probe_figure_publish(snapshot->peer_native_body ? snapshot->peer_native_generation : 0,
        snapshot->peer_native_actor_id,snapshot->peer_native_body ? snapshot->peer_native_sample_ns : 0);
    static uint64_t logged_sample;
    static unsigned native_logs;
    static CoopBody previous_body;
    static uint32_t previous_generation;
    static int32_t previous_actor=-1;
    if (snapshot->peer_native_body && snapshot->peer_native_sample_ns!=logged_sample && native_logs<512) {
        logged_sample=snapshot->peer_native_sample_ns; native_logs++;
        rt_log("coop native figure submitted: sample %llu, generation %u, actor id %d, pos %.6f %.6f %.6f; copied position, native appearance controlled separately",
            (unsigned long long)snapshot->peer_native_sample_ns,snapshot->peer_native_generation,
            snapshot->peer_native_actor_id,figure.feet[0],figure.feet[1],figure.feet[2]);
        if (figure.has_body) {
            int same=previous_generation==snapshot->peer_native_generation && previous_actor==snapshot->peer_native_actor_id;
            int changed=same && memcmp(&previous_body,&figure.body,sizeof previous_body)!=0;
            previous_body=figure.body; previous_generation=snapshot->peer_native_generation; previous_actor=snapshot->peer_native_actor_id;
            rt_log("coop native figure pose: sample %llu, generation %u, actor id %d, changed %u, rotation %u, animation %s; captured body supplied to mapped skeleton",
                (unsigned long long)snapshot->peer_native_sample_ns,snapshot->peer_native_generation,
                snapshot->peer_native_actor_id,changed,!!(snapshot->peer_visual_flags&COOP_SAMPLE_ROTATION),
                (snapshot->peer_visual_flags&COOP_SAMPLE_ANIMATION) ? snapshot->peer_animation : "unavailable");
        }
    }
}
