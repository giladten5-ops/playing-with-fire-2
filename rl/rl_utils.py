from collections import deque
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

try:
    import bomberman_engine as _bme
except ImportError:
    _bme = None

DIRS: Dict[int, Tuple[int, int]] = {
    1: (0, -1),
    2: (0, 1),
    3: (-1, 0),
    4: (1, 0),
}


def compute_bfs_features(
    base_obs: np.ndarray,
    tstate: Union[Dict[str, int], Any],
    width: int = 15,
    height: int = 13,
) -> Tuple[np.ndarray, np.ndarray, float, Dict[str, Any]]:
    """
    Computes tactical BFS reachability map, safe-escape bomb target map,
    PBRS potential phi(s), and tactical analysis metadata from the engine state.
    Delegates to the compiled C++17 implementation when available.
    """
    if isinstance(tstate, dict):
        is_alive = bool(tstate.get("is_alive", 0))
        px = int(tstate.get("x", -1))
        py = int(tstate.get("y", -1))
        has_ring = bool(tstate.get("has_ring", 0))
        has_hammer = bool(tstate.get("has_hammer", 0))
        bomb_radius = int(tstate.get("bomb_radius", 2))
        avail_bombs = int(tstate.get("avail_bombs", 0))
        speed_level = int(tstate.get("speed_level", int(round(float(base_obs[16, 0, 0]) * 2)) if base_obs.shape[0] >= 17 else 0))
        cur_cooldown = int(tstate.get("cooldown", 0))
        facing_dx = int(tstate.get("facing_dx", 0))
        facing_dy = int(tstate.get("facing_dy", 1))
    else:
        is_alive = bool(getattr(tstate, "isAlive", False))
        px = int(getattr(tstate, "x", -1))
        py = int(getattr(tstate, "y", -1))
        has_ring = bool(getattr(tstate, "hasRing", False))
        has_hammer = bool(getattr(tstate, "hasHammer", False))
        bomb_radius = int(getattr(tstate, "bombRadius", 2))
        avail_bombs = int(getattr(tstate, "availBombs", 0))
        speed_level = int(getattr(tstate, "speedLevel", 0))
        cur_cooldown = int(getattr(tstate, "cooldown", 0))
        facing_dx = int(getattr(tstate, "facingDx", 0))
        facing_dy = int(getattr(tstate, "facingDy", 1))

    if _bme is not None and hasattr(_bme, "compute_bfs_features"):
        return _bme.compute_bfs_features(
            base_obs,
            is_alive,
            px,
            py,
            has_ring,
            has_hammer,
            bomb_radius,
            avail_bombs,
            speed_level,
            cur_cooldown,
        )

    h, w = int(base_obs.shape[1]), int(base_obs.shape[2])
    reach_map = np.zeros((h, w), dtype=np.float32)
    bomb_map = np.zeros((h, w), dtype=np.float32)

    if not is_alive:
        return reach_map, bomb_map, 0.0, {
            "safe_escape_from_here": False,
            "bomb_targets_here": 0,
            "enemy_targets_here": 0,
            "enemy_space_compressed_here": 0,
            "trap_bomb_here": False,
            "total_enemy_safe_tiles": 0,
            "trapped_enemies_count": 0,
            "in_danger": False,
            "escape_action": 0,
            "safe_escape_moves": [],
            "safe_reachable_count": 0,
            "hunt_action": 0,
            "valid_moves": [0],
            "can_place_bomb": False,
            "can_push_bomb_now": False,
            "push_actions": [],
            "tactical_push_actions": [],
            "active_bombs_count": 0,
            "local_active_bombs": 0,
            "closest_bombing_site": None,
        }

    solid = base_obs[0] > 0.0
    breakable = base_obs[1] > 0.0
    bombs = base_obs[2] > 0.0
    danger = base_obs[3]
    flames = base_obs[4] > 0.0
    powerups = base_obs[5] > 0.0
    if base_obs.shape[0] >= 17:
        useful_powerups = (
            (base_obs[10] > 0.0)
            | (base_obs[12] > 0.0)
            | ((base_obs[11] > 0.0) & (speed_level < 2))
            | ((base_obs[13] > 0.0) & (not has_hammer))
            | ((base_obs[14] > 0.0) & (not has_ring))
        )
    else:
        useful_powerups = powerups
    enemies = base_obs[7] > 0.0

    in_danger = bool(danger[py, px] > 0.0)
    move_cd = max(4, 6 - max(0, min(2, speed_level)))
    init_wait = max(0, cur_cooldown - 1)
    post_bomb_wait = max(0, cur_cooldown - 2)
    base_tte = np.full((h, w), 9999, dtype=np.int32)
    for y in range(h):
        for x in range(w):
            if flames[y, x] or danger[y, x] >= 0.995:
                base_tte[y, x] = 0
            elif danger[y, x] > 0.0:
                base_tte[y, x] = max(1, int(round((1.0 - float(danger[y, x])) * 100.0)))

    # HAMMER MECHANIC: Walking into an adjacent bomb pushes it if the destination tile is free.
    # Hammer takes priority over Ring when walking into a pushable bomb.
    def can_push_bomb_in_dir(dx: int, dy: int) -> bool:
        if not has_hammer or (dx == 0 and dy == 0) or bombs[py, px]:
            return False
        bx, by = px + dx, py + dy
        dest_x, dest_y = bx + dx, by + dy
        if not (0 <= bx < w and 0 <= by < h and 0 <= dest_x < w and 0 <= dest_y < h):
            return False
        if not bombs[by, bx]:
            return False
        if (
            solid[dest_y, dest_x]
            or breakable[dest_y, dest_x]
            or bombs[dest_y, dest_x]
            or flames[dest_y, dest_x]
            or enemies[dest_y, dest_x]
        ):
            return False
        return True

    def has_push_target_in_dir(dx: int, dy: int) -> bool:
        for dist_step in range(2, 7):
            tx, ty = px + dx * dist_step, py + dy * dist_step
            if not (0 <= tx < w and 0 <= ty < h) or solid[ty, tx]:
                break
            if enemies[ty, tx] or breakable[ty, tx]:
                return True
        return False

    # RING MECHANIC: Ring allows walking onto bombs, except adjacent bombs that Hammer will push instead
    passable = ~(solid | breakable | flames) if has_ring else ~(solid | breakable | bombs | flames)
    if has_ring and has_hammer and not bombs[py, px]:
        passable = passable.copy()
        for _, (dx, dy) in DIRS.items():
            if can_push_bomb_in_dir(dx, dy):
                passable[py + dy, px + dx] = False

    dist = np.full((h, w), -1, dtype=np.int32)
    first_action = np.zeros((h, w), dtype=np.int32)
    q = deque([(px, py)])
    dist[py, px] = 0
    reach_map[py, px] = 1.0 if danger[py, px] == 0.0 else 0.2

    valid_moves = [0]
    escape_action = 0
    min_safe_dist = 999

    while q:
        cx, cy = q.popleft()
        d = int(dist[cy, cx])
        if d >= 26:
            continue
        for act_id, (dx, dy) in DIRS.items():
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and dist[ny, nx] == -1 and passable[ny, nx]:
                next_d = d + 1
                tile_tte = int(base_tte[ny, nx])
                if not in_danger and tile_tte < 9999:
                    continue
                if in_danger:
                    if d == 0 and int(base_tte[py, px]) <= init_wait:
                        continue
                    if tile_tte < 9999 and tile_tte <= init_wait + next_d * move_cd:
                        continue
                dist[ny, nx] = next_d
                fa = act_id if d == 0 else int(first_action[cy, cx])
                first_action[ny, nx] = fa
                if d == 0:
                    valid_moves.append(act_id)
                if tile_tte == 9999:
                    reach_map[ny, nx] = max(0.1, 1.0 - next_d / 26.0)
                    if next_d < min_safe_dist:
                        min_safe_dist = next_d
                        escape_action = fa
                else:
                    reach_map[ny, nx] = 0.15
                q.append((nx, ny))

    safe_escape_moves: List[int] = []
    if in_danger and int(base_tte[py, px]) > init_wait:
        best_escape_dist = 999
        for act_id, (dx, dy) in DIRS.items():
            sx, sy = px + dx, py + dy
            if not (0 <= sx < w and 0 <= sy < h) or not passable[sy, sx]:
                continue
            if int(base_tte[sy, sx]) == 9999:
                safe_escape_moves.append(act_id)
                if 1 < best_escape_dist:
                    best_escape_dist = 1
                    escape_action = act_id
                continue
            if int(base_tte[sy, sx]) <= init_wait + move_cd:
                continue
            visited_e = {(px, py), (sx, sy)}
            eq = deque([(sx, sy, 1)])
            found_d = -1
            while eq and found_d < 0:
                ecx, ecy, ecd = eq.popleft()
                if ecd >= 16:
                    continue
                for _, (ndx, ndy) in DIRS.items():
                    enx, eny = ecx + ndx, ecy + ndy
                    if not (0 <= enx < w and 0 <= eny < h) or (enx, eny) in visited_e or not passable[eny, enx]:
                        continue
                    enext_d = ecd + 1
                    ntte = int(base_tte[eny, enx])
                    if ntte == 9999:
                        found_d = enext_d
                        break
                    if ntte > init_wait + enext_d * move_cd:
                        visited_e.add((enx, eny))
                        eq.append((enx, eny, enext_d))
            if found_d > 0:
                safe_escape_moves.append(act_id)
                if found_d < best_escape_dist:
                    best_escape_dist = found_d
                    escape_action = act_id

    push_actions: List[int] = []
    tactical_push_actions: List[int] = []
    if has_hammer and not bombs[py, px]:
        trapped_no_walk = in_danger and not safe_escape_moves and escape_action == 0
        for act_id, (dx, dy) in DIRS.items():
            if can_push_bomb_in_dir(dx, dy):
                push_actions.append(act_id)
                if act_id not in valid_moves:
                    valid_moves.append(act_id)
                if trapped_no_walk or has_push_target_in_dir(dx, dy):
                    tactical_push_actions.append(act_id)
                    bomb_map[py + dy, px + dx] = 1.0
                if trapped_no_walk:
                    if act_id not in safe_escape_moves:
                        safe_escape_moves.append(act_id)
                    if escape_action == 0:
                        escape_action = act_id

    can_push_bomb_now = len(push_actions) > 0

    def compute_blast_zone(bx: int, by: int, radius: int):
        blast = {(bx, by)}
        for _, (dx, dy) in DIRS.items():
            for r in range(1, radius + 1):
                nx, ny = bx + dx * r, by + dy * r
                if not (0 <= nx < w and 0 <= ny < h) or solid[ny, nx]:
                    break
                blast.add((nx, ny))
                if breakable[ny, nx] or bombs[ny, nx]:
                    break
        return blast

    def has_escape_if_bomb_at(bx: int, by: int, radius: int) -> bool:
        t_hyp = min(90, int(base_tte[by, bx]))
        if t_hyp <= 1 + post_bomb_wait:
            return False
        sim_tte = base_tte.copy()
        sim_tte[by, bx] = min(int(sim_tte[by, bx]), t_hyp)
        cq = deque([(bx, by, radius, t_hyp)])
        while cq:
            cbx, cby, crad, ctte = cq.popleft()
            for _, (dx, dy) in DIRS.items():
                for r in range(1, crad + 1):
                    nx, ny = cbx + dx * r, cby + dy * r
                    if not (0 <= nx < w and 0 <= ny < h) or solid[ny, nx]:
                        break
                    prev_v = int(sim_tte[ny, nx])
                    if ctte < prev_v:
                        sim_tte[ny, nx] = ctte
                    if bombs[ny, nx]:
                        if ctte < prev_v:
                            cq.append((nx, ny, max(radius, 4), ctte))
                        break
                    if breakable[ny, nx]:
                        break

        max_search_steps = min(16, max(6, radius + 4))
        b_dist = np.full((h, w), -1, dtype=np.int32)
        bq = deque([(bx, by)])
        b_dist[by, bx] = 0
        while bq:
            cx, cy = bq.popleft()
            cd = int(b_dist[cy, cx])
            if cd >= max_search_steps:
                continue
            for _, (dx, dy) in DIRS.items():
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and b_dist[ny, nx] == -1 and passable[ny, nx]:
                    next_d = cd + 1
                    tile_tte = int(sim_tte[ny, nx])
                    if tile_tte == 9999:
                        return True
                    if tile_tte > 1 + post_bomb_wait + next_d * move_cd:
                        b_dist[ny, nx] = next_d
                        bq.append((nx, ny))
        return False

    en_ys, en_xs = np.where(enemies)

    def count_enemy_safe_tiles(
        ex: int,
        ey: int,
        sim_bomb: Optional[Tuple[int, int]] = None,
        sim_blast: Optional[set] = None,
        max_steps: int = 6,
    ) -> int:
        """Counts reachable safe tiles for an enemy at (ex, ey), optionally under a hypothetical bomb."""
        visited = {(ex, ey)}
        eq = deque([(ex, ey, 0)])
        safe_tiles = 0
        if danger[ey, ex] == 0.0 and (sim_blast is None or (ex, ey) not in sim_blast):
            safe_tiles += 1

        while eq:
            cx, cy, cd = eq.popleft()
            if cd >= max_steps:
                continue
            for _, (dx, dy) in DIRS.items():
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in visited:
                    continue
                if (
                    solid[ny, nx]
                    or breakable[ny, nx]
                    or bombs[ny, nx]
                    or flames[ny, nx]
                    or (sim_bomb is not None and (nx, ny) == sim_bomb)
                    or (nx == px and ny == py)
                ):
                    continue
                if danger[ny, nx] >= 0.88:
                    continue
                visited.add((nx, ny))
                is_tile_safe = (danger[ny, nx] == 0.0) and (
                    sim_blast is None or (nx, ny) not in sim_blast
                )
                if is_tile_safe:
                    safe_tiles += 1
                eq.append((nx, ny, cd + 1))
        return safe_tiles

    # Baseline safe-tile counts for each visible enemy within tactical range
    enemy_Coords: List[Tuple[int, int]] = [
        (ex, ey)
        for ex, ey in zip(en_xs.tolist(), en_ys.tolist())
        if can_push_bomb_now or (abs(ex - px) + abs(ey - py) <= bomb_radius + 5)
    ]
    enemy_base_safe: Dict[Tuple[int, int], int] = {
        (ex, ey): count_enemy_safe_tiles(ex, ey) for ex, ey in enemy_Coords
    }
    total_enemy_safe_tiles = sum(enemy_base_safe.values())
    trapped_enemies_count = sum(1 for (ex, ey), sc in enemy_base_safe.items() if sc == 0)

    def evaluate_enemy_compression_at(bx: int, by: int, radius: int) -> Tuple[int, bool, bool]:
        """Returns (total_safe_tiles_compressed, traps_any_enemy, pins_any_enemy) if a bomb is placed at (bx, by)."""
        if not enemy_Coords:
            return 0, False, False
        nearby = [
            (ex, ey)
            for (ex, ey) in enemy_Coords
            if abs(ex - bx) + abs(ey - by) <= radius + 3
        ]
        if not nearby:
            return 0, False, False
        sim_blast = compute_blast_zone(bx, by, radius)
        total_compressed = 0
        traps_any = False
        pins_any = False
        for ex, ey in nearby:
            before_sc = enemy_base_safe.get((ex, ey), 0)
            after_sc = count_enemy_safe_tiles(ex, ey, sim_bomb=(bx, by), sim_blast=sim_blast)
            diff = max(0, before_sc - after_sc)
            total_compressed += diff
            if before_sc > 0 and after_sc == 0:
                traps_any = True
                pins_any = True
            elif diff >= 2 and after_sc <= 4:
                pins_any = True
        return total_compressed, traps_any, pins_any

    def count_targets_at(bx: int, by: int, radius: int) -> Tuple[int, int, int, bool]:
        t = 0
        enemy_t = 0
        for _, (dx, dy) in DIRS.items():
            for r in range(1, radius + 1):
                nx, ny = bx + dx * r, by + dy * r
                if not (0 <= nx < w and 0 <= ny < h) or solid[ny, nx]:
                    break
                if enemies[ny, nx]:
                    t += 3
                    enemy_t += 1
                if breakable[ny, nx]:
                    t += 1
                    break
        if enemies[by, bx]:
            t += 3
            enemy_t += 1

        compressed_tiles, traps_enemy, pins_enemy = evaluate_enemy_compression_at(bx, by, radius)
        if traps_enemy:
            t += 5
            enemy_t = max(enemy_t, 1)
        elif pins_enemy:
            t += min(4, compressed_tiles)
            enemy_t = max(enemy_t, 1)

        # Count aligned enemies within 6 tiles when Hammer is active (place-and-kick setups)
        if enemy_t == 0 and has_hammer and len(en_xs) > 0:
            for _, (dx, dy) in DIRS.items():
                for r in range(2, 7):
                    nx, ny = bx + dx * r, by + dy * r
                    if not (0 <= nx < w and 0 <= ny < h) or solid[ny, nx] or breakable[ny, nx]:
                        break
                    if enemies[ny, nx]:
                        t += 2
                        enemy_t += 1
                        break
        return t, enemy_t, compressed_tiles, traps_enemy

    can_place_bomb = (avail_bombs > 0) and (not bombs[py, px])
    safe_escape_here = can_place_bomb and has_escape_if_bomb_at(px, py, bomb_radius)
    targets_here, enemy_targets_here, compressed_here, trap_bomb_here = (
        count_targets_at(px, py, bomb_radius) if safe_escape_here else (0, 0, 0, False)
    )
    if safe_escape_here and targets_here > 0:
        if trap_bomb_here:
            bomb_map[py, px] = 1.0
        else:
            bomb_map[py, px] = min(
                1.0, (targets_here + enemy_targets_here * 2 + compressed_here * 0.5) / 5.0
            )

    # Collect all reachable safe bombing opportunity sites across the board
    bombing_sites: List[Tuple[int, int, int, int, int, int, bool]] = []
    # (distance, bx, by, targets, enemy_targets, compressed, trap)

    # Check all safe reachable tiles for future bombing sites
    reach_ys, reach_xs = np.where((dist >= 0) & (danger == 0.0) & (~bombs))
    for ry, rx in zip(reach_ys, reach_xs):
        rx, ry = int(rx), int(ry)
        if rx == px and ry == py:
            continue
        if has_escape_if_bomb_at(rx, ry, bomb_radius):
            t, et, comp_t, trap_t = count_targets_at(rx, ry, bomb_radius)
            if t > 0:
                bomb_score = 1.0 if trap_t else min(0.9, (t + et * 2 + comp_t * 0.5) / 5.0)
                bomb_map[ry, rx] = max(float(bomb_map[ry, rx]), bomb_score)
                bombing_sites.append((int(dist[ry, rx]), rx, ry, t, et, comp_t, trap_t))

    # Sort bombing sites: prioritize sites that attack/trap/compress enemies,
    # and break ties by closeness to the agent AND closeness to the nearest enemy.
    def _site_sort_key(s: Tuple[int, int, int, int, int, int, bool]) -> Tuple[int, int, float]:
        d_site, sx, sy, _t, et, comp_t, trap_t = s
        is_enemy_attack = 0 if (trap_t or et > 0) else 1
        if len(en_xs) > 0:
            en_md = float(np.min(np.abs(en_xs - sx) + np.abs(en_ys - sy)))
        else:
            en_md = 0.0
        # For enemy attack sites, prefer traps/compression and shortest distance;
        # for wall-breaching sites, prefer walls that advance toward the nearest enemy.
        score = float(d_site) + (0.65 * en_md if is_enemy_attack == 1 else -0.3 * comp_t)
        return (is_enemy_attack, 0 if trap_t else 1, score)

    en_ys, en_xs = np.where(enemies)
    bombing_sites.sort(key=_site_sort_key)
    enemy_bombing_sites = [s for s in bombing_sites if (s[6] or s[4] > 0)]

    hunt_action = 0
    pu_ys, pu_xs = np.where((useful_powerups) & (dist > 0) & (danger == 0.0))

    closest_pu_d = 999
    closest_pu_pos = None
    if len(pu_xs) > 0:
        for py_u, px_u in zip(pu_ys, pu_xs):
            d_u = int(dist[py_u, px_u])
            if 0 < d_u < closest_pu_d:
                closest_pu_d = d_u
                closest_pu_pos = (int(px_u), int(py_u))

    reach_en = (
        sorted(
            [(int(dist[ey, ex]), int(ex), int(ey)) for ex, ey in zip(en_xs, en_ys) if dist[ey, ex] >= 0],
            key=lambda x: x[0],
        )
        if len(en_xs) > 0
        else []
    )

    if not in_danger:
        if (enemy_targets_here > 0 or trap_bomb_here) and safe_escape_here:
            # Immediate offensive strike on enemy in range
            hunt_action = 0
        elif enemy_bombing_sites and enemy_bombing_sites[0][0] <= 6:
            # Close in on an immediate enemy bombing/trapping position
            target_bx, target_by = enemy_bombing_sites[0][1], enemy_bombing_sites[0][2]
            hunt_action = int(first_action[target_by, target_bx])
        elif closest_pu_pos is not None and closest_pu_d <= 3:
            # Grab very close useful powerup on the way
            hunt_action = int(first_action[closest_pu_pos[1], closest_pu_pos[0]])
        elif reach_en and reach_en[0][0] <= 8:
            # Direct path to enemy is open — aggressively close distance to engage
            hunt_action = int(first_action[reach_en[0][2], reach_en[0][1]])
        elif enemy_bombing_sites:
            target_bx, target_by = enemy_bombing_sites[0][1], enemy_bombing_sites[0][2]
            hunt_action = int(first_action[target_by, target_bx])
        elif targets_here > 0 and safe_escape_here:
            # Breach wall at current position if it advances us
            hunt_action = 0
        elif bombing_sites:
            # Breach the wall that best advances toward the enemy
            target_bx, target_by = bombing_sites[0][1], bombing_sites[0][2]
            hunt_action = int(first_action[target_by, target_bx])
        elif reach_en:
            hunt_action = int(first_action[reach_en[0][2], reach_en[0][1]])
        elif closest_pu_pos is not None:
            hunt_action = int(first_action[closest_pu_pos[1], closest_pu_pos[0]])
        elif len(en_xs) > 0:
            # Enemies are blocked behind walls and no bombing sites in range:
            # Move to reachable tile that minimizes Manhattan distance to closest enemy
            best_rx, best_ry = px, py
            min_m_dist = 999
            for ry, rx in zip(reach_ys, reach_xs):
                rx, ry = int(rx), int(ry)
                m_d = int(np.min(np.abs(en_xs - rx) + np.abs(en_ys - ry)))
                if m_d < min_m_dist:
                    min_m_dist = m_d
                    best_rx, best_ry = rx, ry
            if (best_rx, best_ry) != (px, py):
                hunt_action = int(first_action[best_ry, best_rx])

    safe_reachable_count = int(np.sum((dist >= 0) & (danger == 0.0)))
    phi = 0.0
    if len(en_xs) > 0:
        min_en_manhattan = int(np.min(np.abs(en_xs - px) + np.abs(en_ys - py)))
        phi = -0.05 * float(min(min_en_manhattan, 24))

    active_bombs_count = int(np.sum(bombs))
    b_ys, b_xs = np.where(bombs)
    local_active_bombs = int(
        sum(1 for bx_i, by_i in zip(b_xs.tolist(), b_ys.tolist()) if abs(bx_i - px) + abs(by_i - py) <= bomb_radius + 3)
    )

    analysis: Dict[str, Any] = {
        "pos": (px, py),
        "safe_escape_from_here": safe_escape_here,
        "bomb_targets_here": targets_here,
        "enemy_targets_here": enemy_targets_here,
        "enemy_space_compressed_here": compressed_here,
        "trap_bomb_here": trap_bomb_here,
        "total_enemy_safe_tiles": total_enemy_safe_tiles,
        "trapped_enemies_count": trapped_enemies_count,
        "in_danger": in_danger,
        "escape_action": escape_action,
        "safe_escape_moves": safe_escape_moves,
        "safe_reachable_count": safe_reachable_count,
        "hunt_action": hunt_action,
        "valid_moves": valid_moves,
        "can_place_bomb": can_place_bomb,
        "can_push_bomb_now": can_push_bomb_now,
        "push_actions": push_actions,
        "tactical_push_actions": tactical_push_actions,
        "active_bombs_count": active_bombs_count,
        "local_active_bombs": local_active_bombs,
        "closest_bombing_site": bombing_sites[0] if bombing_sites else None,
    }
    return reach_map, bomb_map, phi, analysis


