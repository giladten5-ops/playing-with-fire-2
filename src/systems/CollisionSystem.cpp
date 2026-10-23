#include "../../include/systems/CollisionSystem.h"
#include "../../include/core/World.h"
#include "../../include/entities/Entity.h"

void CollisionSystem::process(World& world) {
    const auto& entities = world.getEntities();
    
    for (size_t i = 0; i < entities.size(); ++i) {
        if (!entities[i]->isAlive()) continue;
        
        for (size_t j = i + 1; j < entities.size(); ++j) {
            if (!entities[j]->isAlive()) continue;
            
            if (entities[i]->getX() == entities[j]->getX() && 
                entities[i]->getY() == entities[j]->getY()) {
                
                entities[i]->onIntersect(*entities[j], world);
                entities[j]->onIntersect(*entities[i], world);
            }
        }
    }
}