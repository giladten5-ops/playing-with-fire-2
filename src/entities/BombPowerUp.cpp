#include "../../include/entities/BombPowerUp.h"
#include "../../include/entities/Player.h"

BombPowerUp::BombPowerUp(int x, int y) : PowerUp(x, y) {}

void BombPowerUp::apply(Player& player) {
    player.increaseMaxBombs();
}

char BombPowerUp::getDisplayChar() const {
    return '+';
}