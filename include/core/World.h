#pragma once
#include <vector>
#include <memory>
#include <unordered_map>
#include "Board.h"
#include "../entities/Entity.h"

class Player;

class World {
private:
    Board m_board;
    std::vector<std::unique_ptr<Entity>> m_entities;
    std::vector<std::unique_ptr<Entity>> m_spawnQueue;
    std::unordered_map<int, int> m_wallsDestroyedByOwner;
    std::unordered_map<int, int> m_enemiesKilledByOwner;

public:
    World(int width, int height);

    Board& getBoard();
    const Board& getBoard() const;

    const std::vector<std::unique_ptr<Entity>>& getEntities() const;
    const std::vector<std::unique_ptr<Entity>>& getSpawnQueue() const;
    std::vector<Entity*> getEntitiesAt(int x, int y) const;

    void addEntity(std::unique_ptr<Entity> entity);
    void sync();
    void clear();

    bool isPositionValid(int x, int y) const;
    bool isTileFree(int x, int y) const;
    int countBombsForOwner(int ownerId) const;
    Player* getPlayer(int id);
    const Player* getPlayer(int id) const;
    int countBreakableWalls() const;

    void recordWallDestroyed(int ownerId);
    int popWallsDestroyed(int ownerId);

    void recordEnemyKilled(int ownerId);
    int popEnemiesKilled(int ownerId);
};
