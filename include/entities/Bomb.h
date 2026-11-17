#pragma once
#include "Entity.h"
#include "../interfaces/IPushable.h"

class World;

class Bomb : public Entity, public IPushable {
public:
    static constexpr int SLIDE_COOLDOWN_FRAMES = 3;

private:
    int m_timer;
    int m_radius;
    int m_ownerId;       // ID of the player who placed the bomb (for maxBombs quota)
    int m_creditOwnerId; // ID of the player credited for blast effects (updated on hammer push)
    int m_dx = 0;
    int m_dy = 0;
    int m_slideCooldown = 0;

public:
    Bomb(int x, int y, int timer, int radius, int ownerId);

    void push(int dx, int dy, int pusherId = -1) override;
    int getRadius() const;
    int getOwnerId() const;
    int getCreditOwnerId() const;
    void setCreditOwnerId(int creditOwnerId);
    int getTimer() const;
    bool isSliding() const;
    int getSlideDx() const;
    int getSlideDy() const;
    int getSlideCooldown() const;

    static bool canSlideTo(const World& world, int x, int y);

    EntityType getType() const override;
    char getDisplayChar() const override;
    void update(World& world) override;

    bool isSolid() const override;
    bool stopsExplosion() const override;
    bool shouldExplode() const override;

    void onExplosionHit(World& world) override;
};
