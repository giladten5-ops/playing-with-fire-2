#pragma once
#include <vector>

enum class CellType {
    EMPTY, // empty cell = 0
    SOLID_WALL, // solid wall = 1
};

class Board {
    private:
        int m_width;
        int m_height;
        std::vector<std::vector<CellType>> m_grid; // 2D grid of cellType vectors representing the board


    public:

        Board(int width, int height);

        int getWidth() const;
        int getHeight() const;

        CellType getCellType(int x, int y) const;
        void setCellType(int x, int y, CellType type);
};