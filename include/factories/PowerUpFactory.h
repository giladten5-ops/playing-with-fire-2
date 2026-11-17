#pragma once

class World;

class PowerUpFactory {
    private:
        static int s_dropChancePercent;

    public:
        static constexpr int DEFAULT_DROP_CHANCE_PERCENT = 30;

        static void setDropChancePercent(int percent);
        static int getDropChancePercent();
        static void trySpawn(World& world, int x, int y);
};