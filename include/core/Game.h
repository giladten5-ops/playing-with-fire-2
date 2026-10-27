#pragma once
#include "World.h"
#include "../interfaces/ILevel.h"
#include "../systems/ExplosionSystem.h"
#include "../systems/CollisionSystem.h"
#include "../systems/SuddenDeathSystem.h"
#include "../interfaces/IInput.h"
#include <vector>

class Game {
private:
    World m_world;
    ExplosionSystem m_explosionSystem;
    CollisionSystem m_collisionSystem;
    SuddenDeathSystem m_suddenDeathSystem;

public:
    Game(int boardWidth, int boardHeight);
    World& getWorld();
    const World& getWorld() const;

    void loadLevel(ILevel& level, int numHumanPlayers = 0, int numBots = 0);
    void update(Command command = Command::NONE);
    void update(const std::vector<PlayerCommand>& commands);

    bool isGameOver() const;
    int getWinnerId() const;
    
    int getSuddenDeathTimer() const;
    bool isSuddenDeathActive() const;
};
