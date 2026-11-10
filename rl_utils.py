from collections import deque
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

DIRS: Dict[int, Tuple[int, int]] = {
    1: (0, -1),
    2: (0, 1),
    3: (-1, 0),
    4: (1, 0),
}


def compute_bfs_features(
    base_obs: np.ndarray,
    tstate: Union[Dict[str, int], Any],
    width: int = 13,
    height: int = 13,
) -> Tuple[np.ndarray, np.ndarray, float, Dict[str, Any]]:
    """
    Computes tactical BFS reachability map, safe-escape bomb target map,
    PBRS potential phi(s), and tactical analysis metadata from the 10-channel engine state.
    """
    h, w = height, width
    reach_map = np.zeros((h, w), dtype=np.float32)
    bomb_map = np.zeros((h, w), dtype=np.float32)

    if isinstance(tstate, dict):
        is_alive = bool(tstate.get("is_alive", 0))
        px = int(tstate.get("x", -1))
        py = int(tstate.get("y", -1))
        has_ring = bool(tstate.get("has_ring", 0))
        has_hammer = bool(tstate.get("has_hammer", 0))
        bomb_radius = int(tstate.get("bomb_radius", 2))
        avail_bombs = int(tstate.get("avail_bombs", 0))
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
        facing_dx = int(getattr(tstate, "facingDx", 0))
        facing_dy = int(getattr(tstate, "facingDy", 1))

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
            "valid_moves": [0],
            "can_place_bomb": False,
            "can_push_bomb_now": False,
            "push_actions": [],
            "tactical_push_actions": [],
        }

    solid = base_obs[0] > 0.0
    breakable = base_obs[1] > 0.0
    bombs = base_obs[2] > 0.0
    danger = base_obs[3]
    flames = base_obs[4] > 0.0
    powerups = base_obs[5] > 0.0
    enemies = base_obs[7] > 0.0

    in_danger = bool(danger[py, px] > 0.0)

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
        if d >= 14:
            continue
        for act_id, (dx, dy) in DIRS.items():
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and dist[ny, nx] == -1 and passable[ny, nx]:
                if not in_danger and danger[ny, nx] > 0.0:
                    continue
                if in_danger and danger[ny, nx] >= 0.88:
                    continue
                dist[ny, nx] = d + 1
                fa = act_id if d == 0 else int(first_action[cy, cx])
                first_action[ny, nx] = fa
                if d == 0:
                    valid_moves.append(act_id)
                if danger[ny, nx] == 0.0:
                    reach_map[ny, nx] = max(0.1, 1.0 - (d + 1) / 15.0)
                    if d + 1 < min_safe_dist:
                        min_safe_dist = d + 1
                        escape_action = fa
                else:
                    reach_map[ny, nx] = 0.15
                q.append((nx, ny))

    push_actions: List[int] = []
    tactical_push_actions: List[int] = []
    if has_hammer and not bombs[py, px]:
        for act_id, (dx, dy) in DIRS.items():
            if can_push_bomb_in_dir(dx, dy):
                push_actions.append(act_id)
                if act_id not in valid_moves:
                    valid_moves.append(act_id)
                if in_danger or has_push_target_in_dir(dx, dy):
                    tactical_push_actions.append(act_id)
                    bomb_map[py + dy, px + dx] = 1.0
                if in_danger and escape_action == 0:
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
        blast_tiles = compute_blast_zone(bx, by, radius)
        max_search_steps = max(6, radius + 3)
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
                if (
                    0 <= nx < w
                    and 0 <= ny < h
                    and b_dist[ny, nx] == -1
                    and passable[ny, nx]
                    and danger[ny, nx] < 0.7
                ):
                    b_dist[ny, nx] = cd + 1
                    if (nx, ny) not in blast_tiles and danger[ny, nx] == 0.0:
                        return True
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

    def evaluate_enemy_compression_at(bx: int, by: int, radius: int) -> Tuple[int, bool]:
        """Returns (total_safe_tiles_compressed, traps_any_enemy) if a bomb is placed at (bx, by)."""
        if not enemy_Coords:
            return 0, False
        nearby = [
            (ex, ey)
            for (ex, ey) in enemy_Coords
            if abs(ex - bx) + abs(ey - by) <= radius + 4
        ]
        if not nearby:
            return 0, False
        sim_blast = compute_blast_zone(bx, by, radius)
        total_compressed = 0
        traps_any = False
        for ex, ey in nearby:
            before_sc = enemy_base_safe.get((ex, ey), 0)
            after_sc = count_enemy_safe_tiles(ex, ey, sim_bomb=(bx, by), sim_blast=sim_blast)
            diff = max(0, before_sc - after_sc)
            total_compressed += diff
            if before_sc > 0 and after_sc == 0:
                traps_any = True
        return total_compressed, traps_any

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

        compressed_tiles, traps_enemy = evaluate_enemy_compression_at(bx, by, radius)
        if traps_enemy:
            t += 5
            enemy_t = max(enemy_t, 1)
        elif compressed_tiles >= 2:
            t += min(4, compressed_tiles)
            enemy_t = max(enemy_t, 1)

        # Also count close-proximity enemies (Manhattan dist <= radius + 1) for corridor trapping
        # and aligned enemies within 6 tiles when Hammer is active (place-and-kick setups)
        if enemy_t == 0 and len(en_xs) > 0:
            min_md = int(np.min(np.abs(en_xs - bx) + np.abs(en_ys - by)))
            if min_md <= radius + 1:
                t += 2
                enemy_t += 1
            elif has_hammer:
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

    for _, (dx, dy) in DIRS.items():
        nx, ny = px + dx, py + dy
        if 0 <= nx < w and 0 <= ny < h and passable[ny, nx] and danger[ny, nx] == 0.0:
            if has_escape_if_bomb_at(nx, ny, bomb_radius):
                t, et, comp_t, trap_t = count_targets_at(nx, ny, bomb_radius)
                if t > 0:
                    if trap_t:
                        bomb_map[ny, nx] = 1.0
                    else:
                        bomb_map[ny, nx] = min(
                            1.0, (t + et * 2 + comp_t * 0.5) / 5.0
                        )

    hunt_action = 0
    pu_ys, pu_xs = np.where((powerups) & (dist > 0) & (danger == 0.0))
    en_ys, en_xs = np.where(enemies)
    if not in_danger:
        best_target_score = 9999.0
        for act in valid_moves:
            if act == 0 or act not in DIRS:
                continue
            dx, dy = DIRS[act]
            nx, ny = px + dx, py + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            score = 999.0
            if len(pu_xs) > 0:
                pu_d = float(np.min(np.abs(pu_xs - nx) + np.abs(pu_ys - ny)))
                score = min(score, pu_d * 0.7)
            if len(en_xs) > 0:
                en_d = float(np.min(np.abs(en_xs - nx) + np.abs(en_ys - ny)))
                score = min(score, en_d)
            if score < best_target_score:
                best_target_score = score
                hunt_action = act

    safe_reachable_count = int(np.sum((dist >= 0) & (danger == 0.0)))
    phi_space = min(safe_reachable_count, 35) * 0.12
    phi_safety = -4.0 * float(danger[py, px]) if in_danger else 0.0
    phi_hunt = 0.0
    if not in_danger:
        if len(pu_xs) > 0:
            phi_hunt += (15.0 - min(int(np.min(dist[pu_ys, pu_xs])), 15)) * 0.18
        if len(en_xs) > 0:
            reach_en = [int(dist[ey, ex]) for ex, ey in zip(en_xs, en_ys) if dist[ey, ex] >= 0]
            if reach_en:
                phi_hunt += (20.0 - min(min(reach_en), 20)) * 0.15
            else:
                phi_hunt += (24.0 - min(int(np.min(np.abs(en_xs - px) + np.abs(en_ys - py))), 24)) * 0.08

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
        "hunt_action": hunt_action,
        "valid_moves": valid_moves,
        "can_place_bomb": can_place_bomb,
        "can_push_bomb_now": can_push_bomb_now,
        "push_actions": push_actions,
        "tactical_push_actions": tactical_push_actions,
    }
    return reach_map, bomb_map, phi_space + phi_safety + phi_hunt, analysis