def apply_tactical_shield(
    raw_action: int,
    analysis: Dict[str, Any],
    rng: Optional[Any] = None,
    mode: str = "clean",
) -> Tuple[int, bool]:
    """
    Applies the safety shield to a raw action.
    - mode="clean" (Option B — Pure CNN Decision Making + Physics/Suicide Safety Only):
      Never forces targets, never overrides safe movement directions with `hunt_action`,
      and never blocks bomb kicks or bomb placements based on heuristic target counts.
      Only prevents:
        1. Staying in or walking into imminent explosion danger when a safe escape exists.
        2. Placing a bomb with zero escape paths (guaranteed self-suicide) or when physically illegal.
        3. Walking into solid/unpassable walls.
    - mode="legacy" (Option C — Legacy BFS Heuristic Guided Shield):
      Preserves previous behavior for backward compatibility with older checkpoints.
    Returns (executed_action, shield_intervened).
    """
    exec_action = int(raw_action)
    shield_intervened = False
    valid_moves: List[int] = list(analysis["valid_moves"])
    push_actions: List[int] = list(analysis.get("push_actions", []))
    tactical_pushes: List[int] = list(analysis.get("tactical_push_actions", []))
    hunt_act = int(analysis.get("hunt_action", 0))
    choice_fn = rng.choice if rng is not None else np.random.choice

    if mode != "legacy":
        in_danger = bool(analysis.get("in_danger", False))
        escape_act = int(analysis.get("escape_action", 0))
        safe_escapes: List[int] = [int(a) for a in analysis.get("safe_escape_moves", []) if int(a) in (1, 2, 3, 4)]
        if in_danger:
            if safe_escapes and exec_action not in safe_escapes:
                exec_action = escape_act if escape_act in safe_escapes else safe_escapes[0]
                shield_intervened = True
            elif not safe_escapes and escape_act != 0 and (
                exec_action == 0
                or exec_action == 5
                or exec_action not in valid_moves
            ):
                exec_action = escape_act
                shield_intervened = True
        elif exec_action == 5 and (
            not analysis.get("can_place_bomb", False)
            or not analysis.get("safe_escape_from_here", False)
            or int(analysis.get("bomb_targets_here", 0)) == 0
        ):
            nz = [m for m in valid_moves if m != 0]
            exec_action = int(choice_fn(nz)) if nz else 0
            shield_intervened = True
        elif exec_action in (1, 2, 3, 4) and exec_action not in valid_moves:
            nz = [m for m in valid_moves if m != 0]
            exec_action = int(choice_fn(nz)) if nz else 0
            shield_intervened = True
        return exec_action, shield_intervened

    if analysis["in_danger"] and int(analysis["escape_action"]) != 0 and (
        exec_action == 0
        or exec_action == 5
        or exec_action not in valid_moves
        or (exec_action != int(analysis["escape_action"]) and exec_action not in tactical_pushes)
    ):
        exec_action = int(analysis["escape_action"])
        shield_intervened = True
    elif exec_action == 5 and (
        not analysis["can_place_bomb"]
        or not analysis["safe_escape_from_here"]
        or int(analysis["bomb_targets_here"]) == 0
    ):
        if tactical_pushes:
            exec_action = int(tactical_pushes[0])
        elif hunt_act in valid_moves and hunt_act != 0 and hunt_act not in push_actions:
            exec_action = hunt_act
        else:
            nz = [m for m in valid_moves if m != 0 and (m not in push_actions or m in tactical_pushes)]
            exec_action = int(choice_fn(nz)) if nz else 0
        shield_intervened = True
    elif exec_action in push_actions and exec_action not in tactical_pushes:
        # Block pointless bomb pushes into empty space; redirect toward hunt objective
        if hunt_act in valid_moves and hunt_act != 0 and (hunt_act not in push_actions or hunt_act in tactical_pushes):
            exec_action = hunt_act
        else:
            nz = [m for m in valid_moves if m != 0 and (m not in push_actions or m in tactical_pushes)]
            exec_action = int(choice_fn(nz)) if nz else 0
        shield_intervened = True
    elif exec_action in (1, 2, 3, 4) and exec_action not in valid_moves:
        if hunt_act in valid_moves and hunt_act != 0:
            exec_action = hunt_act
        else:
            nz = [m for m in valid_moves if m != 0 and (m not in push_actions or m in tactical_pushes)]
            exec_action = int(choice_fn(nz)) if nz else 0
        shield_intervened = True

    return exec_action, shield_intervened


