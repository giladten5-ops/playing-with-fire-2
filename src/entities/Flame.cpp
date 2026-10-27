#include "../../include/entities/Flame.h"
#include "../../include/core/World.h"

Flame::Flame(int x, int y, int timer) 
    : Entity(x, y), m_timer(timer), m_activeForCollision(false) {}

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
        other.onExplosionHit(world);
    }
}
