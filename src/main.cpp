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

int main () {
    srand(static_cast<unsigned int>(time(nullptr)));

    Game game(13, 13);
    ConsoleRenderer renderer;
    ConsoleInput consoleInput;

    ClassicLevel level(4, 13, 13);
    game.loadLevel(level);

    auto spawnPoints = level.getSpawnPoints();
    if (spawnPoints.size() >= 1) {
        game.getWorld().addEntity(std::make_unique<Player>(spawnPoints[0].x, spawnPoints[0].y, 1));
    }
    if (spawnPoints.size() >= 2) {
        game.getWorld().addEntity(std::make_unique<Player>(spawnPoints[1].x, spawnPoints[1].y, 2));
    }
    // כאן הבוט מתווסף בפועל למשחק
    if (spawnPoints.size() >= 3) {
        game.getWorld().addEntity(std::make_unique<DumbBot>(spawnPoints[2].x, spawnPoints[2].y, 3));
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

            if (p1) {
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

            if (p2) {
                if (input == 'w' || input == 'W') p2->handleCommand(Command::UP, game.getWorld());
                if (input == 's' || input == 'S') p2->handleCommand(Command::DOWN, game.getWorld());
                if (input == 'a' || input == 'A') p2->handleCommand(Command::LEFT, game.getWorld());
                if (input == 'd' || input == 'D') p2->handleCommand(Command::RIGHT, game.getWorld());
                if (input == 'e' || input == 'E') p2->handleCommand(Command::PLACE_BOMB, game.getWorld());
            }
        }

        game.update(Command::NONE);
        renderer.render(game.getWorld());

        auto frameEnd = std::chrono::high_resolution_clock::now();
        auto frameDuration = std::chrono::duration_cast<std::chrono::milliseconds>(frameEnd - frameStart).count();

        int sleepTime = FRAME_DURATION - static_cast<int>(frameDuration);
        if (sleepTime > 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(sleepTime));
        }
    }
    return 0;
}
