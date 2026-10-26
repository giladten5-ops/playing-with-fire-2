#pragma once
#include "World.h"
#include "../interfaces/ILevel.h"
#include "../systems/ExplosionSystem.h"
#include "../systems/CollisionSystem.h"
#include "../interfaces/IInput.h"

class Game {
private:
    World m_world;
    ExplosionSystem m_explosionSystem;
    CollisionSystem m_collisionSystem;

public:
    Game(int boardWidth, int boardHeight);
    World& getWorld();
    const World& getWorld() const;
    void loadLevel(ILevel& level);
    void update(Command command);
    
    bool isGameOver() const;
    int getWinnerId() const;
};
