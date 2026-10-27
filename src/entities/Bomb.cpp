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
    return '@';
}

void Bomb::update(World& world) {
    if (m_dx != 0 || m_dy != 0) {
        if (m_slideCooldown > 0) {
            m_slideCooldown--;
        } else {
            int nextX = getX() + m_dx;
            int nextY = getY() + m_dy;
            if (world.isTileFree(nextX, nextY)) {
                setX(nextX);
                setY(nextY);
                m_slideCooldown = 2; // SLIDE_COOLDOWN_FRAMES
            } else {
                m_dx = 0;
                m_dy = 0;
            }
        }
    }

    if (!isAlive()) return;
    if (m_timer > 0) {
        m_timer--;
    }
}

bool Bomb::isSolid() const {
    return true; 
}

bool Bomb::stopsExplosion() const {
    return true; 
}

bool Bomb::shouldExplode() const {
    return isAlive() && m_timer <= 0;
}

void Bomb::onExplosionHit(World& /*world*/) {
    if (isAlive()) {
        m_timer = 0; 
    }
}

void Bomb::push(int dx, int dy) {
    m_dx = dx;
    m_dy = dy;
}
