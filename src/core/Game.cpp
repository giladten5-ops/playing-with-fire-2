#include "../../include/core/Game.h"
#include "../../include/entities/Player.h"
#include "../../include/entities/DumbBot.h"
#include "../../include/entities/Bomb.h"
#include "../../include/entities/BreakableWall.h"
#include "../../include/entities/BombPowerUp.h"
#include "../../include/entities/LightningPowerUp.h"
#include "../../include/entities/SpeedPowerUp.h"
#include "../../include/entities/HammerPowerUp.h"
#include "../../include/entities/RingPowerUp.h"
#include "../../include/entities/Flame.h"
#include <memory>
#include <algorithm>
#include <cstdlib>

Game::Game(int boardWidth, int boardHeight)
    : m_world(boardWidth, boardHeight),
      m_suddenDeathSystem(80 * 30, boardWidth, boardHeight) {}

World& Game::getWorld() { return m_world; }
const World& Game::getWorld() const { return m_world; }
int Game::getSuddenDeathTimer() const { return m_suddenDeathSystem.getTicksRemaining(); }
void Game::setSuddenDeathTimer(int ticks) { m_suddenDeathSystem.setTicksRemaining(ticks); }
bool Game::isSuddenDeathActive() const { return m_suddenDeathSystem.isActive(); }

void Game::loadLevel(ILevel& level, int numHumanPlayers, int numBots, bool shuffleSpawns) {
    level.generate(m_world);
    if (numHumanPlayers > 0 || numBots > 0) {
        auto spawnPoints = level.getSpawnPoints();
        if (shuffleSpawns && spawnPoints.size() > 1) {
            for (size_t i = spawnPoints.size() - 1; i > 0; --i) {
                size_t j = static_cast<size_t>(std::rand()) % (i + 1);
                std::swap(spawnPoints[i], spawnPoints[j]);
            }
        }
        size_t currentSpawnIdx = 0;
        int nextId = 1;
        for (int i = 0; i < numHumanPlayers && currentSpawnIdx < spawnPoints.size(); ++i) {
            m_world.addEntity(std::make_unique<Player>(
                spawnPoints[currentSpawnIdx].x, spawnPoints[currentSpawnIdx].y, nextId++));
            currentSpawnIdx++;
        }
        for (int i = 0; i < numBots && currentSpawnIdx < spawnPoints.size(); ++i) {
            m_world.addEntity(std::make_unique<DumbBot>(
                spawnPoints[currentSpawnIdx].x, spawnPoints[currentSpawnIdx].y, nextId++));
            currentSpawnIdx++;
        }
        m_world.sync();
    }
}

void Game::update(Command command) {
    std::vector<PlayerCommand> commands;
    if (command != Command::NONE) commands.push_back({1, command});
    update(commands);
}

void Game::update(const std::vector<PlayerCommand>& commands) {
    for (const auto& entity : m_world.getEntities()) {
        if (entity->isAlive()) entity->update(m_world);
    }
    m_world.sync();

    if (!commands.empty()) {
        for (const auto& pc : commands) {
            Player* p = m_world.getPlayer(pc.playerId);
            if (p && p->isAlive() && !p->isBot()) {
                p->handleCommand(pc.command, m_world);
            }
        }
        m_world.sync();
    }

    m_explosionSystem.process(m_world);
    m_collisionSystem.process(m_world);
    m_suddenDeathSystem.process(m_world);
    m_world.sync();
}

bool Game::isGameOver() const {
    int alivePlayers = 0;
    for (const auto& entity : m_world.getEntities()) {
        if (entity->isAlive() && entity->getType() == EntityType::PLAYER) alivePlayers++;
    }
    return alivePlayers <= 1;
}

int Game::getWinnerId() const {
    for (const auto& entity : m_world.getEntities()) {
        if (entity->isAlive() && entity->getType() == EntityType::PLAYER) {
            return static_cast<const Player*>(entity.get())->getId();
        }
    }
    return -1;
}

void Game::reset(ILevel& level, int numHumanPlayers, int numBots) {
    m_world.clear();
    int width = m_world.getBoard().getWidth();
    int height = m_world.getBoard().getHeight();
    m_suddenDeathSystem = SuddenDeathSystem(80 * 30, width, height);
    loadLevel(level, numHumanPlayers, numBots, true);
}

