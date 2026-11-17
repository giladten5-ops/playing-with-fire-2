#pragma once
#include "World.h"
#include "../interfaces/ILevel.h"
#include "../systems/ExplosionSystem.h"
#include "../systems/CollisionSystem.h"
#include "../systems/SuddenDeathSystem.h"
#include "../interfaces/IInput.h"
#include <vector>
#include <string>

struct StepResult {
    bool isDone = false;
    float reward = 0.0f;
    int wallsDestroyed = 0;
    int enemiesHit = 0;
    int enemiesKilled = 0;
    int powerUpsCollected = 0;
    int livesLost = 0;
    bool moved = false;
    bool bombPlaced = false;
    bool bombPushed = false;
    bool won = false;
    bool died = false;
};

struct PlayerInfo {
    int id = -1;
    int x = -1;
    int y = -1;
    int lives = 0;
    int maxBombs = 1;
    int availBombs = 0;
    int bombRadius = 2;
    int speedLevel = 0;
    int cooldown = 0;
    int moveCooldownMax = 4;
    int invincibilityTimer = 0;
    int facingDx = 0;
    int facingDy = 1;
    bool hasHammer = false;
    bool hasRing = false;
    bool isBot = false;
    bool isAlive = false;
};

struct BombInfo {
    int x = 0;
    int y = 0;
    int timer = 0;
    int radius = 2;
    int ownerId = -1;
    int creditOwnerId = -1;
    bool isSliding = false;
    int slideDx = 0;
    int slideDy = 0;
    int slideCooldown = 0;
    int slideCooldownMax = 2;
};

struct PowerUpInfo {
    int x = 0;
    int y = 0;
    char type = ' ';
};

struct FlameInfo {
    int x = 0;
    int y = 0;
    int timer = 0;
    int ownerId = -1;
};

class Game {
private:
    World m_world;
    ExplosionSystem m_explosionSystem;
    CollisionSystem m_collisionSystem;
    SuddenDeathSystem m_suddenDeathSystem;

public:
    Game(int boardWidth, int boardHeight);
    World& getWorld();
    const World& getWorld() const;

    void loadLevel(ILevel& level, int numHumanPlayers = 0, int numBots = 0, bool shuffleSpawns = true);
    void reset(ILevel& level, int numHumanPlayers = 0, int numBots = 0);
    StepResult step(int playerId, Command action, const std::vector<PlayerCommand>& extraCommands = {});
    void fillState(int playerId, float* state) const;
    std::vector<float> getState(int playerId) const;
    std::vector<std::vector<int>> getBoardGrid() const;

    PlayerInfo getPlayerInfo(int playerId) const;
    std::vector<BombInfo> getBombs() const;
    std::vector<PowerUpInfo> getPowerUps() const;
    std::vector<FlameInfo> getFlames() const;

    // Deterministic setup helpers for unit testing & custom scenarios
    void clearBoard();
    void setSolidWall(int x, int y, bool solid);
    void addPlayer(int x, int y, int id, bool isBot = false);
    void addBreakableWall(int x, int y);
    void addBomb(int x, int y, int timer, int radius, int ownerId);
    void addPowerUp(int x, int y, const std::string& type);
    void givePlayerPowerUp(int playerId, const std::string& type);

    void update(Command command = Command::NONE);
    void update(const std::vector<PlayerCommand>& commands);

    bool isGameOver() const;
    int getWinnerId() const;

    int getSuddenDeathTimer() const;
    void setSuddenDeathTimer(int ticks);
    bool isSuddenDeathActive() const;
};
