#include <iostream>
#include <ctime>
#include <cstdlib>
#include <thread>
#include <chrono>
#include <limits>
#include <algorithm>

#include "../include/core/Game.h"
#include "../include/levels/ClassicLevel.h"
#include "../include/entities/Player.h"
#include "../include/core/ConsoleRenderer.h"
#include "../include/core/ConsoleInput.h"

namespace {
    constexpr int BOARD_WIDTH = 13;
    constexpr int BOARD_HEIGHT = 13;
    constexpr int MAX_TOTAL_PARTICIPANTS = 4;
    constexpr int MAX_HUMAN_PLAYERS = 2;
    constexpr int TARGET_FPS = 30;
    constexpr int FRAME_DURATION_MS = 1000 / TARGET_FPS;
}

struct GameConfig {
    int numPlayers = 1;
    int numBots = 1;
};

int readBoundedInt(const char* prompt, int minVal, int maxVal) {
    int value = minVal;
    std::cout << prompt;
    if (!(std::cin >> value)) {
        std::cin.clear();
        std::cin.ignore(std::numeric_limits<std::streamsize>::max(), '\n');
        value = minVal;
    }
    return std::clamp(value, minVal, maxVal);
}

GameConfig showMenu() {
    GameConfig config;
    std::cout << "\033[2J\033[1;1H";
    std::cout << "=================================\n";
    std::cout << "         BOMBERMAN CLONE         \n";
    std::cout << "=================================\n\n";

    config.numPlayers = readBoundedInt("Enter number of human players (0 - 2): ", 0, MAX_HUMAN_PLAYERS);

    int maxBots = MAX_TOTAL_PARTICIPANTS - config.numPlayers;
    int minBots = (config.numPlayers == 0) ? 2 : 0;
    std::string botPrompt = "Enter number of bots (" + std::to_string(minBots) + " - " + std::to_string(maxBots) + "): ";
    config.numBots = readBoundedInt(botPrompt.c_str(), minBots, maxBots);

    return config;
}

int main() {
    srand(static_cast<unsigned int>(time(nullptr)));

    GameConfig config = showMenu();
    int totalParticipants = std::max(1, config.numPlayers + config.numBots);

    Game game(BOARD_WIDTH, BOARD_HEIGHT);
    ConsoleRenderer renderer;
    ConsoleInput consoleInput;

    ClassicLevel level(totalParticipants, BOARD_WIDTH, BOARD_HEIGHT);
    game.loadLevel(level, config.numPlayers, config.numBots);

    bool isRunning = true;

    while (isRunning) {
        auto frameStart = std::chrono::high_resolution_clock::now();

        auto commands = consoleInput.pollCommands();
        for (const auto& pc : commands) {
            if (pc.command == Command::QUIT) {
                isRunning = false;
                break;
            }
        }
        if (!isRunning) {
            break;
        }

        game.update(commands);
        
        // מעבירים לרינדור גם את זמן הסיום כדי שיוצג ב-HUD
        renderer.render(game.getWorld(), game.getSuddenDeathTimer(), game.isSuddenDeathActive());

        if (game.isGameOver()) {
            break;
        }

        auto frameEnd = std::chrono::high_resolution_clock::now();
        auto frameDuration = std::chrono::duration_cast<std::chrono::milliseconds>(frameEnd - frameStart).count();

        int sleepTime = FRAME_DURATION_MS - static_cast<int>(frameDuration);
        if (sleepTime > 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(sleepTime));
        }
    }

    int winnerId = game.getWinnerId();
    std::cout << "\n============================================\n";
    if (winnerId == -1) {
        std::cout << "               IT'S A DRAW!                 \n";
    } else {
        const Player* winner = game.getWorld().getPlayer(winnerId);
        if (winner && winner->isBot()) {
            std::cout << "               BOT " << winnerId << " WINS!                 \n";
        } else {
            std::cout << "             PLAYER " << winnerId << " WINS!                \n";
        }
    }
    std::cout << "============================================\n";

    return 0;
}
