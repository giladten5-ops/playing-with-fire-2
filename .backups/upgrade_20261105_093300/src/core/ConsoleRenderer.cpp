#include "../../include/core/ConsoleRenderer.h"
#include "../../include/core/World.h"
#include "../../include/entities/Player.h"
#include <iostream>
#include <vector>
#include <string>

namespace {
    int getRenderPriority(EntityType type) {
        switch (type) {
            case EntityType::POWER_UP:       return 1;
            case EntityType::BOMB:           return 2;
            case EntityType::BREAKABLE_WALL: return 3;
            case EntityType::PLAYER:         return 4;
            case EntityType::FLAME:          return 5;
        }
        return 0;
    }
}

void ConsoleRenderer::render(const World& world, int sdTimerTicks, bool sdActive) {
    const Board& board = world.getBoard();
    int width = board.getWidth();
    int height = board.getHeight();

    std::vector<std::vector<char>> display(width, std::vector<char>(height, ' '));
    std::vector<std::vector<int>> priority(width, std::vector<int>(height, 0));

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            CellType cellType = board.getCellType(x, y);
            if (cellType == CellType::SOLID_WALL) {
                display[x][y] = '#';
                priority[x][y] = 10;
            }
        }
    }

    for (const auto& entity : world.getEntities()) {
        if (!entity->isAlive()) continue;

        int ex = entity->getX();
        int ey = entity->getY();

        if (ex >= 0 && ex < width && ey >= 0 && ey < height) {
            char ch = entity->getDisplayChar();
            if (ch == ' ') continue;

            int p = getRenderPriority(entity->getType());
            if (p >= priority[ex][ey]) {
                display[ex][ey] = ch;
                priority[ex][ey] = p;
            }
        }
    }

    std::cout << "\033[2J\033[1;1H";

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            std::cout << display[x][y] << ' ' << ' ';
        }
        std::cout << std::endl;
    }

    std::cout << "\n============================================\n";
    
    // תצוגת ההתראה של פתאום-מוות
    if (sdActive) {
        std::cout << "      !!! SUDDEN DEATH ACTIVE !!!\n";
    } else if (sdTimerTicks >= 0) {
        int seconds = sdTimerTicks / 30;
        std::cout << "      Sudden Death in: " << seconds << "s\n";
    }
    std::cout << "--------------------------------------------\n";

    for (const auto& entity : world.getEntities()) {
        if (entity->isAlive() && entity->getType() == EntityType::PLAYER) {
            const Player* p = static_cast<const Player*>(entity.get());

            std::cout << " " << p->getDisplayName() << " | ";
            std::cout << "Lives: " << p->getLives() << " | ";
            std::cout << "Bombs: " << p->getMaxBombs() << " | ";
            std::cout << "Rad: " << p->getBombRadius() << " | ";
            std::cout << "Spd: " << p->getSpeedLevel();

            if (p->hasHammer()) std::cout << " [H]";
            if (p->hasRing()) std::cout << " [R]";

            std::cout << "\n";
        }
    }
    std::cout << "============================================\n";
}
