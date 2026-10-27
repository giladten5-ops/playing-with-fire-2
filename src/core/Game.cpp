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
