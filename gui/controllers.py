from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple
import numpy as np
import pygame

from gui.config import BOARD_HEIGHT_TILES, BOARD_WIDTH_TILES, DEFAULT_MODEL_PATHS
from gui.state_snapshot import AIDebugSnapshot, IGameSession, PlayerAction
from rl_utils import (
    DIRS,
    apply_tactical_shield,
    compute_action_mask,
    compute_bfs_features,
    format_obs,
)


class IPlayerController(Protocol):
    """Interface for any player input source (Human Keyboard, PPO Agent, Heuristic Bot)."""

    def get_action(self, session: Optional[IGameSession] = None) -> PlayerAction:
        ...

    def get_command(self, session: Optional[IGameSession] = None) -> PlayerAction:
        ...

    def get_debug_snapshot(self) -> Optional[AIDebugSnapshot]:
        ...


class KeyboardController:
    """
    Reads Player 1 keyboard state (Arrow keys to move, Space to place bomb).
    Combines event-driven tracking (KEYDOWN/KEYUP with physical scancodes and bomb latching)
    and pygame.key.get_pressed() polling so neither quick taps nor held keys are missed.
    """

    _DIR_BINDINGS: Tuple[Tuple[PlayerAction, Tuple[int, ...], int], ...] = (
        (PlayerAction.UP, (pygame.K_UP,), getattr(pygame, "KSCAN_UP", 82)),
        (PlayerAction.DOWN, (pygame.K_DOWN,), getattr(pygame, "KSCAN_DOWN", 81)),
        (PlayerAction.LEFT, (pygame.K_LEFT,), getattr(pygame, "KSCAN_LEFT", 80)),
        (PlayerAction.RIGHT, (pygame.K_RIGHT,), getattr(pygame, "KSCAN_RIGHT", 79)),
    )
    _BOMB_KEYS: Tuple[int, ...] = (pygame.K_SPACE,)
    _BOMB_SCANCODES: Tuple[int, ...] = (getattr(pygame, "KSCAN_SPACE", 44),)

    def __init__(self) -> None:
        self._held_dirs: List[PlayerAction] = []
        self._held_bomb: bool = False
        self._bomb_latched: bool = False

    def reset_state(self) -> None:
        self._held_dirs.clear()
        self._held_bomb = False
        self._bomb_latched = False

    @classmethod
    def _match_action(cls, event: pygame.event.Event) -> Optional[PlayerAction]:
        ev_key = getattr(event, "key", None)
        ev_scan = getattr(event, "scancode", None)
        if ev_key in cls._BOMB_KEYS or (ev_scan is not None and ev_scan in cls._BOMB_SCANCODES):
            return PlayerAction.PLACE_BOMB
        for act, key_codes, scan_code in cls._DIR_BINDINGS:
            if ev_key in key_codes or (ev_scan is not None and scan_code != 0 and ev_scan == scan_code):
                return act
        return None

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type not in (pygame.KEYDOWN, pygame.KEYUP):
            return
        act = self._match_action(event)
        if act is None:
            return
        if event.type == pygame.KEYDOWN:
            if act == PlayerAction.PLACE_BOMB:
                self._held_bomb = True
                self._bomb_latched = True
            else:
                if act in self._held_dirs:
                    self._held_dirs.remove(act)
                self._held_dirs.append(act)
        elif event.type == pygame.KEYUP:
            if act == PlayerAction.PLACE_BOMB:
                self._held_bomb = False
            elif act in self._held_dirs:
                self._held_dirs.remove(act)

    def get_action(self, session: Optional[IGameSession] = None) -> PlayerAction:
        keys = pygame.key.get_pressed()

        if self._bomb_latched or self._held_bomb or keys[pygame.K_SPACE]:
            self._bomb_latched = False
            return PlayerAction.PLACE_BOMB

        if self._held_dirs:
            return self._held_dirs[-1]

        if keys[pygame.K_UP]:
            return PlayerAction.UP
        if keys[pygame.K_DOWN]:
            return PlayerAction.DOWN
        if keys[pygame.K_LEFT]:
            return PlayerAction.LEFT
        if keys[pygame.K_RIGHT]:
            return PlayerAction.RIGHT

        return PlayerAction.NONE

    def get_command(self, session: Optional[IGameSession] = None) -> PlayerAction:
        return self.get_action(session)

    def get_debug_snapshot(self) -> Optional[AIDebugSnapshot]:
        return None


