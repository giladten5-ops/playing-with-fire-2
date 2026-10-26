#pragma once
#include "Entity.h"

class Player : public Entity {
protected:
    int m_id;
    int m_bombRadius;
    int m_maxBombs;
    int m_speedLevel;
    int m_cooldown;
    bool m_hasHammer = false;
    bool m_hasRing = false;
    int m_facingDx = 0;
    int m_facingDy = 1;
    
    int m_startX;
    int m_startY;
    int m_lives;
    int m_invincibilityTimer;

public:
    Player(int startX, int startY, int id);

    int getId() const;
    int getLives() const;
    EntityType getType() const override;
    char getDisplayChar() const override;
    
    void update(World& world) override;
    void handleCommand(Command command, World& world) override;
    void onExplosionHit(World& world) override; // דריסת מתודת הפגיעה

    void increaseBombRadius();
    void increaseMaxBombs();
    void increaseSpeed();
    void enableHammer();
    void enableRing();
};
