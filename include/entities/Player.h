#pragma once
#include "Entity.h"

class Player : public Entity {
    private:
        int m_id;
        int m_bombRadius;
        int m_maxBombs;
        int m_speedLevel;
        int m_cooldown; // Number of ticks until the next move is allowed

    public:
        Player(int startX, int startY, int id);

        EntityType getType() const override;
        char getDisplayChar() const override;
        void update(World& world) override;

        void handleCommand(Command command, World& world) override;

        void increaseBombRadius();
        void increaseMaxBombs();

        void increaseSpeed();
};