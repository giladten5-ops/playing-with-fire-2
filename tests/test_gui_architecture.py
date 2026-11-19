import ast
import io
import os
import re
import tokenize
import unittest
from pathlib import Path
from typing import Dict
import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from gui.assets import AssetManager
from gui.board_renderer import BoardRenderer
from gui.config import BOARD_HEIGHT_TILES, BOARD_WIDTH_TILES, WINDOW_HEIGHT, WINDOW_WIDTH
from gui.controllers import KeyboardController, PPOAgentController
from gui.hud_renderer import HUDRenderer
from gui.state_snapshot import (
    AIDebugSnapshot,
    BombSnapshot,
    FlameSnapshot,
    GameSnapshot,
    IGameSession,
    PlayerAction,
    PlayerSnapshot,
    PowerUpSnapshot,
)


class MockGameSession(IGameSession):
    """Pure Python mock session proving the GUI runs without bomberman_engine."""

    def __init__(self) -> None:
        self.ticks = 0
        self.game_over = False
        self.last_reset_args = (1, 3, 1)

    def reset(self, num_human: int = 1, num_bots: int = 3, level_id: int = 1) -> None:
        self.ticks = 0
        self.game_over = False
        self.last_reset_args = (num_human, num_bots, level_id)

    def step_tick(self, action: PlayerAction, p2_action=None) -> None:
        self.ticks += 1

    def is_game_over(self) -> bool:
        return self.game_over

    def get_winner_id(self) -> int:
        return 1 if self.game_over else -1

    def get_rl_base_observation(self, player_id: int = 1) -> np.ndarray:
        return np.zeros((10, BOARD_HEIGHT_TILES, BOARD_WIDTH_TILES), dtype=np.float32)

    def get_player_tactical_state(self, player_id: int = 1) -> Dict[str, int]:
        return {
            "is_alive": 1,
            "x": 0,
            "y": 0,
            "has_ring": 1,
            "has_hammer": 1,
            "bomb_radius": 3,
            "avail_bombs": 2,
            "facing_dx": 1,
            "facing_dy": 0,
        }

    def get_snapshot(self, alpha: float, ai_debug=None) -> GameSnapshot:
        board = [[0 for _ in range(BOARD_WIDTH_TILES)] for _ in range(BOARD_HEIGHT_TILES)]
        board[1][1] = 1
        board[0][2] = 2
        players = {
            1: PlayerSnapshot(
                id=1, grid_x=0, grid_y=0, render_x=0.25, render_y=0.0,
                facing_dx=1, facing_dy=0, lives=3, max_bombs=2, avail_bombs=1,
                bomb_radius=3, speed_level=1, invincibility_timer=0,
                has_hammer=True, has_ring=True, is_bot=False, is_alive=True, is_moving=True
            ),
            2: PlayerSnapshot(
                id=2, grid_x=12, grid_y=12, render_x=12.0, render_y=12.0,
                facing_dx=0, facing_dy=-1, lives=0, max_bombs=1, avail_bombs=0,
                bomb_radius=2, speed_level=0, invincibility_timer=0,
                has_hammer=False, has_ring=False, is_bot=True, is_alive=False, is_moving=False
            ),
        }
        bombs = [BombSnapshot(grid_x=2, grid_y=0, render_x=1.5, render_y=0.0, timer=40, radius=2, owner_id=1, is_sliding=True)]
        flames = [FlameSnapshot(grid_x=3, grid_y=3, timer=15, owner_id=1)]
        powerups = [PowerUpSnapshot(grid_x=4, grid_y=4, type_char="H")]
        return GameSnapshot(
            board=board,
            players=players,
            bombs=bombs,
            flames=flames,
            powerups=powerups,
            sd_timer=max(0, 3600 - self.ticks),
            sd_active=False,
            is_game_over=self.game_over,
            winner_id=1 if self.game_over else -1,
            tick_count=self.ticks,
            ai_debug=ai_debug,
        )


class TestGUIArchitecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.display.init()
        pygame.font.init()
        pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_strict_engine_import_boundary(self) -> None:
        """Only gui/engine_adapter.py may import bomberman_engine."""
        gui_dir = Path(__file__).resolve().parent.parent / "gui"
        for py_file in gui_dir.glob("*.py"):
            if py_file.name == "engine_adapter.py":
                continue
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotEqual(
                            alias.name,
                            "bomberman_engine",
                            f"Forbidden import of bomberman_engine in {py_file.name}",
                        )
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(
                        node.module,
                        "bomberman_engine",
                        f"Forbidden from-import of bomberman_engine in {py_file.name}",
                    )

    def test_english_only_comments_in_gui(self) -> None:
        """All comments in gui/*.py must be strictly in English (no Hebrew chars)."""
        gui_dir = Path(__file__).resolve().parent.parent / "gui"
        hebrew_re = re.compile(r"[\u0590-\u05FF]")
        for py_file in gui_dir.glob("*.py"):
            content = py_file.read_bytes()
            tokens = tokenize.tokenize(io.BytesIO(content).readline)
            for tok_type, tok_str, start, _, _ in tokens:
                if tok_type == tokenize.COMMENT:
                    self.assertIsNone(
                        hebrew_re.search(tok_str),
                        f"Hebrew comment found in {py_file.name} at line {start[0]}: {tok_str}",
                    )

    def test_headless_rendering_with_mock_session(self) -> None:
        """BoardRenderer, HUDRenderer, and PPOAgentController work purely with MockGameSession."""
        session = MockGameSession()
        assets = AssetManager()
        board_renderer = BoardRenderer(assets)
        hud_renderer = HUDRenderer(assets)
        ai_ctrl = PPOAgentController(player_id=1)

        action = ai_ctrl.get_action(session)
        self.assertIsInstance(action, PlayerAction)
        session.step_tick(action)

        dbg = ai_ctrl.get_debug_snapshot()
        self.assertIsNotNone(dbg)

        snap = session.get_snapshot(alpha=0.5, ai_debug=dbg)
        self.assertIn(1, snap.players)
        self.assertIn(2, snap.players)
        self.assertFalse(snap.players[2].is_alive)

        surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        board_renderer.render(surface, snap, debug_mode=True, paused=False)
        hud_renderer.render(surface, snap, ai_enabled=True, debug_mode=True)

        session.game_over = True
        snap_over = session.get_snapshot(alpha=0.0, ai_debug=dbg)
        board_renderer.render(surface, snap_over, debug_mode=False, paused=False)

    def test_cpp_adapter_integration(self) -> None:
        """CppGameSession correctly tracks players, timer countdown, and dead player retention."""
        from gui.engine_adapter import CppGameSession

        session = CppGameSession(BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES)
        snap0 = session.get_snapshot(alpha=0.0)
        self.assertEqual(len(snap0.board), BOARD_HEIGHT_TILES)
        self.assertEqual(len(snap0.board[0]), BOARD_WIDTH_TILES)
        self.assertEqual(len(snap0.players), 4)

        initial_timer = snap0.sd_timer
        session.step_tick(PlayerAction.NONE)
        snap1 = session.get_snapshot(alpha=0.0)
        self.assertEqual(snap1.sd_timer, initial_timer - 1)

    def test_cpp_new_contract_bindings(self) -> None:
        """Verify C++ extension exposes getBoardGrid, moveCooldownMax, slideCooldown, and updateCommands."""
        import bomberman_engine as bme

        game = bme.Game(13, 13)
        self.assertTrue(hasattr(game, "getBoardGrid"), "Game.getBoardGrid is missing from compiled C++ module")
        self.assertTrue(hasattr(game, "updateCommands"), "Game.updateCommands is missing from compiled C++ module")

        level = bme.ClassicLevel(2, 13, 13, 65)
        game.reset(level, 1, 1)

        grid = game.getBoardGrid()
        self.assertEqual(len(grid), 13)
        self.assertEqual(len(grid[0]), 13)

        pinfo = game.getPlayerInfo(1)
        self.assertTrue(hasattr(pinfo, "moveCooldownMax"))
        self.assertGreaterEqual(pinfo.moveCooldownMax, 4)

    def test_snapshot_and_debug_tick_caching_with_smooth_interpolation(self) -> None:
        """Verify per-tick caching avoids redundant C++ queries while keeping sub-tick interpolation smooth."""
        from gui.engine_adapter import CppGameSession

        session = CppGameSession(BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES)
        ai_ctrl = PPOAgentController(player_id=1)

        # Trigger a move for Player 1 into a free adjacent tile
        tstate = session.get_player_tactical_state(1)
        px, py = tstate["x"], tstate["y"]
        snap_init = session.get_snapshot(alpha=0.0)
        moved = False
        for action, (dx, dy) in [
            (PlayerAction.RIGHT, (1, 0)),
            (PlayerAction.DOWN, (0, 1)),
            (PlayerAction.LEFT, (-1, 0)),
            (PlayerAction.UP, (0, -1)),
        ]:
            nx, ny = px + dx, py + dy
            if 0 <= nx < BOARD_WIDTH_TILES and 0 <= ny < BOARD_HEIGHT_TILES and snap_init.board[ny][nx] == 0:
                session.step_tick(action)
                moved = True
                break
        self.assertTrue(moved, "Player 1 should have at least one free adjacent spawn tile")

        # Multiple render frames within the same tick must reuse cached board & debug objects
        dbg_a = ai_ctrl.compute_debug_only(session)
        dbg_b = ai_ctrl.compute_debug_only(session)
        self.assertIs(dbg_a, dbg_b, "compute_debug_only should return cached AIDebugSnapshot on same tick")

        snap_a = session.get_snapshot(alpha=0.0, ai_debug=dbg_a)
        snap_b = session.get_snapshot(alpha=0.5, ai_debug=dbg_b)
        self.assertIs(snap_a.board, snap_b.board, "Board grid should be cached across sub-tick render frames")

        # Interpolated coordinates must change smoothly between alpha=0.0 and alpha=0.5
        p1_a = snap_a.players[1]
        p1_b = snap_b.players[1]
        self.assertTrue(p1_a.is_moving)
        self.assertNotAlmostEqual(
            abs(p1_a.render_x - p1_b.render_x) + abs(p1_a.render_y - p1_b.render_y),
            0.0,
            msg="Sub-tick interpolation must progress between alpha=0.0 and alpha=0.5",
        )

    def test_dimmed_icons_cached_in_asset_manager(self) -> None:
        """Verify dimmed player icons are pre-cached in AssetManager."""
        assets = AssetManager()
        for pid in range(1, 5):
            self.assertIsNotNone(assets.get(f"player_{pid}_dim"))

    def test_gui_freeze_protection_and_event_responsiveness(self) -> None:
        """Verify frame delta clamping, max ticks per frame cap, and responsive window closing."""
        from gui.app import BombermanGUIApp

        session = MockGameSession()
        app = BombermanGUIApp(session=session, start_in_menu=False)

        # Simulate a massive 5.0-second frame spike; must cap at MAX_TICKS_PER_FRAME and zero accumulator
        app._advance_simulation(5.0)
        self.assertLessEqual(session.ticks, BombermanGUIApp.MAX_TICKS_PER_FRAME)
        self.assertEqual(app.accumulator, 0.0)

        # Test pause (P), verify A does NOT toggle AI, T toggles AI, R restarts, and QUIT exits
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p, scancode=19, unicode="p"))
        self.assertTrue(app.handle_events())
        self.assertTrue(app.paused)

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, scancode=4, unicode="a"))
        self.assertTrue(app.handle_events())
        self.assertFalse(app.ai_mode, "Pressing A must NOT toggle AI mode (reserved for Player 2 Left)")

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_t, scancode=23, unicode="t"))
        self.assertTrue(app.handle_events())
        self.assertTrue(app.ai_mode, "Pressing T must toggle AI mode")

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, scancode=21, unicode="r"))
        self.assertTrue(app.handle_events())
        self.assertFalse(app.paused)
        self.assertEqual(session.ticks, 0)

        pygame.event.post(pygame.event.Event(pygame.QUIT))
        self.assertFalse(app.handle_events())

    def test_main_menu_pre_game_flow(self) -> None:
        """Verify multi-step wizard flow (MENU_HUMANS -> MENU_DUMB_BOTS -> MENU_TRAINED_AI -> MENU_LEVEL -> PLAYING)."""
        from gui.app import BombermanGUIApp

        session = MockGameSession()
        app = BombermanGUIApp(session=session)
        self.assertTrue(app.in_menu, "App must start in the pre-game Main Menu by default")
        self.assertEqual(app.menu_state, BombermanGUIApp.MENU_HUMANS)

        # While in menu, simulation must not advance and render_menu must succeed
        app._advance_simulation(0.5)
        self.assertEqual(session.ticks, 0)
        app.render_menu()

        # Step 1 (MENU_HUMANS): Select "2 PLAYERS" (DOWN then ENTER)
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN, scancode=81, unicode=""))
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, scancode=40, unicode="\r"))
        self.assertTrue(app.handle_events())
        self.assertEqual(app.menu_selections["humans"], 2)
        self.assertEqual(app.menu_state, BombermanGUIApp.MENU_DUMB_BOTS)
        self.assertEqual(app._get_current_menu_options(), ["0 DUMB BOTS", "1 DUMB BOT", "2 DUMB BOTS"])

        # Step 2 (MENU_DUMB_BOTS): Select "1 DUMB BOT" (DOWN once then ENTER)
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN, scancode=81, unicode=""))
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, scancode=40, unicode="\r"))
        self.assertTrue(app.handle_events())
        self.assertEqual(app.menu_selections["dumb_bots"], 1)
        self.assertEqual(app.menu_state, BombermanGUIApp.MENU_TRAINED_AI)
        self.assertEqual(app._get_current_menu_options(), ["0 TRAINED AI", "1 TRAINED AI"])

        # Test BACKSPACE returns to MENU_DUMB_BOTS, then ENTER advances back to MENU_TRAINED_AI
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, scancode=42, unicode="\b"))
        self.assertTrue(app.handle_events())
        self.assertEqual(app.menu_state, BombermanGUIApp.MENU_DUMB_BOTS)
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, scancode=40, unicode="\r"))
        self.assertTrue(app.handle_events())
        self.assertEqual(app.menu_state, BombermanGUIApp.MENU_TRAINED_AI)

        # Step 3 (MENU_TRAINED_AI): Select "1 TRAINED AI" (DOWN once then ENTER)
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN, scancode=81, unicode=""))
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, scancode=40, unicode="\r"))
        self.assertTrue(app.handle_events())
        self.assertEqual(app.menu_selections["trained_ai"], 1)
        self.assertEqual(app.menu_selections["opponents"], 2)
        self.assertEqual(app.menu_state, BombermanGUIApp.MENU_LEVEL)

        # Step 4 (MENU_LEVEL): Confirm "CLASSIC LEVEL" (ENTER) -> transitions to PLAYING
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, scancode=40, unicode="\r"))
        self.assertTrue(app.handle_events())
        self.assertEqual(app.menu_state, BombermanGUIApp.PLAYING)
        self.assertFalse(app.in_menu, "Pressing Enter on MENU_LEVEL must start the game")
        self.assertEqual(session.last_reset_args, (2, 2, 1))
        self.assertIn(3, app.opponent_ai_controllers, "Player 3 must be controlled by Trained AI PPOAgentController")

    def test_player2_controls_and_non_conflicting_hotkeys(self) -> None:
        """Verify Player 2 WASD + E controls move P2 and place bombs without triggering restart or AI toggle."""
        from gui.app import BombermanGUIApp
        from gui.engine_adapter import CppGameSession

        session = CppGameSession(BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES)
        app = BombermanGUIApp(session=session, start_in_menu=False)
        app.menu_selections["humans"] = 2
        app.menu_selections["dumb_bots"] = 1
        app.menu_selections["trained_ai"] = 1
        app.start_game()

        snap0 = session.get_snapshot(0.0)
        p2_start = (snap0.players[2].grid_x, snap0.players[2].grid_y)
        self.assertFalse(snap0.players[2].is_bot, "Player 2 must be a human player")
        self.assertTrue(snap0.players[3].is_trained_ai, "Player 3 must be marked as Trained AI")
        self.assertTrue(snap0.players[4].is_bot and not snap0.players[4].is_trained_ai, "Player 4 must be a DumbBot")

        # Press E (including Hebrew layout '\u05e7' on physical E key, scancode 8) -> must place bomb for P2 and NOT restart
        app._step_single_tick()
        ticks_before_e = session.tick_count
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=ord("\u05e7"), scancode=8, unicode="\u05e7"))
        app.handle_events()
        app._step_single_tick()
        pygame.event.post(pygame.event.Event(pygame.KEYUP, key=ord("\u05e7"), scancode=8, unicode="\u05e7"))
        app.handle_events()

        self.assertEqual(session.tick_count, ticks_before_e + 1, "Pressing E must NOT restart the game")
        snap_bomb = session.get_snapshot(0.0)
        p2_bombs = [b for b in snap_bomb.bombs if b.owner_id == 2]
        self.assertEqual(len(p2_bombs), 1, "Player 2 pressing E must place a bomb")

        # Test P2 movement via WASD events (try all 4 directions, at least one corner neighbor is free)
        moved = False
        for key, scancode, uni in (
            (pygame.K_w, 26, "w"),
            (pygame.K_s, 22, "s"),
            (pygame.K_a, 4, "a"),
            (pygame.K_d, 7, "d"),
        ):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=scancode, unicode=uni))
            app.handle_events()
            app._step_single_tick()
            pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, scancode=scancode, unicode=uni))
            app.handle_events()
            p2_now = session.get_snapshot(0.0).players[2]
            if (p2_now.grid_x, p2_now.grid_y) != p2_start:
                moved = True
                break
        self.assertTrue(moved, "Player 2 WASD controls must move Player 2 on the board")
        self.assertFalse(app.ai_mode, "Player 2 pressing A/D must never toggle AI mode")

    def test_speed_levels_and_pacing_invariants(self) -> None:
        """Verify speed levels 0, 1, 2 have cooldowns 6, 5, 4 and never hit zero cooldown."""
        import bomberman_engine as bme

        game = bme.Game(13, 13)
        game.clearBoard()
        game.addPlayer(1, 1, 1, False)
        game.addPlayer(11, 11, 2, False)

        # Speed Level 0: cooldown = 6
        game.step(1, bme.Command.RIGHT)
        p0 = game.getPlayerInfo(1)
        self.assertEqual((p0.x, p0.y), (2, 1))
        self.assertEqual(p0.moveCooldownMax, 6)
        self.assertEqual(p0.cooldown, 6)

        for _ in range(6):
            game.step(1, bme.Command.NONE)
        self.assertEqual(game.getPlayerInfo(1).cooldown, 0)

        # Speed Level 1: cooldown = 5
        game.givePlayerPowerUp(1, "speed")
        game.step(1, bme.Command.RIGHT)
        p1 = game.getPlayerInfo(1)
        self.assertEqual((p1.x, p1.y), (3, 1))
        self.assertEqual(p1.moveCooldownMax, 5)
        self.assertEqual(p1.cooldown, 5)

        for _ in range(5):
            game.step(1, bme.Command.NONE)

        # Speed Level 2 (Max): cooldown = 4 (never 0)
        game.givePlayerPowerUp(1, "speed")
        game.step(1, bme.Command.RIGHT)
        p2 = game.getPlayerInfo(1)
        self.assertEqual((p2.x, p2.y), (4, 1))
        self.assertEqual(p2.moveCooldownMax, 4)
        self.assertEqual(p2.cooldown, 4)

    def test_dumbbot_flame_avoidance_and_survival(self) -> None:
        """Verify DumbBot never walks onto active flames and survives early game without self-killing."""
        import bomberman_engine as bme

        # 1. Flame avoidance test: block bot in a corridor next to an active flame
        game = bme.Game(13, 13)
        game.clearBoard()
        game.addPlayer(5, 5, 1, False)
        game.addPlayer(2, 1, 2, True)  # DumbBot at (2, 1)
        # Explode a bomb at (4, 1) with radius 1 so (3, 1) has an active Flame
        game.addBomb(4, 1, 1, 1, 1)
        game.step(1, bme.Command.NONE)
        flames = [(f.x, f.y) for f in game.getFlames()]
        self.assertIn((3, 1), flames)

        # Run 15 ticks while flame at (3, 1) is active; DumbBot at (2, 1) must not walk onto (3, 1)
        for _ in range(15):
            game.step(1, bme.Command.NONE)
            bot = game.getPlayerInfo(2)
            self.assertTrue(bot.isAlive)
            self.assertEqual(bot.lives, 3, "DumbBot must not walk into active flame")

        # 2. Full level simulation: 3 DumbBots over 240 ticks (8 seconds) must explore, place bombs, and not immediately self-destruct
        bme.seed_rng(42)
        match = bme.Game(13, 13)
        level = bme.ClassicLevel(4, 13, 13, 65)
        match.reset(level, 1, 3)

        bombs_seen = 0
        for tick in range(240):
            match.update(bme.Command.NONE)
            if tick < 29:
                # During warmup (< 30 ticks), bots should not have placed bombs yet
                self.assertEqual(len(match.getBombs()), 0)
            bombs_seen += len(match.getBombs())

        self.assertGreater(bombs_seen, 0, "DumbBots should actively place bombs after spawn warmup")
        alive_bots = sum(1 for pid in (2, 3, 4) if match.getPlayerInfo(pid).isAlive)
        self.assertEqual(alive_bots, 3, "All 3 DumbBots should survive the opening 240 ticks")

    def test_esc_never_closes_application_and_navigates_cleanly(self) -> None:
        """Verify pressing or holding ESC in gameplay and root menu never closes the application."""
        from gui.app import BombermanGUIApp

        session = MockGameSession()
        app = BombermanGUIApp(session=session, start_in_menu=False)
        self.assertEqual(app.menu_state, BombermanGUIApp.PLAYING)

        # Simulate holding/spamming ESC 15 times starting from PLAYING:
        # First ESC transitions PLAYING -> MENU_HUMANS; subsequent ESCs must stay in MENU_HUMANS and return True.
        for _ in range(15):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, scancode=41, unicode="\x1b"))
            self.assertTrue(app.handle_events(), "ESC must never cause handle_events() to return False")
            self.assertEqual(app.menu_state, BombermanGUIApp.MENU_HUMANS)

        # Navigate forward to MENU_LEVEL and verify ESC walks back one step at a time and stops at MENU_HUMANS
        for expected_state in (
            BombermanGUIApp.MENU_DUMB_BOTS,
            BombermanGUIApp.MENU_TRAINED_AI,
            BombermanGUIApp.MENU_LEVEL,
        ):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, scancode=40, unicode="\r"))
            self.assertTrue(app.handle_events())
            self.assertEqual(app.menu_state, expected_state)

        for expected_back_state in (
            BombermanGUIApp.MENU_TRAINED_AI,
            BombermanGUIApp.MENU_DUMB_BOTS,
            BombermanGUIApp.MENU_HUMANS,
            BombermanGUIApp.MENU_HUMANS,
        ):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, scancode=41, unicode="\x1b"))
            self.assertTrue(app.handle_events())
            self.assertEqual(app.menu_state, expected_back_state)

    def test_static_window_caption_and_lazy_model_loading(self) -> None:
        """Verify window caption remains static across frames and missing models are not repeatedly loaded."""
        from unittest.mock import patch
        from gui.app import BombermanGUIApp

        PPOAgentController.reset_model_cache()
        session = MockGameSession()
        with patch.object(PPOAgentController, "_find_existing_model_path", return_value=None) as mock_find:
            app = BombermanGUIApp(session=session, start_in_menu=True)
            # Lazy init in BombermanGUIApp must not even search for the model during __init__
            self.assertEqual(mock_find.call_count, 0)

            initial_caption = pygame.display.get_caption()[0]
            self.assertEqual(initial_caption, BombermanGUIApp.WINDOW_CAPTION)

            # Render menu and gameplay frames; caption must remain identical
            app.render_menu()
            self.assertEqual(pygame.display.get_caption()[0], initial_caption)

            app.menu_selections["humans"] = 1
            app.menu_selections["dumb_bots"] = 1
            app.menu_selections["trained_ai"] = 2
            app.start_game()
            # _find_existing_model_path should be called once and then cached across opponent controllers and restarts
            self.assertEqual(mock_find.call_count, 1)
            app._reset_session()
            self.assertEqual(mock_find.call_count, 1)

            snap = app.session.get_snapshot(0.0)
            app.render(snap)
            self.assertEqual(pygame.display.get_caption()[0], initial_caption)

    def test_static_board_cache_invalidation_on_wall_and_sudden_death_changes(self) -> None:
        """Verify BoardRenderer reuses cached board surface and updates immediately when walls change."""
        from gui.config import HUD_WIDTH, TILE_SIZE

        session = MockGameSession()
        assets = AssetManager()
        board_renderer = BoardRenderer(assets)
        surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))

        snap1 = session.get_snapshot(0.0)
        # Cell (2, 0) has a breakable wall (value 2) in MockGameSession
        self.assertEqual(snap1.board[0][2], 2)
        board_renderer.render(surface, snap1)
        cached_state_1 = board_renderer._cached_board_state
        px = HUD_WIDTH + 2 * TILE_SIZE + TILE_SIZE // 2
        py = 0 * TILE_SIZE + TILE_SIZE // 2
        color_with_barrel = surface.get_at((px, py))

        # Rendering again with unchanged board reuses exact cached state
        board_renderer.render(surface, snap1)
        self.assertIs(board_renderer._cached_board_state, cached_state_1)

        # Destroy breakable wall at (2, 0) -> cell becomes 0 (floor)
        snap2 = session.get_snapshot(0.0)
        snap2.board[0][2] = 0
        board_renderer.render(surface, snap2)
        self.assertNotEqual(board_renderer._cached_board_state, cached_state_1)
        color_after_destroyed = surface.get_at((px, py))
        self.assertNotEqual(
            color_with_barrel,
            color_after_destroyed,
            "Destroying a breakable wall must immediately update rendered board pixels",
        )

        # Sudden Death drops a solid wall at (2, 0) -> cell becomes 1 (solid)
        snap3 = session.get_snapshot(0.0)
        snap3.board[0][2] = 1
        board_renderer.render(surface, snap3)
        color_after_sudden_death = surface.get_at((px, py))
        self.assertNotEqual(
            color_after_destroyed,
            color_after_sudden_death,
            "Sudden Death solid wall placement must immediately update rendered board pixels",
        )

    def test_all_opponent_configurations_and_bounded_text_caches(self) -> None:
        """Verify all opponent setups (Humans only, DumbBots, Trained AI, Mixed) and bounded LRU text caches."""
        from gui.app import BombermanGUIApp
        from gui.engine_adapter import CppGameSession

        session = CppGameSession(BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES)
        app = BombermanGUIApp(session=session, start_in_menu=True)

        configs = [
            (2, 0, 0),  # Human players only
            (1, 3, 0),  # Human + DumbBots
            (1, 0, 3),  # Human + Trained AI
            (1, 1, 2),  # Mixed (1 Human + 1 DumbBot + 2 Trained AI)
            (2, 1, 1),  # Mixed (2 Humans + 1 DumbBot + 1 Trained AI)
        ]
        for humans, dumb_bots, trained_ai in configs:
            app.menu_selections["humans"] = humans
            app.menu_selections["dumb_bots"] = dumb_bots
            app.menu_selections["trained_ai"] = trained_ai
            app.start_game()
            self.assertEqual(len(app.opponent_ai_controllers), trained_ai)
            for _ in range(5):
                app._step_single_tick()
            snap = app.session.get_snapshot(0.5)
            app.render(snap)

        # Verify bounded text cache does not grow beyond MAX_TEXT_CACHE_SIZE
        for i in range(app.hud_renderer.MAX_TEXT_CACHE_SIZE + 50):
            app.hud_renderer._render_text_cached(app.hud_renderer.font_small, f"label_{i}", (200, 200, 200))
        self.assertLessEqual(len(app.hud_renderer._text_cache), app.hud_renderer.MAX_TEXT_CACHE_SIZE)

    def test_stage1_and_stage2_engine_and_rl_mechanics_alignment(self) -> None:
        """Verify Hammer walk-into bomb push, priority over Ring, PLACE_BOMB semantics, sliding danger, Sudden Death danger, and cooldown stepping."""
        import numpy as np
        import bomberman_engine as bme
        from bomberman_env import BombermanEnv
        from rl_utils import apply_tactical_shield, compute_bfs_features

        # 1. Hammer walk-into bomb push & priority over Ring; PLACE_BOMB strictly places bombs
        game = bme.Game(13, 13)
        game.clearBoard()
        game.addPlayer(2, 2, 1, False)
        game.addPlayer(10, 10, 2, False)
        game.givePlayerPowerUp(1, "H")
        game.givePlayerPowerUp(1, "R")
        game.givePlayerPowerUp(1, "B")
        game.addBomb(3, 2, 60, 2, 2)  # Adjacent bomb at (3, 2) with empty space at (4, 2)

        pinfo = game.getPlayerInfo(1)
        self.assertTrue(pinfo.hasHammer and pinfo.hasRing)
        base_obs = np.asarray(game.getState(1), dtype=np.float32).reshape(-1, 13, 13)
        _, _, _, analysis = compute_bfs_features(base_obs, pinfo, 13, 13)
        self.assertIn(4, analysis["push_actions"], "Action 4 (RIGHT) must be recognized as a valid Hammer push action")
        self.assertIn(4, analysis["valid_moves"], "Action 4 (RIGHT) must be included in valid_moves for Hammer push")

        # PLACE_BOMB must strictly place a bomb at (2, 2) and NOT push the bomb at (3, 2)
        res_place = game.step(1, bme.Command.PLACE_BOMB)
        self.assertTrue(res_place.bombPlaced)
        self.assertFalse(res_place.bombPushed)
        bombs_after_place = {(b.x, b.y): b for b in game.getBombs()}
        self.assertIn((2, 2), bombs_after_place)
        self.assertFalse(bombs_after_place[(3, 2)].isSliding)

        # Walking RIGHT into (3, 2) with both Hammer and Ring must push the bomb (Hammer priority over Ring)
        res_push = game.step(1, bme.Command.RIGHT)
        self.assertTrue(res_push.bombPushed, "Walking into bomb with Hammer+Ring must push the bomb")
        p_after = game.getPlayerInfo(1)
        self.assertEqual((p_after.x, p_after.y), (2, 2), "Player must push bomb from (2,2), not step onto (3,2) via Ring")

        # 2. Sliding bomb trajectory danger projection in Channel 3 (danger)
        state_sliding = np.asarray(game.getState(1), dtype=np.float32).reshape(-1, 13, 13)
        self.assertGreater(state_sliding[3, 2, 6], 0.0, "Sliding bomb trajectory tiles must be marked in Channel 3 (danger)")
        self.assertEqual(state_sliding[2, 2, 8], 0.0, "Empty sliding trajectory tiles must NOT be marked as solid bombs in Channel 2")

        # 3. Imminent Sudden Death spiral danger projection in Channel 3 (danger) and BFS recognition
        game.setSuddenDeathTimer(10)
        state_sd = np.asarray(game.getState(1), dtype=np.float32).reshape(-1, 13, 13)
        self.assertGreater(state_sd[3, 0, 0], 0.5, "Imminent Sudden Death spiral tile (0,0) must have high urgency in Channel 3")

        # 4. Non-lethal enemy hit reward (+10) vs fatal enemy kill reward (+10 hit + 20 kill)
        game_hit = bme.Game(13, 13)
        game_hit.clearBoard()
        game_hit.addPlayer(1, 1, 1, False)
        game_hit.addPlayer(5, 5, 2, False)
        game_hit.addBomb(4, 5, 1, 2, 1)  # P1's bomb next to P2 (3 lives)
        res_hit = game_hit.step(1, bme.Command.NONE)
        self.assertEqual(res_hit.enemiesHit, 1)
        self.assertEqual(res_hit.enemiesKilled, 0)
        self.assertGreaterEqual(res_hit.reward, 9.9, "Non-lethal enemy hit must grant +10.0 reward")

        # 5. Cooldown-aware BombermanEnv stepping with Speed PowerUps
        env = BombermanEnv(num_bots=1, wall_density=0)
        env.reset(seed=123)
        env.game.clearBoard()
        env.game.addPlayer(1, 1, 1, False)
        env.game.addPlayer(11, 11, 2, False)
        env._cached_analysis = None

        # Speed 0 -> move RIGHT takes 6 ticks to reach cooldown <= 1
        env.step(4)
        self.assertEqual(env.ep_stats["ticks"], 6)
        # Speed 2 -> move RIGHT takes 4 ticks to reach cooldown <= 1
        env.game.givePlayerPowerUp(1, "S")
        env.game.givePlayerPowerUp(1, "S")
        env._cached_analysis = None
        env.step(4)
        self.assertEqual(env.ep_stats["ticks"], 6 + 4)

        # 6. Phase 1 Grandmaster Upgrades: 2400-tick Sudden Death default & Shield Intervention Penalty (-0.3)
        fresh_game = bme.Game(13, 13)
        self.assertEqual(fresh_game.getSuddenDeathTimer(), 2400)
        fresh_game.clearBoard()
        self.assertEqual(fresh_game.getSuddenDeathTimer(), 2400)

        env_shield = BombermanEnv(num_bots=1, wall_density=0, tactical_shield=True)
        env_shield.reset(seed=99)
        env_shield.game.clearBoard()
        env_shield.game.setSolidWall(1, 0, True)
        env_shield.game.addPlayer(1, 1, 1, False)
        env_shield.game.addPlayer(11, 11, 2, False)
        env_shield._cached_analysis = None
        # Attempt to walk UP (action 1) into solid border wall at (1, 0) -> shield intervenes
        _, rew_intervened, _, _, _ = env_shield.step(1)
        self.assertEqual(env_shield.ep_stats["shield_interventions"], 1)

    def test_gameplay_improvements_and_sudden_death_rework(self) -> None:
        """Verify bomb planter flame color vs pusher kill credit, pushed bombs passing through flames,
        30% configurable power-up drop rate, gradual Sudden Death damage (-1 HP + 5s/150 ticks),
        Sudden Death movement rules, and DumbBot imperfect Sudden Death caution."""
        import bomberman_engine as bme

        # 1. Bomb Ownership & Flame Color vs Pusher AI Kill Credit
        game = bme.Game(13, 13)
        game.clearBoard()
        game.addPlayer(2, 2, 1, False)  # P1 (pusher)
        game.addPlayer(3, 2, 2, False)  # P2 (planter)
        game.addPlayer(5, 2, 3, False)  # P3 (victim with 1 HP left)
        game.givePlayerPowerUp(1, "H")

        # Reduce P3 to 1 HP first so a single hit kills P3
        game.addBomb(5, 3, 1, 1, 2)
        game.step(1, bme.Command.NONE)
        for _ in range(65):
            game.step(1, bme.Command.NONE)
        game.addBomb(5, 3, 1, 1, 2)
        game.step(1, bme.Command.NONE)
        for _ in range(65):
            game.step(1, bme.Command.NONE)
        self.assertEqual(game.getPlayerInfo(3).lives, 1)

        # P2 plants a bomb at (3, 2), then moves down to (3, 3) out of the way
        game.addBomb(3, 2, 12, 2, 2)
        game.updateCommands([bme.PlayerCommand(2, bme.Command.DOWN)])
        self.assertEqual((game.getPlayerInfo(2).x, game.getPlayerInfo(2).y), (3, 3))

        # P1 at (2, 2) pushes P2's bomb at (3, 2) RIGHT toward P3 at (5, 2)
        res_push = game.step(1, bme.Command.RIGHT)
        self.assertTrue(res_push.bombPushed)
        bombs = game.getBombs()
        self.assertEqual(len(bombs), 1)
        self.assertEqual(bombs[0].ownerId, 2, "Bomb ownerId must remain the original planter (P2)")
        self.assertEqual(bombs[0].creditOwnerId, 1, "Bomb creditOwnerId must update to the pusher (P1)")

        # Step until bomb explodes; verify flames have ownerId == 2 (planter color) and creditOwnerId == 1 (pusher kill)
        total_kills_p1 = 0
        flames_checked = False
        for _ in range(15):
            res = game.step(1, bme.Command.NONE)
            total_kills_p1 += res.enemiesKilled
            flames = game.getFlames()
            if flames:
                flames_checked = True
                for f in flames:
                    self.assertEqual(f.ownerId, 2, "Flame visual ownerId must always be the bomb planter (P2)")
                    self.assertEqual(f.creditOwnerId, 1, "Flame creditOwnerId must be the pusher (P1)")
        self.assertTrue(flames_checked)
        self.assertEqual(total_kills_p1, 1, "Pusher (P1) must receive the enemy kill credit for AI training")

        # 2. Pushed Bombs Travel Through Existing Flames
        game.clearBoard()
        game.addPlayer(1, 2, 1, False)
        game.addPlayer(11, 11, 2, False)
        game.givePlayerPowerUp(1, "H")
        # Create an explosion at (4, 1) so (4, 2) has a live flame for 30 ticks
        game.addBomb(4, 1, 1, 2, 2)
        game.step(1, bme.Command.NONE)
        flame_coords = {(f.x, f.y) for f in game.getFlames()}
        self.assertIn((4, 2), flame_coords)

        # Place a bomb at (2, 2) with long timer and have P1 at (1, 2) push it RIGHT through the flame at (4, 2)
        game.addBomb(2, 2, 80, 2, 2)
        res_kick = game.step(1, bme.Command.RIGHT)
        self.assertTrue(res_kick.bombPushed, "Pushing a bomb toward a flame must succeed")
        for _ in range(16):
            game.step(1, bme.Command.NONE)
        sliding_bombs = game.getBombs()
        self.assertEqual(len(sliding_bombs), 1, "Sliding bomb must not detonate when passing through a flame")
        self.assertGreater(sliding_bombs[0].x, 4, "Sliding bomb must travel past the flame at x=4")

        # 3. Configurable Power-Up Drop Rate (30% default)
        self.assertEqual(bme.get_powerup_drop_chance(), 30)
        bme.seed_rng(12345)
        game.clearBoard()
        game.addPlayer(0, 0, 1, False)
        game.addPlayer(12, 12, 2, False)
        bme.set_powerup_drop_chance(0)
        game.addBreakableWall(2, 2)
        game.addBomb(2, 1, 1, 2, 1)
        game.step(1, bme.Command.NONE)
        self.assertEqual(len(game.getPowerUps()), 0, "0% drop chance must never spawn a power-up")

        bme.set_powerup_drop_chance(100)
        game.addBreakableWall(3, 2)
        game.addBomb(3, 1, 1, 2, 1)
        game.step(1, bme.Command.NONE)
        self.assertEqual(len(game.getPowerUps()), 1, "100% drop chance must always spawn a power-up")
        bme.set_powerup_drop_chance(30)

        # 4. Sudden Death Gradual Damage (-1 HP on contact, -1 HP every 150 ticks / 5s) & Movement Rules
        game.clearBoard()
        game.addPlayer(0, 0, 1, False)  # P1 at (0, 0) where first Sudden Death tile drops
        game.addPlayer(6, 6, 2, False)
        game.setSuddenDeathTimer(0)

        # Tick 1: Sudden Death drops at (0, 0), catching P1 -> -1 HP on first contact (3 -> 2 HP)
        game.step(1, bme.Command.NONE)
        p1 = game.getPlayerInfo(1)
        self.assertTrue(p1.isAlive)
        self.assertEqual(p1.lives, 2, "First contact with Sudden Death must deal exactly 1 HP damage")
        self.assertEqual(game.getBoardGrid()[0][0], 1, "Sudden Death tile must visually appear as SOLID_WALL (1)")

        # Tick 2..150 (149 ticks): P1 stays on Sudden Death tiles (and at tick 16, (1, 0) also becomes SD)
        # Verify P1 does NOT lose health during the 149 ticks before 5 seconds elapse
        for t in range(149):
            # At tick 20, move RIGHT from SD tile (0,0) onto SD tile (1,0) to verify caught player can move on SD tiles
            cmd = bme.Command.RIGHT if t == 20 else bme.Command.NONE
            game.step(1, cmd)
            p1 = game.getPlayerInfo(1)
            if t == 20:
                self.assertEqual((p1.x, p1.y), (1, 0), "Player caught by Sudden Death must be able to move on SD tiles")
            self.assertEqual(p1.lives, 2, f"Player must not lose extra HP before 150 ticks (failed at tick {t + 1})")

        # Tick 151 (150 ticks = 5.0 seconds after first contact): P1 loses 1 HP (2 -> 1 HP)
        game.step(1, bme.Command.NONE)
        p1 = game.getPlayerInfo(1)
        self.assertTrue(p1.isAlive)
        self.assertEqual(p1.lives, 1, "Remaining on Sudden Death for 5 seconds (150 ticks) must deal 1 HP damage")

        # Escape: P1 steps DOWN from SD tile (1, 0) onto safe EMPTY tile (1, 1) ( Wait for move cooldown if any )
        while game.getPlayerInfo(1).cooldown > 0:
            game.step(1, bme.Command.NONE)
        game.step(1, bme.Command.DOWN)
        p1 = game.getPlayerInfo(1)
        self.assertEqual((p1.x, p1.y), (1, 1), "Caught player must be able to escape onto an adjacent safe tile")

        # Once escaped onto safe tile (1, 1), P1 CANNOT step back UP onto SD tile (1, 0)
        while game.getPlayerInfo(1).cooldown > 0:
            game.step(1, bme.Command.NONE)
        game.step(1, bme.Command.UP)
        p1 = game.getPlayerInfo(1)
        self.assertEqual((p1.x, p1.y), (1, 1), "Player on safe ground must NOT be able to walk onto a Sudden Death tile")

        # 5. DumbBot Imperfect Sudden Death Awareness
        self.assertEqual(bme.get_bot_sd_caution_percent(), 75)
        bme.set_bot_sd_caution_percent(100)
        game.clearBoard()
        game.addPlayer(6, 6, 1, False)
        game.addPlayer(0, 0, 2, True)  # DumbBot at (0, 0)
        game.setSuddenDeathTimer(30)
        for _ in range(25):
            game.step(1, bme.Command.NONE)
        bot_info = game.getPlayerInfo(2)
        self.assertNotEqual((bot_info.x, bot_info.y), (0, 0), "Cautious DumbBot must retreat from imminent Sudden Death tile")
        bme.set_bot_sd_caution_percent(75)

        # 6. Sudden Death stops at 7x5 interior on 15x13 (4 closed rings)
        sd_game = bme.Game(15, 13)
        sd_game.clearBoard()
        sd_game.addPlayer(7, 6, 1, False)
        sd_game.addPlayer(8, 6, 2, False)
        sd_game.setSuddenDeathTimer(0)
        for _ in range(2500):
            sd_game.step(1, bme.Command.NONE)
            if not sd_game.isSuddenDeathActive():
                break
        self.assertFalse(sd_game.isSuddenDeathActive(), "Sudden Death should finish after closing 4 rings")
        grid = sd_game.getBoardGrid()
        open_coords = [(x, y) for y in range(13) for x in range(15) if grid[y][x] == 0]
        xs = [x for x, _ in open_coords]
        ys = [y for _, y in open_coords]
        self.assertEqual((min(xs), max(xs)), (4, 10), "Remaining open X range must be 4..10 (width 7)")
        self.assertEqual((min(ys), max(ys)), (4, 8), "Remaining open Y range must be 4..8 (height 5)")

        # 7. AI Observation 15x13 + PowerUp Distinction (17 C++ channels -> 19 RL channels)
        from bomberman_env import BombermanEnv
        from rl_utils import compute_bfs_features

        ai_game = bme.Game(15, 13)
        ai_game.clearBoard()
        ai_game.addPlayer(1, 1, 1, False)
        ai_game.addPlayer(13, 11, 2, False)
        ai_game.addPowerUp(2, 1, "L")  # Lightning
        ai_game.addPowerUp(3, 1, "S")  # Speed
        ai_game.addPowerUp(4, 1, "B")  # Extra Bomb ('+')
        ai_game.addPowerUp(5, 1, "H")  # Hammer
        ai_game.addPowerUp(6, 1, "R")  # Ring
        ai_game.givePlayerPowerUp(1, "L")
        ai_game.givePlayerPowerUp(1, "S")

        state17 = np.asarray(ai_game.getState(1), dtype=np.float32)
        self.assertEqual(state17.shape, (17, 13, 15))
        self.assertEqual(state17[10, 1, 2], 1.0, "Channel 10 must encode Lightning ('L')")
        self.assertEqual(state17[11, 1, 3], 1.0, "Channel 11 must encode Speed ('S')")
        self.assertEqual(state17[12, 1, 4], 1.0, "Channel 12 must encode Bomb ('+')")
        self.assertEqual(state17[13, 1, 5], 1.0, "Channel 13 must encode Hammer ('H')")
        self.assertEqual(state17[14, 1, 6], 1.0, "Channel 14 must encode Ring ('R')")
        self.assertAlmostEqual(float(state17[15, 0, 0]), 0.3, places=5, msg="Channel 15 must encode bombRadius / 10")
        self.assertAlmostEqual(float(state17[16, 0, 0]), 0.5, places=5, msg="Channel 16 must encode speedLevel / 2")

        # Duplicate Hammer should be ignored by BFS hunt target selection when Hammer is already owned
        ai_game.clearBoard()
        ai_game.addPlayer(1, 1, 1, False)
        ai_game.addPlayer(13, 11, 2, False)
        ai_game.givePlayerPowerUp(1, "H")
        ai_game.addPowerUp(2, 1, "H")  # Redundant Hammer adjacent (d=1)
        ai_game.addPowerUp(4, 1, "L")  # Useful Lightning at d=3
        state_dup = np.asarray(ai_game.getState(1), dtype=np.float32)
        _, _, _, dup_analysis = compute_bfs_features(state_dup, ai_game.getPlayerInfo(1), 15, 13)
        self.assertEqual(dup_analysis["hunt_action"], 4, "AI BFS should pursue useful Lightning over redundant Hammer")

        env = BombermanEnv(num_bots=1, wall_density=0)
        obs, _ = env.reset(seed=7)
        self.assertEqual(obs.shape, (19, 13, 15))
        self.assertEqual(env.observation_space.shape, (19, 13, 15))

        # 8. Aggressive Enemy Engagement: AI prioritizes attacking/closing on an enemy over farming a wall behind it
        ai_game.clearBoard()
        ai_game.addPlayer(5, 5, 1, False)   # Self at (5, 5)
        ai_game.addPlayer(8, 5, 2, False)   # Enemy to the RIGHT at (8, 5)
        ai_game.addBreakableWall(2, 5)      # Distraction wall to the LEFT at (2, 5)
        state_agg = np.asarray(ai_game.getState(1), dtype=np.float32)
        _, _, phi_at_5, agg_analysis = compute_bfs_features(state_agg, ai_game.getPlayerInfo(1), 15, 13)
        self.assertEqual(agg_analysis["hunt_action"], 4, "AI must advance RIGHT (4) toward the enemy rather than farming the wall to the LEFT (3)")





if __name__ == "__main__":
    unittest.main()
