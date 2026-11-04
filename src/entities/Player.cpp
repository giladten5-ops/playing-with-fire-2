#include "../../include/interfaces/IPushable.h"
#include "../../include/entities/Player.h"
#include "../../include/core/World.h"
#include "../../include/entities/Bomb.h"

Player::Player(int startX, int startY, int id)
    : Entity(startX, startY),
      m_id(id),
      m_bombRadius(INITIAL_BOMB_RADIUS),
      m_maxBombs(INITIAL_MAX_BOMBS),
      m_speedLevel(0),
      m_cooldown(0),
      m_lives(INITIAL_LIVES),
      m_invincibilityTimer(0) {}

int Player::getId() const { return m_id; }
int Player::getLives() const { return m_lives; }
int Player::getMaxBombs() const { return m_maxBombs; }
int Player::getBombRadius() const { return m_bombRadius; }
int Player::getSpeedLevel() const { return m_speedLevel; }
int Player::getCooldown() const { return m_cooldown; }
int Player::getInvincibilityTimer() const { return m_invincibilityTimer; }
int Player::getFacingDx() const { return m_facingDx; }
int Player::getFacingDy() const { return m_facingDy; }
bool Player::hasHammer() const { return m_hasHammer; }
bool Player::hasRing() const { return m_hasRing; }

bool Player::isBot() const { return false; }
std::string Player::getDisplayName() const { return "P" + std::to_string(m_id); }

bool Player::isOnCooldown() const { return m_cooldown > 0; }
void Player::addCooldown(int frames) { if (frames > 0) m_cooldown += frames; }
bool Player::canPlaceBomb(const World& world) const { return world.countBombsForOwner(m_id) < m_maxBombs; }

EntityType Player::getType() const { return EntityType::PLAYER; }

char Player::getDisplayChar() const {
    if (m_invincibilityTimer > 0 && (m_invincibilityTimer % 4 < 2)) {
        return ' ';
    }
    return 'P';
}

void Player::update(World& /*world*/) {
    if (m_cooldown > 0) m_cooldown--;
    if (m_invincibilityTimer > 0) m_invincibilityTimer--;
}

void Player::onExplosionHit(World& /*world*/) {
    if (m_invincibilityTimer > 0) return;
    m_lives--;
    if (m_lives > 0) {
        m_invincibilityTimer = INVINCIBILITY_FRAMES;
    } else {
        destroy();
    }
}

void Player::tryPlaceOrPushBomb(World& world) {
    int cx = getX();
    int cy = getY();

    // Standing on a bomb: do nothing (neither place duplicate bomb nor push from on top)
    for (auto* e : world.getEntitiesAt(cx, cy)) {
        if (e->isAlive() && e->getType() == EntityType::BOMB) {
            return;
        }
    }

    bool pushedBomb = false;

    if (m_hasHammer && (m_facingDx != 0 || m_facingDy != 0)) {
        int checkX = cx + m_facingDx;
        int checkY = cy + m_facingDy;
        int destX = checkX + m_facingDx;
        int destY = checkY + m_facingDy;

        if (Bomb::canSlideTo(world, destX, destY)) {
            auto entitiesInFront = world.getEntitiesAt(checkX, checkY);
            for (auto* e : entitiesInFront) {
                if (!e->isAlive()) continue;
                if (auto* pushable = dynamic_cast<IPushable*>(e)) {
                    pushable->push(m_facingDx, m_facingDy, m_id);
                    pushedBomb = true;
                    break;
                }
            }
        }
    }

    if (!pushedBomb && canPlaceBomb(world)) {
        world.addEntity(std::make_unique<Bomb>(cx, cy, DEFAULT_BOMB_TIMER, m_bombRadius, m_id));
    }
}

void Player::tryMove(int targetX, int targetY, World& world) {
    bool canMove = world.isTileFree(targetX, targetY);

    if (!canMove && m_hasRing && world.isPositionValid(targetX, targetY)) {
        if (world.getBoard().getCellType(targetX, targetY) != CellType::SOLID_WALL) {
            canMove = true;
            auto entities = world.getEntitiesAt(targetX, targetY);
            for (auto* e : entities) {
                if (e->isAlive() && e->isSolid() && e->getType() != EntityType::BOMB) {
                    canMove = false;
                    break;
                }
            }
        }
    }

    if (canMove) {
        setX(targetX);
        setY(targetY);
        m_cooldown = BASE_MOVE_COOLDOWN - (m_speedLevel * 2);
    }
}

void Player::handleCommand(Command command, World& world) {
    if (!isAlive()) return;

    if (command == Command::PLACE_BOMB) {
        tryPlaceOrPushBomb(world);
        return;
    }

    int newDx = 0;
    int newDy = 0;
    switch (command) {
        case Command::UP:    newDx = 0;  newDy = -1; break;
        case Command::DOWN:  newDx = 0;  newDy = 1;  break;
        case Command::LEFT:  newDx = -1; newDy = 0;  break;
        case Command::RIGHT: newDx = 1;  newDy = 0;  break;
        default: return;
    }

    int cx = getX();
    int cy = getY();
    int targetX = cx + newDx;
    int targetY = cy + newDy;

    bool wasFacingTarget = (m_facingDx == newDx && m_facingDy == newDy);
    m_facingDx = newDx;
    m_facingDy = newDy;

    if (isOnCooldown()) {
        return;
    }

    // If a bomb is in the target tile and the player wasn't facing it yet,
    // rotate in place first without stepping onto the bomb.
    if (m_hasRing && m_hasHammer && !wasFacingTarget && !isBot() && world.isPositionValid(targetX, targetY)) {
        for (auto* e : world.getEntitiesAt(targetX, targetY)) {
            if (e->isAlive() && e->getType() == EntityType::BOMB) {
                return;
            }
        }
    }

    tryMove(targetX, targetY, world);
}

void Player::increaseBombRadius() { m_bombRadius++; }
void Player::increaseMaxBombs() { m_maxBombs++; }
void Player::increaseSpeed() { if (m_speedLevel < MAX_SPEED_LEVEL) m_speedLevel++; }
void Player::enableHammer() { m_hasHammer = true; }
void Player::enableRing() { m_hasRing = true; }
