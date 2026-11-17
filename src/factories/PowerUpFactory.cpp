#include "../../include/factories/PowerUpFactory.h"
#include "../../include/core/World.h"
#include "../../include/entities/LightningPowerUp.h"
#include "../../include/entities/SpeedPowerUp.h"
#include "../../include/entities/BombPowerUp.h"
#include "../../include/entities/HammerPowerUp.h"
#include "../../include/entities/RingPowerUp.h"
#include <algorithm>
#include <cstdlib>
#include <memory>

int PowerUpFactory::s_dropChancePercent = PowerUpFactory::DEFAULT_DROP_CHANCE_PERCENT;

void PowerUpFactory::setDropChancePercent(int percent) {
    s_dropChancePercent = std::clamp(percent, 0, 100);
}

int PowerUpFactory::getDropChancePercent() {
    return s_dropChancePercent;
}

void PowerUpFactory::trySpawn(World& world, int x, int y) {
    int dropRoll = std::rand() % 100;
    if (dropRoll >= s_dropChancePercent) {
        return;
    }

    int typeRoll = std::rand() % 5;
    switch (typeRoll) {
        case 0:
            world.addEntity(std::make_unique<LightningPowerUp>(x, y));
            break;
        case 1:
            world.addEntity(std::make_unique<SpeedPowerUp>(x, y));
            break;
        case 2:
            world.addEntity(std::make_unique<BombPowerUp>(x, y));
            break;
        case 3:
            world.addEntity(std::make_unique<HammerPowerUp>(x, y));
            break;
        case 4:
        default:
            world.addEntity(std::make_unique<RingPowerUp>(x, y));
            break;
    }
}
