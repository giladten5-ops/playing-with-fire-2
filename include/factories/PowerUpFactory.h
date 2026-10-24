#pragma once

class World;

class PowerUpFactory {
    public:
        static void trySpawn(World& world, int x, int y);
};