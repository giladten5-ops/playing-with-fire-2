#pragma once
#include "World.h"
#include "../systems/ExplosionSystem.h"
#include "../systems/CollisionSystem.h"
#include "../interfaces/IInput.h"
#include "../interfaces/ILevel.h"

class Game {
    private:
        World m_world;
        ExplosionSystem m_explosionSystem;
        CollisionSystem m_collisionSystem;

    public:
        Game(int boardWidth, int boardHeight);

        void loadLevel(ILevel& level);
        void update(Command command);
        
        World& getWorld();
        const World& getWorld() const;
};