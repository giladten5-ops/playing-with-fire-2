#include "../../include/entities/LightningPowerUp.h"
#include "../../include/entities/Player.h"

LightningPowerUp::LightningPowerUp(int x, int y) : PowerUp(x, y) {}

void LightningPowerUp::apply(Player& player) {
    player.increaseBombRadius();
}

char LightningPowerUp::getDisplayChar() const { return 'L'; } // L for Lightning Power-Up