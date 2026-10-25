#include "../../include/entities/HammerPowerUp.h"
#include "../../include/entities/Player.h"

HammerPowerUp::HammerPowerUp(int x, int y) : PowerUp(x, y) {}

void HammerPowerUp::apply(Player& player) {
    player.enableHammer();
}

char HammerPowerUp::getDisplayChar() const {
    return 'H';
}