PlayerInfo Game::getPlayerInfo(int playerId) const {
    PlayerInfo info;
    info.id = playerId;
    const Player* p = m_world.getPlayer(playerId);
    if (!p || !p->isAlive()) {
        return info;
    }
    info.x = p->getX();
    info.y = p->getY();
    info.lives = p->getLives();
    info.maxBombs = p->getMaxBombs();
    int activeB = m_world.countBombsForOwner(playerId);
    info.availBombs = std::max(0, info.maxBombs - activeB);
    info.bombRadius = p->getBombRadius();
    info.speedLevel = p->getSpeedLevel();
    info.cooldown = p->getCooldown();
    info.moveCooldownMax = p->getMoveCooldownMax();
    info.invincibilityTimer = p->getInvincibilityTimer();
    info.facingDx = p->getFacingDx();
    info.facingDy = p->getFacingDy();
    info.hasHammer = p->hasHammer();
    info.hasRing = p->hasRing();
    info.isBot = p->isBot();
    info.isAlive = p->isAlive();
    return info;
}

std::vector<BombInfo> Game::getBombs() const {
    std::vector<BombInfo> bombs;
    for (const auto& entity : m_world.getEntities()) {
        if (entity->isAlive() && entity->getType() == EntityType::BOMB) {
            const auto* b = static_cast<const Bomb*>(entity.get());
            BombInfo bi;
            bi.x = b->getX();
            bi.y = b->getY();
            bi.timer = b->getTimer();
            bi.radius = b->getRadius();
            bi.ownerId = b->getOwnerId();
            bi.creditOwnerId = b->getCreditOwnerId();
            bi.isSliding = b->isSliding();
            bi.slideDx = b->getSlideDx();
            bi.slideDy = b->getSlideDy();
            bi.slideCooldown = b->getSlideCooldown();
            bi.slideCooldownMax = Bomb::SLIDE_COOLDOWN_FRAMES;
            bombs.push_back(bi);
        }
    }
    return bombs;
}

void Game::clearBoard() {
    m_world.clear();
    int width = m_world.getBoard().getWidth();
    int height = m_world.getBoard().getHeight();
    m_suddenDeathSystem = SuddenDeathSystem(80 * 30, width, height);
}

void Game::setSolidWall(int x, int y, bool solid) {
    m_world.getBoard().setCellType(x, y, solid ? CellType::SOLID_WALL : CellType::EMPTY);
}

void Game::addPlayer(int x, int y, int id, bool isBot) {
    if (isBot) {
        m_world.addEntity(std::make_unique<DumbBot>(x, y, id));
    } else {
        m_world.addEntity(std::make_unique<Player>(x, y, id));
    }
    m_world.sync();
}

void Game::addBreakableWall(int x, int y) {
    m_world.getBoard().setCellType(x, y, CellType::BREAKABLE_WALL);
}

void Game::addBomb(int x, int y, int timer, int radius, int ownerId) {
    m_world.addEntity(std::make_unique<Bomb>(x, y, timer, radius, ownerId));
    m_world.sync();
}

void Game::addPowerUp(int x, int y, const std::string& type) {
    if (type == "hammer" || type == "H") m_world.addEntity(std::make_unique<HammerPowerUp>(x, y));
    else if (type == "ring" || type == "R") m_world.addEntity(std::make_unique<RingPowerUp>(x, y));
    else if (type == "bomb" || type == "B") m_world.addEntity(std::make_unique<BombPowerUp>(x, y));
    else if (type == "lightning" || type == "L") m_world.addEntity(std::make_unique<LightningPowerUp>(x, y));
    else if (type == "speed" || type == "S") m_world.addEntity(std::make_unique<SpeedPowerUp>(x, y));
    m_world.sync();
}

void Game::givePlayerPowerUp(int playerId, const std::string& type) {
    Player* p = m_world.getPlayer(playerId);
    if (!p || !p->isAlive()) return;
    if (type == "hammer" || type == "H") p->enableHammer();
    else if (type == "ring" || type == "R") p->enableRing();
    else if (type == "bomb" || type == "B") p->increaseMaxBombs();
    else if (type == "lightning" || type == "L") p->increaseBombRadius();
    else if (type == "speed" || type == "S") p->increaseSpeed();
}

