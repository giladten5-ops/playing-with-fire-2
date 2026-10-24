#include <iostream>
#include <memory>
#include <ctime>
#include <cstdlib>
#include <thread>
#include <chrono>

#include "../include/core/Game.h"
#include "../include/levels/ClassicLevel.h"
#include "../include/entities/Player.h"
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
    if (!spawnPoints.empty()) {
        game.getWorld().addEntity(std::make_unique<Player>(spawnPoints[0].x, spawnPoints[0].y, 1));
        game.getWorld().sync();
    }

    bool isRunning = true;
    const int TARGET_FPS = 30;
    const int FRAME_DURATION = 1000 / TARGET_FPS; 

    while (isRunning) {
        auto frameStart = std::chrono::high_resolution_clock::now();

        Command command = consoleInput.getCommand();
        if (command == Command::QUIT) {
            isRunning = false;
        }

        game.update(command);
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