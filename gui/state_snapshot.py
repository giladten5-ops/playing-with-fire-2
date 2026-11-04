import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional

# --- Dataclasses: מבני נתונים פשוטים שמייצגים כל אובייקט במסך ---

@dataclass
class PlayerSnapshot:
    id: int
    grid_x: int
    grid_y: int
    render_x: float  # קואורדינטה חלקה לציור (עשרונית)
    render_y: float
    facing_dx: int
    facing_dy: int
    lives: int
    max_bombs: int
    avail_bombs: int
    bomb_radius: int
    speed_level: int
    invincibility_timer: int
    has_hammer: bool
    has_ring: bool
    is_bot: bool
    is_alive: bool

@dataclass
class BombSnapshot:
    grid_x: int
    grid_y: int
    render_x: float
    render_y: float
    timer: int
    radius: int
    owner_id: int
    is_sliding: bool

@dataclass
class FlameSnapshot:
    grid_x: int
    grid_y: int
    timer: int
    owner_id: int

@dataclass
class PowerUpSnapshot:
    grid_x: int
    grid_y: int
    type_char: str  # 'H', 'R', 'S', 'L', '+'

@dataclass
class AIDebugSnapshot:
    # נמלא את זה בשלבים מאוחרים יותר כשנחבר את המודל עצמו
    action_probs: List[float]
    value: float
    reach_map: np.ndarray
    bomb_map: np.ndarray

@dataclass
class GameSnapshot:
    board: List[List[int]]  # 0 = Empty, 1 = Solid, 2 = Breakable
    players: Dict[int, PlayerSnapshot]
    bombs: List[BombSnapshot]
    flames: List[FlameSnapshot]
    powerups: List[PowerUpSnapshot]
    sd_timer: int
    sd_active: bool
    ai_debug: Optional[AIDebugSnapshot] = None


class SnapshotBuilder:
    """
    אחראי לשלוף את המידע ממנוע ה-C++ (bme.Game) ולהכין אותו לציור,
    תוך הפעלת אינטרפולציה מתמטית לתנועה חלקה.
    """
    def __init__(self, width: int = 13, height: int = 13):
        self.width = width
        self.height = height

    def build_snapshot(self, game, alpha: float) -> GameSnapshot:
        """
        alpha (0.0 to 1.0) = כמה זמן עבר מאז הטיק האחרון של המנוע (לצורך החלקת תנועה).
        """
        # 1. חילוץ מבנה הלוח מתוך ערוצים 0 ו-1 של ה-State
        raw_state = game.getState(1) 
        state_np = np.array(raw_state, dtype=np.float32).reshape(-1, self.height, self.width)
        
        board = [[0 for _ in range(self.width)] for _ in range(self.height)]
        for y in range(self.height):
            for x in range(self.width):
                if state_np[0, y, x] > 0:
                    board[y][x] = 1  # קיר קבוע
                elif state_np[1, y, x] > 0:
                    board[y][x] = 2  # קיר לבנים

        # 2. חילוץ שחקנים ואינטרפולציית תנועה
        players = {}
        for pid in range(1, 5): # תומך בעד 4 שחקנים (שחקן 1 + 3 בוטים)
            pinfo = game.getPlayerInfo(pid)
            if not pinfo.isAlive:
                continue
            
            # חישוב התנועה החלקה:
            # ה-Cooldown המקסימלי תלוי ברמת המהירות של השחקן (4, 2 או 0)
            max_cd = max(1, 4 - (pinfo.speedLevel * 2))
            render_x, render_y = float(pinfo.x), float(pinfo.y)
            
            # אם השחקן נמצא ב-Cooldown, זה אומר שהוא עדיין "בדרך" למשבצת הנוכחית
            if pinfo.cooldown > 0:
                # Progress: כמה אחוז מהתנועה כבר הושלמה
                progress = (max_cd - pinfo.cooldown + alpha) / max_cd
                progress = max(0.0, min(progress, 1.0)) # חוסם בין 0 ל-1
                
                # הולכים אחורה לכיוון שממנו הוא בא, ומתקדמים לפי האחוז
                render_x = pinfo.x - pinfo.facingDx * (1.0 - progress)
                render_y = pinfo.y - pinfo.facingDy * (1.0 - progress)

            players[pid] = PlayerSnapshot(
                id=pinfo.id,
                grid_x=pinfo.x, grid_y=pinfo.y,
                render_x=render_x, render_y=render_y,
                facing_dx=pinfo.facingDx, facing_dy=pinfo.facingDy,
                lives=pinfo.lives,
                max_bombs=pinfo.maxBombs, avail_bombs=pinfo.availBombs,
                bomb_radius=pinfo.bombRadius, speed_level=pinfo.speedLevel,
                invincibility_timer=pinfo.invincibilityTimer,
                has_hammer=pinfo.hasHammer, has_ring=pinfo.hasRing,
                is_bot=pinfo.isBot, is_alive=pinfo.isAlive
            )

        # 3. חילוץ פצצות (בהמשך נוכל להחליק גם את ההחלקה של הפצצה)
        bombs = []
        for binfo in game.getBombs():
            bombs.append(BombSnapshot(
                grid_x=binfo.x, grid_y=binfo.y,
                render_x=float(binfo.x), render_y=float(binfo.y),
                timer=binfo.timer, radius=binfo.radius,
                owner_id=binfo.ownerId, is_sliding=binfo.isSliding
            ))

        # 4. חילוץ להבות ובונוסים ישירות מ-C++
        flames = [FlameSnapshot(f.x, f.y, f.timer, f.ownerId) for f in game.getFlames()]
        powerups = [PowerUpSnapshot(pu.x, pu.y, pu.type) for pu in game.getPowerUps()]

        return GameSnapshot(
            board=board,
            players=players,
            bombs=bombs,
            flames=flames,
            powerups=powerups,
            sd_timer=game.getSuddenDeathTimer(),
            sd_active=game.isSuddenDeathActive(),
            ai_debug=None
        )