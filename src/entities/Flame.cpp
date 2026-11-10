#include "../../include/entities/Flame.h"
#include "../../include/entities/Player.h"
#include "../../include/entities/Bomb.h"
#include "../../include/core/World.h"

Flame::Flame(int x, int y, int timer, int ownerId)
    : Entity(x, y), m_timer(timer), m_ownerId(ownerId), m_activeForCollision(true) {}

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
        bool isBreakable = (other.getType() == EntityType::BREAKABLE_WALL);
        bool isPlayer = (other.getType() == EntityType::PLAYER);
        int victimId = isPlayer ? static_cast<Player&>(other).getId() : -1;
        int livesBefore = isPlayer ? static_cast<Player&>(other).getLives() : 0;

        if (other.getType() == EntityType::BOMB && m_ownerId > 0) {
            static_cast<Bomb&>(other).push(0, 0, m_ownerId);
        }

        other.onExplosionHit(world);

        if (isBreakable && !other.isAlive() && m_ownerId > 0) {
            world.recordWallDestroyed(m_ownerId);
        }
        if (isPlayer && m_ownerId > 0 && m_ownerId != victimId) {
            int livesAfter = other.isAlive() ? static_cast<Player&>(other).getLives() : 0;
            if (livesAfter < livesBefore) {
                world.recordEnemyHit(m_ownerId);
            }
            if (!other.isAlive()) {
                world.recordEnemyKilled(m_ownerId);
            }
        }
    }
}
