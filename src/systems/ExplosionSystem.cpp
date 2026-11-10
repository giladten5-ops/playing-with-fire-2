#include "../../include/systems/ExplosionSystem.h"
#include "../../include/core/World.h"
#include "../../include/entities/Flame.h"
#include "../../include/entities/Bomb.h"
#include "../../include/entities/Player.h"
#include "../../include/factories/PowerUpFactory.h"

void ExplosionSystem::process(World& world) {
    bool hasExplodingBombs = true;
    int maxIterations = static_cast<int>(world.getEntities().size()) + 16;

    while (hasExplodingBombs && maxIterations-- > 0) {
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

            int bx = bombToExplode->getX();
            int by = bombToExplode->getY();
            int radius = bombToExplode->getRadius();
            int creditOwnerId = bombToExplode->getCreditOwnerId();

            bombToExplode->destroy();

            explodeTile(world, bx, by, creditOwnerId);

            explodeInDirection(world, bx, by, 1, 0, radius, creditOwnerId);
            explodeInDirection(world, bx, by, -1, 0, radius, creditOwnerId);
            explodeInDirection(world, bx, by, 0, 1, radius, creditOwnerId);
            explodeInDirection(world, bx, by, 0, -1, radius, creditOwnerId);

            world.sync();
        }
    }
}

bool ExplosionSystem::explodeTile(World& world, int targetX, int targetY, int ownerId) {
    if (!world.isPositionValid(targetX, targetY)) {
        return false;
    }

    CellType cellType = world.getBoard().getCellType(targetX, targetY);
    if (cellType == CellType::SOLID_WALL) {
        return false;
    }

    bool explosionStopped = false;
    if (cellType == CellType::BREAKABLE_WALL) {
        world.getBoard().setCellType(targetX, targetY, CellType::EMPTY);
        if (ownerId > 0) {
            world.recordWallDestroyed(ownerId);
        }
        PowerUpFactory::trySpawn(world, targetX, targetY);
        explosionStopped = true;
    }

    auto entitiesHere = world.getEntitiesAt(targetX, targetY);

    for (auto* entity : entitiesHere) {
        if (entity->isAlive()) {
            EntityType type = entity->getType();
            bool isPlayer = (type == EntityType::PLAYER);
            int victimId = isPlayer ? static_cast<Player*>(entity)->getId() : -1;
            int livesBefore = isPlayer ? static_cast<Player*>(entity)->getLives() : 0;
            bool blocksBlast = entity->stopsExplosion();

            if (type == EntityType::BOMB && ownerId > 0) {
                // Propagate credit owner in chain reactions
                static_cast<Bomb*>(entity)->push(0, 0, ownerId);
            }

            entity->onExplosionHit(world);

            if (isPlayer && ownerId > 0 && ownerId != victimId) {
                int livesAfter = entity->isAlive() ? static_cast<Player*>(entity)->getLives() : 0;
                if (livesAfter < livesBefore) {
                    world.recordEnemyHit(ownerId);
                }
                if (!entity->isAlive()) {
                    world.recordEnemyKilled(ownerId);
                }
            }

            if (blocksBlast) {
                explosionStopped = true;
            }
        }
    }

    world.addEntity(std::make_unique<Flame>(targetX, targetY, 30, ownerId));

    return !explosionStopped;
}

void ExplosionSystem::explodeInDirection(World& world, int startX, int startY, int dx, int dy, int radius, int ownerId) {
    for (int i = 1; i <= radius; i++) {
        if (!explodeTile(world, startX + i * dx, startY + i * dy, ownerId)) {
            break;
        }
    }
}
