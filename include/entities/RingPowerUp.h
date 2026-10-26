#pragma once
#include "PowerUp.h"

class RingPowerUp : public PowerUp {
    public:
        RingPowerUp(int x, int y);
        char getDisplayChar() const override;
        void apply(Player& player) override;
};