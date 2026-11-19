#include "../../include/systems/SuddenDeathSystem.h"
#include "../../include/core/World.h"
#include "../../include/core/Board.h"
#include "../../include/entities/Entity.h"
#include "../../include/entities/Player.h"

SuddenDeathSystem::SuddenDeathSystem(int startDelayTicks, int boardWidth, int boardHeight)
    : m_ticksUntilStart(startDelayTicks),
      m_dropCooldown(10), // 10 frames cooldown = 1 tile every 11 ticks (~31% faster closure)
      m_currentCooldown(0),
      m_minX(0), m_maxX(boardWidth - 1),
      m_minY(0), m_maxY(boardHeight - 1),
      m_x(0), m_y(0),
      m_dx(1), m_dy(0),
      m_isFinished(false) {}

int SuddenDeathSystem::getTicksRemaining() const { 
    return m_ticksUntilStart; 
}

void SuddenDeathSystem::setTicksRemaining(int ticks) {
    m_ticksUntilStart = ticks;
}

bool SuddenDeathSystem::isActive() const { 
    return m_ticksUntilStart <= 0 && !m_isFinished; 
}

std::vector<SuddenDeathDangerTile> SuddenDeathSystem::getImminentDangerTiles(int lookaheadTicks) const {
    std::vector<SuddenDeathDangerTile> result;
    if (m_isFinished || m_ticksUntilStart > lookaheadTicks) {
        return result;
    }

    int ticksUntilNext = (m_ticksUntilStart > 0 ? m_ticksUntilStart : 0) + m_currentCooldown;
    int minX = m_minX, maxX = m_maxX;
    int minY = m_minY, maxY = m_maxY;
    int x = m_x, y = m_y;
    int dx = m_dx, dy = m_dy;
    bool finished = m_isFinished;

    while (!finished && ticksUntilNext <= lookaheadTicks) {
        result.push_back({x, y, ticksUntilNext});

        if (dx == 1 && x == maxX) {
            dx = 0; dy = 1; minY++;
        } else if (dx == 0 && dy == 1 && y == maxY) {
            dx = -1; dy = 0; maxX--;
        } else if (dx == -1 && x == minX) {
            dx = 0; dy = -1; maxY--;
        } else if (dx == 0 && dy == -1 && y == minY) {
            dx = 1; dy = 0; minX++;
        }

        x += dx;
        y += dy;

        if (minX > maxX || minY > maxY || ((maxX - minX + 1) <= 7 && (maxY - minY + 1) <= 6)) {
            finished = true;
        } else {
            ticksUntilNext += m_dropCooldown + 1;
        }
    }
    return result;
}

void SuddenDeathSystem::process(World& world) {
    if (!m_isFinished) {
        if (m_ticksUntilStart > 0) {
            m_ticksUntilStart--;
        } else if (m_currentCooldown > 0) {
            m_currentCooldown--;
        } else {
            if (world.getBoard().getCellType(m_x, m_y) != CellType::SOLID_WALL) {
                world.setSuddenDeathTile(m_x, m_y, true);
            }
            world.getBoard().setCellType(m_x, m_y, CellType::SOLID_WALL);

            auto crushNonPlayerEntities = [&](const std::vector<std::unique_ptr<Entity>>& list) {
                for (const auto& e : list) {
                    if (e->isAlive() && e->getX() == m_x && e->getY() == m_y) {
                        if (e->getType() != EntityType::PLAYER) {
                            e->destroy();
                        }
                    }
                }
            };
            crushNonPlayerEntities(world.getEntities());
            crushNonPlayerEntities(world.getSpawnQueue());

            if (m_dx == 1 && m_x == m_maxX) {
                m_dx = 0; m_dy = 1; m_minY++;
            } else if (m_dx == 0 && m_dy == 1 && m_y == m_maxY) {
                m_dx = -1; m_dy = 0; m_maxX--;
            } else if (m_dx == -1 && m_x == m_minX) {
                m_dx = 0; m_dy = -1; m_maxY--;
            } else if (m_dx == 0 && m_dy == -1 && m_y == m_minY) {
                m_dx = 1; m_dy = 0; m_minX++;
            }

            m_x += m_dx;
            m_y += m_dy;

            if (m_minX > m_maxX || m_minY > m_maxY || ((m_maxX - m_minX + 1) <= 7 && (m_maxY - m_minY + 1) <= 6)) {
                m_isFinished = true;
            } else {
                m_currentCooldown = m_dropCooldown;
            }
        }
    }

    world.clearImminentSuddenDeathTicks();
    for (const auto& tile : getImminentDangerTiles(90)) {
        world.setImminentSuddenDeathTick(tile.x, tile.y, tile.ticksUntilDrop);
    }

    auto updatePlayers = [&](const std::vector<std::unique_ptr<Entity>>& list) {
        for (const auto& e : list) {
            if (e->isAlive() && e->getType() == EntityType::PLAYER) {
                static_cast<Player*>(e.get())->updateSuddenDeathStatus(world);
            }
        }
    };
    updatePlayers(world.getEntities());
    updatePlayers(world.getSpawnQueue());
}
