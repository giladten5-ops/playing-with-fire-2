#include "../../include/entities/Bomb.h"
#include "../../include/core/World.h"

Bomb::Bomb(int x, int y, int timer, int radius, int ownerId) 
    : Entity(x, y), m_timer(timer), m_radius(radius), m_ownerId(ownerId) {}

int Bomb::getRadius() const { return m_radius; }
int Bomb::getOwnerId() const { return m_ownerId; }

EntityType Bomb::getType() const {
    return EntityType::BOMB;
}

char Bomb::getDisplayChar() const {
    return '@'; // Representing the bomb with '@'
}

void Bomb::update(World& world) {
    if (!m_isAlive) return;
    if (m_timer > 0) {
        m_timer--;
    }
}

bool Bomb::isSolid() const {
    return true; // You can't walk on a bomb
}

bool Bomb::stopsExplosion() const {
    return true; // Explosions stop when hitting another bomb
}

bool Bomb::shouldExplode() const {
    // The ExplosionSystem will check this every frame
    return m_isAlive && m_timer <= 0;
}

void Bomb::onExplosionHit(World& world) {
    if (m_isAlive) {
        // Chain reaction: Instead of exploding recursively, 
        // just set timer to 0. The ExplosionSystem will pick it up immediately.
        m_timer = 0; 
    }
}