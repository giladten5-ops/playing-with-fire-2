#include "../../include/core/ConsoleInput.h"
#include <unistd.h>
#include <fcntl.h>

ConsoleInput::ConsoleInput() {
    setNonBlocking(true);
}

ConsoleInput::~ConsoleInput() {
    setNonBlocking(false);
}

void ConsoleInput::setNonBlocking(bool enable) {
    if (enable && !m_isNonBlocking) {
        tcgetattr(STDIN_FILENO, &m_oldTermios);
        struct termios newt = m_oldTermios;
        newt.c_lflag &= ~(ICANON | ECHO);
        tcsetattr(STDIN_FILENO, TCSANOW, &newt);
        int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
        fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);
        m_isNonBlocking = true;
    } else if (!enable && m_isNonBlocking) {
        tcsetattr(STDIN_FILENO, TCSANOW, &m_oldTermios);
        int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
        fcntl(STDIN_FILENO, F_SETFL, flags & ~O_NONBLOCK);
        m_isNonBlocking = false;
    }
}

char ConsoleInput::getRawChar() {
    char c = '\0';
    if (read(STDIN_FILENO, &c, 1) == 1) {
        return c;
    }
    return '\0';
}

Command ConsoleInput::getCommand() {
    char c = getRawChar();
    switch (c) {
        case 'w': case 'W': return Command::UP;
        case 's': case 'S': return Command::DOWN;
        case 'a': case 'A': return Command::LEFT;
        case 'd': case 'D': return Command::RIGHT;
        case ' ': return Command::PLACE_BOMB;
        case 'q': case 'Q': return Command::QUIT;
        default: return Command::NONE;
    }
}

std::vector<PlayerCommand> ConsoleInput::pollCommands() {
    std::vector<PlayerCommand> commands;
    char pending = '\0';

    while (true) {
        char input = (pending != '\0') ? pending : getRawChar();
        pending = '\0';
        if (input == '\0') break;

        if (input == 'q' || input == 'Q') {
            commands.push_back({0, Command::QUIT});
            break;
        }

        if (input == '\033') {
            char next = getRawChar();
            if (next == '[') {
                char arrow = getRawChar();
                if (arrow == 'A') commands.push_back({1, Command::UP});
                else if (arrow == 'B') commands.push_back({1, Command::DOWN});
                else if (arrow == 'C') commands.push_back({1, Command::RIGHT});
                else if (arrow == 'D') commands.push_back({1, Command::LEFT});
            } else if (next != '\0') {
                pending = next;
            }
            continue;
        }

        switch (input) {
            case ' ': commands.push_back({1, Command::PLACE_BOMB}); break;
            case 'w': case 'W': commands.push_back({2, Command::UP}); break;
            case 's': case 'S': commands.push_back({2, Command::DOWN}); break;
            case 'a': case 'A': commands.push_back({2, Command::LEFT}); break;
            case 'd': case 'D': commands.push_back({2, Command::RIGHT}); break;
            case 'e': case 'E': commands.push_back({2, Command::PLACE_BOMB}); break;
            default: break;
        }
    }
    return commands;
}
