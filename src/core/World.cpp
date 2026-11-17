#include "../../include/core/World.h"
#include "../../include/entities/Player.h"
#include "../../include/entities/Bomb.h"
#include <algorithm>

World::World(int width, int height)
    : m_board(width, height),
      m_suddenDeathTiles(width, std::vector<bool>(height, false)),
      m_imminentSuddenDeathTicks(width, std::vector<int>(height, 9999)) {}

Board& World::getBoard() { return m_board; }
const Board& World::getBoard() const { return m_board; }

const std::vector<std::unique_ptr<Entity>>& World::getEntities() const {
    return m_entities;
}

const std::vector<std::unique_ptr<Entity>>& World::getSpawnQueue() const {
    return m_spawnQueue;
}

std::vector<Entity*> World::getEntitiesAt(int x, int y) const {
    std::vector<Entity*> result;
    for (const auto& entity : m_entities) {
        if (entity->isAlive() && entity->getX() == x && entity->getY() == y) {
            result.push_back(entity.get());
        }
    }
    for (const auto& entity : m_spawnQueue) {
        if (entity->isAlive() && entity->getX() == x && entity->getY() == y) {
            result.push_back(entity.get());
        }
    }
    return result;
}

void World::addEntity(std::unique_ptr<Entity> entity) {
    if (entity) {
        m_spawnQueue.push_back(std::move(entity));
    }
}

void World::sync() {
    for (auto& entity : m_spawnQueue) {
        m_entities.push_back(std::move(entity));
    }
    m_spawnQueue.clear();

    m_entities.erase(
        std::remove_if(m_entities.begin(), m_entities.end(),
            [](const std::unique_ptr<Entity>& entity) {
                return !entity->isAlive();
            }),
        m_entities.end()
    );
}

bool World::isPositionValid(int x, int y) const {
    return x >= 0 && x < m_board.getWidth() && y >= 0 && y < m_board.getHeight();
}

bool World::isTileFree(int x, int y) const {
    if (!isPositionValid(x, y)) {
        return false;
    }

    if (m_board.getCellType(x, y) != CellType::EMPTY) {
        return false;
    }

    for (const auto& entity : m_entities) {
        if (entity->isAlive() && entity->getX() == x && entity->getY() == y && entity->isSolid()) {
            return false;
        }
    }
    for (const auto& entity : m_spawnQueue) {
        if (entity->isAlive() && entity->getX() == x && entity->getY() == y && entity->isSolid()) {
            return false;
        }
    }
    return true;
}

bool World::canPlayerMoveTo(int fromX, int fromY, int toX, int toY) const {
    if (!isPositionValid(toX, toY)) {
        return false;
    }
    if (isTileFree(toX, toY)) {
        return true;
    }
    if (isSuddenDeathTile(fromX, fromY) && isSuddenDeathTile(toX, toY)) {
        for (const auto& entity : m_entities) {
            if (entity->isAlive() && entity->getX() == toX && entity->getY() == toY && entity->isSolid()) {
                return false;
            }
        }
        for (const auto& entity : m_spawnQueue) {
            if (entity->isAlive() && entity->getX() == toX && entity->getY() == toY && entity->isSolid()) {
                return false;
            }
        }
        return true;
    }
    return false;
}

void World::setSuddenDeathTile(int x, int y, bool active) {
    if (isPositionValid(x, y)) {
        m_suddenDeathTiles[x][y] = active;
    }
}

bool World::isSuddenDeathTile(int x, int y) const {
    if (!isPositionValid(x, y)) {
        return false;
    }
    return m_suddenDeathTiles[x][y];
}

void World::clearImminentSuddenDeathTicks() {
    for (auto& col : m_imminentSuddenDeathTicks) {
        std::fill(col.begin(), col.end(), 9999);
    }
}

void World::setImminentSuddenDeathTick(int x, int y, int ticksUntilDrop) {
    if (isPositionValid(x, y)) {
        m_imminentSuddenDeathTicks[x][y] = std::min(m_imminentSuddenDeathTicks[x][y], ticksUntilDrop);
    }
}

int World::getSuddenDeathTicksUntilDrop(int x, int y) const {
    if (!isPositionValid(x, y)) {
        return 9999;
    }
    return m_imminentSuddenDeathTicks[x][y];
}

int World::countBombsForOwner(int ownerId) const {
    int count = 0;
    for (const auto& entity : m_entities) {
        if (entity->isAlive() && entity->getType() == EntityType::BOMB) {
            if (static_cast<const Bomb*>(entity.get())->getOwnerId() == ownerId) count++;
        }
    }
    for (const auto& entity : m_spawnQueue) {
        if (entity->isAlive() && entity->getType() == EntityType::BOMB) {
            if (static_cast<const Bomb*>(entity.get())->getOwnerId() == ownerId) count++;
        }
    }
    return count;
}

Player* World::getPlayer(int id) {
    for (auto& e : m_entities) {
        if (e->isAlive() && e->getType() == EntityType::PLAYER) {
            auto* p = static_cast<Player*>(e.get());
            if (p->getId() == id) return p;
        }
    }
    return nullptr;
}

const Player* World::getPlayer(int id) const {
    for (const auto& e : m_entities) {
        if (e->isAlive() && e->getType() == EntityType::PLAYER) {
            const auto* p = static_cast<const Player*>(e.get());
            if (p->getId() == id) return p;
        }
    }
    return nullptr;
}

void World::clear() {
    m_entities.clear();
    m_spawnQueue.clear();
    m_wallsDestroyedByOwner.clear();
    m_enemiesKilledByOwner.clear();
    m_enemiesHitByOwner.clear();

    int width = m_board.getWidth();
    int height = m_board.getHeight();

    for (int x = 0; x < width; x++) {
        for (int y = 0; y < height; y++) {
            m_board.setCellType(x, y, CellType::EMPTY);
            m_suddenDeathTiles[x][y] = false;
            m_imminentSuddenDeathTicks[x][y] = 9999;
        }
    }
}

int World::countBreakableWalls() const {
    int count = 0;
    int width = m_board.getWidth();
    int height = m_board.getHeight();
    for (int x = 0; x < width; ++x) {
        for (int y = 0; y < height; ++y) {
            if (m_board.getCellType(x, y) == CellType::BREAKABLE_WALL) {
                count++;
            }
        }
    }
    return count;
}

void World::recordWallDestroyed(int ownerId) {
    if (ownerId > 0) {
        m_wallsDestroyedByOwner[ownerId]++;
    }
}

int World::popWallsDestroyed(int ownerId) {
    auto it = m_wallsDestroyedByOwner.find(ownerId);
    if (it == m_wallsDestroyedByOwner.end()) {
        return 0;
    }
    int count = it->second;
    it->second = 0;
    return count;
}

void World::recordEnemyKilled(int ownerId) {
    if (ownerId > 0) {
        m_enemiesKilledByOwner[ownerId]++;
    }
}

int World::popEnemiesKilled(int ownerId) {
    auto it = m_enemiesKilledByOwner.find(ownerId);
    if (it == m_enemiesKilledByOwner.end()) {
        return 0;
    }
    int count = it->second;
    it->second = 0;
    return count;
}

void World::recordEnemyHit(int ownerId) {
    if (ownerId > 0) {
        m_enemiesHitByOwner[ownerId]++;
    }
}

int World::popEnemiesHit(int ownerId) {
    auto it = m_enemiesHitByOwner.find(ownerId);
    if (it == m_enemiesHitByOwner.end()) {
        return 0;
    }
    int count = it->second;
    it->second = 0;
    return count;
}
