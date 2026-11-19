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
    int speed_level
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
        analysis["hunt_action"] = 0;
        py::list vm;
        vm.append(0);
        analysis["valid_moves"] = vm;
        analysis["can_place_bomb"] = false;
        analysis["can_push_bomb_now"] = false;
        analysis["push_actions"] = py::list();
        analysis["tactical_push_actions"] = py::list();
        analysis["active_bombs_count"] = 0;
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

    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            int idx = y * w + x;
            solid[idx] = ch_solid[idx] > 0.0f;
            breakable[idx] = ch_breakable[idx] > 0.0f;
            bombs[idx] = ch_bombs[idx] > 0.0f;
            if (bombs[idx]) active_bombs_count++;
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

    auto has_push_target_in_dir = [&](int dx, int dy) -> bool {
        for (int dist_step = 2; dist_step < 7; ++dist_step) {
            int tx = px + dx * dist_step;
            int ty = py + dy * dist_step;
            if (tx < 0 || tx >= w || ty < 0 || ty >= h) break;
            int t_idx = ty * w + tx;
            if (solid[t_idx]) break;
            if (enemies[t_idx] || breakable[t_idx]) return true;
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
        if (d >= 16) continue;

        for (int dir = 0; dir < 4; ++dir) {
            int act_id = ACT_IDS[dir];
            int nx = cx + DX[dir];
            int ny = cy + DY[dir];
            if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
                int n_idx = ny * w + nx;
                if (dist[n_idx] == -1 && passable[n_idx]) {
                    float ndanger = ch_danger[n_idx];
                    if (!in_danger && ndanger > 0.0f) continue;
                    if (in_danger && ndanger >= 0.88f) continue;

                    dist[n_idx] = d + 1;
                    int fa = (d == 0) ? act_id : first_action[c_idx];
                    first_action[n_idx] = fa;
                    if (d == 0) {
                        valid_moves.push_back(act_id);
                    }
                    if (ndanger == 0.0f) {
                        reach_map[n_idx] = std::max(0.1f, 1.0f - static_cast<float>(d + 1) / 17.0f);
                        if (d + 1 < min_safe_dist) {
                            min_safe_dist = d + 1;
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

    std::vector<int> push_actions;
    std::vector<int> tactical_push_actions;
    if (has_hammer && !bombs[p_idx]) {
        for (int dir = 0; dir < 4; ++dir) {
            int act_id = ACT_IDS[dir];
            int dx = DX[dir], dy = DY[dir];
            if (can_push_bomb_in_dir(dx, dy)) {
                push_actions.push_back(act_id);
                if (std::find(valid_moves.begin(), valid_moves.end(), act_id) == valid_moves.end()) {
                    valid_moves.push_back(act_id);
                }
                if (in_danger || has_push_target_in_dir(dx, dy)) {
                    tactical_push_actions.push_back(act_id);
                    bomb_map[(py + dy) * w + (px + dx)] = 1.0f;
                }
                if (in_danger && escape_action == 0) {
                    escape_action = act_id;
                }
            }
        }
    }
    const bool can_push_bomb_now = !push_actions.empty();

    std::vector<int> blast_stamp(hw, 0);
    std::vector<int> bfs_stamp(hw, 0);
    std::vector<int> bfs_dist(hw, 0);
    std::vector<int> bqx(hw);
    std::vector<int> bqy(hw);
    int cur_blast_id = 0;
    int cur_bfs_id = 0;

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

    auto has_escape_if_bomb_at = [&](int bx, int by, int radius) -> bool {
        int bid = mark_blast_zone(bx, by, radius);
        int max_search_steps = std::max(6, radius + 3);
        int sid = ++cur_bfs_id;
        int head = 0, tail = 0;
        int start_idx = by * w + bx;
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
                if (nx >= 0 && nx < w && ny >= 0 && ny < h) {
                    int n_idx = ny * w + nx;
                    if (bfs_stamp[n_idx] != sid && passable[n_idx] && ch_danger[n_idx] < 0.7f) {
                        bfs_stamp[n_idx] = sid;
                        bfs_dist[n_idx] = cd + 1;
                        if (blast_stamp[n_idx] != bid && ch_danger[n_idx] == 0.0f) {
                            return true;
                        }
                        bqx[tail] = nx;
                        bqy[tail] = ny;
                        tail++;
                    }
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
            if (std::abs(ec.first - bx) + std::abs(ec.second - by) <= radius + 3) {
                has_nearby = true;
                break;
            }
        }
        if (!has_nearby) return;

        int bid = mark_blast_zone(bx, by, radius);
        for (size_t i = 0; i < enemy_coords.size(); ++i) {
            int ex = enemy_coords[i].first;
            int ey = enemy_coords[i].second;
            if (std::abs(ex - bx) + std::abs(ey - by) > radius + 3) continue;
            int before_sc = enemy_base_safe[i];
            int after_sc = count_enemy_safe_tiles(ex, ey, bx, by, bid, 6);
            int diff = std::max(0, before_sc - after_sc);
            out_compressed += diff;
            if (before_sc > 0 && after_sc == 0) {
                out_traps = true;
                out_pins = true;
            } else if (diff >= 2 && after_sc <= 4) {
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

        if (out_et == 0 && has_hammer && !en_all.empty()) {
            for (int dir = 0; dir < 4; ++dir) {
                int dx = DX[dir], dy = DY[dir];
                for (int r = 2; r < 7; ++r) {
                    int nx = bx + dx * r;
                    int ny = by + dy * r;
                    if (nx < 0 || nx >= w || ny < 0 || ny >= h) break;
                    int n_idx = ny * w + nx;
                    if (solid[n_idx] || breakable[n_idx]) break;
                    if (enemies[n_idx]) {
                        out_t += 2;
                        out_et += 1;
                        break;
                    }
                }
            }
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
        } else if (!enemy_bombing_sites.empty() && enemy_bombing_sites[0].dist <= 6) {
            hunt_action = first_action[enemy_bombing_sites[0].by * w + enemy_bombing_sites[0].bx];
        } else if (closest_pu_x >= 0 && closest_pu_d <= 3) {
            hunt_action = first_action[closest_pu_y * w + closest_pu_x];
        } else if (!reach_en.empty() && std::get<0>(reach_en[0]) <= 8) {
            hunt_action = first_action[std::get<2>(reach_en[0]) * w + std::get<1>(reach_en[0])];
        } else if (!enemy_bombing_sites.empty()) {
            hunt_action = first_action[enemy_bombing_sites[0].by * w + enemy_bombing_sites[0].bx];
        } else if (targets_here > 0 && safe_escape_here) {
            hunt_action = 0;
        } else if (!bombing_sites.empty()) {
            hunt_action = first_action[bombing_sites[0].by * w + bombing_sites[0].bx];
        } else if (!reach_en.empty()) {
            hunt_action = first_action[std::get<2>(reach_en[0]) * w + std::get<1>(reach_en[0])];
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

    float phi_space = std::min(safe_reachable_count, 35) * 0.12f;
    float phi_safety = in_danger ? (-4.0f * ch_danger[p_idx]) : 0.0f;
    float phi_hunt = 0.0f;
    if (!in_danger) {
        if (closest_pu_x >= 0) {
            phi_hunt += (15.0f - std::min(closest_pu_d, 15)) * 0.16f;
        }
        if (!enemy_bombing_sites.empty()) {
            int min_ebs_d = enemy_bombing_sites[0].dist;
            phi_hunt += (16.0f - std::min(min_ebs_d, 16)) * 0.35f;
        } else if (!bombing_sites.empty()) {
            int min_bs_d = bombing_sites[0].dist;
            phi_hunt += (15.0f - std::min(min_bs_d, 15)) * 0.16f;
        }
        if (!en_all.empty()) {
            int min_en_manhattan = 999;
            for (const auto& ec : en_all) {
                min_en_manhattan = std::min(min_en_manhattan, std::abs(ec.first - px) + std::abs(ec.second - py));
            }
            phi_hunt += (26.0f - std::min(min_en_manhattan, 26)) * 0.18f;
            if (!reach_en.empty()) {
                phi_hunt += (22.0f - std::min(std::get<0>(reach_en[0]), 22)) * 0.30f;
            }
        }
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
    analysis["hunt_action"] = hunt_action;
    analysis["valid_moves"] = py::cast(valid_moves);
    analysis["can_place_bomb"] = can_place_bomb;
    analysis["can_push_bomb_now"] = can_push_bomb_now;
    analysis["push_actions"] = py::cast(push_actions);
    analysis["tactical_push_actions"] = py::cast(tactical_push_actions);
    analysis["active_bombs_count"] = active_bombs_count;
    if (!bombing_sites.empty()) {
        const auto& s0 = bombing_sites[0];
        analysis["closest_bombing_site"] = py::make_tuple(
            s0.dist, s0.bx, s0.by, s0.targets, s0.enemy_targets, s0.compressed, s0.trap
        );
    } else {
        analysis["closest_bombing_site"] = py::none();
    }

    return py::make_tuple(reach_arr, bomb_arr, phi_space + phi_safety + phi_hunt, analysis);
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
