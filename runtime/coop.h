// Shared-world cooperative multiplayer (TOTK_COOP_MODE, TOTK_COOP_IP, TOTK_COOP_PORT).
// Synchronises 3D player positions, action states and shared world progression events over non-blocking UDP.
#pragma once
#include <stdint.h>

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

typedef struct {
    int mode;               // COOP_OFF .. COOP_BOT
    int connected;          // 1 when a peer (or local bot) exchanged packets within the last 5 s
    uint32_t ping_ms;       // latest round-trip estimate in ms
    uint32_t packets_tx;
    uint32_t packets_rx;
    uint32_t world_syncs;   // shared world / save progression events synced in this session
    int has_local_pos;      // 1 once the 3D scene camera block has been captured
    float local_pos[3];     // local player 3D world position (X, Y, Z in meters)
    float local_fwd[3];     // camera forward unit vector
    int local_action;       // COOP_ACT_*
    int has_peer_pos;       // 1 when peer position is valid
    float peer_pos[3];      // remote partner 3D world position (X, Y, Z in meters)
    float peer_yaw;
    int peer_action;        // COOP_ACT_*
    float peer_dist;        // 3D Euclidean distance to partner in meters
    int peer_on_screen;     // 1 when projected in front of the camera, 0 when clamped to screen edge
    float peer_screen[2];   // 2D window coordinates (pixels) for the overlay marker
    float peer_foot_screen[2]; // 2D window coordinates of partner's ground point
    char status_text[160];  // human-readable connection status for the F1 menu
    char event_banner[160]; // active shared-world progression toast, empty when none
    float event_alpha;      // 0..1 fade of the shared-world toast
} CoopSnapshot;

// 1 when TOTK_COOP_MODE is not "off". Fast atomic check for render/overlay hooks.
int coop_active(void);

// Called from vk_exec_draw.c when a scene draw binds the 0x940 camera uniform block at bank c4.
void coop_capture_camera(uint64_t cam_addr);

// Called once per presented frame from menu_overlay_frame: ticks the UDP socket / bot and fills *out for the UI.
void coop_tick(uint32_t width, uint32_t height, CoopSnapshot *out);

// Broadcasts a shared world progression event (mission flag / save commit) to the connected partner.
void coop_notify_world_event(const char *label);

// Called from fs_host.c after a save commit completes.
void coop_on_save_commit(int changed_files);

// Teleports the test bot or sends a rally beacon to the local player's current 3D world position.
void coop_summon_partner(void);

#ifdef __cplusplus
}
#endif
