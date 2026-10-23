#include "../../include/levels/ClassicLevel.h"
#include "../../include/core/World.h"
#include "../../include/entities/BreakableWall.h"
#include <cstdlib>

ClassicLevel::ClassicLevel(int numPlayers, int boardWidth, int boardHeight) {
    m_numPlayers = numPlayers;
    
    if (numPlayers >=1) m_spawnPoints.push_back({0, 0}); 
    if (numPlayers >=2) m_spawnPoints.push_back({boardWidth - 1, boardHeight - 1}); 
    if (numPlayers >=3) m_spawnPoints.push_back({0, boardHeight - 1}); 
    if (numPlayers >=4) m_spawnPoints.push_back({boardWidth - 1, 0}); 
}

std::vector<Position> ClassicLevel::getSpawnPoints() const {
    return m_spawnPoints;
}

bool ClassicLevel::isSafeZone(int x, int y) const {
    for (const auto& spawnPoint : m_spawnPoints) {
        int manhattanDistance = abs(spawnPoint.x - x) + abs(spawnPoint.y - y);
        if (manhattanDistance <= 1) { 
            return true;
        }
    }
    return false;
}

void ClassicLevel::generate(World& world) {
    Board& board = world.getBoard();
    int width = board.getWidth();
    int height = board.getHeight();

    for (int x = 0; x < width; x++) {
        for (int y = 0; y < height; y++) {
            if ((x % 2) != 0 && (y % 2) != 0) {
                board.setCellType(x, y, CellType::SOLID_WALL);
            }
        }
    }
    
    for (int x = 0; x < width; x++) {
        for (int y = 0; y < height; y++) {
            if (board.getCellType(x, y) == CellType::SOLID_WALL) {
                continue;
            }
            if (rand() % 100 < 65) { 
                if (!isSafeZone(x, y)) { 
                    world.addEntity(std::make_unique<BreakableWall>(x, y));
                }
            }
        }
    }
    world.sync();
}