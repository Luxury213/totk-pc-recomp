// Feed copied session state into the diagnostic 3D figure. Never reads or writes guest actors.
#include "figure.h"
#include "link_figure.h"
#include "platform/platform.h"
#include <math.h>
#include <string.h>

void coop_figure_publish(const CoopSnapshot *snapshot) {
    static uint64_t previous_ms;
    static float fallback_frame;
    static int previous_animation = -1;
    if (!snapshot->has_peer_pos || !snapshot->has_local_pos || !gfx_figures_wanted()) {
        gfx_figures_set(NULL, 0);
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
    float q[4];
    if (snapshot->peer_visual_flags & COOP_SAMPLE_ROTATION) memcpy(q, snapshot->peer_rotation, sizeof q);
    else {
        float angle = snapshot->peer_yaw * (3.14159265359f / 360);
        q[0] = q[2] = 0; q[1] = sinf(angle); q[3] = cosf(angle);
    }
    link_figure_orient(q, link_figure_root_yaw(model, figure.anim, figure.frame), figure.rot);
    gfx_figures_set(&figure, 1);
}
