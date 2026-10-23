#pragma once
#include "Entity.h"

class Flame : public Entity {
    private:
        int m_timer;

    public:
        Flame(int x, int y, int timer);

        EntityType getType() const override;
        void update(World& world) override;

        void onExplosionHit(World& world) override;
        void onIntersect(Entity& other, World& world) override;
};