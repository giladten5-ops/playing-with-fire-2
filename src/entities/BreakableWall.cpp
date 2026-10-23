#include "../../include/entities/BreakableWall.h"

BreakableWall::BreakableWall(int x, int y) : Entity(x, y) {}

EntityType BreakableWall::getType() const {
    return EntityType::BREAKABLE_WALL;
}

char BreakableWall::getDisplayChar() const { return 'B'; }

void BreakableWall::update(World& world) {
    // BreakableWall does not change over time
}

bool BreakableWall::isSolid() const {
    return true;
}

bool BreakableWall::stopsExplosion() const {
    return true;
}