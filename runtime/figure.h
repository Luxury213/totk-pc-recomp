// Adapted from arnaldolima1/totk-recomp runtime/host.h GfxFigure @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c.
// MIT, Copyright (c) 2026 Valiantsin Dzerakh; runtime/third_party/licenses/totk-recomp.txt.
// Host presentation data only. A figure owns no native actor, physics, input or camera.
#pragma once
#include "coop.h"

typedef struct {
    int anim, prev_anim;
    float frame, prev_frame, fps, blend;
    float feet[3], vel[3], yaw;
    float rot[9];
    const void *fig;
    float hair[3];
} GfxFigure;

#ifdef __cplusplus
extern "C" {
#endif
int gfx_figures_wanted(void);
void gfx_figures_set(const GfxFigure *figures, int count);
void coop_figure_publish(const CoopSnapshot *snapshot);
#ifdef __cplusplus
}
#endif