class Player2KeyboardController:
    """
    Reads Player 2 keyboard state (WASD to move, E or Left Shift to place bomb).
    Matches physical scancodes, English keycodes, and Hebrew layout keycodes/unicode
    so Player 2 controls work reliably regardless of active OS keyboard layout.
    """

    # Physical scancodes: W=26, S=22, A=4, D=7, E=8, LSHIFT=225
    _DIR_BINDINGS: Tuple[Tuple[PlayerAction, Tuple[int, ...], int, str], ...] = (
        (
            PlayerAction.UP,
            (pygame.K_w, ord("W"), ord("'")),
            getattr(pygame, "KSCAN_W", 26),
            "wW'",
        ),
        (
            PlayerAction.DOWN,
            (pygame.K_s, ord("S"), ord("\u05d3")),
            getattr(pygame, "KSCAN_S", 22),
            "sS\u05d3",
        ),
        (
            PlayerAction.LEFT,
            (pygame.K_a, ord("A"), ord("\u05e9")),
            getattr(pygame, "KSCAN_A", 4),
            "aA\u05e9",
        ),
        (
            PlayerAction.RIGHT,
            (pygame.K_d, ord("D"), ord("\u05d2")),
            getattr(pygame, "KSCAN_D", 7),
            "dD\u05d2",
        ),
    )
    _BOMB_KEYS: Tuple[int, ...] = (
        pygame.K_e,
        ord("E"),
        ord("\u05e7"),
        pygame.K_LSHIFT,
    )
    _BOMB_SCANCODES: Tuple[int, ...] = (
        getattr(pygame, "KSCAN_E", 8),
        getattr(pygame, "KSCAN_LSHIFT", 225),
    )
    _BOMB_CHARS: str = "eE\u05e7"

    def __init__(self) -> None:
        self._held_dirs: List[PlayerAction] = []
        self._held_bomb: bool = False
        self._bomb_latched: bool = False

    def reset_state(self) -> None:
        self._held_dirs.clear()
        self._held_bomb = False
        self._bomb_latched = False

    @classmethod
    def _match_action(cls, event: pygame.event.Event) -> Optional[PlayerAction]:
        ev_key = getattr(event, "key", None)
        ev_scan = getattr(event, "scancode", None)
        ev_uni = getattr(event, "unicode", "") or ""

        if (
            ev_key in cls._BOMB_KEYS
            or (ev_scan is not None and ev_scan in cls._BOMB_SCANCODES)
            or (ev_uni and ev_uni in cls._BOMB_CHARS)
        ):
            return PlayerAction.PLACE_BOMB

        for act, key_codes, scan_code, chars in cls._DIR_BINDINGS:
            if (
                ev_key in key_codes
                or (ev_scan is not None and scan_code != 0 and ev_scan == scan_code)
                or (ev_uni and ev_uni in chars)
            ):
                return act
        return None

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type not in (pygame.KEYDOWN, pygame.KEYUP):
            return
        act = self._match_action(event)
        if act is None:
            return
        if event.type == pygame.KEYDOWN:
            if act == PlayerAction.PLACE_BOMB:
                self._held_bomb = True
                self._bomb_latched = True
            else:
                if act in self._held_dirs:
                    self._held_dirs.remove(act)
                self._held_dirs.append(act)
        elif event.type == pygame.KEYUP:
            if act == PlayerAction.PLACE_BOMB:
                self._held_bomb = False
            elif act in self._held_dirs:
                self._held_dirs.remove(act)

    @staticmethod
    def _is_any_key_pressed(keys: object, key_codes: Tuple[int, ...]) -> bool:
        for k in key_codes:
            try:
                if keys[k]:  # type: ignore[index]
                    return True
            except (IndexError, KeyError, TypeError):
                continue
        return False

    def get_action(self, session: Optional[IGameSession] = None) -> PlayerAction:
        keys = pygame.key.get_pressed()

        if (
            self._bomb_latched
            or self._held_bomb
            or self._is_any_key_pressed(keys, self._BOMB_KEYS)
        ):
            self._bomb_latched = False
            return PlayerAction.PLACE_BOMB

        if self._held_dirs:
            return self._held_dirs[-1]

        for act, key_codes, _, _ in self._DIR_BINDINGS:
            if self._is_any_key_pressed(keys, key_codes):
                return act

        return PlayerAction.NONE

    def get_command(self, session: Optional[IGameSession] = None) -> PlayerAction:
        return self.get_action(session)

    def get_debug_snapshot(self) -> Optional[AIDebugSnapshot]:
        return None


