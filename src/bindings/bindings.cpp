#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <ctime>
#include <tuple>
#include <vector>
#include "../../include/core/Game.h"
#include "../../include/levels/ClassicLevel.h"
#include "../../include/factories/PowerUpFactory.h"
#include "../../include/entities/DumbBot.h"

namespace py = pybind11;

namespace {

struct BombSite {
    int dist;
    int bx;
    int by;
    int targets;
    int enemy_targets;
    int compressed;
    bool trap;
};

py::tuple compute_bfs_features_cpp(
    py::array_t<float, py::array::c_style | py::array::forcecast> base_obs,
    bool is_alive,
    int px,
    int py,
    bool has_ring,
    bool has_hammer,
    int bomb_radius,
    int avail_bombs,
    int speed_level,
    int cur_cooldown = 0
) {
    auto buf = base_obs.request();
    const int channels = static_cast<int>(buf.shape[0]);
    const int h = static_cast<int>(buf.shape[1]);
    const int w = static_cast<int>(buf.shape[2]);
    const int hw = h * w;
    const float* ptr = static_cast<const float*>(buf.ptr);

    py::array_t<float> reach_arr({h, w});
    py::array_t<float> bomb_arr({h, w});
    float* reach_map = static_cast<float*>(reach_arr.request().ptr);
    float* bomb_map = static_cast<float*>(bomb_arr.request().ptr);
    std::fill(reach_map, reach_map + hw, 0.0f);
    std::fill(bomb_map, bomb_map + hw, 0.0f);

    if (!is_alive || px < 0 || px >= w || py < 0 || py >= h) {
        py::dict analysis;
        analysis["safe_escape_from_here"] = false;
        analysis["bomb_targets_here"] = 0;
        analysis["enemy_targets_here"] = 0;
        analysis["enemy_space_compressed_here"] = 0;
        analysis["trap_bomb_here"] = false;
        analysis["total_enemy_safe_tiles"] = 0;
        analysis["trapped_enemies_count"] = 0;
        analysis["in_danger"] = false;
        analysis["escape_action"] = 0;
        analysis["safe_escape_moves"] = py::list();
        analysis["safe_reachable_count"] = 0;
        analysis["hunt_action"] = 0;
        py::list vm;
        vm.append(0);
        analysis["valid_moves"] = vm;
        analysis["can_place_bomb"] = false;
        analysis["can_push_bomb_now"] = false;
        analysis["push_actions"] = py::list();
        analysis["tactical_push_actions"] = py::list();
        analysis["active_bombs_count"] = 0;
        analysis["local_active_bombs"] = 0;
        analysis["closest_bombing_site"] = py::none();
        return py::make_tuple(reach_arr, bomb_arr, 0.0f, analysis);
    }

    const float* ch_solid = ptr + 0 * hw;
    const float* ch_breakable = ptr + 1 * hw;
    const float* ch_bombs = ptr + 2 * hw;
    const float* ch_danger = ptr + 3 * hw;
    const float* ch_flames = ptr + 4 * hw;
    const float* ch_powerups = ptr + 5 * hw;
    const float* ch_enemies = ptr + 7 * hw;

    std::vector<uint8_t> solid(hw, 0);
    std::vector<uint8_t> breakable(hw, 0);
    std::vector<uint8_t> bombs(hw, 0);
    std::vector<uint8_t> flames(hw, 0);
    std::vector<uint8_t> useful_powerups(hw, 0);
    std::vector<uint8_t> enemies(hw, 0);
    std::vector<std::pair<int, int>> en_all;
    int active_bombs_count = 0;
    int local_active_bombs = 0;

    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            int idx = y * w + x;
            solid[idx] = ch_solid[idx] > 0.0f;
            breakable[idx] = ch_breakable[idx] > 0.0f;
            bombs[idx] = ch_bombs[idx] > 0.0f;
            if (bombs[idx]) {
                active_bombs_count++;
                if (std::abs(x - px) + std::abs(y - py) <= bomb_radius + 3) {
                    local_active_bombs++;
                }
            }
            flames[idx] = ch_flames[idx] > 0.0f;
            enemies[idx] = ch_enemies[idx] > 0.0f;
            if (enemies[idx]) {
                en_all.emplace_back(x, y);
            }
            if (channels >= 17) {
                bool u = (ptr[10 * hw + idx] > 0.0f) ||
                         (ptr[12 * hw + idx] > 0.0f) ||
                         (ptr[11 * hw + idx] > 0.0f && speed_level < 2) ||
                         (ptr[13 * hw + idx] > 0.0f && !has_hammer) ||
                         (ptr[14 * hw + idx] > 0.0f && !has_ring);
                useful_powerups[idx] = u ? 1 : 0;
            } else {
                useful_powerups[idx] = ch_powerups[idx] > 0.0f ? 1 : 0;
            }
        }
    }

    const int p_idx = py * w + px;
    const bool in_danger = ch_danger[p_idx] > 0.0f;
    const int move_cd = std::max(4, 6 - std::clamp(speed_level, 0, 2));
    const int init_wait = std::max(0, cur_cooldown - 1);
    const int post_bomb_wait = std::max(0, cur_cooldown - 2);

    // Reconstruct remaining time-to-explode (in C++ ticks) for every tile from Channel 3 (ch_danger)
    std::vector<int> base_tte(hw, 9999);
    for (int i = 0; i < hw; ++i) {
        if (flames[i] || ch_danger[i] >= 0.995f) {
            base_tte[i] = 0;
        } else if (ch_danger[i] > 0.0f) {
            base_tte[i] = std::max(1, static_cast<int>(std::lround((1.0f - ch_danger[i]) * 100.0f)));
        }
    }

    constexpr int ACT_IDS[4] = {1, 2, 3, 4};
    constexpr int DX[4] = {0, 0, -1, 1};
    constexpr int DY[4] = {-1, 1, 0, 0};

    auto can_push_bomb_in_dir = [&](int dx, int dy) -> bool {
        if (!has_hammer || (dx == 0 && dy == 0) || bombs[p_idx]) return false;
        int bx = px + dx, by = py + dy;
        int dest_x = bx + dx, dest_y = by + dy;
        if (bx < 0 || bx >= w || by < 0 || by >= h || dest_x < 0 || dest_x >= w || dest_y < 0 || dest_y >= h) {
            return false;
        }
        if (!bombs[by * w + bx]) return false;
        int d_idx = dest_y * w + dest_x;
        if (solid[d_idx] || breakable[d_idx] || bombs[d_idx] || flames[d_idx] || enemies[d_idx]) {
            return false;
        }
        return true;
    };

    auto has_enemy_push_target_in_dir = [&](int dx, int dy) -> bool {
        // Check if kicking the adjacent bomb at (px+dx, py+dy) in direction (dx, dy)
        // slides it toward an enemy (either on the slide line or within blast radius of the slide path)
        int cur_x = px + dx;
        int cur_y = py + dy;
        for (int step = 1; step <= 8; ++step) {
            int nx = cur_x + dx * step;
            int ny = cur_y + dy * step;
            if (nx < 0 || nx >= w || ny < 0 || ny >= h) break;
            int n_idx = ny * w + nx;
            if (solid[n_idx] || breakable[n_idx] || bombs[n_idx]) break;
            if (enemies[n_idx]) return true;
            // Also check perpendicular within 2 tiles along the slide path
            int px1 = nx + dy, py1 = ny + dx;
            if (px1 >= 0 && px1 < w && py1 >= 0 && py1 < h && enemies[py1 * w + px1]) return true;
            int px2 = nx - dy, py2 = ny - dx;
            if (px2 >= 0 && px2 < w && py2 >= 0 && py2 < h && enemies[py2 * w + px2]) return true;
        }
        return false;
    };

    std::vector<uint8_t> passable(hw, 0);
    for (int i = 0; i < hw; ++i) {
        if (has_ring) {
            passable[i] = !(solid[i] || breakable[i] || flames[i]);
        } else {
            passable[i] = !(solid[i] || breakable[i] || bombs[i] || flames[i]);
        }
    }
    if (has_ring && has_hammer && !bombs[p_idx]) {
        for (int dir = 0; dir < 4; ++dir) {
            if (can_push_bomb_in_dir(DX[dir], DY[dir])) {
                passable[(py + DY[dir]) * w + (px + DX[dir])] = 0;
            }
        }
    }

    std::vector<int> dist(hw, -1);
    std::vector<int> first_action(hw, 0);
    std::vector<int> qx(hw);
    std::vector<int> qy(hw);
    int q_head = 0, q_tail = 0;

    qx[q_tail] = px;
    qy[q_tail] = py;
    q_tail++;
    dist[p_idx] = 0;
    reach_map[p_idx] = (ch_danger[p_idx] == 0.0f) ? 1.0f : 0.2f;

    std::vector<int> valid_moves = {0};
    int escape_action = 0;
    int min_safe_dist = 999;

    while (q_head < q_tail) {
        int cx = qx[q_head];
        int cy = qy[q_head];
        q_head++;
        int c_idx = cy * w + cx;
        int d = dist[c_idx];
        if (d >= 26) continue;

        for (int dir = 0; dir < 4; ++dir) {
            int act_id = ACT_IDS[dir];
            int nx = cx + DX[dir];
            int ny = cy + DY[dir];
            if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
                int n_idx = ny * w + nx;
                if (dist[n_idx] == -1 && passable[n_idx]) {
                    int next_d = d + 1;
                    int tile_tte = base_tte[n_idx];
                    if (!in_danger && tile_tte < 9999) continue;
                    // When escaping danger, allow stepping onto a permanently safe tile (9999)
                    // or an intermediate danger tile that survives until we leave it on tick init_wait + next_d * move_cd + 1.
                    if (in_danger) {
                        if (d == 0 && base_tte[p_idx] <= init_wait) continue;
                        if (tile_tte < 9999 && tile_tte <= init_wait + next_d * move_cd) continue;
                    }

                    dist[n_idx] = next_d;
                    int fa = (d == 0) ? act_id : first_action[c_idx];
                    first_action[n_idx] = fa;
                    if (d == 0) {
                        valid_moves.push_back(act_id);
                    }
                    if (tile_tte == 9999) {
                        reach_map[n_idx] = std::max(0.1f, 1.0f - static_cast<float>(next_d) / 26.0f);
                        if (next_d < min_safe_dist) {
                            min_safe_dist = next_d;
                            escape_action = fa;
                        }
                    } else {
                        reach_map[n_idx] = 0.15f;
                    }
                    qx[q_tail] = nx;
                    qy[q_tail] = ny;
                    q_tail++;
                }
            }
        }
    }

    std::vector<int> blast_stamp(hw, 0);
    std::vector<int> sim_tte_stamp(hw, 0);
    std::vector<int> sim_tte_val(hw, 9999);
    std::vector<int> bfs_stamp(hw, 0);
    std::vector<int> bfs_dist(hw, 0);
    std::vector<int> bqx(hw);
    std::vector<int> bqy(hw);
    int cur_blast_id = 0;
    int cur_sim_id = 0;
    int cur_bfs_id = 0;

    // Independent per-direction fuse-accurate escape verification when in_danger:
    // finds ALL initial directions a in {1..4} that can reach a permanently safe tile (base_tte == 9999)
    // before any traversed tile explodes under the player's actual move_cd and init_wait.
    std::vector<int> safe_escape_moves;
    if (in_danger && base_tte[p_idx] > init_wait) {
        int best_escape_dist = 999;
        for (int dir = 0; dir < 4; ++dir) {
            int act_id = ACT_IDS[dir];
            int sx = px + DX[dir];
            int sy = py + DY[dir];
            if (sx < 0 || sx >= w || sy < 0 || sy >= h) continue;
            int s_idx = sy * w + sx;
            if (!passable[s_idx]) continue;
            if (base_tte[s_idx] == 9999) {
                safe_escape_moves.push_back(act_id);
                if (1 < best_escape_dist) {
                    best_escape_dist = 1;
                    escape_action = act_id;
                }
                continue;
            }
            if (base_tte[s_idx] <= init_wait + move_cd) continue;

            int sid = ++cur_bfs_id;
            int head = 0, tail = 0;
            bfs_stamp[p_idx] = sid;
            bfs_stamp[s_idx] = sid;
            bfs_dist[s_idx] = 1;
            bqx[tail] = sx;
            bqy[tail] = sy;
            tail++;

            int found_dist = -1;
            while (head < tail && found_dist < 0) {
                int cx = bqx[head];
                int cy = bqy[head];
                head++;
                int cd = bfs_dist[cy * w + cx];
                if (cd >= 16) continue;
                for (int nd = 0; nd < 4; ++nd) {
                    int nx = cx + DX[nd];
                    int ny = cy + DY[nd];
                    if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
                    int n_idx = ny * w + nx;
                    if (bfs_stamp[n_idx] == sid || !passable[n_idx]) continue;
                    int next_d = cd + 1;
                    int n_tte = base_tte[n_idx];
                    if (n_tte == 9999) {
                        found_dist = next_d;
                        break;
                    }
                    if (n_tte > init_wait + next_d * move_cd) {
                        bfs_stamp[n_idx] = sid;
                        bfs_dist[n_idx] = next_d;
                        bqx[tail] = nx;
                        bqy[tail] = ny;
                        tail++;
                    }
                }
            }
            if (found_dist > 0) {
                safe_escape_moves.push_back(act_id);
                if (found_dist < best_escape_dist) {
                    best_escape_dist = found_dist;
                    escape_action = act_id;
                }
            }
        }
    }

    std::vector<int> push_actions;
    std::vector<int> tactical_push_actions;
    if (has_hammer && !bombs[p_idx]) {
        bool trapped_without_walk_escape = (in_danger && safe_escape_moves.empty() && escape_action == 0);
        for (int dir = 0; dir < 4; ++dir) {
            int act_id = ACT_IDS[dir];
            int dx = DX[dir], dy = DY[dir];
            if (can_push_bomb_in_dir(dx, dy)) {
                push_actions.push_back(act_id);
                if (std::find(valid_moves.begin(), valid_moves.end(), act_id) == valid_moves.end()) {
                    valid_moves.push_back(act_id);
                }
                if (trapped_without_walk_escape || has_enemy_push_target_in_dir(dx, dy)) {
                    tactical_push_actions.push_back(act_id);
                    bomb_map[(py + dy) * w + (px + dx)] = 1.0f;
                }
                if (trapped_without_walk_escape) {
                    if (std::find(safe_escape_moves.begin(), safe_escape_moves.end(), act_id) == safe_escape_moves.end()) {
                        safe_escape_moves.push_back(act_id);
                    }
                    if (escape_action == 0) {
                        escape_action = act_id;
                    }
                }
            }
        }
    }
    const bool can_push_bomb_now = !push_actions.empty();

    auto mark_blast_zone = [&](int bx, int by, int radius) -> int {
        int bid = ++cur_blast_id;
        blast_stamp[by * w + bx] = bid;
        for (int dir = 0; dir < 4; ++dir) {
            int dx = DX[dir], dy = DY[dir];
            for (int r = 1; r <= radius; ++r) {
                int nx = bx + dx * r;
                int ny = by + dy * r;
                if (nx < 0 || nx >= w || ny < 0 || ny >= h) break;
                int n_idx = ny * w + nx;
                if (solid[n_idx]) break;
                blast_stamp[n_idx] = bid;
                if (breakable[n_idx] || bombs[n_idx]) break;
            }
        }
        return bid;
    };

    // Complete fuse-aware & chain-aware hypothetical bomb escape check:
    // Fuses the hypothetical bomb's blast zone and chained explosion time T_hyp into sim_tte
    // across EVERY tile along the escape path (not just the destination), and validates each
    // intermediate tile's entry/exit timing against move_cd and post_bomb_wait.
    auto has_escape_if_bomb_at = [&](int bx, int by, int radius) -> bool {
        int start_idx = by * w + bx;
        int t_hyp = std::min(90, base_tte[start_idx]);
        // Player places bomb on Tick 1, then leaves (bx, by) on Tick 2 + post_bomb_wait.
        // Thus (bx, by) must survive through Tick 1 + post_bomb_wait.
        if (t_hyp <= 1 + post_bomb_wait) {
            return false;
        }

        int sim_id = ++cur_sim_id;
        auto get_sim_tte = [&](int idx) -> int {
            return (sim_tte_stamp[idx] == sim_id) ? sim_tte_val[idx] : base_tte[idx];
        };
        auto set_min_sim_tte = [&](int idx, int val) {
            int cur_v = get_sim_tte(idx);
            if (val < cur_v) {
                sim_tte_stamp[idx] = sim_id;
                sim_tte_val[idx] = val;
            }
        };

        // Propagate hypothetical bomb blast zone AND any secondary bombs it chain-detonates earlier
        struct ChainNode { int x; int y; int rad; int tte; };
        ChainNode chain_q[32];
        int cq_head = 0, cq_tail = 0;
        chain_q[cq_tail++] = {bx, by, radius, t_hyp};
        set_min_sim_tte(start_idx, t_hyp);

        while (cq_head < cq_tail) {
            ChainNode cn = chain_q[cq_head++];
            for (int dir = 0; dir < 4; ++dir) {
                int dx = DX[dir], dy = DY[dir];
                for (int r = 1; r <= cn.rad; ++r) {
                    int nx = cn.x + dx * r;
                    int ny = cn.y + dy * r;
                    if (nx < 0 || nx >= w || ny < 0 || ny >= h) break;
                    int n_idx = ny * w + nx;
                    if (solid[n_idx]) break;
                    int prev_tte = get_sim_tte(n_idx);
                    set_min_sim_tte(n_idx, cn.tte);
                    if (bombs[n_idx]) {
                        if (cn.tte < prev_tte && cq_tail < 32) {
                            chain_q[cq_tail++] = {nx, ny, std::max(radius, 4), cn.tte};
                        }
                        break;
                    }
                    if (breakable[n_idx]) break;
                }
            }
        }

        // BFS escape path from (bx, by) checking EVERY traversed tile against sim_tte
        int max_search_steps = std::min(16, std::max(6, radius + 4));
        int sid = ++cur_bfs_id;
        int head = 0, tail = 0;
        bfs_stamp[start_idx] = sid;
        bfs_dist[start_idx] = 0;
        bqx[tail] = bx;
        bqy[tail] = by;
        tail++;

        while (head < tail) {
            int cx = bqx[head];
            int cy = bqy[head];
            head++;
            int cd = bfs_dist[cy * w + cx];
            if (cd >= max_search_steps) continue;

            for (int dir = 0; dir < 4; ++dir) {
                int nx = cx + DX[dir];
                int ny = cy + DY[dir];
                if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
                int n_idx = ny * w + nx;
                if (bfs_stamp[n_idx] == sid || !passable[n_idx]) continue;

                int next_d = cd + 1;
                int tile_tte = get_sim_tte(n_idx);
                if (tile_tte == 9999) {
                    return true;
                }
                // After placing a bomb on Tick 1, step next_d arrives on Tick 2 + post_bomb_wait + (next_d - 1) * move_cd
                // and leaves on Tick 2 + post_bomb_wait + next_d * move_cd.
                // Thus intermediate tile n_idx must remain unexploded through Tick 1 + post_bomb_wait + next_d * move_cd.
                if (tile_tte > 1 + post_bomb_wait + next_d * move_cd) {
                    bfs_stamp[n_idx] = sid;
                    bfs_dist[n_idx] = next_d;
                    bqx[tail] = nx;
                    bqy[tail] = ny;
                    tail++;
                }
            }
        }
        return false;
    };

    auto count_enemy_safe_tiles = [&](int ex, int ey, int sim_bx, int sim_by, int bid, int max_steps) -> int {
        int sid = ++cur_bfs_id;
        int head = 0, tail = 0;
        int e_idx = ey * w + ex;
        bfs_stamp[e_idx] = sid;
        bfs_dist[e_idx] = 0;
        bqx[tail] = ex;
        bqy[tail] = ey;
        tail++;

        int safe_tiles = 0;
        if (ch_danger[e_idx] == 0.0f && (bid < 0 || blast_stamp[e_idx] != bid)) {
            safe_tiles++;
        }

        while (head < tail) {
            int cx = bqx[head];
            int cy = bqy[head];
            head++;
            int cd = bfs_dist[cy * w + cx];
            if (cd >= max_steps) continue;

            for (int dir = 0; dir < 4; ++dir) {
                int nx = cx + DX[dir];
                int ny = cy + DY[dir];
                if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
                int n_idx = ny * w + nx;
                if (bfs_stamp[n_idx] == sid) continue;
                if (solid[n_idx] || breakable[n_idx] || bombs[n_idx] || flames[n_idx] ||
                    (sim_bx == nx && sim_by == ny) || (nx == px && ny == py)) {
                    continue;
                }
                if (ch_danger[n_idx] >= 0.88f) continue;
                bfs_stamp[n_idx] = sid;
                bfs_dist[n_idx] = cd + 1;
                if (ch_danger[n_idx] == 0.0f && (bid < 0 || blast_stamp[n_idx] != bid)) {
                    safe_tiles++;
                }
                bqx[tail] = nx;
                bqy[tail] = ny;
                tail++;
            }
        }
        return safe_tiles;
    };

    std::vector<std::pair<int, int>> enemy_coords;
    std::vector<int> enemy_base_safe;
    int total_enemy_safe_tiles = 0;
    int trapped_enemies_count = 0;

    for (const auto& ec : en_all) {
        int ex = ec.first, ey = ec.second;
        if (can_push_bomb_now || (std::abs(ex - px) + std::abs(ey - py) <= bomb_radius + 5)) {
            enemy_coords.push_back(ec);
            int sc = count_enemy_safe_tiles(ex, ey, -1, -1, -1, 6);
            enemy_base_safe.push_back(sc);
            total_enemy_safe_tiles += sc;
            if (sc == 0) trapped_enemies_count++;
        }
    }

    auto evaluate_enemy_compression_at = [&](int bx, int by, int radius, int& out_compressed, bool& out_traps, bool& out_pins) {
        out_compressed = 0;
        out_traps = false;
        out_pins = false;
        if (enemy_coords.empty()) return;

        bool has_nearby = false;
        for (const auto& ec : enemy_coords) {
            if (std::abs(ec.first - bx) + std::abs(ec.second - by) <= radius + 2) {
                has_nearby = true;
                break;
            }
        }
        if (!has_nearby) return;

        int bid = mark_blast_zone(bx, by, radius);
        for (size_t i = 0; i < enemy_coords.size(); ++i) {
            int ex = enemy_coords[i].first;
            int ey = enemy_coords[i].second;
            if (std::abs(ex - bx) + std::abs(ey - by) > radius + 2) continue;
            int before_sc = enemy_base_safe[i];
            int after_sc = count_enemy_safe_tiles(ex, ey, bx, by, bid, 6);
            int diff = std::max(0, before_sc - after_sc);
            out_compressed += diff;
            if (before_sc > 0 && after_sc == 0) {
                out_traps = true;
                out_pins = true;
            } else if (diff >= 2 && after_sc <= 2) {
                out_pins = true;
            }
        }
    };

    auto count_targets_at = [&](int bx, int by, int radius, int& out_t, int& out_et, int& out_comp, bool& out_trap) {
        out_t = 0;
        out_et = 0;
        for (int dir = 0; dir < 4; ++dir) {
            int dx = DX[dir], dy = DY[dir];
            for (int r = 1; r <= radius; ++r) {
                int nx = bx + dx * r;
                int ny = by + dy * r;
                if (nx < 0 || nx >= w || ny < 0 || ny >= h) break;
                int n_idx = ny * w + nx;
                if (solid[n_idx]) break;
                if (enemies[n_idx]) {
                    out_t += 3;
                    out_et += 1;
                }
                if (breakable[n_idx]) {
                    out_t += 1;
                    break;
                }
            }
        }
        if (enemies[by * w + bx]) {
            out_t += 3;
            out_et += 1;
        }

        bool pins_enemy = false;
        evaluate_enemy_compression_at(bx, by, radius, out_comp, out_trap, pins_enemy);
        if (out_trap) {
            out_t += 5;
            out_et = std::max(out_et, 1);
        } else if (pins_enemy) {
            out_t += std::min(4, out_comp);
            out_et = std::max(out_et, 1);
        }
    };

    const bool can_place_bomb = (avail_bombs > 0) && (!bombs[p_idx]);
    const bool safe_escape_here = can_place_bomb && has_escape_if_bomb_at(px, py, bomb_radius);
    int targets_here = 0, enemy_targets_here = 0, compressed_here = 0;
    bool trap_bomb_here = false;
    if (safe_escape_here) {
        count_targets_at(px, py, bomb_radius, targets_here, enemy_targets_here, compressed_here, trap_bomb_here);
    }
    if (safe_escape_here && targets_here > 0) {
        if (trap_bomb_here) {
            bomb_map[p_idx] = 1.0f;
        } else {
            bomb_map[p_idx] = std::min(1.0f, (targets_here + enemy_targets_here * 2 + compressed_here * 0.5f) / 5.0f);
        }
    }

    std::vector<BombSite> bombing_sites;
    std::vector<std::pair<int, int>> reach_tiles;
    for (int ry = 0; ry < h; ++ry) {
        for (int rx = 0; rx < w; ++rx) {
            int r_idx = ry * w + rx;
            if (dist[r_idx] >= 0 && ch_danger[r_idx] == 0.0f && !bombs[r_idx]) {
                reach_tiles.emplace_back(rx, ry);
                if (rx == px && ry == py) continue;
                if (has_escape_if_bomb_at(rx, ry, bomb_radius)) {
                    int t = 0, et = 0, comp_t = 0;
                    bool trap_t = false;
                    count_targets_at(rx, ry, bomb_radius, t, et, comp_t, trap_t);
                    if (t > 0) {
                        float bomb_score = trap_t ? 1.0f : std::min(0.9f, (t + et * 2 + comp_t * 0.5f) / 5.0f);
                        bomb_map[r_idx] = std::max(bomb_map[r_idx], bomb_score);
                        bombing_sites.push_back({dist[r_idx], rx, ry, t, et, comp_t, trap_t});
                    }
                }
            }
        }
    }

    auto site_key = [&](const BombSite& s) {
        int is_enemy_attack = (s.trap || s.enemy_targets > 0) ? 0 : 1;
        int is_not_trap = s.trap ? 0 : 1;
        float en_md = 0.0f;
        if (!en_all.empty()) {
            int min_md = 9999;
            for (const auto& ec : en_all) {
                min_md = std::min(min_md, std::abs(ec.first - s.bx) + std::abs(ec.second - s.by));
            }
            en_md = static_cast<float>(min_md);
        }
        float score = static_cast<float>(s.dist) + (is_enemy_attack == 1 ? 0.65f * en_md : -0.3f * s.compressed);
        return std::make_tuple(is_enemy_attack, is_not_trap, score);
    };

    std::stable_sort(bombing_sites.begin(), bombing_sites.end(), [&](const BombSite& a, const BombSite& b) {
        return site_key(a) < site_key(b);
    });

    std::vector<BombSite> enemy_bombing_sites;
    for (const auto& s : bombing_sites) {
        if (s.trap || s.enemy_targets > 0) {
            enemy_bombing_sites.push_back(s);
        }
    }

    int closest_pu_d = 999;
    int closest_pu_x = -1, closest_pu_y = -1;
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            int idx = y * w + x;
            if (useful_powerups[idx] && dist[idx] > 0 && ch_danger[idx] == 0.0f) {
                if (dist[idx] < closest_pu_d) {
                    closest_pu_d = dist[idx];
                    closest_pu_x = x;
                    closest_pu_y = y;
                }
            }
        }
    }

    std::vector<std::tuple<int, int, int>> reach_en;
    for (const auto& ec : en_all) {
        int d_e = dist[ec.second * w + ec.first];
        if (d_e >= 0) {
            reach_en.emplace_back(d_e, ec.first, ec.second);
        }
    }
    std::stable_sort(reach_en.begin(), reach_en.end(), [](const auto& a, const auto& b) {
        return std::get<0>(a) < std::get<0>(b);
    });

    int hunt_action = 0;
    if (!in_danger) {
        if ((enemy_targets_here > 0 || trap_bomb_here) && safe_escape_here) {
            hunt_action = 0;
        } else if (!tactical_push_actions.empty()) {
            hunt_action = tactical_push_actions[0];
        } else if (!enemy_bombing_sites.empty() && enemy_bombing_sites[0].dist <= 8) {
            hunt_action = first_action[enemy_bombing_sites[0].by * w + enemy_bombing_sites[0].bx];
        } else if (closest_pu_x >= 0 && closest_pu_d <= 3) {
            hunt_action = first_action[closest_pu_y * w + closest_pu_x];
        } else if (!reach_en.empty()) {
            hunt_action = first_action[std::get<2>(reach_en[0]) * w + std::get<1>(reach_en[0])];
        } else if (!enemy_bombing_sites.empty()) {
            hunt_action = first_action[enemy_bombing_sites[0].by * w + enemy_bombing_sites[0].bx];
        } else if (targets_here > 0 && safe_escape_here) {
            hunt_action = 0;
        } else if (!bombing_sites.empty()) {
            hunt_action = first_action[bombing_sites[0].by * w + bombing_sites[0].bx];
        } else if (closest_pu_x >= 0) {
            hunt_action = first_action[closest_pu_y * w + closest_pu_x];
        } else if (!en_all.empty()) {
            int best_rx = px, best_ry = py;
            int min_m_dist = 999;
            for (const auto& rt : reach_tiles) {
                int rx = rt.first, ry = rt.second;
                int m_d = 999;
                for (const auto& ec : en_all) {
                    m_d = std::min(m_d, std::abs(ec.first - rx) + std::abs(ec.second - ry));
                }
                if (m_d < min_m_dist) {
                    min_m_dist = m_d;
                    best_rx = rx;
                    best_ry = ry;
                }
            }
            if (best_rx != px || best_ry != py) {
                hunt_action = first_action[best_ry * w + best_rx];
            }
        }
    }

    int safe_reachable_count = 0;
    for (int i = 0; i < hw; ++i) {
        if (dist[i] >= 0 && ch_danger[i] == 0.0f) {
            safe_reachable_count++;
        }
    }

    // Standard PBRS State Potential Phi(s) in [-1.20, 0.0]:
    // Strictly based on Manhattan distance to nearest alive enemy (0.0 if none alive).
    float phi = 0.0f;
    if (!en_all.empty()) {
        int min_en_manhattan = 999;
        for (const auto& ec : en_all) {
            min_en_manhattan = std::min(min_en_manhattan, std::abs(ec.first - px) + std::abs(ec.second - py));
        }
        phi = -0.05f * static_cast<float>(std::min(min_en_manhattan, 24));
    }

    py::dict analysis;
    analysis["pos"] = py::make_tuple(px, py);
    analysis["safe_escape_from_here"] = safe_escape_here;
    analysis["bomb_targets_here"] = targets_here;
    analysis["enemy_targets_here"] = enemy_targets_here;
    analysis["enemy_space_compressed_here"] = compressed_here;
    analysis["trap_bomb_here"] = trap_bomb_here;
    analysis["total_enemy_safe_tiles"] = total_enemy_safe_tiles;
    analysis["trapped_enemies_count"] = trapped_enemies_count;
    analysis["in_danger"] = in_danger;
    analysis["escape_action"] = escape_action;
    analysis["safe_escape_moves"] = py::cast(safe_escape_moves);
    analysis["safe_reachable_count"] = safe_reachable_count;
    analysis["hunt_action"] = hunt_action;
    analysis["valid_moves"] = py::cast(valid_moves);
    analysis["can_place_bomb"] = can_place_bomb;
    analysis["can_push_bomb_now"] = can_push_bomb_now;
    analysis["push_actions"] = py::cast(push_actions);
    analysis["tactical_push_actions"] = py::cast(tactical_push_actions);
    analysis["active_bombs_count"] = active_bombs_count;
    analysis["local_active_bombs"] = local_active_bombs;
    if (!bombing_sites.empty()) {
        const auto& s0 = bombing_sites[0];
        analysis["closest_bombing_site"] = py::make_tuple(
            s0.dist, s0.bx, s0.by, s0.targets, s0.enemy_targets, s0.compressed, s0.trap
        );
    } else {
        analysis["closest_bombing_site"] = py::none();
    }

    return py::make_tuple(reach_arr, bomb_arr, phi, analysis);
}

} // namespace

