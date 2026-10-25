#pragma once
#include "PowerUp.h"

class HammerPowerUp : public PowerUp {
    public:
        HammerPowerUp(int x, int y);
        void apply(Player& player) override;
        char getDisplayChar() const override;
};
