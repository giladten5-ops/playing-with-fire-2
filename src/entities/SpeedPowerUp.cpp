#include "../../include/entities/SpeedPowerUp.h"
#include "../../include/entities/Player.h"

SpeedPowerUp::SpeedPowerUp(int x, int y) : PowerUp(x, y) {}

void SpeedPowerUp::apply(Player& player) {
    player.increaseSpeed();
}

char SpeedPowerUp::getDisplayChar() const {
    return 'S';
}