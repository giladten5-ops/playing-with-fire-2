#include "../../include/core/Board.h"

Board::Board(int width, int height) {
    m_width = width;
    m_height = height;
    m_grid.resize(m_width, std::vector<CellType>(m_height, CellType::EMPTY));
}

int Board::getWidth() const {
    return m_width;
}

int Board::getHeight() const {
    return m_height;
}

CellType Board::getCellType(int x, int y) const {
    if (x < 0 || x >= m_width || y < 0 || y >= m_height) {
        return CellType::SOLID_WALL; // Out of bounds, treat as solid wall
    }
    return m_grid[x][y];
}

void Board::setCellType(int x, int y, CellType type) {
    if (x < 0 || x >= m_width || y < 0 || y >= m_height) {
        return; // Out of bounds, do nothing
    }
    m_grid[x][y] = type;
}


