#pragma once
#include <vector>

class World;

struct Position {
    int x;
    int y;
};

class ILevel {
public:
    virtual ~ILevel() = default;
    virtual void generate(World& world) = 0;
    virtual std::vector<Position> getSpawnPoints() const = 0;
};
