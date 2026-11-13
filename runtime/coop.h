// Experimental co-op presence (TOTK_COOP_MODE, TOTK_COOP_IP, TOTK_COOP_PORT).
// Exchanges player positions, action states and notifications; no world or save replication yet.
#pragma once
#include <stdint.h>
#include "coop_session.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    COOP_OFF = 0,
    COOP_HOST = 1,
    COOP_CLIENT = 2,
    COOP_BOT = 3,
};

enum {
    COOP_ACT_EXPLORING = 0,
    COOP_ACT_BOW = 1,
    COOP_ACT_ABILITY = 2,
};

enum {
    COOP_BOT_FOLLOW = 0,
    COOP_BOT_STAY = 1,
};

typedef struct {
    int mode;               // COOP_OFF .. COOP_BOT
    int session_state;      // COOP_SESSION_*; a transport connection is not native gameplay readiness
    uint32_t native_capabilities;
    uint32_t observation_generation;
    uint32_t commands_rejected;
    char adapter_status[128];
    int bot_mode;           // COOP_BOT_FOLLOW or COOP_BOT_STAY
    int connected;          // live peer within 5 s, or a spawned local visual bot
    uint32_t ping_ms;       // latest round-trip estimate in ms
    uint32_t packets_tx;
    uint32_t packets_rx;
    uint32_t world_syncs;   // notification counter; does not count replicated world changes
    int has_local_pos;      // 1 when a playable Player actor was found in the latest sample
    int has_camera;         // 1 once a finite scene view-projection matrix has been captured
    float local_pos[3];     // local player exact 3D world position (X, Y, Z in meters)
    float local_fwd[3];     // player/camera forward unit vector
    int local_action;       // COOP_ACT_*
    float vp[16];           // 4x4 row-major View-Projection matrix for 3D-to-2D rendering
    int has_peer_pos;       // 1 when peer position is valid
    float peer_pos[3];      // remote partner 3D world position (X, Y, Z in meters)
    float peer_yaw;         // partner facing angle in degrees (0 = +Z, 90 = +X)
    float peer_speed;       // partner horizontal movement speed in m/s (drives 3D walk animation)
    float peer_anim_phase;  // continuous walk-cycle phase in radians
    uint32_t peer_visual_flags; // optional COOP_SAMPLE_ROTATION/ANIMATION presence
    float peer_rotation[4]; // captured unit quaternion, separate from the yaw fallback
    char peer_animation[COOP_ANIMATION_MAX];
    float peer_animation_frame;
    int peer_action;        // COOP_ACT_*
    float peer_dist;        // 3D Euclidean distance to partner in meters
    int peer_on_screen;     // 1 when projected in front of the camera, 0 when clamped to screen edge
    float peer_screen[2];   // 2D window coordinates (pixels) for the overhead marker
    float peer_foot_screen[2]; // 2D window coordinates of partner's ground point
    char status_text[160];  // human-readable connection status for the F1 menu
    char event_banner[160]; // active session notification, empty when none
    float event_alpha;      // 0..1 fade of the shared-world toast
} CoopSnapshot;

// 1 when TOTK_COOP_MODE is not "off". Fast atomic check for render/overlay hooks.
int coop_active(void);

struct Cpu;
// Read-only guest observation before the presentation call releases its virtual core.
void coop_guest_observe(const struct Cpu *cpu);

// Capture a camera block from the guest snapshot when no replay-local update applies.
void coop_capture_camera(uint64_t cam_addr);
// Camera values after replay-local uniform updates have been applied; copied before returning.
void coop_capture_camera_values(const float camera[28]);

// Called once per presented frame from menu_overlay_frame: ticks the UDP socket / bot and fills *out for the UI.
void coop_tick(uint32_t width, uint32_t height, CoopSnapshot *out);

// Broadcasts a notification label to the connected partner. Does not change missions, inventory or saves.
void coop_notify_world_event(const char *label);

// Called from fs_host.c after a save commit completes.
void coop_on_save_commit(int changed_files);

// Repositions the visual test bot, or sends a rally notification without moving the remote player.
void coop_summon_partner(void);

// Reports that teleport is unavailable until a native world-thread operation and destination checks are verified.
void coop_teleport_to_partner(void);

// Toggles the local 3D test bot between following Link (COOP_BOT_FOLLOW) and holding position (COOP_BOT_STAY).
void coop_toggle_bot_mode(void);

#ifdef __cplusplus
}
#endif
