// Experimental co-op presence (TOTK_COOP_MODE, TOTK_COOP_IP, TOTK_COOP_PORT).
//
// Presentation reads copies from the guest observer and ENet worker. It never touches actor or physics memory.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cfg.h"
#include "coop.h"
#include "coop_adapter.h"
#include "coop_net.h"
#include "coop_native_probe.h"
#include "coop_interp.h"
#include "host.h"
#include "nvn_api.h"
#include "platform/platform.h"
#include "vk.h"

#define EVENT_SHOW_NS 6000000000ull

// ---- state protected by lock
static PlatMutex C_lock = PLAT_MUTEX_INIT;
static volatile int C_active_flag;

static struct {
    unsigned cfg_ver;
    int mode;
    int bot_mode;
    char ip[64];
    int port;
    CoopNet *net;
    uint64_t last_notices;
    uint64_t net_session;
    int session_state;
    CoopInterpolator interpolation;
    uint64_t received_ns;

    // Camera & local player state
    uint64_t cam_frame;
    int has_camera;
    int has_local;
    int has_actor_pos;
    uint64_t actor;
    float local_pos[3];
    float local_fwd[3];
    float local_yaw;
    float vp[16];
    int local_action;

    // Remote partner state
    int has_peer;
    float peer_pos[3];
    float peer_target[3];
    float peer_yaw;
    float peer_speed;
    float peer_anim_phase;
    CoopSample peer_visual;
    int peer_action;
    uint64_t last_rx_ns;
    uint32_t ping_ms;
    uint32_t packets_tx;
    uint32_t packets_rx;
    uint32_t world_syncs;

    // Bot companion state
    int bot_spawned;
    int bot_walking;

    // Banner notification
    char event_banner[160];
    uint64_t event_until_ns;
} C;

static int parse_mode(const char *s) {
    if (!s || !strcmp(s, "off") || !strcmp(s, "0")) return COOP_OFF;
    if (!strcmp(s, "host")) return COOP_HOST;
    if (!strcmp(s, "client")) return COOP_CLIENT;
    if (!strcmp(s, "bot")) return COOP_BOT;
    return COOP_OFF;
}

static void configure_net_locked(void) {
    if (!C.net && (C.mode == COOP_HOST || C.mode == COOP_CLIENT)) C.net = coop_net_create();
    CoopNetConfig config = {.mode = C.mode == COOP_HOST ? 1 : C.mode == COOP_CLIENT ? 2 : 0,
                            .port = (uint16_t)C.port, .game_version = (uint32_t)rt_game_version,
                            .capabilities = coop_adapter_capabilities()};
    snprintf(config.ip, sizeof config.ip, "%s", C.ip);
    if (config.mode) {
        char content[256] = "";
        size_t at = 0;
        for (int i = 0; i < rt_exefs_sha256_count; i++) {
            const RtFileHash *h = &rt_exefs_sha256[i];
            if (!strcmp(h->file, "main") || !strcmp(h->file, "sdk") || !strcmp(h->file, "subsdk0"))
                at += (size_t)snprintf(content + at, sizeof content - at, "%s", h->sha256);
        }
        rt_sha256(content, at, config.content_id);
        if (!coop_net_player_id(rt_config()->profile, &config.player))
            rt_log("coop: cannot load or persist the isolated profile's player identity");
    }
    coop_net_configure(C.net, &config);
}

