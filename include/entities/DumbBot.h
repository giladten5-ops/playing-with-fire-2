#pragma once
#include "Player.h"
#include <string>

class DumbBot : public Player {
public:
    static constexpr int DEFAULT_SD_CAUTION_PERCENT = 75;

    static void setSuddenDeathCautionPercent(int percent);
    static int getSuddenDeathCautionPercent();

private:
    static constexpr int BOT_REACTION_COOLDOWN = 6;
    static constexpr int SPAWN_BOMB_WARMUP_TICKS = 30;
    static constexpr int BOMB_PLACEMENT_COOLDOWN = 45;
    static constexpr int SD_DECISION_WINDOW_TICKS = 24;

    static int s_sdCautionPercent;

    Command m_currentDir = Command::NONE;
    int m_ticksAlive = 0;
    int m_bombCooldown = 0;
    int m_sdCautionPercent = DEFAULT_SD_CAUTION_PERCENT;
    int m_sdLookaheadTicks = 60;
    int m_sdDecisionTimer = 0;
    bool m_sdAwareThisWindow = true;
    int m_enemyBombLookaheadTicks = 9999;

    bool canStepOn(int x, int y, const World& world) const;
    bool hasClearBlastPath(int bx, int by, int tx, int ty, const World& world) const;
    int getTileTimeToExplode(int x, int y, const World& world, int extraBx = -1, int extraBy = -1, int extraRadius = 0) const;
    bool isTileDangerous(int x, int y, const World& world) const;
    bool isTileDangerousWithExtraBomb(int x, int y, const World& world, int extraBx, int extraBy, int extraRadius) const;
    Command findEscapeDirection(const World& world, int extraBx = -1, int extraBy = -1, int extraRadius = 0) const;
    Command findExplorationDirection(const World& world) const;

public:
    DumbBot(int startX, int startY, int id);

    bool isBot() const override;
    std::string getDisplayName() const override;
    char getDisplayChar() const override;
    void update(World& world) override;

    void setEnemyBombLookaheadTicks(int ticks);
    int getEnemyBombLookaheadTicks() const;
};
