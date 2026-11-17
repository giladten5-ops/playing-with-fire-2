#pragma once

class World;
class Bomb;

class ExplosionSystem {
    private:
        bool explodeTile(World& world, int targetX, int targetY, int ownerId = -1, int creditOwnerId = -1);
        void explodeInDirection(World& world, int startX, int startY, int dx, int dy, int radius, int ownerId = -1, int creditOwnerId = -1);

    public:
        void process(World& world);
};