static void refresh_cfg_locked(void) {
    unsigned v = cfg_version();
    if (v == C.cfg_ver && C.cfg_ver != 0) return;
    C.cfg_ver = v ? v : 1;
    int m = parse_mode(cfg_value("TOTK_COOP_MODE"));
    const char *ip = cfg_value("TOTK_COOP_IP");
    int port = cfg_int("TOTK_COOP_PORT");
    if (port < 1024 || port > 65535) port = 7777;
    int changed = (m != C.mode) || (port != C.port) || strncmp(C.ip, ip ? ip : "127.0.0.1", sizeof C.ip - 1);
    C.mode = m;
    snprintf(C.ip, sizeof C.ip, "%s", ip && *ip ? ip : "127.0.0.1");
    C.port = port;
    __atomic_store_n(&C_active_flag, m != COOP_OFF, __ATOMIC_RELEASE);
    if (changed) {
        C.has_peer = 0;
        C.has_local = C.has_actor_pos = C.has_camera = 0;
        C.actor = C.cam_frame = 0;
        memset(C.local_pos, 0, sizeof C.local_pos);
        memset(C.local_fwd, 0, sizeof C.local_fwd);
        memset(C.vp, 0, sizeof C.vp);
        memset(C.peer_pos, 0, sizeof C.peer_pos);
        memset(C.peer_target, 0, sizeof C.peer_target);
        C.local_yaw = C.peer_yaw = 0;
        C.bot_spawned = 0;
        C.bot_walking = 0;
        C.peer_speed = C.peer_anim_phase = 0;
        C.last_rx_ns = 0;
        C.ping_ms = C.world_syncs = 0;
        C.last_notices = C.net_session = 0;
        C.interpolation.count = 0; C.received_ns = 0;
        C.event_until_ns = 0;
        C.event_banner[0] = 0;
        C.packets_rx = C.packets_tx = 0;
        configure_net_locked();
    }
}

int coop_active(void) {
    static unsigned seen_ver;
    unsigned v = cfg_version();
    unsigned seen = __atomic_load_n(&seen_ver, __ATOMIC_RELAXED);
    if (v != seen || !seen) {
        plat_mutex_lock(&C_lock);
        refresh_cfg_locked();
        __atomic_store_n(&seen_ver, C.cfg_ver, __ATOMIC_RELAXED);
        plat_mutex_unlock(&C_lock);
    }
    return __atomic_load_n(&C_active_flag, __ATOMIC_ACQUIRE);
}

void coop_guest_observe(const Cpu *cpu) {
    int active = coop_active();
    coop_adapter_trace_enable(active && rt_game_version == 143 && cfg_bool("TOTK_COOP_TRACE_GUEST"));
    if (!active) return;
    coop_adapter_observe(cpu);
    CoopAdapterSnapshot adapter;
    coop_adapter_snapshot(&adapter);
    int peer_probe = coop_native_probe_peer_enabled();
    CoopNetSnapshot peer;
    plat_mutex_lock(&C_lock);
    coop_net_publish(C.net, &adapter.sample);
    if (peer_probe) coop_net_snapshot(C.net, &peer);
    plat_mutex_unlock(&C_lock);
    if (peer_probe && coop_native_probe_peer_offer(&peer, adapter.sample.generation, plat_now_ns())) {
        plat_mutex_lock(&C_lock);
        coop_net_notice(C.net, "npc-velocity-ready-v1");
        plat_mutex_unlock(&C_lock);
    }
}

// Guest-snapshot entry for callers without replay-local uniform updates.
void coop_capture_camera(uint64_t cam_addr) {
    if (!__atomic_load_n(&C_active_flag, __ATOMIC_RELAXED) || !cam_addr) return;
    const float *f = (const float *)vk_usnap_bytes(cam_addr, 112);
    coop_capture_camera_values(f);
}

void coop_capture_camera_values(const float f[28]) {
    if (!__atomic_load_n(&C_active_flag, __ATOMIC_RELAXED) || !f) return;
    uint64_t frame = __atomic_load_n(&gfx_counters.frames, __ATOMIC_RELAXED);
    plat_mutex_lock(&C_lock);
    int captured = frame == C.cam_frame && C.has_camera;
    plat_mutex_unlock(&C_lock);
    if (captured) return;
    // Rows 0-2 are view, rows 3-6 view-projection. The replay may have updated them after its guest snapshot.
    for (int i = 0; i < 28; i++) if (!isfinite(f[i])) return;
    // Camera forward vector (-row 2 of R)
    float fx = -f[8], fy = -f[9], fz = -f[10];
    plat_mutex_lock(&C_lock);
    C.cam_frame = frame;
    C.has_camera = 1;
    C.local_fwd[0] = fx;
    C.local_fwd[1] = fy;
    C.local_fwd[2] = fz;
    memcpy(C.vp, f + 12, 16 * sizeof(float));
    plat_mutex_unlock(&C_lock);
}

