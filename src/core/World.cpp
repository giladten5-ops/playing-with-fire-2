#include "../../include/core/World.h"
#include "../../include/entities/Player.h"
#include "../../include/entities/Bomb.h"
#include <algorithm>

World::World(int width, int height) : m_board(width, height) {}

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

    int width = m_board.getWidth();
    int height = m_board.getHeight();

    for (int x = 0; x < width; x++) {
        for (int y = 0; y < height; y++) {
            m_board.setCellType(x, y, CellType::EMPTY);
        }
    }
}

