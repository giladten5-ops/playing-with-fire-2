#pragma once
#include "Entity.h"
#include "../interfaces/IPushable.h"
#include "../interfaces/IPushable.h"

class Bomb : public Entity, public IPushable {
    private:
        int m_timer;
        int m_radius;
        int m_ownerId; // ID of the player who placed the bomb
        int m_dx = 0;
        int m_dy = 0;
        int m_slideCooldown = 0;
    public:
        void push(int dx, int dy) override;

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