void Game::fillState(int playerId, float* state) const {
    const Board& board = m_world.getBoard();
    int width = board.getWidth();
    int height = board.getHeight();

    auto setPixel = [&](int c, int x, int y, float value) {
        if (x >= 0 && x < width && y >= 0 && y < height) {
            int index = c * width * height + y * width + x;
            state[index] = std::max(state[index], value);
        }
    };
    auto getPixel = [&](int c, int x, int y) -> float {
        if (x >= 0 && x < width && y >= 0 && y < height) {
            return state[c * width * height + y * width + x];
        }
        return 0.0f;
    };

    for (int x = 0; x < width; x++) {
        for (int y = 0; y < height; y++) {
            CellType ct = board.getCellType(x, y);
            if (ct == CellType::SOLID_WALL) setPixel(0, x, y, 1.0f);
            else if (ct == CellType::BREAKABLE_WALL) setPixel(1, x, y, 1.0f);
        }
    }

    const Player* selfPlayer = m_world.getPlayer(playerId);
    if (selfPlayer) {
        int maxB = selfPlayer->getMaxBombs();
        int activeB = m_world.countBombsForOwner(playerId);
        float availB = std::max(0, maxB - activeB) / 10.0f;
        float specialVal = (selfPlayer->hasHammer() ? 0.6f : 0.0f) + (selfPlayer->hasRing() ? 0.4f : 0.0f);
        for (int i = 0; i < width * height; ++i) {
            state[8 * width * height + i] = availB;
            state[9 * width * height + i] = specialVal;
        }
    }

    std::vector<const Bomb*> activeBombs;
    for (const auto& entity : m_world.getEntities()) {
        if (!entity->isAlive()) continue;
        int ex = entity->getX(), ey = entity->getY();
        EntityType type = entity->getType();

        if (type == EntityType::FLAME) { setPixel(4, ex, ey, 1.0f); setPixel(3, ex, ey, 1.0f); }
        else if (type == EntityType::POWER_UP) setPixel(5, ex, ey, 1.0f);
        else if (type == EntityType::PLAYER) {
            const Player* player = static_cast<const Player*>(entity.get());
            if (player->getId() == playerId) {
                setPixel(6, ex, ey, player->isOnCooldown() ? 0.5f : 1.0f);
            } else {
                setPixel(7, ex, ey, 1.0f);
            }
        } else if (type == EntityType::BOMB) {
            activeBombs.push_back(static_cast<const Bomb*>(entity.get()));
        }
    }

    const int dx[] = {1, -1, 0, 0};
    const int dy[] = {0, 0, 1, -1};

    // Chain-Reaction Timer Propagation across bombs in line-of-fire
    int nBombs = static_cast<int>(activeBombs.size());
    std::vector<int> effectiveTimers(nBombs);
    for (int i = 0; i < nBombs; ++i) {
        effectiveTimers[i] = activeBombs[i]->getTimer();
    }

    bool changed = true;
    int maxIter = nBombs + 1;
    while (changed && maxIter-- > 0) {
        changed = false;
        for (int i = 0; i < nBombs; ++i) {
            int bx = activeBombs[i]->getX();
            int by = activeBombs[i]->getY();
            int radius = activeBombs[i]->getRadius();
            int t_i = effectiveTimers[i];

            for (int dir = 0; dir < 4; ++dir) {
                for (int r = 1; r <= radius; ++r) {
                    int nx = bx + dx[dir] * r;
                    int ny = by + dy[dir] * r;
                    if (!m_world.isPositionValid(nx, ny) || board.getCellType(nx, ny) == CellType::SOLID_WALL) break;
                    if (getPixel(1, nx, ny) > 0.0f) break; // Breakable wall blocks chain

                    bool hitOtherBomb = false;
                    for (int j = 0; j < nBombs; ++j) {
                        if (i != j && activeBombs[j]->getX() == nx && activeBombs[j]->getY() == ny) {
                            if (t_i < effectiveTimers[j]) {
                                effectiveTimers[j] = t_i;
                                changed = true;
                            }
                            hitOtherBomb = true;
                        }
                    }
                    if (hitOtherBomb) break;
                }
            }
        }
    }

    for (int bIdx = 0; bIdx < nBombs; ++bIdx) {
        const Bomb* bomb = activeBombs[bIdx];
        int ex = bomb->getX(), ey = bomb->getY();
        float tNorm = std::clamp(1.0f - (static_cast<float>(effectiveTimers[bIdx]) / 100.0f), 0.1f, 1.0f);
        setPixel(2, ex, ey, tNorm);
        setPixel(3, ex, ey, tNorm);

        auto projectBlastFrom = [&](int cx, int cy, float urgency) {
            setPixel(3, cx, cy, urgency);
            for (int i = 0; i < 4; ++i) {
                for (int r = 1; r <= bomb->getRadius(); ++r) {
                    int nx = cx + dx[i] * r, ny = cy + dy[i] * r;
                    if (!m_world.isPositionValid(nx, ny) || board.getCellType(nx, ny) == CellType::SOLID_WALL) break;
                    setPixel(3, nx, ny, urgency);
                    if (getPixel(1, nx, ny) > 0.0f) break;
                }
            }
        };

        projectBlastFrom(ex, ey, tNorm);

        // If the bomb is sliding, project its slide trajectory and final stopping blast zone
        if (bomb->isSliding()) {
            int sdx = bomb->getSlideDx();
            int sdy = bomb->getSlideDy();
            int curX = ex;
            int curY = ey;
            int ticksLeft = std::max(0, effectiveTimers[bIdx]);
            int stepTicks = Bomb::SLIDE_COOLDOWN_FRAMES + 1;
            int maxSlideSteps = std::max(1, (ticksLeft + stepTicks - 1) / stepTicks);

            for (int s = 1; s <= maxSlideSteps; ++s) {
                int nextX = curX + sdx;
                int nextY = curY + sdy;
                if (!Bomb::canSlideTo(m_world, nextX, nextY)) {
                    break;
                }
                curX = nextX;
                curY = nextY;
                float slideDanger = std::clamp(std::max(tNorm, 0.72f - 0.04f * s), 0.25f, 1.0f);
                setPixel(3, curX, curY, slideDanger);
            }
            if (curX != ex || curY != ey) {
                projectBlastFrom(curX, curY, tNorm);
            }
        }
    }

    // Imminent Sudden Death spiral danger projection into Channel 3 (danger)
    auto sdTiles = m_suddenDeathSystem.getImminentDangerTiles(90);
    for (const auto& sdt : sdTiles) {
        float sdUrgency = std::clamp(1.0f - (static_cast<float>(sdt.ticksUntilDrop) / 95.0f), 0.25f, 1.0f);
        setPixel(3, sdt.x, sdt.y, sdUrgency);
    }
}

