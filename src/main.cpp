#include <iostream>
#include <memory>
#include <ctime>
#include <cstdlib>
#include <thread>
#include <chrono>

#include "../include/core/Game.h"
#include "../include/levels/ClassicLevel.h"
#include "../include/entities/Player.h"
#include "../include/entities/DumbBot.h"
#include "../include/core/ConsoleRenderer.h"
#include "../include/core/ConsoleInput.h"

struct GameConfig {
    int numPlayers = 1;
    int numBots = 1;
};

GameConfig showMenu() {
    GameConfig config;
    std::cout << "\033[2J\033[1;1H"; 
    std::cout << "=================================\n";
    std::cout << "        BOMBERMAN CLONE          \n";
    std::cout << "=================================\n\n";
    
    std::cout << "Enter number of human players (0 - 2): ";
    std::cin >> config.numPlayers;
    if (config.numPlayers < 0) config.numPlayers = 0;
    if (config.numPlayers > 2) config.numPlayers = 2;

    std::cout << "Enter number of bots (0 - 4): ";
    std::cin >> config.numBots;
    if (config.numBots < 0) config.numBots = 0;
    if (config.numBots > 4) config.numBots = 4;

    return config;
}

int main () {
    srand(static_cast<unsigned int>(time(nullptr)));

    GameConfig config = showMenu();

    Game game(13, 13);
    ConsoleRenderer renderer;
    ConsoleInput consoleInput; 

    ClassicLevel level(4, 13, 13);
    game.loadLevel(level);

    auto spawnPoints = level.getSpawnPoints();
    int currentSpawnIdx = 0;
    int nextId = 1;

    for (int i = 0; i < config.numPlayers; i++) {
        if (currentSpawnIdx < spawnPoints.size()) {
            game.getWorld().addEntity(std::make_unique<Player>(
                spawnPoints[currentSpawnIdx].x, spawnPoints[currentSpawnIdx].y, nextId));
            currentSpawnIdx++;
            nextId++;
        }
    }

    for (int i = 0; i < config.numBots; i++) {
        if (currentSpawnIdx < spawnPoints.size()) {
            game.getWorld().addEntity(std::make_unique<DumbBot>(
                spawnPoints[currentSpawnIdx].x, spawnPoints[currentSpawnIdx].y, nextId));
            currentSpawnIdx++;
            nextId++;
        }
    }
    
    game.getWorld().sync();

    bool isRunning = true;
    const int TARGET_FPS = 30;
    const int FRAME_DURATION = 1000 / TARGET_FPS; 

    while (isRunning) {
        auto frameStart = std::chrono::high_resolution_clock::now();

        Player* p1 = game.getWorld().getPlayer(1);
        Player* p2 = game.getWorld().getPlayer(2);

        char input;
        while ((input = consoleInput.getRawChar()) != '\0') {
            if (input == 'q' || input == 'Q') {
                isRunning = false;
                break;
            }

            if (p1 && dynamic_cast<DumbBot*>(p1) == nullptr) {
                if (input == '\033') { 
                    if (consoleInput.getRawChar() == '[') {
                        char arrow = consoleInput.getRawChar();
                        if (arrow == 'A') p1->handleCommand(Command::UP, game.getWorld());
                        if (arrow == 'B') p1->handleCommand(Command::DOWN, game.getWorld());
                        if (arrow == 'C') p1->handleCommand(Command::RIGHT, game.getWorld());
                        if (arrow == 'D') p1->handleCommand(Command::LEFT, game.getWorld());
                    }
                } else if (input == ' ') {
                    p1->handleCommand(Command::PLACE_BOMB, game.getWorld());
                }
            }

            if (p2 && dynamic_cast<DumbBot*>(p2) == nullptr) {
                if (input == 'w' || input == 'W') p2->handleCommand(Command::UP, game.getWorld());
                if (input == 's' || input == 'S') p2->handleCommand(Command::DOWN, game.getWorld());
                if (input == 'a' || input == 'A') p2->handleCommand(Command::LEFT, game.getWorld());
                if (input == 'd' || input == 'D') p2->handleCommand(Command::RIGHT, game.getWorld());
                if (input == 'e' || input == 'E') p2->handleCommand(Command::PLACE_BOMB, game.getWorld());
            }
        }

        game.update(Command::NONE);
        renderer.render(game.getWorld());

        if (game.isGameOver()) {
            break;
        }

        auto frameEnd = std::chrono::high_resolution_clock::now();
        auto frameDuration = std::chrono::duration_cast<std::chrono::milliseconds>(frameEnd - frameStart).count();

        int sleepTime = FRAME_DURATION - static_cast<int>(frameDuration);
        if (sleepTime > 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(sleepTime));
        }
    }

    int winnerId = game.getWinnerId();
    std::cout << "\n============================================\n";
    if (winnerId == -1) {
        std::cout << "               IT'S A DRAW!                 \n";
    } else {
        Player* winner = game.getWorld().getPlayer(winnerId);
        bool isBot = false;
        if (winner) isBot = dynamic_cast<DumbBot*>(winner) != nullptr;
        
        if (isBot) {
            std::cout << "               BOT " << winnerId << " WINS!                 \n";
        } else {
            std::cout << "             PLAYER " << winnerId << " WINS!                \n";
        }
    }
    std::cout << "============================================\n";
    
    return 0;
}