def choose_bfs_fallback_action(analysis: Dict[str, Any], rng: Optional[Any] = None) -> int:
    """Tactical BFS heuristic fallback action when no PPO model checkpoint is loaded."""
    if analysis["in_danger"] and int(analysis["escape_action"]) != 0:
        return int(analysis["escape_action"])
    tactical_pushes: List[int] = list(analysis.get("tactical_push_actions", []))
    if tactical_pushes:
        return int(tactical_pushes[0])
    if (
        analysis["can_place_bomb"]
        and analysis["safe_escape_from_here"]
        and int(analysis["bomb_targets_here"]) > 0
    ):
        return 5
    hunt_act = int(analysis.get("hunt_action", 0))
    if hunt_act != 0 and hunt_act in analysis["valid_moves"]:
        return hunt_act
    valid_moves: List[int] = list(analysis["valid_moves"])
    non_zero = [m for m in valid_moves if m != 0]
    choice_fn = rng.choice if rng is not None else np.random.choice
    return int(choice_fn(non_zero)) if non_zero else 0


def compute_action_mask(
    analysis: Optional[Dict[str, Any]],
    mode: str = "clean",
) -> np.ndarray:
    """Computes a boolean action mask [can_idle, can_up, can_down, can_left, can_right, can_bomb]
    used by MaskablePPO.

    - mode="clean" (Option B — Pure CNN Decision Making + Physics & Suicide Masking Only):
      The CNN makes 100% of tactical and strategic decisions (where to walk, who to chase,
      when to place a bomb, when to kick a bomb, when to wait).
      The mask ONLY blocks physically invalid moves (walls/flames) and guaranteed self-suicide:
        * Moves 1..4: any passable safe step (or valid Hammer bomb kick) in `valid_moves`.
        * Action 5 (PLACE_BOMB): allowed whenever off cooldown and at least one escape route exists (`safe_escape_from_here`).
        * Action 0 (NONE): allowed whenever not standing on an active danger tile (or if no escape exists).
        * When `in_danger`: any safe step in `valid_moves` is allowed (or `escape_action` if deeper escape is needed).
    - mode="legacy" (Option C — Legacy Heavy BFS Heuristic Mask):
      Preserves previous target-forcing mask for legacy comparisons if explicitly requested.
    """
    mask = np.zeros(6, dtype=bool)
    if analysis is None:
        mask[0] = True
        return mask

    in_danger = bool(analysis.get("in_danger", False))
    escape_act = int(analysis.get("escape_action", 0))
    valid_moves = set(analysis.get("valid_moves", [0]))

    if mode != "legacy":
        if in_danger:
            safe_escapes = [int(a) for a in analysis.get("safe_escape_moves", []) if int(a) in (1, 2, 3, 4)]
            if safe_escapes:
                for a in safe_escapes:
                    mask[a] = True
            else:
                for a in (1, 2, 3, 4):
                    if a in valid_moves:
                        mask[a] = True
                if escape_act in (1, 2, 3, 4):
                    mask[escape_act] = True
            if not np.any(mask):
                mask[0] = True
            return mask

        # Not in danger: allow ALL physically passable safe moves (including valid Hammer pushes)
        for a in (1, 2, 3, 4):
            if a in valid_moves:
                mask[a] = True

        # Allow idle (standing still) unconditionally when safe (Markovian mask)
        mask[0] = True

        # Allow placing a bomb whenever physically legal, fuse-accurate escape exists,
        # and at least one crate or enemy is in blast range (never forces PLACE_BOMB).
        mask[5] = (
            bool(analysis.get("can_place_bomb", False))
            and bool(analysis.get("safe_escape_from_here", False))
            and int(analysis.get("bomb_targets_here", 0)) > 0
        )

        if not np.any(mask):
            mask[0] = True
        return mask

    push_set = set(analysis.get("push_actions", []))
    tactical_push_set = set(analysis.get("tactical_push_actions", []))
    hunt_act = int(analysis.get("hunt_action", 0))
    local_bombs = int(analysis.get("local_active_bombs", analysis.get("active_bombs_count", 0)))

    if in_danger and escape_act in (1, 2, 3, 4):
        mask[escape_act] = True
        for tp in tactical_push_set:
            if tp in (1, 2, 3, 4):
                mask[tp] = True
        return mask

    can_bomb = (
        (not in_danger)
        and bool(analysis.get("can_place_bomb", False))
        and bool(analysis.get("safe_escape_from_here", False))
        and int(analysis.get("bomb_targets_here", 0)) > 0
    )
    enemy_strike_ready = can_bomb and (
        int(analysis.get("enemy_targets_here", 0)) > 0
        or bool(analysis.get("trap_bomb_here", False))
    )

    if enemy_strike_ready:
        mask[5] = True
        for tp in tactical_push_set:
            if tp in (1, 2, 3, 4):
                mask[tp] = True
        return mask

    if not in_danger and tactical_push_set:
        for tp in tactical_push_set:
            if tp in (1, 2, 3, 4):
                mask[tp] = True
        if can_bomb:
            mask[5] = True
        return mask

    if can_bomb and hunt_act == 0 and local_bombs == 0:
        mask[5] = True
        return mask

    if not in_danger and local_bombs > 0 and not can_bomb:
        mask[0] = True
        if hunt_act in (1, 2, 3, 4) and hunt_act in valid_moves and hunt_act not in push_set:
            mask[hunt_act] = True
        return mask

    if (
        not in_danger
        and not can_bomb
        and hunt_act in (1, 2, 3, 4)
        and hunt_act in valid_moves
        and (hunt_act not in push_set or hunt_act in tactical_push_set)
    ):
        mask[hunt_act] = True
        return mask

    for a in (1, 2, 3, 4):
        if a in push_set:
            mask[a] = a in tactical_push_set
        else:
            mask[a] = a in valid_moves

    mask[5] = can_bomb

    has_directional_moves = any(mask[1:5])
    if has_directional_moves:
        mask[0] = (not in_danger) and (local_bombs > 0)
    else:
        mask[0] = not in_danger

    if not np.any(mask):
        if escape_act in (1, 2, 3, 4):
            mask[escape_act] = True
        elif has_directional_moves:
            for a in (1, 2, 3, 4):
                if a in valid_moves:
                    mask[a] = True
                    break
        else:
            mask[0] = True

    return mask


