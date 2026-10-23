#include "../../include/core/Game.h"

Game::Game(int boardWidth, int boardHeight) 
    : m_world(boardWidth, boardHeight) {}

World& Game::getWorld() {
    return m_world;
}

const World& Game::getWorld() const {
    return m_world;
}

void Game::loadLevel(ILevel& level) {
    level.generate(m_world);
}

void Game::update(Command command) {
    if (command != Command::NONE) {
        for (const auto& entity : m_world.getEntities()) {
            if (entity->isAlive()) {
                entity->handleCommand(command, m_world);
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
    
    m_world.sync();
}