static void tick_bot_locked(uint64_t now_ns, double dt) {
    if (!C.has_actor_pos) return;
    float lx = C.local_pos[0], ly = C.local_pos[1], lz = C.local_pos[2];
    if (!C.bot_spawned) {
        float fx = C.local_fwd[0], fz = C.local_fwd[2];
        float fh = sqrtf(fx * fx + fz * fz);
        float hfx = fh > 1e-4f ? fx / fh : 0.0f;
        float hfz = fh > 1e-4f ? fz / fh : 1.0f;
        C.peer_pos[0] = C.peer_target[0] = lx + hfx * 4.5f;
        C.peer_pos[1] = C.peer_target[1] = ly;
        C.peer_pos[2] = C.peer_target[2] = lz + hfz * 4.5f;
        C.peer_yaw = atan2f(-hfx, -hfz) * (180.0f / 3.14159265f);
        C.peer_speed = 0.0f;
        C.bot_spawned = 1;
        C.bot_walking = 0;
        C.has_peer = 1;
        snprintf(C.event_banner, sizeof C.event_banner,
                 "Bot visual de prueba: 4.5 m frente a Link");
        C.event_until_ns = now_ns + EVENT_SHOW_NS;
    }

    float to_link_x = lx - C.peer_pos[0];
    float to_link_y = ly - C.peer_pos[1];
    float to_link_z = lz - C.peer_pos[2];
    float dist_xz = sqrtf(to_link_x * to_link_x + to_link_z * to_link_z);

    if (C.bot_mode == COOP_BOT_STAY) {
        // Hold fixed 3D position in Hyrule so the player can walk far away and test "Teleport to Partner"
        C.bot_walking = 0;
        C.peer_speed = 0.0f;
        if (dist_xz > 0.25f) {
            C.peer_yaw = atan2f(to_link_x, to_link_z) * (180.0f / 3.14159265f);
        }
    } else {
        // Follow mode with hysteresis: stand calmly when within 5.5 m, jog after Link when further away
        if (dist_xz > 5.5f) C.bot_walking = 1;
        else if (dist_xz < 3.4f) C.bot_walking = 0;

        if (C.bot_walking && dist_xz > 0.1f) {
            float dir_x = to_link_x / dist_xz;
            float dir_z = to_link_z / dist_xz;
            float speed = (dist_xz - 3.0f) * 2.2f;
            if (speed < 2.6f) speed = 2.6f;
            if (speed > 8.0f) speed = 8.0f;
            float step = (float)fmin((double)speed * dt, (double)(dist_xz - 3.2f));
            if (step > 0.0f) {
                C.peer_pos[0] += dir_x * step;
                C.peer_pos[2] += dir_z * step;
            }
            float y_rate = (float)fmin(1.0, dt * 6.0);
            C.peer_pos[1] += to_link_y * y_rate;
            C.peer_yaw = atan2f(dir_x, dir_z) * (180.0f / 3.14159265f);
            C.peer_speed = speed;
            C.peer_anim_phase = fmodf(C.peer_anim_phase + (float)dt * speed * 2.5f, 6.2831853f);
        } else {
            C.peer_speed = 0.0f;
            float y_rate = (float)fmin(1.0, dt * 4.0);
            if (fabsf(to_link_y) < 3.0f) C.peer_pos[1] += to_link_y * y_rate;
            if (dist_xz > 0.25f) {
                C.peer_yaw = atan2f(to_link_x, to_link_z) * (180.0f / 3.14159265f);
            }
        }
    }

    // Mirror Link's combat/ability stance so the user can test bow and Zonai ability poses in real time
    C.peer_action = C.local_action;
}

