#pragma once
#include "Entity.h"

class Player; 

class PowerUp : public Entity {
    public:
        PowerUp(int x, int y);

        EntityType getType() const override;
        void update(World& world) override;

        bool isSolid() const override;
        bool stopsExplosion() const override;
        
        void onExplosionHit(World& world) override;
        void onIntersect(Entity& other, World& world) override;

        virtual void apply(Player& player) = 0;
};