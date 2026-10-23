#pragma once
#include <vector>
#include <memory>
#include "Board.h"
#include "../entities/Entity.h"

class World {
    private:
        Board m_board;
        std::vector<std::unique_ptr<Entity>> m_entities;
        std::vector<std::unique_ptr<Entity>> m_spawnQueue;

    public:
        World(int width, int height);

        Board& getBoard();
        const Board& getBoard() const;

        const std::vector<std::unique_ptr<Entity>>& getEntities() const;
        std::vector<Entity*> getEntitiesAt(int x, int y) const;

        void addEntity(std::unique_ptr<Entity> entity);
        void sync();

        bool isPositionValid(int x, int y) const;
        bool isTileFree(int x, int y) const;
        int countBombsForOwner(int ownerId) const;
};