std::vector<float> Game::getState(int playerId) const {
    const Board& board = m_world.getBoard();
    int width = board.getWidth();
    int height = board.getHeight();
    int channels = 10;

    std::vector<float> state(channels * width * height, 0.0f);
    fillState(playerId, state.data());
    return state;
}

StepResult Game::step(int playerId, Command action, const std::vector<PlayerCommand>& extraCommands) {
    StepResult result;
    result.isDone = false;
    result.reward = -0.01f;

    const Player* player = m_world.getPlayer(playerId);
    bool wasAlive = player && player->isAlive();
    int oldX = wasAlive ? player->getX() : -1;
    int oldY = wasAlive ? player->getY() : -1;
    int livesBefore = wasAlive ? player->getLives() : 0;
    int maxBombsBefore = wasAlive ? player->getMaxBombs() : 0;
    int radiusBefore = wasAlive ? player->getBombRadius() : 0;
    int speedBefore = wasAlive ? player->getSpeedLevel() : 0;
    bool hammerBefore = wasAlive ? player->hasHammer() : false;
    bool ringBefore = wasAlive ? player->hasRing() : false;
    int bombsOwnedBefore = m_world.countBombsForOwner(playerId);

    int slidingBefore = 0;
    for (const auto& entity : m_world.getEntities()) {
        if (entity->isAlive() && entity->getType() == EntityType::BOMB) {
            const auto* b = static_cast<const Bomb*>(entity.get());
            if (b->isSliding() && b->getCreditOwnerId() == playerId) slidingBefore++;
        }
    }

    m_world.popWallsDestroyed(playerId);
    m_world.popEnemiesHit(playerId);
    m_world.popEnemiesKilled(playerId);

    std::vector<PlayerCommand> commands;
    if (action != Command::NONE) commands.push_back({playerId, action});
    for (const auto& ec : extraCommands) {
        if (ec.playerId != playerId && ec.command != Command::NONE) {
            commands.push_back(ec);
        }
    }
    update(commands);

    if (action == Command::PLACE_BOMB && m_world.countBombsForOwner(playerId) > bombsOwnedBefore) {
        result.bombPlaced = true;
    }

    int slidingAfter = 0;
    for (const auto& entity : m_world.getEntities()) {
        if (entity->isAlive() && entity->getType() == EntityType::BOMB) {
            const auto* b = static_cast<const Bomb*>(entity.get());
            if (b->isSliding() && b->getCreditOwnerId() == playerId) slidingAfter++;
        }
    }
    if (slidingAfter > slidingBefore) {
        result.bombPushed = true;
    }

    int wallsDestroyedByPlayer = m_world.popWallsDestroyed(playerId);
    result.wallsDestroyed = wallsDestroyedByPlayer;
    if (wallsDestroyedByPlayer > 0) result.reward += wallsDestroyedByPlayer * 3.0f;

    player = m_world.getPlayer(playerId);
    bool isAliveNow = player && player->isAlive();

    if (isAliveNow) {
        result.moved = (player->getX() != oldX || player->getY() != oldY);
        if (player->getLives() < livesBefore) {
            result.livesLost = (livesBefore - player->getLives());
            result.reward -= result.livesLost * 25.0f;
        }

        int powerUpsGained = 0;
        if (player->getMaxBombs() > maxBombsBefore) powerUpsGained++;
        if (player->getBombRadius() > radiusBefore) powerUpsGained++;
        if (player->getSpeedLevel() > speedBefore) powerUpsGained++;
        if (player->hasHammer() && !hammerBefore) powerUpsGained++;
        if (player->hasRing() && !ringBefore) powerUpsGained++;

        result.powerUpsCollected = powerUpsGained;
        if (powerUpsGained > 0) result.reward += powerUpsGained * 8.0f;
    } else if (wasAlive) {
        result.livesLost = livesBefore;
        result.reward -= result.livesLost * 25.0f;
    }

    int enemiesHitByPlayer = m_world.popEnemiesHit(playerId);
    if (enemiesHitByPlayer > 0) {
        result.enemiesHit = enemiesHitByPlayer;
        result.reward += result.enemiesHit * 10.0f;
    }

    int enemiesKilledByPlayer = m_world.popEnemiesKilled(playerId);
    if (enemiesKilledByPlayer > 0) {
        result.enemiesKilled = enemiesKilledByPlayer;
        result.reward += result.enemiesKilled * 20.0f;
    }

    result.isDone = isGameOver();
    if (wasAlive && !isAliveNow) {
        result.died = true;
        result.reward -= 100.0f;
        result.isDone = true;
    } else if (result.isDone && isAliveNow) {
        result.won = true;
        result.reward += 100.0f;
    }

    return result;
}

