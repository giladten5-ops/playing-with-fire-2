#include "../../include/entities/DumbBot.h"
#include "../../include/core/World.h"
#include "../../include/entities/Bomb.h"
#include <cstdlib>
#include <vector>
#include <queue>
#include <cmath>
#include <algorithm>

namespace {
Command getOppositeCommand(Command cmd) {
    switch (cmd) {
        case Command::UP:    return Command::DOWN;
        case Command::DOWN:  return Command::UP;
        case Command::LEFT:  return Command::RIGHT;
        case Command::RIGHT: return Command::LEFT;
        default:             return Command::NONE;
    }
}
} // namespace

int DumbBot::s_sdCautionPercent = DumbBot::DEFAULT_SD_CAUTION_PERCENT;

void DumbBot::setSuddenDeathCautionPercent(int percent) {
    s_sdCautionPercent = std::clamp(percent, 0, 100);
}

int DumbBot::getSuddenDeathCautionPercent() {
    return s_sdCautionPercent;
}

DumbBot::DumbBot(int startX, int startY, int id)
    : Player(startX, startY, id) {
    int offset = ((id % 3) - 1) * 6;
    m_sdCautionPercent = std::clamp(s_sdCautionPercent + offset, 0, 100);
    m_sdLookaheadTicks = 45 + (id % 3) * 15;
    m_sdAwareThisWindow = (std::rand() % 100) < m_sdCautionPercent;
}

bool DumbBot::isBot() const { return true; }
std::string DumbBot::getDisplayName() const { return "BOT" + std::to_string(getId()); }

char DumbBot::getDisplayChar() const {
    if (Player::getDisplayChar() == ' ') return ' ';
    return 'D';
}

bool DumbBot::canStepOn(int x, int y, const World& world) const {
    if (!world.isPositionValid(x, y)) return false;
    CellType ct = world.getBoard().getCellType(x, y);
    if (ct != CellType::EMPTY) {
        if (!(world.isSuddenDeathTile(getX(), getY()) && world.isSuddenDeathTile(x, y))) {
            return false;
        }
    }

    for (const auto* e : world.getEntitiesAt(x, y)) {
        if (!e->isAlive()) continue;
        if (e->getType() == EntityType::FLAME) {
            return false;
        }
        if (e->isSolid()) {
            if (e->getType() == EntityType::BOMB) {
                const auto* bomb = static_cast<const Bomb*>(e);
                if (!hasRing() || hasHammer() || bomb->getTimer() <= 20) {
                    return false;
                }
            } else {
                return false;
            }
        }
    }
    return true;
}

bool DumbBot::hasClearBlastPath(int bx, int by, int tx, int ty, const World& world) const {
    int dx = (tx > bx) ? 1 : ((tx < bx) ? -1 : 0);
    int dy = (ty > by) ? 1 : ((ty < by) ? -1 : 0);

    int cx = bx + dx;
    int cy = by + dy;
    while (cx != tx || cy != ty) {
        if (world.getBoard().getCellType(cx, cy) != CellType::EMPTY) return false;
        auto entities = world.getEntitiesAt(cx, cy);
        for (const auto* e : entities) {
            if (e->isAlive() && e->stopsExplosion() && e->getType() != EntityType::BOMB) {
                return false;
            }
        }
        cx += dx;
        cy += dy;
    }
    return true;
}

