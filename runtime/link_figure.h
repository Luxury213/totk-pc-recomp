// Adapted from arnaldolima1/totk-recomp runtime/link_figure.h @ 7cd8a6b6fa29df2f0c2591e3f0c34fc6e60f590c.
// MIT, Copyright (c) 2026 Valiantsin Dzerakh; runtime/third_party/licenses/totk-recomp.txt.
// Link's figure for friends in a multiplayer room (link_figure.c, tools/link_figure.py).
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
// Material classes of the triangles, as tools/link_figure.py CLASSES numbers them.
enum { LF_UNTEXTURED = 0x80 };
enum { LF_SKIN, LF_HAIR, LF_TUNIC, LF_TROUSERS, LF_LEATHER, LF_EYE, LF_DARK, LF_METAL, LF_RAURU, LF_CLASSES };
// The animations: the four the speed picks lead (tools/link_figure.py ANIMS order), every other one of Link's follows.
enum { LF_WAIT = 0, LF_WALK, LF_RUN, LF_DASH };
typedef struct {
    char name[48];
    uint32_t frames;   // at 30 a second
    int loop;          // 1: it loops; else it holds its last frame
    float speed;       // ground speed it was made for (m/s), 0 standing or not one of the four
    float *mats;       // a version 3 file: frames x bones x 12, row-major 3x4 skinning matrices
    // a version 4 file: curves evaluated at the frame (link_figure_pose), pointing into the file kept in memory
    uint32_t nbones, ncurves;
    const uint8_t *bones;    // per animated bone u16 bone, u16 curve count, 9 floats (its still local transform)
    const uint8_t *curves;   // per curve u8 channel, u8 0, u16 key count
    const uint8_t **keys;    // per curve its first key: u16 frame x 32, 4 halves
} LinkAnim;
typedef struct {
    uint32_t nverts, ntris;
    float *verts;      // 3 per vertex: metres, x right, y up, z forward (the way the figure faces)
    uint32_t *tris;    // 3 vertex indices per triangle
    uint8_t *cls;      // LF_* per triangle; bit 7 (LF_UNTEXTURED): coloured by class, not by the atlas
    float *normals;    // 3 per triangle, unit length (bind pose)
    int winding;       // 1: (b - a) x (c - a) points out of the body, -1: in
    float *uvs;        // 6 per triangle: its corners in the atlas (0..1)
    uint8_t *atlas;    // atlas_side x atlas_side RGBA8, lifted for the overlay
    uint8_t *albedo;   // the same as stored (sRGB)
    uint32_t atlas_side;
    uint32_t atlas_rows;   // the albedo's rows when not square (a dressed figure, 2048 x 1024), 0 square
    uint32_t nbones;
    uint16_t *skin;    // per vertex four (bone, weight of 65535)
    int nanims;
    LinkAnim *anims;
    // version 4: the skeleton the animations move
    int root;          // the bone whose ground travel is left out, -1 none
    int32_t *parent;   // per bone, -1 none; a parent comes before its children
    float *bind;       // per bone 9 floats: scale xyz, euler XYZ, translation xyz
    float *inv_bind;   // per bone its inverse bind world, row-major 3x4
    char *bone_names;  // per bone 32 bytes
    // Link_RaulSkin's skinning palette (the game's, game_player_body) as the figure's bones: per entry its bone
    // (0xffff none) and 1 when rigid (the pose itself, not the pose times the inverse bind); npalm 0 in an older file
    uint32_t npalm;
    uint16_t *palm_bone;
    uint8_t *palm_rigid;
} LinkFigure;
// NULL when <profile>/link-figure.bin is missing or unreadable.
const LinkFigure *link_figure(void);
void link_figure_pose(const LinkFigure *figure, int animation, float frame, float *vertices);
int link_figure_find(const LinkFigure *figure, const char *name);
void link_figure_rotate(const LinkFigure *figure, float *vertices, const float rotation[9]);
void link_figure_orient(const float quaternion[4], float turn, float rotation[9]);
int link_figure_bone(const LinkFigure *figure, const char *name);
float link_figure_root_yaw(const LinkFigure *figure, int animation, float frame);
int link_figure_bones_at(const LinkFigure *figure, int animation, float frame,
                        const int *bones, int count, float (*positions)[3]);
#ifdef __cplusplus
}
#endif