class PPOAgentController:
    """
    AI Controller that wraps the trained PPO Grandmaster model (or BFS tactical fallback)
    and produces real-time AIDebugSnapshot heatmaps for GUI visualization.
    Checks for model file existence before importing heavy ML dependencies (PyTorch / SB3),
    supports lazy loading, and shares the loaded model across all controller instances.
    """

    DIRS: Dict[int, Tuple[int, int]] = DIRS

    _shared_model: Optional[object] = None
    _shared_expected_channels: int = 12
    _model_load_attempted: bool = False

    def __init__(
        self,
        player_id: int = 1,
        width: int = BOARD_WIDTH_TILES,
        height: int = BOARD_HEIGHT_TILES,
        tactical_shield: bool = True,
        frame_skip: int = 6,
        shared_model: Optional[object] = None,
        expected_channels: int = 12,
        lazy: bool = False,
        model_path: Optional[str] = None,
        temperature: float = 0.2,
    ) -> None:
        self.player_id = player_id
        self.width = width
        self.height = height
        self.tactical_shield = tactical_shield
        self.frame_skip = max(1, int(frame_skip))
        self.temperature = float(temperature)
        self._tick_counter = 0
        self._idle_cooldown = 0
        self._recent_positions: deque[Tuple[int, int]] = deque(maxlen=8)
        self.model = shared_model
        self.expected_channels = expected_channels
        self.model_path = model_path
        self._last_debug: Optional[AIDebugSnapshot] = None
        self._last_debug_tick: Optional[int] = None
        if self.model is None:
            if self.model_path is not None:
                if not lazy:
                    self._load_from_path(self.model_path)
            elif PPOAgentController._model_load_attempted:
                self.model = PPOAgentController._shared_model
                self.expected_channels = PPOAgentController._shared_expected_channels
            elif not lazy:
                self._load_model_if_available()

    @classmethod
    def reset_model_cache(cls) -> None:
        """Resets class-level model cache (for testing or explicit reload)."""
        cls._shared_model = None
        cls._shared_expected_channels = 12
        cls._model_load_attempted = False

    @staticmethod
    def _find_existing_model_path() -> Optional[Path]:
        for path in DEFAULT_MODEL_PATHS:
            p = Path(path)
            if p.is_file():
                return p
        return None

    def reset(self) -> None:
        self._tick_counter = 0
        self._idle_cooldown = 0
        self._recent_positions.clear()
        self._last_debug = None
        self._last_debug_tick = None

    def ensure_model_loaded(self) -> None:
        """Ensures the PPO model load has been attempted once when AI is actually needed."""
        if self.model is None:
            if self.model_path is not None:
                self._load_from_path(self.model_path)
            else:
                self._load_model_if_available()

    def _load_from_path(self, path: str) -> None:
        p = Path(path)
        if not p.is_file():
            self.model = None
            return
        try:
            if pygame.display.get_init():
                pygame.event.pump()
            import torch as th
            from bomberman_env import BombermanCNN
            try:
                from sb3_contrib import MaskablePPO
                self.model = MaskablePPO.load(
                    str(p), custom_objects={"BombermanCNN": BombermanCNN}
                )
            except Exception:
                from stable_baselines3 import PPO
                self.model = PPO.load(
                    str(p), custom_objects={"BombermanCNN": BombermanCNN}
                )

            obs_shape = getattr(self.model.observation_space, "shape", None)
            if obs_shape and len(obs_shape) == 3:
                self.expected_channels = int(obs_shape[0])
            dummy_obs = np.zeros(
                (self.expected_channels, self.height, self.width), dtype=np.float32
            )
            dummy_mask = np.ones(6, dtype=bool)
            with th.no_grad():
                obs_tensor, _ = self.model.policy.obs_to_tensor(dummy_obs)
                try:
                    _ = self.model.policy.get_distribution(obs_tensor, action_masks=dummy_mask)
                except TypeError:
                    _ = self.model.policy.get_distribution(obs_tensor)
                _ = self.model.policy.predict_values(obs_tensor)
        except Exception:
            self.model = None

    def _load_model_if_available(self) -> None:
        if self.model is not None:
            return
        if PPOAgentController._model_load_attempted:
            self.model = PPOAgentController._shared_model
            self.expected_channels = PPOAgentController._shared_expected_channels
            return

        PPOAgentController._model_load_attempted = True
        model_path = self._find_existing_model_path()
        if model_path is None:
            self.model = None
            return

        try:
            if pygame.display.get_init():
                pygame.event.pump()

            import torch as th
            from bomberman_env import BombermanCNN
            try:
                from sb3_contrib import MaskablePPO
                self.model = MaskablePPO.load(
                    str(model_path), custom_objects={"BombermanCNN": BombermanCNN}
                )
            except Exception:
                from stable_baselines3 import PPO
                self.model = PPO.load(
                    str(model_path), custom_objects={"BombermanCNN": BombermanCNN}
                )

            obs_shape = getattr(self.model.observation_space, "shape", None)
            if obs_shape and len(obs_shape) == 3:
                self.expected_channels = int(obs_shape[0])
            # Warm up PyTorch CPU thread pool and conv kernels once
            dummy_obs = np.zeros(
                (self.expected_channels, self.height, self.width), dtype=np.float32
            )
            dummy_mask = np.ones(6, dtype=bool)
            with th.no_grad():
                obs_tensor, _ = self.model.policy.obs_to_tensor(dummy_obs)
                try:
                    _ = self.model.policy.get_distribution(obs_tensor, action_masks=dummy_mask)
                except TypeError:
                    _ = self.model.policy.get_distribution(obs_tensor)
                _ = self.model.policy.predict_values(obs_tensor)

            PPOAgentController._shared_model = self.model
            PPOAgentController._shared_expected_channels = self.expected_channels

            if pygame.display.get_init():
                pygame.event.pump()
        except Exception:
            self.model = None
            PPOAgentController._shared_model = None

    def _compute_bfs_features(
        self, base_obs: np.ndarray, tstate: Dict[str, int]
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, object]]:
        reach_map, bomb_map, _, analysis = compute_bfs_features(
            base_obs, tstate, self.width, self.height
        )
        return reach_map, bomb_map, analysis

    def _format_obs(self, base_obs: np.ndarray, reach_map: np.ndarray, bomb_map: np.ndarray) -> np.ndarray:
        return format_obs(base_obs, reach_map, bomb_map, expected_channels=self.expected_channels)

    @staticmethod
    def _get_session_tick(session: IGameSession) -> Optional[int]:
        tick = getattr(session, "tick_count", None)
        if tick is None:
            tick = getattr(session, "ticks", None)
        return int(tick) if tick is not None else None

    def compute_debug_only(self, session: IGameSession) -> Optional[AIDebugSnapshot]:
        session_tick = self._get_session_tick(session)
        if (
            self._last_debug is not None
            and session_tick is not None
            and self._last_debug_tick == session_tick
        ):
            return self._last_debug

        tstate = session.get_player_tactical_state(self.player_id)
        base_obs = session.get_rl_base_observation(self.player_id)
        reach_map, bomb_map, analysis = self._compute_bfs_features(base_obs, tstate)
        self._last_debug = AIDebugSnapshot(
            action_probs=self._last_debug.action_probs if self._last_debug else None,
            chosen_action=self._last_debug.chosen_action if self._last_debug else 0,
            value=self._last_debug.value if self._last_debug else 0.0,
            reach_map=reach_map,
            bomb_map=bomb_map,
            in_danger=bool(analysis["in_danger"]),
            shield_intervened=self._last_debug.shield_intervened if self._last_debug else False,
        )
        self._last_debug_tick = session_tick
        return self._last_debug

    def get_action(self, session: Optional[IGameSession] = None) -> PlayerAction:
        if session is None:
            return PlayerAction.NONE

        tstate = session.get_player_tactical_state(self.player_id)
        if not tstate.get("is_alive", 0):
            return PlayerAction.NONE

        self._tick_counter += 1
        if "cooldown" in tstate:
            # Player::update decrements cooldown before Player::handleCommand in Game::update,
            # so cooldown <= 1 means the player will be ready to act on this tick.
            if int(tstate["cooldown"]) > 1:
                return PlayerAction.NONE
            if self._idle_cooldown > 0:
                self._idle_cooldown -= 1
                return PlayerAction.NONE
        else:
            is_decision_tick = ((self._tick_counter - 1) % self.frame_skip) == 0
            if not is_decision_tick:
                return PlayerAction.NONE

        self.ensure_model_loaded()
        base_obs = session.get_rl_base_observation(self.player_id)
        reach_map, bomb_map, analysis = self._compute_bfs_features(base_obs, tstate)
        obs = self._format_obs(base_obs, reach_map, bomb_map)

        raw_action = 0
        action_probs: Optional[List[float]] = None
        value_est = 0.0
        cur_pos = (int(tstate.get("x", -1)), int(tstate.get("y", -1)))

        if self.model is not None:
            try:
                import torch as th
                action_mask = compute_action_mask(analysis)
                obs_tensor, _ = self.model.policy.obs_to_tensor(obs)
                with th.no_grad():
                    try:
                        dist = self.model.policy.get_distribution(
                            obs_tensor, action_masks=action_mask
                        )
                    except TypeError:
                        dist = self.model.policy.get_distribution(obs_tensor)
                    probs = dist.distribution.probs.cpu().numpy()[0]
                    action_probs = [float(p) for p in probs]
                    val = self.model.policy.predict_values(obs_tensor).cpu().numpy()[0]
                    value_est = float(val.item() if hasattr(val, "item") else val[0])

                # Check for 2-cycle oscillation in recent positions (A <-> B <-> A <-> B)
                is_oscillating = False
                if len(self._recent_positions) >= 4:
                    if (
                        self._recent_positions[-1] == self._recent_positions[-3]
                        and cur_pos == self._recent_positions[-2]
                    ):
                        is_oscillating = True

                if is_oscillating:
                    hunt_act = int(analysis.get("hunt_action", 0))
                    if hunt_act != 0 and hunt_act in analysis.get("valid_moves", []):
                        raw_action = hunt_act
                    elif self.temperature > 0.0:
                        p_temp = np.power(probs, 1.0 / max(0.01, self.temperature))
                        p_sum = np.sum(p_temp)
                        raw_action = (
                            int(np.random.choice(len(p_temp), p=p_temp / p_sum))
                            if p_sum > 0
                            else int(np.argmax(probs))
                        )
                    else:
                        raw_action = int(np.argmax(probs))
                elif self.temperature > 0.0:
                    p_temp = np.power(probs, 1.0 / max(0.01, self.temperature))
                    p_sum = np.sum(p_temp)
                    raw_action = (
                        int(np.random.choice(len(p_temp), p=p_temp / p_sum))
                        if p_sum > 0
                        else int(np.argmax(probs))
                    )
                else:
                    raw_action = int(np.argmax(probs))
            except Exception:
                try:
                    action_mask = compute_action_mask(analysis)
                    pred, _ = self.model.predict(
                        obs, action_masks=action_mask, deterministic=(self.temperature == 0.0)
                    )
                except (TypeError, Exception):
                    pred, _ = self.model.predict(obs, deterministic=(self.temperature == 0.0))
                raw_action = int(pred.item() if hasattr(pred, "item") else pred)
        else:
            # Tactical BFS heuristic fallback when no PPO model file is present
            if analysis["in_danger"] and int(analysis["escape_action"]) != 0:
                raw_action = int(analysis["escape_action"])
            elif analysis["safe_escape_from_here"] and int(analysis["bomb_targets_here"]) > 0:
                raw_action = int(PlayerAction.PLACE_BOMB)
            else:
                hunt_act = int(analysis.get("hunt_action", 0))
                if hunt_act != 0 and hunt_act in analysis.get("valid_moves", []):
                    raw_action = hunt_act
                else:
                    valid_moves: List[int] = list(analysis["valid_moves"])  # type: ignore
                    non_zero = [m for m in valid_moves if m != 0]
                    raw_action = int(np.random.choice(non_zero)) if non_zero else 0

        self._recent_positions.append(cur_pos)

        exec_action = raw_action
        shield_intervened = False
        if self.tactical_shield:
            exec_action, shield_intervened = apply_tactical_shield(raw_action, analysis)

        if exec_action == int(PlayerAction.NONE):
            self._idle_cooldown = max(0, self.frame_skip - 1)
        else:
            self._idle_cooldown = 0

        self._last_debug = AIDebugSnapshot(
            action_probs=action_probs,
            chosen_action=exec_action,
            value=value_est,
            reach_map=reach_map,
            bomb_map=bomb_map,
            in_danger=bool(analysis["in_danger"]),
            shield_intervened=shield_intervened,
        )
        self._last_debug_tick = self._get_session_tick(session)
        return PlayerAction(exec_action)

    def get_command(self, session: Optional[IGameSession] = None) -> PlayerAction:
        return self.get_action(session)

    def get_debug_snapshot(self) -> Optional[AIDebugSnapshot]:
        return self._last_debug
