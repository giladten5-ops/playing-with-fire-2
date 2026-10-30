#include "../../include/core/Game.h"
#include "../../include/entities/Player.h"
#include "../../include/entities/DumbBot.h"
#include <memory>

Game::Game(int boardWidth, int boardHeight)
    : m_world(boardWidth, boardHeight),
      m_suddenDeathSystem(120 * 30, boardWidth, boardHeight) // 120 seconds (2 minutes) * 30 FPS
{}

World& Game::getWorld() { return m_world; }
const World& Game::getWorld() const { return m_world; }

int Game::getSuddenDeathTimer() const { return m_suddenDeathSystem.getTicksRemaining(); }
bool Game::isSuddenDeathActive() const { return m_suddenDeathSystem.isActive(); }

void Game::loadLevel(ILevel& level, int numHumanPlayers, int numBots) {
    level.generate(m_world);

    if (numHumanPlayers > 0 || numBots > 0) {
        auto spawnPoints = level.getSpawnPoints();
        int totalSpawns = static_cast<int>(spawnPoints.size());
        int currentSpawnIdx = 0;
        int nextId = 1;

        for (int i = 0; i < numHumanPlayers && currentSpawnIdx < totalSpawns; ++i) {
            m_world.addEntity(std::make_unique<Player>(
                spawnPoints[currentSpawnIdx].x, spawnPoints[currentSpawnIdx].y, nextId));
            currentSpawnIdx++;
            nextId++;
        }

        for (int i = 0; i < numBots && currentSpawnIdx < totalSpawns; ++i) {
            m_world.addEntity(std::make_unique<DumbBot>(
                spawnPoints[currentSpawnIdx].x, spawnPoints[currentSpawnIdx].y, nextId));
            currentSpawnIdx++;
            nextId++;
        }

        m_world.sync();
    }
}

void Game::update(Command command) {
    std::vector<PlayerCommand> commands;
    if (command != Command::NONE) {
        commands.push_back({1, command});
    }
    update(commands);
}

void Game::update(const std::vector<PlayerCommand>& commands) {
    if (!commands.empty()) {
        for (const auto& pc : commands) {
            Player* p = m_world.getPlayer(pc.playerId);
            if (p && p->isAlive() && !p->isBot()) {
                p->handleCommand(pc.command, m_world);
            }
        }
        m_world.sync();
    }

    for (const auto& entity : m_world.getEntities()) {
        if (entity->isAlive()) {
            entity->update(m_world);
        }
    }
    m_world.sync();

    m_explosionSystem.process(m_world);
    m_collisionSystem.process(m_world);
    m_suddenDeathSystem.process(m_world);
    m_world.sync();
}

bool Game::isGameOver() const {
    int alivePlayers = 0;
    for (const auto& entity : m_world.getEntities()) {
        if (entity->isAlive() && entity->getType() == EntityType::PLAYER) {
            alivePlayers++;
        }
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
    m_suddenDeathSystem = SuddenDeathSystem(120 * 30, width, height); // Reset sudden death system
    loadLevel(level, numHumanPlayers, numBots);
}

std::vector<float> Game::getState(int playerId) const {
    const Board& board = m_world.getBoard();
    int width = board.getWidth();
    int height = board.getHeight();
    int channels = 7; // 7 channels: walls, destructible, bombs, explosions, powerUps, the player, other players

    std::vector<float> state(channels * width * height, 0.0f); // Initialize all to 0.0f

    auto setPixel = [&](int c, int x, int y, float value) {
        if (x >= 0 && x < width && y >= 0 && y < height) {
            state[c * width * height + y * width + x] = value;
        }
    };

    for (int x = 0; x < width; x++) {
        for (int y = 0; y < height; y++) {
            if (board.getCellType(x, y) == CellType::SOLID_WALL) {
                setPixel(0, x, y, 1.0f);
            }
        }
    }

    for (const auto& entity : m_world.getEntities()) {
        if (!entity->isAlive()) continue;

        int ex = entity->getX();
        int ey = entity->getY();
        EntityType type = entity->getType();

        if (type == EntityType::BREAKABLE_WALL) {
            setPixel(1, ex, ey, 1.0f);
        } else if (type == EntityType::BOMB) {
            setPixel(2, ex, ey, 1.0f);
        } else if (type == EntityType::FLAME) {
            setPixel(3, ex, ey, 1.0f);
        } else if (type == EntityType::POWER_UP) {
            setPixel(4, ex, ey, 1.0f);
        } else if (type == EntityType::PLAYER) {
            const Player* player = static_cast<const Player*>(entity.get());
            if (player->getId() == playerId) {
                setPixel(5, ex, ey, 1.0f); // The player itself
            } else {
                setPixel(6, ex, ey, 1.0f); // Other players
            }
        }
    }

    return state;
}


StepResult Game::step(int playerId, Command action) {
    StepResult result;
    result.isDone = false;
    result.reward = -0.1f; // Step penalty to discourage stalling

    const Player* player = m_world.getPlayer(playerId);
    bool wasAlive = player && player->isAlive();

    // Count breakable walls before executing actions and explosions
    int wallsBefore = m_world.countBreakableWalls();

    std::vector<PlayerCommand> commands;
    if (action != Command::NONE) {
        commands.push_back({playerId, action});
    }
    update(commands); // Process player move, bomb ticks, explosions, sudden death

    // Count breakable walls after update
    int wallsAfter = m_world.countBreakableWalls();
    int wallsDestroyed = wallsBefore - wallsAfter;
    if (wallsDestroyed > 0) {
        result.reward += wallsDestroyed * 2.0f; // Reward for destroying walls
    }

    player = m_world.getPlayer(playerId);
    bool isAliveNow = player && player->isAlive();
    result.isDone = isGameOver();

    if (wasAlive && !isAliveNow) {
        result.reward = -100.0f; // Player died
        result.isDone = true;
    } else if (result.isDone && isAliveNow) {
        result.reward = 100.0f; // Player won
    }
    return result;
}