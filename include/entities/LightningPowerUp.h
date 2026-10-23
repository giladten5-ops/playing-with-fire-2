#pragma once
#include "PowerUp.h"

class LightningPowerUp : public PowerUp {
    public:
        LightningPowerUp(int x, int y);
        void apply(Player& player) override;
        char getDisplayChar() const override;
};