def apply_tactical_shield(
    raw_action: int,
    analysis: Dict[str, Any],
    rng: Optional[Any] = None,
) -> Tuple[int, bool]:
    """
    Applies the tactical safety shield to a raw action using BFS analysis.
    Action 5 is strictly PLACE_BOMB; Hammer bomb pushing is performed via
    directional movement actions (1..4) in analysis['push_actions'].
    Returns (executed_action, shield_intervened).
    """
    exec_action = int(raw_action)
    shield_intervened = False
    valid_moves: List[int] = list(analysis["valid_moves"])
    tactical_pushes: List[int] = list(analysis.get("tactical_push_actions", []))
    choice_fn = rng.choice if rng is not None else np.random.choice

    if analysis["in_danger"] and int(analysis["escape_action"]) != 0 and (
        exec_action == 0
        or exec_action == 5
        or exec_action not in valid_moves
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
        else:
            nz = [m for m in valid_moves if m != 0]
            exec_action = int(choice_fn(nz)) if nz else 0
        shield_intervened = True
    elif exec_action in (1, 2, 3, 4) and exec_action not in valid_moves:
        nz = [m for m in valid_moves if m != 0]
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


def format_obs(
    base_obs: np.ndarray,
    reach_map: np.ndarray,
    bomb_map: np.ndarray,
    expected_channels: int = 12,
) -> np.ndarray:
    """Formats the multi-channel observation tensor for 8, 10, or 12 channel policies."""
    if expected_channels == 10:
        return np.concatenate([base_obs[:8], reach_map[None, ...], bomb_map[None, ...]], axis=0)
    if expected_channels == 8:
        return base_obs[:8]
    return np.concatenate([base_obs, reach_map[None, ...], bomb_map[None, ...]], axis=0)

