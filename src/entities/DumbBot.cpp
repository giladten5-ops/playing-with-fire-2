#include "../../include/entities/DumbBot.h"
#include "../../include/core/World.h"
#include "../../include/entities/Bomb.h"
#include <cstdlib>
#include <vector>
#include <queue>
#include <cmath>

DumbBot::DumbBot(int startX, int startY, int id)
    : Player(startX, startY, id) {}

bool DumbBot::isBot() const { return true; }
std::string DumbBot::getDisplayName() const { return "BOT" + std::to_string(getId()); }

char DumbBot::getDisplayChar() const {
    if (Player::getDisplayChar() == ' ') return ' ';
    return 'D';
}

bool DumbBot::canStepOn(int x, int y, const World& world) const {
    if (world.isTileFree(x, y)) return true;
    if (!hasRing() || !world.isPositionValid(x, y)) return false;
    if (world.getBoard().getCellType(x, y) == CellType::SOLID_WALL) return false;
    for (const auto* e : world.getEntitiesAt(x, y)) {
        if (e->isAlive() && e->isSolid() && e->getType() != EntityType::BOMB) {
            return false;
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
        if (world.getBoard().getCellType(cx, cy) == CellType::SOLID_WALL) return false;
        auto entities = world.getEntitiesAt(cx, cy);
        for (const auto* e : entities) {
            if (e->isAlive() && e->stopsExplosion()) return false;
        }
        cx += dx;
        cy += dy;
    }
    return true;
}

bool DumbBot::isTileDangerous(int x, int y, const World& world) const {
    auto checkList = [&](const std::vector<std::unique_ptr<Entity>>& list) {
        for (const auto& entity : list) {
            if (!entity->isAlive()) continue;

            if (entity->getType() == EntityType::BOMB) {
                const auto* bomb = static_cast<const Bomb*>(entity.get());
                int bx = bomb->getX();
                int by = bomb->getY();
                int radius = bomb->getRadius();

                if (bx == x && std::abs(by - y) <= radius) {
                    if (hasClearBlastPath(bx, by, x, y, world)) return true;
                }
                if (by == y && std::abs(bx - x) <= radius) {
                    if (hasClearBlastPath(bx, by, x, y, world)) return true;
                }
            } else if (entity->getType() == EntityType::FLAME) {
                if (entity->getX() == x && entity->getY() == y) return true;
            }
        }
        return false;
    };
    return checkList(world.getEntities()) || checkList(world.getSpawnQueue());
}

bool DumbBot::isTileDangerousWithExtraBomb(int x, int y, const World& world, int extraBx, int extraBy, int extraRadius) const {
    if (isTileDangerous(x, y, world)) return true;

    if (extraBx >= 0 && extraBy >= 0) {
        if (extraBx == x && std::abs(extraBy - y) <= extraRadius) {
            if (hasClearBlastPath(extraBx, extraBy, x, y, world)) return true;
        }
        if (extraBy == y && std::abs(extraBx - x) <= extraRadius) {
            if (hasClearBlastPath(extraBx, extraBy, x, y, world)) return true;
        }
    }
    return false;
}

Command DumbBot::findEscapeDirection(const World& world, int extraBx, int extraBy, int extraRadius) const {
    int width = world.getBoard().getWidth();
    int height = world.getBoard().getHeight();
    int startX = getX();
    int startY = getY();

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
    DirInfo dirs[4] = {
        {0, -1, Command::UP},
        {0, 1, Command::DOWN},
        {-1, 0, Command::LEFT},
        {1, 0, Command::RIGHT}
    };

    int offset = rand() % 4;
    for (int i = 0; i < 4; ++i) {
        const auto& d = dirs[(i + offset) % 4];
        int nx = startX + d.dx;
        int ny = startY + d.dy;
        if (canStepOn(nx, ny, world)) {
            if (!isTileDangerousWithExtraBomb(nx, ny, world, extraBx, extraBy, extraRadius)) {
                return d.cmd;
            }
            visited[nx][ny] = true;
            q.push({nx, ny, d.cmd, 1});
        }
    }

    const int MAX_ESCAPE_STEPS = 6;
    while (!q.empty()) {
        StepNode curr = q.front();
        q.pop();

        if (curr.dist >= MAX_ESCAPE_STEPS) continue;

        for (int i = 0; i < 4; ++i) {
            const auto& d = dirs[(i + offset) % 4];
            int nx = curr.x + d.dx;
            int ny = curr.y + d.dy;
            if (world.isPositionValid(nx, ny) && !visited[nx][ny] && canStepOn(nx, ny, world)) {
                visited[nx][ny] = true;
                if (!isTileDangerousWithExtraBomb(nx, ny, world, extraBx, extraBy, extraRadius)) {
                    return curr.firstCommand;
                }
                q.push({nx, ny, curr.firstCommand, curr.dist + 1});
            }
        }
    }

    return Command::NONE;
}

void DumbBot::update(World& world) {
    Player::update(world);

    if (!isAlive() || isOnCooldown()) return;

    int cx = getX();
    int cy = getY();
    bool amIDangerous = isTileDangerous(cx, cy, world);

    if (!amIDangerous) {
        auto isBreakableWall = [&](int nx, int ny) {
            if (!world.isPositionValid(nx, ny)) return false;
            auto entities = world.getEntitiesAt(nx, ny);
            for (auto* e : entities) {
                if (e->getType() == EntityType::BREAKABLE_WALL) return true;
            }
            return false;
        };

        bool nearWall = isBreakableWall(cx + 1, cy) || isBreakableWall(cx - 1, cy) ||
                        isBreakableWall(cx, cy + 1) || isBreakableWall(cx, cy - 1);

        bool wantsToBomb = nearWall || (rand() % 100 < 2);
        if (wantsToBomb && canPlaceBomb(world)) {
            Command escapeDir = findEscapeDirection(world, cx, cy, getBombRadius());
            if (escapeDir != Command::NONE) {
                handleCommand(Command::PLACE_BOMB, world);
                m_currentDir = escapeDir;
                handleCommand(m_currentDir, world);
                if (!isOnCooldown()) addCooldown(BOT_REACTION_COOLDOWN);
                return;
            }
        }

        if (rand() % 100 < 10) {
            addCooldown(BOT_REACTION_COOLDOWN);
            return;
        }
    }

    if (amIDangerous) {
        Command escapeDir = findEscapeDirection(world);
        if (escapeDir != Command::NONE) {
            m_currentDir = escapeDir;
            handleCommand(m_currentDir, world);
        } else {
            std::vector<Command> freeMoves;
            if (canStepOn(cx, cy - 1, world)) freeMoves.push_back(Command::UP);
            if (canStepOn(cx, cy + 1, world)) freeMoves.push_back(Command::DOWN);
            if (canStepOn(cx - 1, cy, world)) freeMoves.push_back(Command::LEFT);
            if (canStepOn(cx + 1, cy, world)) freeMoves.push_back(Command::RIGHT);

            if (!freeMoves.empty()) {
                m_currentDir = freeMoves[rand() % freeMoves.size()];
                handleCommand(m_currentDir, world);
            }
        }
        if (!isOnCooldown()) addCooldown(BOT_REACTION_COOLDOWN);
        return;
    }

    std::vector<Command> safeMoves;
    if (canStepOn(cx, cy - 1, world) && !isTileDangerous(cx, cy - 1, world)) safeMoves.push_back(Command::UP);
    if (canStepOn(cx, cy + 1, world) && !isTileDangerous(cx, cy + 1, world)) safeMoves.push_back(Command::DOWN);
    if (canStepOn(cx - 1, cy, world) && !isTileDangerous(cx - 1, cy, world)) safeMoves.push_back(Command::LEFT);
    if (canStepOn(cx + 1, cy, world) && !isTileDangerous(cx + 1, cy, world)) safeMoves.push_back(Command::RIGHT);

    int nx = cx, ny = cy;
    if (m_currentDir == Command::UP) ny--;
    if (m_currentDir == Command::DOWN) ny++;
    if (m_currentDir == Command::LEFT) nx--;
    if (m_currentDir == Command::RIGHT) nx++;

    bool canContinueSafely = (m_currentDir != Command::NONE &&
                              canStepOn(nx, ny, world) &&
                              !isTileDangerous(nx, ny, world));

    if (canContinueSafely && (rand() % 100 < 80)) {
        handleCommand(m_currentDir, world);
    } else if (!safeMoves.empty()) {
        m_currentDir = safeMoves[rand() % safeMoves.size()];
        handleCommand(m_currentDir, world);
    } else {
        m_currentDir = Command::NONE;
    }

    if (!isOnCooldown()) addCooldown(BOT_REACTION_COOLDOWN);
}
