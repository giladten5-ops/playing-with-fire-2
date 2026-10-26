#include "../../include/entities/DumbBot.h"
#include "../../include/core/World.h"
#include "../../include/entities/Bomb.h"
#include <cstdlib>
#include <vector>
#include <cmath>

DumbBot::DumbBot(int startX, int startY, int id) 
    : Player(startX, startY, id) {}

char DumbBot::getDisplayChar() const {
    return 'D';
}

bool DumbBot::isTileDangerous(int x, int y, World& world) const {
    for (const auto& entity : world.getEntities()) {
        if (entity->getType() == EntityType::BOMB && entity->isAlive()) {
            auto* bomb = static_cast<const Bomb*>(entity.get());
            int bx = bomb->getX();
            int by = bomb->getY();
            int radius = bomb->getRadius();
            
            if (bx == x && std::abs(by - y) <= radius) return true;
            if (by == y && std::abs(bx - x) <= radius) return true;
        }
        if (entity->getType() == EntityType::FLAME && entity->isAlive()) {
            if (entity->getX() == x && entity->getY() == y) return true;
        }
    }
    return false;
}

void DumbBot::update(World& world) {
    Player::update(world);

    if (!isAlive()) {
        return;
    }

    if (m_cooldown > 0) {
        return; 
    }

    int cx = getX();
    int cy = getY();
    bool amIDangerous = isTileDangerous(cx, cy, world);
    bool placedBomb = false;
    
    // ספירת נתיבי מילוט אפשריים סביב הבוט
    int freeMoves = 0;
    if (world.isTileFree(cx, cy - 1)) freeMoves++;
    if (world.isTileFree(cx, cy + 1)) freeMoves++;
    if (world.isTileFree(cx - 1, cy)) freeMoves++;
    if (world.isTileFree(cx + 1, cy)) freeMoves++;

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

        // הנחת פצצה תתבצע רק אם הבוט אינו בתוך סמטה ללא מוצא (freeMoves >= 2)
        if (freeMoves >= 2 && nearWall) {
            if (world.countBombsForOwner(getId()) < m_maxBombs) {
                handleCommand(Command::PLACE_BOMB, world);
                placedBomb = true;
                amIDangerous = true; 
            }
        }

        if (freeMoves >= 2 && !placedBomb && (rand() % 100 < 2)) {
            if (world.countBombsForOwner(getId()) < m_maxBombs) {
                handleCommand(Command::PLACE_BOMB, world);
                placedBomb = true;
                amIDangerous = true; 
            }
        }
        
        if (!placedBomb && (rand() % 100 < 40)) {
            m_cooldown += 10; 
            return;
        }
    }

    std::vector<Command> safeMoves;
    std::vector<Command> allMoves;

    auto checkMove = [&](int nx, int ny, Command cmd) {
        if (world.isTileFree(nx, ny)) {
            allMoves.push_back(cmd);
            if (!isTileDangerous(nx, ny, world)) {
                safeMoves.push_back(cmd);
            }
        }
    };

    checkMove(cx, cy - 1, Command::UP);
    checkMove(cx, cy + 1, Command::DOWN);
    checkMove(cx - 1, cy, Command::LEFT);
    checkMove(cx + 1, cy, Command::RIGHT);

    if (amIDangerous) {
        if (!safeMoves.empty()) {
            m_currentDir = safeMoves[rand() % safeMoves.size()];
            handleCommand(m_currentDir, world);
        } else {
            int nx = cx, ny = cy;
            if (m_currentDir == Command::UP) ny--;
            if (m_currentDir == Command::DOWN) ny++;
            if (m_currentDir == Command::LEFT) nx--;
            if (m_currentDir == Command::RIGHT) nx++;

            if (m_currentDir != Command::NONE && world.isTileFree(nx, ny)) {
                handleCommand(m_currentDir, world);
            } else if (!allMoves.empty()) {
                m_currentDir = allMoves[rand() % allMoves.size()];
                handleCommand(m_currentDir, world);
            } else {
                m_currentDir = Command::NONE;
            }
        }
    } else {
        int nx = cx, ny = cy;
        if (m_currentDir == Command::UP) ny--;
        if (m_currentDir == Command::DOWN) ny++;
        if (m_currentDir == Command::LEFT) nx--;
        if (m_currentDir == Command::RIGHT) nx++;

        bool canContinue = (m_currentDir != Command::NONE && world.isTileFree(nx, ny));
        bool continueSafe = canContinue && !isTileDangerous(nx, ny, world);

        if (canContinue && continueSafe && (rand() % 100 < 80)) {
            handleCommand(m_currentDir, world);
        } else {
            if (!safeMoves.empty()) {
                m_currentDir = safeMoves[rand() % safeMoves.size()];
                handleCommand(m_currentDir, world);
            } else if (!allMoves.empty()) {
                m_currentDir = allMoves[rand() % allMoves.size()];
                handleCommand(m_currentDir, world);
            } else {
                m_currentDir = Command::NONE;
            }
        }
    }

    // הוספת זמן תגובה ארוך יותר כדי לדמות אנושיות
    m_cooldown += 10; 
}