int DumbBot::getTileTimeToExplode(int x, int y, const World& world, int extraBx, int extraBy, int extraRadius) const {
    if (!world.isPositionValid(x, y)) return 0;

    int sdMinTimer = 9999;
    if (world.isSuddenDeathTile(x, y)) {
        sdMinTimer = std::max(35, getSuddenDeathTimer());
    } else {
        int ticksUntilDrop = world.getSuddenDeathTicksUntilDrop(x, y);
        if (ticksUntilDrop < 9999) {
            if (m_sdAwareThisWindow && ticksUntilDrop <= m_sdLookaheadTicks) {
                sdMinTimer = std::max(1, ticksUntilDrop);
            } else if (!m_sdAwareThisWindow && ticksUntilDrop <= 6) {
                sdMinTimer = std::max(1, ticksUntilDrop);
            }
        }
    }

    struct BombData {
        int x;
        int y;
        int radius;
        int timer;
    };
    std::vector<BombData> bombs;

    auto collectFromList = [&](const std::vector<std::unique_ptr<Entity>>& list) {
        for (const auto& entity : list) {
            if (!entity->isAlive()) continue;
            if (entity->getType() == EntityType::FLAME) {
                if (entity->getX() == x && entity->getY() == y) {
                    return true;
                }
            } else if (entity->getType() == EntityType::BOMB) {
                const auto* b = static_cast<const Bomb*>(entity.get());
                bombs.push_back({b->getX(), b->getY(), b->getRadius(), b->getTimer()});
                if (b->isSliding()) {
                    int sdx = b->getSlideDx();
                    int sdy = b->getSlideDy();
                    int sx = b->getX();
                    int sy = b->getY();
                    for (int s = 1; s <= 4; ++s) {
                        int nx = sx + sdx;
                        int ny = sy + sdy;
                        if (!Bomb::canSlideTo(world, nx, ny)) break;
                        sx = nx;
                        sy = ny;
                        bombs.push_back({sx, sy, b->getRadius(), std::max(1, b->getTimer())});
                    }
                }
            }
        }
        return false;
    };

    if (collectFromList(world.getEntities()) || collectFromList(world.getSpawnQueue())) {
        return 0;
    }

    if (extraBx >= 0 && extraBy >= 0) {
        bombs.push_back({extraBx, extraBy, extraRadius, DEFAULT_BOMB_TIMER});
    }

    if (bombs.empty()) return sdMinTimer;

    // Propagate chain-reaction timers across bombs in line-of-fire
    bool changed = true;
    int maxIter = static_cast<int>(bombs.size()) + 1;
    while (changed && maxIter-- > 0) {
        changed = false;
        for (size_t i = 0; i < bombs.size(); ++i) {
            for (size_t j = 0; j < bombs.size(); ++j) {
                if (i == j) continue;
                bool alignedX = (bombs[i].x == bombs[j].x && std::abs(bombs[i].y - bombs[j].y) <= bombs[i].radius);
                bool alignedY = (bombs[i].y == bombs[j].y && std::abs(bombs[i].x - bombs[j].x) <= bombs[i].radius);
                if ((alignedX || alignedY) && bombs[i].timer < bombs[j].timer) {
                    if (hasClearBlastPath(bombs[i].x, bombs[i].y, bombs[j].x, bombs[j].y, world)) {
                        bombs[j].timer = bombs[i].timer;
                        changed = true;
                    }
                }
            }
        }
    }

    int minTimer = sdMinTimer;
    for (const auto& b : bombs) {
        if (b.x == x && std::abs(b.y - y) <= b.radius) {
            if (hasClearBlastPath(b.x, b.y, x, y, world)) {
                minTimer = std::min(minTimer, b.timer);
            }
        }
        if (b.y == y && std::abs(b.x - x) <= b.radius) {
            if (hasClearBlastPath(b.x, b.y, x, y, world)) {
                minTimer = std::min(minTimer, b.timer);
            }
        }
    }
    return minTimer;
}

bool DumbBot::isTileDangerous(int x, int y, const World& world) const {
    return getTileTimeToExplode(x, y, world) < 9999;
}

bool DumbBot::isTileDangerousWithExtraBomb(int x, int y, const World& world, int extraBx, int extraBy, int extraRadius) const {
    return getTileTimeToExplode(x, y, world, extraBx, extraBy, extraRadius) < 9999;
}

