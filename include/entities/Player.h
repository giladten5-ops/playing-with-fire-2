#pragma once
#include "Entity.h"
#include <string>

class Player : public Entity {
public:
    static constexpr int INITIAL_LIVES = 3;
    static constexpr int INITIAL_BOMB_RADIUS = 2;
    static constexpr int INITIAL_MAX_BOMBS = 1;
    static constexpr int DEFAULT_BOMB_TIMER = 90;
    static constexpr int INVINCIBILITY_FRAMES = 60;
    static constexpr int BASE_MOVE_COOLDOWN = 4;
    static constexpr int MAX_SPEED_LEVEL = 2;

private:
    int m_id;
    int m_bombRadius;
    int m_maxBombs;
    int m_speedLevel;
    int m_cooldown;
    bool m_hasHammer = false;
    bool m_hasRing = false;
    int m_facingDx = 0;
    int m_facingDy = 1;
    int m_lives;
    int m_invincibilityTimer;

    void tryMove(int targetX, int targetY, World& world);
    void tryPlaceOrPushBomb(World& world);

protected:
    void addCooldown(int frames);
    bool canPlaceBomb(const World& world) const;

public:
    Player(int startX, int startY, int id);

    int getId() const;
    int getLives() const;
    int getMaxBombs() const;
    int getBombRadius() const;
    int getSpeedLevel() const;
    int getCooldown() const;
    int getInvincibilityTimer() const;
    int getFacingDx() const;
    int getFacingDy() const;
    bool hasHammer() const;
    bool hasRing() const;
    bool isOnCooldown() const;

    virtual bool isBot() const;
    virtual std::string getDisplayName() const;

    EntityType getType() const override;
    char getDisplayChar() const override;

    void update(World& world) override;
    void handleCommand(Command command, World& world) override;
    void onExplosionHit(World& world) override;

    void increaseBombRadius();
    void increaseMaxBombs();
    void increaseSpeed();
    void enableHammer();
    void enableRing();
};
