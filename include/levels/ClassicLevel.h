#pragma once
#include "../interfaces/ILevel.h"
#include <vector>

class World;

class ClassicLevel : public ILevel {
private:
    int m_numPlayers;
    int m_wallDensityPercent;
    std::vector<Position> m_spawnPoints;

    bool isSafeZone(int x, int y) const;

public:
    ClassicLevel(int numPlayers, int boardWidth, int boardHeight, int wallDensityPercent = 65);
    void generate(World& world) override;
    std::vector<Position> getSpawnPoints() const override;
};