// Projects a 3D world point (x, y, z) through the row-major 4x4 View-Projection matrix vp[0..15] to 2D window pixels.
static int project_3d(const float vp[16], const float p[3], float w, float h, float out[2]) {
    float x = p[0], y = p[1], z = p[2];
    float cx = vp[0] * x + vp[1] * y + vp[2] * z + vp[3];
    float cy = vp[4] * x + vp[5] * y + vp[6] * z + vp[7];
    float cw = vp[12] * x + vp[13] * y + vp[14] * z + vp[15];
    if (cw > 0.1f) {
        float ndc_x = cx / cw;
        float ndc_y = cy / cw;
        out[0] = (ndc_x * 0.5f + 0.5f) * w;
        out[1] = (0.5f - ndc_y * 0.5f) * h;
        if (out[0] >= 24.0f && out[0] <= w - 24.0f && out[1] >= 24.0f && out[1] <= h - 24.0f) return 1;
    }
    // Behind camera or off-screen: clamp to screen border so the player always knows which direction their partner is
    float dir_x = cw > 0.0f ? cx : -cx;
    float dir_y = cw > 0.0f ? -cy : cy;
    float len = sqrtf(dir_x * dir_x + dir_y * dir_y);
    if (len < 1e-4f) {
        dir_x = 0.0f;
        dir_y = -1.0f;
    } else {
        dir_x /= len;
        dir_y /= len;
    }
    float pad = 48.0f;
    float rx = (w * 0.5f - pad) * dir_x + w * 0.5f;
    float ry = (h * 0.5f - pad) * dir_y + h * 0.5f;
    out[0] = fmaxf(pad, fminf(w - pad, rx));
    out[1] = fmaxf(pad, fminf(h - pad, ry));
    return 0;
}

