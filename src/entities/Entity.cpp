#include "../../include/entities/Entity.h"

Entity::Entity(int startX, int startY) : m_x(startX), m_y(startY), m_isAlive(true) {}

int Entity::getX() const { return m_x; }
int Entity::getY() const { return m_y; }
void Entity::setX(int x) { m_x = x; }
void Entity::setY(int y) { m_y = y; }
bool Entity::isAlive() const { return m_isAlive; }
void Entity::destroy() { m_isAlive = false; }

void Entity::onExplosionHit(World& /*world*/) {
    destroy(); 
}
