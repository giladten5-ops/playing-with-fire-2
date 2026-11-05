#include "../../include/entities/Bomb.h"
#include "../../include/core/World.h"

Bomb::Bomb(int x, int y, int timer, int radius, int ownerId)
    : Entity(x, y),
      m_timer(timer),
      m_radius(radius),
      m_ownerId(ownerId),
      m_creditOwnerId(ownerId) {}

int Bomb::getRadius() const { return m_radius; }
int Bomb::getOwnerId() const { return m_ownerId; }
int Bomb::getCreditOwnerId() const { return m_creditOwnerId; }
int Bomb::getTimer() const { return m_timer; }
bool Bomb::isSliding() const { return m_dx != 0 || m_dy != 0; }
int Bomb::getSlideDx() const { return m_dx; }
int Bomb::getSlideDy() const { return m_dy; }

EntityType Bomb::getType() const {
    return EntityType::BOMB;
}

char Bomb::getDisplayChar() const {
    return '@';
}

bool Bomb::canSlideTo(const World& world, int x, int y) {
    if (!world.isTileFree(x, y)) {
        return false;
    }
    for (const auto* e : world.getEntitiesAt(x, y)) {
        if (e->isAlive() && (e->getType() == EntityType::PLAYER || e->getType() == EntityType::FLAME)) {
            return false;
        }
    }
    return true;
}

void Bomb::update(World& world) {
    if (m_dx != 0 || m_dy != 0) {
        if (m_slideCooldown > 0) {
            m_slideCooldown--;
        } else {
            int nextX = getX() + m_dx;
            int nextY = getY() + m_dy;
            if (canSlideTo(world, nextX, nextY)) {
                setX(nextX);
                setY(nextY);
                m_slideCooldown = 2; // SLIDE_COOLDOWN_FRAMES
            } else {
                m_dx = 0;
                m_dy = 0;
                m_slideCooldown = 0;
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

void Bomb::push(int dx, int dy, int pusherId) {
    m_dx = dx;
    m_dy = dy;
    m_slideCooldown = 0;
    if (pusherId > 0) {
        m_creditOwnerId = pusherId;
    }
}