void coop_tick(uint32_t width, uint32_t height, CoopSnapshot *out) {
    memset(out, 0, sizeof *out);
    uint64_t now = plat_now_ns();
    static uint64_t last_tick_ns;
    double dt = last_tick_ns ? (double)(now - last_tick_ns) / 1e9 : 1.0 / 60.0;
    if (dt < 0.0001 || dt > 0.25) dt = 1.0 / 60.0;
    last_tick_ns = now;

    CoopAdapterSnapshot adapter;
    coop_adapter_snapshot(&adapter);
    int observed = adapter.sample.time_ns && now - adapter.sample.time_ns < 1000000000ull;
    uint64_t actor = observed && (adapter.sample.flags & COOP_SAMPLE_PLAYER) ? adapter.actor : 0;
    const float *actor_pos = adapter.sample.pos;
    float actor_yaw = adapter.sample.yaw;
    int act = (int)adapter.sample.action;

    plat_mutex_lock(&C_lock);
    refresh_cfg_locked();
    C.local_action = act;
    if (C.mode == COOP_OFF) {
        plat_mutex_unlock(&C_lock);
        return;
    }

    float jump = actor && C.has_actor_pos
                     ? hypotf(hypotf(actor_pos[0] - C.local_pos[0], actor_pos[2] - C.local_pos[2]),
                              actor_pos[1] - C.local_pos[1]) : 0;
    if (!actor || actor != C.actor || jump > 128.0f) {
        C.bot_spawned = C.bot_walking = 0;
        if (C.mode == COOP_BOT) C.has_peer = 0;
    }
    C.actor = actor;
    C.has_local = C.has_actor_pos = actor != 0;
    if (actor) {
        memcpy(C.local_pos, actor_pos, sizeof C.local_pos);
        C.local_yaw = actor_yaw;
    } else {
        memset(C.local_pos, 0, sizeof C.local_pos);
        C.local_yaw = 0;
    }

    if (C.mode == COOP_BOT) {
        tick_bot_locked(now, dt);
    } else {
        CoopNetSnapshot network;
        coop_net_snapshot(C.net, &network);
        C.session_state = network.state;
        C.packets_tx = network.packets_tx; C.packets_rx = network.packets_rx; C.ping_ms = network.ping_ms;
        if (C.net_session != network.session) {
            C.has_peer = 0; C.last_notices = 0; C.net_session = network.session;
            C.interpolation.count = 0; C.received_ns = 0;
        }
        C.has_peer = network.has_remote;
        if (C.has_peer) {
            if (C.received_ns != network.state_received_ns) {
                coop_interp_push(&C.interpolation, &network.remote, network.state_received_ns);
                C.received_ns = network.state_received_ns;
            }
            CoopSample visual = network.remote;
            coop_interp_read(&C.interpolation, now, &visual);
            memcpy(C.peer_pos, visual.pos, sizeof C.peer_pos);
            C.peer_yaw = visual.yaw; C.peer_action = (int)visual.action;
            C.peer_visual = visual;
            C.peer_speed = hypotf(visual.velocity[0], visual.velocity[2]);
            C.last_rx_ns = now;
        } else {
            C.last_rx_ns = 0; C.peer_speed = 0; C.interpolation.count = 0; C.received_ns = 0;
        }
        if (network.notices != C.last_notices) {
            if (network.notices > C.last_notices) C.world_syncs += (uint32_t)(network.notices - C.last_notices);
            C.last_notices = network.notices;
            snprintf(C.event_banner, sizeof C.event_banner, "%s", network.notice);
            C.event_until_ns = now + EVENT_SHOW_NS;
        }
        if (network.error[0]) snprintf(out->status_text, sizeof out->status_text, "%s", network.error);
        if (C.has_peer) {
            if (C.peer_speed > 0.1f) {
                C.peer_anim_phase = fmodf(C.peer_anim_phase + (float)dt * C.peer_speed * 2.5f, 6.2831853f);
            }
        }
    }

    int connected = C.mode == COOP_BOT ? C.bot_spawned && C.has_actor_pos
                                         : C.session_state == COOP_SESSION_LOADING || C.session_state == COOP_SESSION_READY;
    out->mode = C.mode;
    out->session_state = C.session_state;
    out->native_capabilities = coop_adapter_capabilities();
    out->observation_generation = adapter.sample.generation;
    out->commands_rejected = adapter.commands_rejected + adapter.commands_stale;
    snprintf(out->adapter_status, sizeof out->adapter_status, "%s", adapter.reason[0] ? adapter.reason :
             "Waiting for the guest observer; native actor operations disabled");
    out->bot_mode = C.bot_mode;
    out->connected = connected;
    out->ping_ms = C.ping_ms;
    out->packets_tx = C.packets_tx;
    out->packets_rx = C.packets_rx;
    out->world_syncs = C.world_syncs;
    out->has_local_pos = C.has_local;
    out->has_camera = C.has_camera;
    memcpy(out->local_pos, C.local_pos, sizeof out->local_pos);
    memcpy(out->local_fwd, C.local_fwd, sizeof out->local_fwd);
    memcpy(out->vp, C.vp, sizeof out->vp);
    out->local_action = C.local_action;
    out->has_peer_pos = connected && C.has_peer;
    if (out->has_peer_pos) {
        memcpy(out->peer_pos, C.peer_pos, sizeof out->peer_pos);
        out->peer_yaw = C.peer_yaw;
        out->peer_speed = C.peer_speed;
        out->peer_anim_phase = C.peer_anim_phase;
        if (C.mode != COOP_BOT) {
            out->peer_visual_flags = C.peer_visual.flags & (COOP_SAMPLE_ROTATION | COOP_SAMPLE_ANIMATION);
            memcpy(out->peer_rotation, C.peer_visual.rotation, sizeof out->peer_rotation);
            memcpy(out->peer_animation, C.peer_visual.animation, sizeof out->peer_animation);
            out->peer_animation_frame = C.peer_visual.animation_frame;
        }
        out->peer_action = C.peer_action;
        float dx = C.peer_pos[0] - C.local_pos[0];
        float dy = C.peer_pos[1] - C.local_pos[1];
        float dz = C.peer_pos[2] - C.local_pos[2];
        out->peer_dist = sqrtf(dx * dx + dy * dy + dz * dz);
        if (C.has_local && C.has_camera && width > 0 && height > 0) {
            float head[3] = {C.peer_pos[0], C.peer_pos[1] + 2.05f, C.peer_pos[2]};
            out->peer_on_screen = project_3d(C.vp, head, (float)width, (float)height, out->peer_screen);
            project_3d(C.vp, C.peer_pos, (float)width, (float)height, out->peer_foot_screen);
        }
    }

    if (C.mode == COOP_BOT) {
        if (C.has_actor_pos)
            snprintf(out->status_text, sizeof out->status_text, "Bot visual (%s) · %.1f m",
                     C.bot_mode == COOP_BOT_STAY ? "Posición fija" : "Siguiendo", out->peer_dist);
        else snprintf(out->status_text, sizeof out->status_text, "Bot visual: esperando partida cargada");
    } else if (out->status_text[0]) {
        // The worker already supplied a concrete initialization or negotiation error.
    } else if (connected) {
        snprintf(out->status_text, sizeof out->status_text, "ENet conectado · %u ms · %.1f m · motor pendiente",
                 out->ping_ms, out->peer_dist);
    } else if (!C.net) {
        snprintf(out->status_text, sizeof out->status_text, "No se pudo iniciar el trabajador de red");
    } else if (C.session_state == COOP_SESSION_DISCONNECTED) {
        snprintf(out->status_text, sizeof out->status_text, "Desconectado: vuelve a entrar para reconectar");
    } else if (C.mode == COOP_HOST) {
        snprintf(out->status_text, sizeof out->status_text, "Esperando compañero en ENet :%d...", C.port);
    } else {
        snprintf(out->status_text, sizeof out->status_text, "ENet: %s:%d · conectando/cargando...", C.ip, C.port);
    }

    if (now < C.event_until_ns && C.event_banner[0]) {
        snprintf(out->event_banner, sizeof out->event_banner, "%s", C.event_banner);
        double rem = (double)(C.event_until_ns - now) / 1e9;
        out->event_alpha = rem < 1.0 ? (float)rem : 1.0f;
    }
    plat_mutex_unlock(&C_lock);
}

