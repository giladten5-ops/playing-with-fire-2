#include "../../include/entities/RingPowerUp.h"
#include "../../include/entities/Player.h"

RingPowerUp::RingPowerUp(int x, int y) : PowerUp(x, y) {}

char RingPowerUp::getDisplayChar() const {
    return 'R';
}

void RingPowerUp::apply(Player& player) {
    player.enableRing();
}