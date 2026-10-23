#pragma once

class World;
class Bomb;

class ExplosionSystem {
    private:
        bool explodeTile(World& world, int targetX, int targetY);
        void explodeInDirection(World& world, int startX, int startY, int dx, int dy, int radius);

    public:
        void process(World& world);
};