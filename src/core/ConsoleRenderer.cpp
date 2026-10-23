#include "../../include/core/ConsoleRenderer.h"
#include <iostream>
#include <vector>

void ConsoleRenderer::render(const World& world) {
    const Board& board = world.getBoard();
    int width = board.getWidth();
    int height = board.getHeight();

    std::vector<std::vector<char>> display(width, std::vector<char>(height, ' '));

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            CellType cellType = board.getCellType(x, y);
            if (cellType == CellType::SOLID_WALL) {
                display[x][y] = '#';
            }
        }
    }

    for (const auto& entity : world.getEntities()) {
        int ex = entity->getX();
        int ey = entity->getY();

        if (ex >= 0 && ex < width && ey >= 0 && ey < height && entity->isAlive()) {
            display[ex][ey] = entity->getDisplayChar();
        }
    }

    std::cout << "\033[2J\033[1;1H"; 

    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            std::cout << display[x][y] << ' ' << ' ';
        }
        std::cout << std::endl;
    }
}