#pragma once
#include "Entity.h"

class Flame : public Entity {
private:
    int m_timer;
    int m_ownerId;
    bool m_activeForCollision = true;

public:
    Flame(int x, int y, int timer, int ownerId = -1);

    int getOwnerId() const;
    int getTimer() const;

    EntityType getType() const override;
    char getDisplayChar() const override;
    void update(World& world) override;

    void onExplosionHit(World& world) override;
    void onIntersect(Entity& other, World& world) override;
};