Command DumbBot::findEscapeDirection(const World& world, int extraBx, int extraBy, int extraRadius) const {
    int width = world.getBoard().getWidth();
    int height = world.getBoard().getHeight();
    int startX = getX();
    int startY = getY();
    int moveCd = getMoveCooldownMax();

    struct StepNode {
        int x;
        int y;
        Command firstCommand;
        int dist;
    };

    std::vector<std::vector<bool>> visited(width, std::vector<bool>(height, false));
    std::queue<StepNode> q;
    visited[startX][startY] = true;

    struct DirInfo { int dx; int dy; Command cmd; };
    const DirInfo baseDirs[4] = {
        {0, -1, Command::UP},
        {0, 1, Command::DOWN},
        {-1, 0, Command::LEFT},
        {1, 0, Command::RIGHT}
    };

    // Order directions so m_currentDir is evaluated first (committing to active escape path),
    // and the opposite direction is evaluated last (avoiding oscillation).
    std::vector<DirInfo> orderedDirs;
    orderedDirs.reserve(4);
    Command oppositeDir = getOppositeCommand(m_currentDir);
    for (const auto& d : baseDirs) {
        if (d.cmd == m_currentDir) orderedDirs.push_back(d);
    }
    for (const auto& d : baseDirs) {
        if (d.cmd != m_currentDir && d.cmd != oppositeDir) orderedDirs.push_back(d);
    }
    for (const auto& d : baseDirs) {
        if (d.cmd == oppositeDir && d.cmd != m_currentDir) orderedDirs.push_back(d);
    }

    const int maxEscapeSteps = (extraBx >= 0) ? 3 : 6;

    for (const auto& d : orderedDirs) {
        int nx = startX + d.dx;
        int ny = startY + d.dy;
        if (canStepOn(nx, ny, world)) {
            int tte = getTileTimeToExplode(nx, ny, world, extraBx, extraBy, extraRadius);
            if (tte == 9999) {
                return d.cmd;
            }
            if (tte > moveCd + 3) {
                visited[nx][ny] = true;
                q.push({nx, ny, d.cmd, 1});
            }
        }
    }

    while (!q.empty()) {
        StepNode curr = q.front();
        q.pop();

        if (curr.dist >= maxEscapeSteps) continue;

        for (const auto& d : orderedDirs) {
            int nx = curr.x + d.dx;
            int ny = curr.y + d.dy;
            if (world.isPositionValid(nx, ny) && !visited[nx][ny] && canStepOn(nx, ny, world)) {
                int nextDist = curr.dist + 1;
                int tte = getTileTimeToExplode(nx, ny, world, extraBx, extraBy, extraRadius);
                visited[nx][ny] = true;
                if (tte == 9999) {
                    return curr.firstCommand;
                }
                if (tte > nextDist * moveCd + 3) {
                    q.push({nx, ny, curr.firstCommand, nextDist});
                }
            }
        }
    }

    return Command::NONE;
}

