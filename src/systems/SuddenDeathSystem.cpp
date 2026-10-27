#include "../../include/systems/SuddenDeathSystem.h"
#include "../../include/core/World.h"
#include "../../include/core/Board.h"
#include "../../include/entities/Entity.h"

SuddenDeathSystem::SuddenDeathSystem(int startDelayTicks, int boardWidth, int boardHeight)
    : m_ticksUntilStart(startDelayTicks),
      m_dropCooldown(15), // 15 frames at 30 FPS = 2 tiles per second
      m_currentCooldown(0),
      m_minX(0), m_maxX(boardWidth - 1),
      m_minY(0), m_maxY(boardHeight - 1),
      m_x(0), m_y(0),
      m_dx(1), m_dy(0),
      m_isFinished(false) {}

int SuddenDeathSystem::getTicksRemaining() const { 
    return m_ticksUntilStart; 
}

bool SuddenDeathSystem::isActive() const { 
    return m_ticksUntilStart <= 0 && !m_isFinished; 
}

void SuddenDeathSystem::process(World& world) {
    if (m_isFinished) return;

    if (m_ticksUntilStart > 0) {
        m_ticksUntilStart--;
        return;
    }

    if (m_currentCooldown > 0) {
        m_currentCooldown--;
        return;
    }

    world.getBoard().setCellType(m_x, m_y, CellType::SOLID_WALL);

    auto crushEntities = [&](const std::vector<std::unique_ptr<Entity>>& list) {
        for (const auto& e : list) {
            if (e->isAlive() && e->getX() == m_x && e->getY() == m_y) {
                e->destroy();
            }
        }
    };
    crushEntities(world.getEntities());
    crushEntities(world.getSpawnQueue());

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

    if (m_minX > m_maxX || m_minY > m_maxY || (m_maxX - m_minX <= 4 && m_maxY - m_minY <= 4)) {
        m_isFinished = true;
    } else {
        m_currentCooldown = m_dropCooldown;
    }
}
