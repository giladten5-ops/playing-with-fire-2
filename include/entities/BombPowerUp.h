#pragma once
#include "PowerUp.h"

class BombPowerUp : public PowerUp {
    public:
        BombPowerUp(int x, int y);
        void apply(Player& player) override;
        char getDisplayChar() const override;
};