Command DumbBot::findExplorationDirection(const World& world) const {
    int cx = getX();
    int cy = getY();

    struct DirInfo { int dx; int dy; Command cmd; };
    const DirInfo baseDirs[4] = {
        {0, -1, Command::UP},
        {0, 1, Command::DOWN},
        {-1, 0, Command::LEFT},
        {1, 0, Command::RIGHT}
    };

    Command oppositeDir = getOppositeCommand(m_currentDir);
    std::vector<Command> safeMoves;
    std::vector<Command> forwardSafeMoves;

    for (const auto& d : baseDirs) {
        int nx = cx + d.dx;
        int ny = cy + d.dy;
        if (canStepOn(nx, ny, world) && !isTileDangerous(nx, ny, world)) {
            // Immediate priority: step onto adjacent power-up
            for (const auto* e : world.getEntitiesAt(nx, ny)) {
                if (e->isAlive() && e->getType() == EntityType::POWER_UP) {
                    return d.cmd;
                }
            }
            safeMoves.push_back(d.cmd);
            if (d.cmd != oppositeDir) {
                forwardSafeMoves.push_back(d.cmd);
            }
        }
    }

    if (safeMoves.empty()) {
        return Command::NONE;
    }

    // If this bot already has an active bomb on the board and is standing on a safe tile,
    // wait calmly for the bomb to detonate (only stepping 1 tile further if directly adjacent to a blast line).
    if (world.countBombsForOwner(getId()) > 0) {
        auto countDangerousNeighbors = [&](int tx, int ty) {
            int count = 0;
            for (const auto& d : baseDirs) {
                int wx = tx + d.dx;
                int wy = ty + d.dy;
                if (world.isPositionValid(wx, wy) && isTileDangerous(wx, wy, world)) {
                    count++;
                }
            }
            return count;
        };

        int curDangerAdj = countDangerousNeighbors(cx, cy);
        if (curDangerAdj > 0) {
            for (const auto& d : baseDirs) {
                int nx = cx + d.dx;
                int ny = cy + d.dy;
                if (canStepOn(nx, ny, world) && !isTileDangerous(nx, ny, world)) {
                    if (countDangerousNeighbors(nx, ny) == 0) {
                        return d.cmd;
                    }
                }
            }
        }
        return Command::NONE;
    }

    // Run a safe-BFS (depth <= 10) to locate the nearest reachable power-up, breakable wall, or open space
    int width = world.getBoard().getWidth();
    int height = world.getBoard().getHeight();
    std::vector<std::vector<bool>> visited(width, std::vector<bool>(height, false));
    struct Node { int x; int y; Command firstCmd; int dist; };
    std::queue<Node> q;
    visited[cx][cy] = true;
    int reachableSafeCount = 1;

    std::vector<DirInfo> orderedDirs;
    for (const auto& d : baseDirs) {
        if (d.cmd == m_currentDir) orderedDirs.push_back(d);
    }
    for (const auto& d : baseDirs) {
        if (d.cmd != m_currentDir && d.cmd != oppositeDir) orderedDirs.push_back(d);
    }
    for (const auto& d : baseDirs) {
        if (d.cmd == oppositeDir && d.cmd != m_currentDir) orderedDirs.push_back(d);
    }

    for (const auto& d : orderedDirs) {
        int nx = cx + d.dx;
        int ny = cy + d.dy;
        if (canStepOn(nx, ny, world) && !isTileDangerous(nx, ny, world)) {
            visited[nx][ny] = true;
            reachableSafeCount++;
            q.push({nx, ny, d.cmd, 1});
        }
    }

    Command wallTargetCmd = Command::NONE;
    Command enemyTargetCmd = Command::NONE;
    while (!q.empty()) {
        Node curr = q.front();
        q.pop();

        for (const auto* e : world.getEntitiesAt(curr.x, curr.y)) {
            if (e->isAlive() && e->getType() == EntityType::POWER_UP) {
                return curr.firstCmd;
            }
        }

        if (enemyTargetCmd == Command::NONE) {
            for (const auto& entity : world.getEntities()) {
                if (entity->isAlive() && entity->getType() == EntityType::PLAYER && entity.get() != this) {
                    int dist = std::abs(entity->getX() - curr.x) + std::abs(entity->getY() - curr.y);
                    if (dist <= 2) {
                        enemyTargetCmd = curr.firstCmd;
                        break;
                    }
                }
            }
        }

        if (wallTargetCmd == Command::NONE) {
            for (const auto& d : baseDirs) {
                int wx = curr.x + d.dx;
                int wy = curr.y + d.dy;
                if (world.isPositionValid(wx, wy) &&
                    world.getBoard().getCellType(wx, wy) == CellType::BREAKABLE_WALL) {
                    wallTargetCmd = curr.firstCmd;
                    break;
                }
            }
        }

        if (curr.dist >= 12) continue;

        for (const auto& d : orderedDirs) {
            int nx = curr.x + d.dx;
            int ny = curr.y + d.dy;
            if (world.isPositionValid(nx, ny) && !visited[nx][ny] &&
                canStepOn(nx, ny, world) && !isTileDangerous(nx, ny, world)) {
                visited[nx][ny] = true;
                reachableSafeCount++;
                q.push({nx, ny, curr.firstCmd, curr.dist + 1});
            }
        }
    }

    // If already positioned next to a breakable wall with a valid escape route (waiting on warmup,
    // bomb cooldown, or a nearby bomb to clear) and no power-up is reachable, hold position instead of pacing.
    bool currentlyNearWall = false;
    for (const auto& d : baseDirs) {
        int wx = cx + d.dx;
        int wy = cy + d.dy;
        if (world.isPositionValid(wx, wy) &&
            world.getBoard().getCellType(wx, wy) == CellType::BREAKABLE_WALL) {
            currentlyNearWall = true;
            break;
        }
    }
    if (currentlyNearWall && findEscapeDirection(world, cx, cy, getBombRadius()) != Command::NONE) {
        return Command::NONE;
    }

    Command primaryTargetCmd = (wallTargetCmd != Command::NONE) ? wallTargetCmd : enemyTargetCmd;

    // If temporarily confined to a small safe pocket (<= 3 tiles) with no targets inside
    // (e.g. waiting for another player's bomb blast to clear), stand still instead of pacing back and forth.
    if (primaryTargetCmd == Command::NONE && reachableSafeCount <= 3) {
        return Command::NONE;
    }

    if (primaryTargetCmd != Command::NONE) {
        if (std::find(forwardSafeMoves.begin(), forwardSafeMoves.end(), primaryTargetCmd) != forwardSafeMoves.end() ||
            forwardSafeMoves.empty()) {
            return primaryTargetCmd;
        }
    }

    if (forwardSafeMoves.size() == 1) {
        return forwardSafeMoves[0];
    }

    if (!forwardSafeMoves.empty()) {
        if (std::find(forwardSafeMoves.begin(), forwardSafeMoves.end(), m_currentDir) != forwardSafeMoves.end() &&
            (std::rand() % 100 < 85)) {
            return m_currentDir;
        }
        return forwardSafeMoves[std::rand() % forwardSafeMoves.size()];
    }

    return safeMoves[0];
}

