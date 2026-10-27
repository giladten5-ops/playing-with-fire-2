#pragma once

class World;

class SuddenDeathSystem {
private:
    int m_ticksUntilStart;
    int m_dropCooldown;
    int m_currentCooldown;

    int m_minX, m_maxX;
    int m_minY, m_maxY;
    int m_x, m_y;
    int m_dx, m_dy;

    bool m_isFinished;

public:
    SuddenDeathSystem(int startDelayTicks, int boardWidth, int boardHeight);
    void process(World& world);
    
    int getTicksRemaining() const;
    bool isActive() const;
};
