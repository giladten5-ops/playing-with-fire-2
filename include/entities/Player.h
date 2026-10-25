#pragma once
#include "Entity.h"

class Player : public Entity {
    private:
        int m_id;
        int m_bombRadius;
        int m_maxBombs;
        int m_speedLevel;
        int m_cooldown; // Number of ticks until the next move is allowed
        bool m_hasHammer = false; // Indicates if the player has the hammer power-up
        int m_facingDx = 0; // Direction the player is facing (x-axis)
        int m_facingDy = 1; // Direction the player is facing (y-axis)
    public:
        Player(int startX, int startY, int id);

        EntityType getType() const override;
        char getDisplayChar() const override;
        void update(World& world) override;

        void handleCommand(Command command, World& world) override;

        void increaseBombRadius();
        void increaseMaxBombs();
        void enableHammer();

        void increaseSpeed();
};