def format_obs(
    base_obs: np.ndarray,
    reach_map: np.ndarray,
    bomb_map: np.ndarray,
    expected_channels: int = 17,
) -> np.ndarray:
    """Formats the multi-channel observation tensor for 8, 10, 12, 17 (Pure C++ CNN), or 19 (Legacy BFS) channel policies."""
    if expected_channels == 17:
        if base_obs.shape[0] < 17:
            pad = np.zeros((17 - base_obs.shape[0], base_obs.shape[1], base_obs.shape[2]), dtype=base_obs.dtype)
            base_obs = np.concatenate([base_obs, pad], axis=0)
        return base_obs[:17]
    if expected_channels == 19:
        if base_obs.shape[0] < 17:
            pad = np.zeros((17 - base_obs.shape[0], base_obs.shape[1], base_obs.shape[2]), dtype=base_obs.dtype)
            base_obs = np.concatenate([base_obs, pad], axis=0)
        return np.concatenate([base_obs[:17], reach_map[None, ...], bomb_map[None, ...]], axis=0)
    if expected_channels == 12:
        return np.concatenate([base_obs[:10], reach_map[None, ...], bomb_map[None, ...]], axis=0)
    if expected_channels == 10:
        return np.concatenate([base_obs[:8], reach_map[None, ...], bomb_map[None, ...]], axis=0)
    if expected_channels == 8:
        return base_obs[:8]
    return np.concatenate([base_obs, reach_map[None, ...], bomb_map[None, ...]], axis=0)

