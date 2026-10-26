#pragma once
#include "Player.h"

class DumbBot : public Player {
private:
    Command m_currentDir = Command::NONE;
    bool isTileDangerous(int x, int y, World& world) const;

public:
    DumbBot(int startX, int startY, int id);
    char getDisplayChar() const override;
    void update(World& world) override;
};
