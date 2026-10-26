#include "../../include/interfaces/IPushable.h"
#include "../../include/entities/Player.h"
#include "../../include/core/World.h"
#include "../../include/entities/Bomb.h"

Player::Player(int startX, int startY, int id) 
    : Entity(startX, startY), m_id(id), m_bombRadius(2), m_maxBombs(1), 
      m_speedLevel(0), m_cooldown(0), m_startX(startX), m_startY(startY), 
      m_lives(3), m_invincibilityTimer(0) {}

int Player::getId() const { return m_id; }
int Player::getLives() const { return m_lives; }

EntityType Player::getType() const {
    return EntityType::PLAYER;
}

char Player::getDisplayChar() const {
    if (m_invincibilityTimer > 0 && (m_invincibilityTimer % 4 < 2)) {
        return ' ';
    }
    return 'P';
}

void Player::update(World& world) {
    if (m_cooldown > 0) m_cooldown--;
    if (m_invincibilityTimer > 0) m_invincibilityTimer--;
}

void Player::onExplosionHit(World& world) {
    if (m_invincibilityTimer > 0) return; 
    
    m_lives--;
    if (m_lives > 0) {
        m_invincibilityTimer = 60; 
    } else {
        destroy(); 
    }
}

void Player::handleCommand(Command command, World& world) {    
    if (!m_isAlive) return;
    
    bool isMoveCommand = (command == Command::UP || command == Command::DOWN || 
                          command == Command::LEFT || command == Command::RIGHT);
    if (isMoveCommand && m_cooldown > 0) {
        return;
    }

    int targetX = m_x;
    int targetY = m_y;

    switch (command) {
        case Command::UP: targetY--; m_facingDx = 0; m_facingDy = -1; break;
        case Command::DOWN: targetY++; m_facingDx = 0; m_facingDy = 1; break;
        case Command::LEFT: targetX--; m_facingDx = -1; m_facingDy = 0; break;
        case Command::RIGHT: targetX++; m_facingDx = 1; m_facingDy = 0; break;
            
        case Command::PLACE_BOMB: {
            bool pushedBomb = false;
            if (m_hasHammer) {
                int checkX = m_x + m_facingDx;
                int checkY = m_y + m_facingDy;
                auto entitiesInFront = world.getEntitiesAt(checkX, checkY);
                for (auto* e : entitiesInFront) {
                    if (auto* pushable = dynamic_cast<IPushable*>(e)) {
                        pushable->push(m_facingDx, m_facingDy);
                        pushedBomb = true;
                    }
                }
            }

            if (!pushedBomb && world.countBombsForOwner(m_id) < m_maxBombs) {
                bool bombExists = false;
                auto entitiesHere = world.getEntitiesAt(m_x, m_y);
                for (auto* e : entitiesHere) {
                    if (e->getType() == EntityType::BOMB) {
                        bombExists = true;
                        break;
                    }
                }
                
                if (!bombExists) {
                    const int DEFAULT_BOMB_TIMER = 90;
                    world.addEntity(std::make_unique<Bomb>(m_x, m_y, DEFAULT_BOMB_TIMER, m_bombRadius, m_id));
                }
            }
            break;
        }
        default: break;
    }

    if (targetX != m_x || targetY != m_y) {
        bool canMove = world.isTileFree(targetX, targetY);

        if (!canMove && m_hasRing) {
            if (world.getBoard().getCellType(targetX, targetY) != CellType::SOLID_WALL) {
                canMove = true;
                auto entities = world.getEntitiesAt(targetX, targetY);
                for (auto* e : entities) {
                    if (e->isSolid() && e->getType() != EntityType::BOMB) {
                        canMove = false;
                        break;
                    }
                }
            }
        }

        if (canMove) {
            m_x = targetX;
            m_y = targetY;
            m_cooldown = 4 - (m_speedLevel * 2);
        }
    }
}

void Player::increaseBombRadius() { m_bombRadius++; }
void Player::increaseMaxBombs() { m_maxBombs++; }
void Player::increaseSpeed() { if (m_speedLevel < 2) m_speedLevel++; }
void Player::enableHammer() { m_hasHammer = true; }
void Player::enableRing() { m_hasRing = true; }
