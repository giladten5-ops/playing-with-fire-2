#pragma once
#include "Player.h"
#include <string>

class DumbBot : public Player {
private:
    static constexpr int BOT_REACTION_COOLDOWN = 4;
    Command m_currentDir = Command::NONE;

    bool canStepOn(int x, int y, const World& world) const;
    bool hasClearBlastPath(int bx, int by, int tx, int ty, const World& world) const;
    bool isTileDangerous(int x, int y, const World& world) const;
    bool isTileDangerousWithExtraBomb(int x, int y, const World& world, int extraBx, int extraBy, int extraRadius) const;
    Command findEscapeDirection(const World& world, int extraBx = -1, int extraBy = -1, int extraRadius = 0) const;

public:
    DumbBot(int startX, int startY, int id);

    bool isBot() const override;
    std::string getDisplayName() const override;
    char getDisplayChar() const override;
    void update(World& world) override;
};
