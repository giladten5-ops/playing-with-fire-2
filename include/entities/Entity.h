#pragma once
#include "../interfaces/IInput.h"

enum class EntityType {
    PLAYER,
    BOMB,
    FLAME,
    BREAKABLE_WALL,
    POWER_UP
};

class World;

class Entity {
private:
    int m_x;
    int m_y;
    bool m_isAlive;

protected:
    virtual void setX(int x);
    virtual void setY(int y);

public:
    Entity(int startX, int startY);
    virtual ~Entity() = default;

    virtual int getX() const;
    virtual int getY() const;
    virtual bool isAlive() const;
    virtual void destroy();

    virtual char getDisplayChar() const = 0;
    virtual EntityType getType() const = 0;
    virtual void update(World& world) = 0;

    virtual bool isSolid() const { return false; }
    virtual bool stopsExplosion() const { return false; }
    virtual bool shouldExplode() const { return false; }

    virtual void handleCommand(Command /*cmd*/, World& /*world*/) {}
    virtual void onExplosionHit(World& world);
    virtual void onIntersect(Entity& /*other*/, World& /*world*/) {}
};