void DumbBot::update(World& world) {
    Player::update(world);
    m_ticksAlive++;
    if (m_bombCooldown > 0) m_bombCooldown--;

    int baseCaution = std::clamp(s_sdCautionPercent + ((getId() % 3) - 1) * 6, 0, 100);
    m_sdCautionPercent = baseCaution;
    if (m_sdDecisionTimer > 0) {
        m_sdDecisionTimer--;
    } else {
        m_sdDecisionTimer = SD_DECISION_WINDOW_TICKS + (std::rand() % 12);
        int effectiveCaution = m_sdCautionPercent;
        if (world.countBombsForOwner(getId()) > 0 && s_sdCautionPercent < 100 && s_sdCautionPercent > 0) {
            effectiveCaution = std::max(5, effectiveCaution - 10);
        }
        m_sdAwareThisWindow = (std::rand() % 100) < effectiveCaution;
    }

    if (!isAlive() || isOnCooldown()) return;

    int cx = getX();
    int cy = getY();
    bool amIDangerous = isTileDangerous(cx, cy, world);

    if (amIDangerous) {
        Command escapeDir = findEscapeDirection(world);
        if (escapeDir != Command::NONE) {
            m_currentDir = escapeDir;
            handleCommand(m_currentDir, world);
            return;
        }

        // If trapped by an adjacent bomb and we have Hammer or Ring, kick or cross the bomb to escape
        struct DirInfo { int dx; int dy; Command cmd; };
        const DirInfo dirs[4] = {
            {0, -1, Command::UP},
            {0, 1, Command::DOWN},
            {-1, 0, Command::LEFT},
            {1, 0, Command::RIGHT}
        };
        if (hasHammer() || hasRing()) {
            for (const auto& d : dirs) {
                int nx = cx + d.dx;
                int ny = cy + d.dy;
                if (!world.isPositionValid(nx, ny)) continue;
                for (const auto* e : world.getEntitiesAt(nx, ny)) {
                    if (e->isAlive() && e->getType() == EntityType::BOMB) {
                        bool canKick = hasHammer() && Bomb::canSlideTo(world, nx + d.dx, ny + d.dy);
                        bool canCross = hasRing() && !canKick;
                        if (canKick || canCross) {
                            m_currentDir = d.cmd;
                            handleCommand(m_currentDir, world);
                            return;
                        }
                    }
                }
            }
        }

        // Otherwise step to the neighbor with the longest survival time
        int bestTte = getTileTimeToExplode(cx, cy, world);
        Command bestCmd = Command::NONE;
        int moveCd = getMoveCooldownMax();
        for (const auto& d : dirs) {
            int nx = cx + d.dx;
            int ny = cy + d.dy;
            if (canStepOn(nx, ny, world)) {
                int tte = getTileTimeToExplode(nx, ny, world);
                if (tte > bestTte || (tte == bestTte && d.cmd == m_currentDir && bestTte > moveCd)) {
                    bestTte = tte;
                    bestCmd = d.cmd;
                }
            }
        }
        if (bestCmd != Command::NONE) {
            m_currentDir = bestCmd;
            handleCommand(m_currentDir, world);
        }
        return;
    }

    // Offensive Hammer kick: if an adjacent bomb can be kicked toward an aligned enemy or wall, kick it
    if (hasHammer()) {
        struct KickDir { int dx; int dy; Command cmd; };
        const KickDir kDirs[4] = {
            {0, -1, Command::UP},
            {0, 1, Command::DOWN},
            {-1, 0, Command::LEFT},
            {1, 0, Command::RIGHT}
        };
        for (const auto& d : kDirs) {
            int bx = cx + d.dx;
            int by = cy + d.dy;
            if (!world.isPositionValid(bx, by) || !Bomb::canSlideTo(world, bx + d.dx, by + d.dy)) continue;
            bool hasBombAtB = false;
            for (const auto* e : world.getEntitiesAt(bx, by)) {
                if (e->isAlive() && e->getType() == EntityType::BOMB) {
                    hasBombAtB = true;
                    break;
                }
            }
            if (!hasBombAtB) continue;

            bool targetAhead = false;
            for (int dist = 2; dist <= 6; ++dist) {
                int tx = cx + d.dx * dist;
                int ty = cy + d.dy * dist;
                if (!world.isPositionValid(tx, ty)) break;
                CellType ct = world.getBoard().getCellType(tx, ty);
                if (ct == CellType::SOLID_WALL) break;
                if (ct == CellType::BREAKABLE_WALL) {
                    targetAhead = true;
                    break;
                }
                for (const auto* e : world.getEntitiesAt(tx, ty)) {
                    if (e->isAlive() && e->getType() == EntityType::PLAYER && e != this) {
                        targetAhead = true;
                        break;
                    }
                }
                if (targetAhead) break;
            }
            if (targetAhead) {
                m_currentDir = d.cmd;
                handleCommand(m_currentDir, world);
                return;
            }
        }
    }

    // Evaluate strategic bomb placement only when safe, warmed up, off bomb cooldown, and having no active bomb out
    if (m_ticksAlive >= SPAWN_BOMB_WARMUP_TICKS &&
        m_bombCooldown == 0 &&
        canPlaceBomb(world) &&
        world.countBombsForOwner(getId()) == 0) {

        // Avoid dropping a second bomb right next to another ticking bomb (prevents multi-bot corridor corking)
        bool bombNearby = false;
        for (const auto& entity : world.getEntities()) {
            if (entity->isAlive() && entity->getType() == EntityType::BOMB) {
                int dist = std::abs(entity->getX() - cx) + std::abs(entity->getY() - cy);
                if (dist <= 4) {
                    bombNearby = true;
                    break;
                }
            }
        }

        if (!bombNearby) {
            auto isBreakableWall = [&](int nx, int ny) {
                if (!world.isPositionValid(nx, ny)) return false;
                return world.getBoard().getCellType(nx, ny) == CellType::BREAKABLE_WALL;
            };

            bool nearWall = isBreakableWall(cx + 1, cy) || isBreakableWall(cx - 1, cy) ||
                            isBreakableWall(cx, cy + 1) || isBreakableWall(cx, cy - 1);

            bool nearEnemy = false;
            for (const auto& entity : world.getEntities()) {
                if (entity->isAlive() && entity->getType() == EntityType::PLAYER && entity.get() != this) {
                    int dist = std::abs(entity->getX() - cx) + std::abs(entity->getY() - cy);
                    if (dist <= 2) {
                        nearEnemy = true;
                        break;
                    }
                }
            }

            if (nearWall || nearEnemy) {
                Command escapeDir = findEscapeDirection(world, cx, cy, getBombRadius());
                if (escapeDir != Command::NONE) {
                    handleCommand(Command::PLACE_BOMB, world);
                    m_bombCooldown = BOMB_PLACEMENT_COOLDOWN;
                    m_currentDir = escapeDir;
                    handleCommand(m_currentDir, world);
                    return;
                }
            }
        }
    }

    Command moveDir = findExplorationDirection(world);
    if (moveDir != Command::NONE) {
        m_currentDir = moveDir;
        handleCommand(m_currentDir, world);
    } else {
        m_currentDir = Command::NONE;
    }
}
