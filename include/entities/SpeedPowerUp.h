#pragma once
#include "PowerUp.h"

class SpeedPowerUp : public PowerUp {
    public:
        SpeedPowerUp(int x, int y);
        void apply(Player& player) override;
        char getDisplayChar() const override;
};