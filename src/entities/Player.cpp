#include "../../include/entities/Player.h"
#include "../../include/core/World.h"
#include "../../include/entities/Bomb.h"

Player::Player(int startX, int startY, int id) 
    : Entity(startX, startY), m_id(id), m_bombRadius(2), m_maxBombs(1) {}
    
EntityType Player::getType() const {
    return EntityType::PLAYER;
}

char Player::getDisplayChar() const { return 'P'; }

void Player::update(World& world) {
}

void Player::handleCommand(Command command, World& world) {    
    if (!m_isAlive) return;
    
    int targetX = m_x;
    int targetY = m_y;

    switch (command) {
        case Command::UP:
            targetY--;
            break;
        case Command::DOWN:
            targetY++;
            break;
        case Command::LEFT:
            targetX--;
            break;
        case Command::RIGHT:
            targetX++;
            break;
        case Command::PLACE_BOMB: {
            if (world.countBombsForOwner(m_id) < m_maxBombs) {
                bool bombExists = false;
                auto entitiesHere = world.getEntitiesAt(m_x, m_y);
                for (auto* e : entitiesHere) {
                    if (e->getType() == EntityType::BOMB) {
                        bombExists = true;
                        break;
                    }
                }
                
                if (!bombExists) {
                    const int DEFAULT_BOMB_TIMER = 30;
                    world.addEntity(std::make_unique<Bomb>(m_x, m_y, DEFAULT_BOMB_TIMER, m_bombRadius, m_id));
                }
            }
            break;
        }
        default:
            break;
    }

    if (targetX != m_x || targetY != m_y) {
        if (world.isTileFree(targetX, targetY)) {
            m_x = targetX;
            m_y = targetY;
        }
    }
}

void Player::increaseBombRadius() {
    m_bombRadius++;
}

void Player::increaseMaxBombs() {
    m_maxBombs++;
}