std::vector<PowerUpInfo> Game::getPowerUps() const {
    std::vector<PowerUpInfo> powerUps;
    for (const auto& entity : m_world.getEntities()) {
        if (entity->isAlive() && entity->getType() == EntityType::POWER_UP) {
            PowerUpInfo pui;
            pui.x = entity->getX();
            pui.y = entity->getY();
            pui.type = entity->getDisplayChar(); 
            powerUps.push_back(pui);
        }
    }
    return powerUps;
}

std::vector<FlameInfo> Game::getFlames() const {
    std::vector<FlameInfo> flames;
    for (const auto& entity : m_world.getEntities()) {
        if (entity->isAlive() && entity->getType() == EntityType::FLAME) {
            const auto* flame = static_cast<const Flame*>(entity.get());
            FlameInfo fi;
            fi.x = flame->getX();
            fi.y = flame->getY();
            fi.timer = flame->getTimer();
            fi.ownerId = flame->getOwnerId();
            fi.creditOwnerId = flame->getCreditOwnerId();
            flames.push_back(fi);
        }
    }
    return flames;
}

std::vector<std::vector<int>> Game::getBoardGrid() const {
    const Board& board = m_world.getBoard();
    int width = board.getWidth();
    int height = board.getHeight();
    std::vector<std::vector<int>> grid(height, std::vector<int>(width, 0));

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            CellType ct = board.getCellType(x, y);
            if (ct == CellType::SOLID_WALL) {
                grid[y][x] = 1;
            } else if (ct == CellType::BREAKABLE_WALL) {
                grid[y][x] = 2;
            }
        }
    }
    return grid;
}
