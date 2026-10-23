#pragma once
#include "../interfaces/ILevel.h"
#include <vector>

class World;

struct Position {
    int x;
    int y;
};

class ClassicLevel : public ILevel {
    private:
        int m_numPlayers;
        std::vector<Position> m_spawnPoints;

        bool isSafeZone(int x, int y) const;

    public:
        ClassicLevel(int numPlayers, int boardWidth, int boardHeight);
        void generate(World& world) override;
        
        std::vector<Position> getSpawnPoints() const;
};