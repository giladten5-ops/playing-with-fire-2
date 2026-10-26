#include "../../include/factories/PowerUpFactory.h"
#include "../../include/core/World.h"
#include "../../include/entities/LightningPowerUp.h"
#include "../../include/entities/SpeedPowerUp.h"
#include "../../include/entities/BombPowerUp.h"
#include "../../include/entities/HammerPowerUp.h"
#include "../../include/entities/RingPowerUp.h"
#include <cstdlib>
#include <memory>

void PowerUpFactory::trySpawn(World& world, int x, int y) {
    int r = rand() % 100;
    if (r < 15) {
        world.addEntity(std::make_unique<LightningPowerUp>(x, y));
    } else if (r < 30) {
        world.addEntity(std::make_unique<SpeedPowerUp>(x, y));
    } else if (r < 45) {
        world.addEntity(std::make_unique<BombPowerUp>(x, y));
    } else if (r < 60) {
        world.addEntity(std::make_unique<HammerPowerUp>(x, y));
    } else if (r < 75) {
        world.addEntity(std::make_unique<RingPowerUp>(x, y));
    }
}
