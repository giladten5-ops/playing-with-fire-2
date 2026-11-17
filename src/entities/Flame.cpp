#include "../../include/entities/Flame.h"
#include "../../include/entities/Player.h"
#include "../../include/entities/Bomb.h"
#include "../../include/core/World.h"

Flame::Flame(int x, int y, int timer, int ownerId, int creditOwnerId)
    : Entity(x, y),
      m_timer(timer),
      m_ownerId(ownerId),
      m_creditOwnerId(creditOwnerId > 0 ? creditOwnerId : ownerId),
      m_activeForCollision(true) {}

int Flame::getOwnerId() const { return m_ownerId; }
int Flame::getCreditOwnerId() const { return m_creditOwnerId; }
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
        if (other.getType() == EntityType::BOMB) {
            auto& bomb = static_cast<Bomb&>(other);
            if (bomb.isSliding()) {
                return;
            }
            if (m_creditOwnerId > 0) {
                bomb.setCreditOwnerId(m_creditOwnerId);
            }
        }

        bool isBreakable = (other.getType() == EntityType::BREAKABLE_WALL);
        bool isPlayer = (other.getType() == EntityType::PLAYER);
        int victimId = isPlayer ? static_cast<Player&>(other).getId() : -1;
        int livesBefore = isPlayer ? static_cast<Player&>(other).getLives() : 0;

        other.onExplosionHit(world);

        if (isBreakable && !other.isAlive() && m_creditOwnerId > 0) {
            world.recordWallDestroyed(m_creditOwnerId);
        }
        if (isPlayer && m_creditOwnerId > 0 && m_creditOwnerId != victimId) {
            int livesAfter = other.isAlive() ? static_cast<Player&>(other).getLives() : 0;
            if (livesAfter < livesBefore) {
                world.recordEnemyHit(m_creditOwnerId);
            }
            if (!other.isAlive()) {
                world.recordEnemyKilled(m_creditOwnerId);
            }
        }
    }
}
