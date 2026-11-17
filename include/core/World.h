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
    std::unordered_map<int, int> m_enemiesHitByOwner;
    std::vector<std::vector<bool>> m_suddenDeathTiles;
    std::vector<std::vector<int>> m_imminentSuddenDeathTicks;

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
    bool canPlayerMoveTo(int fromX, int fromY, int toX, int toY) const;
    void setSuddenDeathTile(int x, int y, bool active);
    bool isSuddenDeathTile(int x, int y) const;
    void clearImminentSuddenDeathTicks();
    void setImminentSuddenDeathTick(int x, int y, int ticksUntilDrop);
    int getSuddenDeathTicksUntilDrop(int x, int y) const;
    int countBombsForOwner(int ownerId) const;
    Player* getPlayer(int id);
    const Player* getPlayer(int id) const;
    int countBreakableWalls() const;

    void recordWallDestroyed(int ownerId);
    int popWallsDestroyed(int ownerId);

    void recordEnemyKilled(int ownerId);
    int popEnemiesKilled(int ownerId);

    void recordEnemyHit(int ownerId);
    int popEnemiesHit(int ownerId);
};
