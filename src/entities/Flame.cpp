#include "../../include/entities/Flame.h"
#include "../../include/entities/Player.h"
#include "../../include/core/World.h"

Flame::Flame(int x, int y, int timer, int ownerId)
    : Entity(x, y), m_timer(timer), m_ownerId(ownerId), m_activeForCollision(false) {}

int Flame::getOwnerId() const { return m_ownerId; }
int Flame::getTimer() const { return m_timer; }

EntityType Flame::getType() const {
    return EntityType::FLAME;
}

char Flame::getDisplayChar() const { return '*'; }

void Flame::update(World& /*world*/) {
    if (!isAlive()) return;

    m_activeForCollision = true;

    if (m_timer > 0) {
        m_timer--;
        if (m_timer == 0) {
            destroy();
        }
    }
}

void Flame::onExplosionHit(World& /*world*/) {
    // Flames pass through other flames without being destroyed
}

void Flame::onIntersect(Entity& other, World& world) {
    if (!isAlive() || !other.isAlive() || !m_activeForCollision) return;

    if (other.getType() != EntityType::FLAME) {
        bool isPlayer = (other.getType() == EntityType::PLAYER);
        int victimId = isPlayer ? static_cast<Player&>(other).getId() : -1;

        other.onExplosionHit(world);

        if (isPlayer && !other.isAlive() && m_ownerId > 0 && m_ownerId != victimId) {
            world.recordEnemyKilled(m_ownerId);
        }
    }
}
