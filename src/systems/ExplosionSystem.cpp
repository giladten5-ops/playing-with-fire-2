#include "../../include/systems/ExplosionSystem.h"
#include "../../include/core/World.h"
#include "../../include/entities/Flame.h"
#include "../../include/entities/Bomb.h"

void ExplosionSystem::process(World& world) {
    bool hasExplodingBombs = true;

    while (hasExplodingBombs) {
        hasExplodingBombs = false;
        
        const auto& entities = world.getEntities();
        Bomb* bombToExplode = nullptr;

        for (const auto& entity : entities) {
            if (entity->isAlive() && entity->shouldExplode() && entity->getType() == EntityType::BOMB) {
                bombToExplode = static_cast<Bomb*>(entity.get());
                break;
            }
        }

        if (bombToExplode) {
            hasExplodingBombs = true;
            
            bombToExplode->destroy();
            
            int bx = bombToExplode->getX();
            int by = bombToExplode->getY();
            int radius = bombToExplode->getRadius();

            explodeTile(world, bx, by);
            
            explodeInDirection(world, bx, by, 1, 0, radius); 
            explodeInDirection(world, bx, by, -1, 0, radius); 
            explodeInDirection(world, bx, by, 0, 1, radius); 
            explodeInDirection(world, bx, by, 0, -1, radius); 
            
            world.sync();
        }
    }
}

bool ExplosionSystem::explodeTile(World& world, int targetX, int targetY) {
    if (!world.isPositionValid(targetX, targetY)) {
        return false; 
    }

    if (world.getBoard().getCellType(targetX, targetY) == CellType::SOLID_WALL) {
        return false; 
    }
    
    bool explosionStopped = false;
    auto entitiesHere = world.getEntitiesAt(targetX, targetY);
    
    for (auto* entity : entitiesHere) {
        if (entity->isAlive()) {
            entity->onExplosionHit(world);
            
            if (entity->stopsExplosion()) {
                explosionStopped = true;
            }
        }
    }

    world.addEntity(std::make_unique<Flame>(targetX, targetY, 30));

    return !explosionStopped;
}

void ExplosionSystem::explodeInDirection(World& world, int startX, int startY, int dx, int dy, int radius) {
    for (int i = 1; i <= radius; i++) {
        if (!explodeTile(world, startX + i * dx, startY + i * dy)) {
            break; 
        }
    }
}