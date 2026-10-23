#pragma once
#include "Entity.h"

class BreakableWall : public Entity {
    public:
        BreakableWall(int x, int y);

        EntityType getType() const override;
        void update(World& world) override;

        bool isSolid() const override;
        bool stopsExplosion() const override;
};