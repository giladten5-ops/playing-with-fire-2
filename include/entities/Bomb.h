#pragma once
#include "Entity.h"

class Bomb : public Entity {
    private:
        int m_timer;
        int m_radius;
        int m_ownerId; // ID of the player who placed the bomb

    public:
        Bomb(int x, int y, int timer, int radius, int ownerId);
        
        int getRadius() const;
        int getOwnerId() const;

        EntityType getType() const override;
        char getDisplayChar() const override;
        void update(World& world) override;

        bool isSolid() const override;
        bool stopsExplosion() const override;
        bool shouldExplode() const override;
        
        void onExplosionHit(World& world) override;
};