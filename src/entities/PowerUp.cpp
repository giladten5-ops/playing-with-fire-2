#include "../../include/entities/PowerUp.h"
#include "../../include/entities/Player.h"
#include "../../include/core/World.h"

PowerUp::PowerUp(int x, int y) : Entity(x, y) {}

EntityType PowerUp::getType() const {
    return EntityType::POWER_UP;
}

void PowerUp::update(World& world) {
}

bool PowerUp::isSolid() const {
    return false;
}

bool PowerUp::stopsExplosion() const {
    return false;
}

void PowerUp::onExplosionHit(World& world) {
    return;
}

void PowerUp::onIntersect(Entity& other, World& world) {
    if (!m_isAlive || !other.isAlive()) return;

    if (other.getType() == EntityType::PLAYER) {
        apply(static_cast<Player&>(other));
        destroy();
    }
}