PYBIND11_MODULE(bomberman_engine, m) {
    m.doc() = "C++ Bomberman Engine bound to Python";

    std::srand(static_cast<unsigned int>(std::time(nullptr)));

    m.def("seed_rng", [](unsigned int seed) {
        std::srand(seed);
    }, "Seeds the C++ rand() generator for reproducible level generation");

    m.def("set_powerup_drop_chance", &PowerUpFactory::setDropChancePercent, py::arg("percent"),
          "Sets the percentage chance (0-100) that a destroyed breakable wall drops a power-up");
    m.def("get_powerup_drop_chance", &PowerUpFactory::getDropChancePercent,
          "Gets the percentage chance (0-100) that a destroyed breakable wall drops a power-up");

    m.def("set_bot_sd_caution_percent", &DumbBot::setSuddenDeathCautionPercent, py::arg("percent"),
          "Sets the base caution probability (0-100) for DumbBot Sudden Death awareness");
    m.def("get_bot_sd_caution_percent", &DumbBot::getSuddenDeathCautionPercent,
          "Gets the base caution probability (0-100) for DumbBot Sudden Death awareness");

    m.def("compute_bfs_features", &compute_bfs_features_cpp,
          py::arg("base_obs"),
          py::arg("is_alive"),
          py::arg("px"),
          py::arg("py"),
          py::arg("has_ring"),
          py::arg("has_hammer"),
          py::arg("bomb_radius"),
          py::arg("avail_bombs"),
          py::arg("speed_level") = 0,
          py::arg("cur_cooldown") = 0,
          "Computes tactical BFS reachability map, bomb target map, PBRS potential, and analysis dict in C++17");

    py::enum_<Command>(m, "Command")
        .value("NONE", Command::NONE)
        .value("UP", Command::UP)
        .value("DOWN", Command::DOWN)
        .value("LEFT", Command::LEFT)
        .value("RIGHT", Command::RIGHT)
        .value("PLACE_BOMB", Command::PLACE_BOMB)
        .export_values();

    py::class_<PlayerCommand>(m, "PlayerCommand")
        .def(py::init<int, Command>(), py::arg("playerId"), py::arg("command"))
        .def_readwrite("playerId", &PlayerCommand::playerId)
        .def_readwrite("command", &PlayerCommand::command);

    py::class_<StepResult>(m, "StepResult")
        .def_readonly("isDone", &StepResult::isDone)
        .def_readonly("reward", &StepResult::reward)
        .def_readonly("wallsDestroyed", &StepResult::wallsDestroyed)
        .def_readonly("enemiesHit", &StepResult::enemiesHit)
        .def_readonly("enemiesKilled", &StepResult::enemiesKilled)
        .def_readonly("powerUpsCollected", &StepResult::powerUpsCollected)
        .def_readonly("livesLost", &StepResult::livesLost)
        .def_readonly("moved", &StepResult::moved)
        .def_readonly("bombPlaced", &StepResult::bombPlaced)
        .def_readonly("bombPushed", &StepResult::bombPushed)
        .def_readonly("won", &StepResult::won)
        .def_readonly("died", &StepResult::died);

    py::class_<PlayerInfo>(m, "PlayerInfo")
        .def_readonly("id", &PlayerInfo::id)
        .def_readonly("x", &PlayerInfo::x)
        .def_readonly("y", &PlayerInfo::y)
        .def_readonly("lives", &PlayerInfo::lives)
        .def_readonly("maxBombs", &PlayerInfo::maxBombs)
        .def_readonly("availBombs", &PlayerInfo::availBombs)
        .def_readonly("bombRadius", &PlayerInfo::bombRadius)
        .def_readonly("speedLevel", &PlayerInfo::speedLevel)
        .def_readonly("cooldown", &PlayerInfo::cooldown)
        .def_readonly("moveCooldownMax", &PlayerInfo::moveCooldownMax)
        .def_readonly("invincibilityTimer", &PlayerInfo::invincibilityTimer)
        .def_readonly("facingDx", &PlayerInfo::facingDx)
        .def_readonly("facingDy", &PlayerInfo::facingDy)
        .def_readonly("hasHammer", &PlayerInfo::hasHammer)
        .def_readonly("hasRing", &PlayerInfo::hasRing)
        .def_readonly("isBot", &PlayerInfo::isBot)
        .def_readonly("isAlive", &PlayerInfo::isAlive);

    py::class_<BombInfo>(m, "BombInfo")
        .def_readonly("x", &BombInfo::x)
        .def_readonly("y", &BombInfo::y)
        .def_readonly("timer", &BombInfo::timer)
        .def_readonly("radius", &BombInfo::radius)
        .def_readonly("ownerId", &BombInfo::ownerId)
        .def_readonly("creditOwnerId", &BombInfo::creditOwnerId)
        .def_readonly("isSliding", &BombInfo::isSliding)
        .def_readonly("slideDx", &BombInfo::slideDx)
        .def_readonly("slideDy", &BombInfo::slideDy)
        .def_readonly("slideCooldown", &BombInfo::slideCooldown)
        .def_readonly("slideCooldownMax", &BombInfo::slideCooldownMax);

    py::class_<PowerUpInfo>(m, "PowerUpInfo")
        .def_readonly("x", &PowerUpInfo::x)
        .def_readonly("y", &PowerUpInfo::y)
        .def_readonly("type", &PowerUpInfo::type);

    py::class_<FlameInfo>(m, "FlameInfo")
        .def_readonly("x", &FlameInfo::x)
        .def_readonly("y", &FlameInfo::y)
        .def_readonly("timer", &FlameInfo::timer)
        .def_readonly("ownerId", &FlameInfo::ownerId)
        .def_readonly("creditOwnerId", &FlameInfo::creditOwnerId);

    py::class_<ILevel>(m, "ILevel");
    py::class_<ClassicLevel, ILevel>(m, "ClassicLevel")
        .def(py::init<int, int, int, int>(),
             py::arg("numPlayers"),
             py::arg("boardWidth"),
             py::arg("boardHeight"),
             py::arg("wallDensityPercent") = 65);

    py::class_<Game>(m, "Game")
        .def(py::init<int, int>())
        .def("reset", &Game::reset)
        .def("step", &Game::step,
             py::arg("playerId"),
             py::arg("action"),
             py::arg("extraCommands") = std::vector<PlayerCommand>{})
        .def("update", py::overload_cast<Command>(&Game::update), py::arg("command") = Command::NONE)
        .def("updateCommands", py::overload_cast<const std::vector<PlayerCommand>&>(&Game::update), py::arg("commands"))
        .def("getState", [](const Game& self, int playerId) {
            const int width = self.getWorld().getBoard().getWidth();
            const int height = self.getWorld().getBoard().getHeight();
            constexpr int channels = 17;
            py::array_t<float> result({channels, height, width});
            float* ptr = static_cast<float*>(result.request().ptr);
            std::fill(ptr, ptr + (channels * height * width), 0.0f);
            self.fillState(playerId, ptr);
            return result;
        }, py::arg("playerId"))
        .def("getBoardGrid", &Game::getBoardGrid)
        .def("getPlayerInfo", &Game::getPlayerInfo)
        .def("getBombs", &Game::getBombs)
        .def("getPowerUps", &Game::getPowerUps)
        .def("getFlames", &Game::getFlames)
        .def("clearBoard", &Game::clearBoard)
        .def("setSolidWall", &Game::setSolidWall)
        .def("addPlayer", &Game::addPlayer, py::arg("x"), py::arg("y"), py::arg("id"), py::arg("isBot") = false)
        .def("addBreakableWall", &Game::addBreakableWall)
        .def("addBomb", &Game::addBomb)
        .def("addPowerUp", &Game::addPowerUp)
        .def("givePlayerPowerUp", &Game::givePlayerPowerUp)
        .def("isGameOver", &Game::isGameOver)
        .def("getWinnerId", &Game::getWinnerId)
        .def("getSuddenDeathTimer", &Game::getSuddenDeathTimer)
        .def("setSuddenDeathTimer", &Game::setSuddenDeathTimer)
        .def("isSuddenDeathActive", &Game::isSuddenDeathActive);
}