void coop_notify_world_event(const char *label) {
    if (!coop_active()) return;
    uint64_t now = plat_now_ns();
    plat_mutex_lock(&C_lock);
    C.world_syncs++;
    snprintf(C.event_banner, sizeof C.event_banner, "%s (Evento #%u)",
             label && *label ? label : "Aviso de sesión", C.world_syncs);
    C.event_until_ns = now + EVENT_SHOW_NS;
    if (C.mode == COOP_HOST || C.mode == COOP_CLIENT) coop_net_notice(C.net, C.event_banner);
    rt_log("coop: notification #%u sent: %s", C.world_syncs, C.event_banner);
    plat_mutex_unlock(&C_lock);
}

void coop_on_save_commit(int changed_files) {
    if (!__atomic_load_n(&C_active_flag, __ATOMIC_RELAXED) || changed_files <= 0) return;
    char msg[128];
    snprintf(msg, sizeof msg, "Guardado local completado (%d archivos; sin replicar)", changed_files);
    coop_notify_world_event(msg);
}

void coop_summon_partner(void) {
    if (!coop_active()) return;
    plat_mutex_lock(&C_lock);
    if (!C.has_actor_pos) {
        plat_mutex_unlock(&C_lock);
        return;
    }
    if (C.mode == COOP_BOT) {
        float fx = C.local_fwd[0], fz = C.local_fwd[2];
        float fh = sqrtf(fx * fx + fz * fz);
        float hfx = fh > 1e-4f ? fx / fh : 0.0f;
        float hfz = fh > 1e-4f ? fz / fh : 1.0f;
        C.peer_pos[0] = C.peer_target[0] = C.local_pos[0] + hfx * 4.5f;
        C.peer_pos[1] = C.peer_target[1] = C.local_pos[1];
        C.peer_pos[2] = C.peer_target[2] = C.local_pos[2] + hfz * 4.5f;
        C.peer_yaw = atan2f(-hfx, -hfz) * (180.0f / 3.14159265f);
        C.peer_speed = 0.0f;
        C.has_peer = 1;
        C.bot_spawned = 1;
        C.bot_walking = 0;
    }
    plat_mutex_unlock(&C_lock);
    coop_notify_world_event("Solicitud de reunión en la posición de Link (baliza visual)");
}

void coop_teleport_to_partner(void) {
    if (!coop_active()) return;
    plat_mutex_lock(&C_lock);
    // No guest writes or success event: neither the actor/physics operation nor its scheduling phase is verified.
    // See docs/coop.md. Being on a guest thread or near the destination does not establish safety.
    snprintf(C.event_banner, sizeof C.event_banner, "Teletransporte no disponible: integración con el motor pendiente");
    C.event_until_ns = plat_now_ns() + EVENT_SHOW_NS;
    plat_mutex_unlock(&C_lock);
}

void coop_toggle_bot_mode(void) {
    plat_mutex_lock(&C_lock);
    C.bot_mode = (C.bot_mode == COOP_BOT_FOLLOW) ? COOP_BOT_STAY : COOP_BOT_FOLLOW;
    int bm = C.bot_mode;
    plat_mutex_unlock(&C_lock);
    coop_notify_world_event(bm == COOP_BOT_STAY
                                ? "Bot visual: posición fija activada"
                                : "Bot visual: seguimiento de Link activado");
}
