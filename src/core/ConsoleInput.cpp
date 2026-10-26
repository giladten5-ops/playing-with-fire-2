#include "../../include/core/ConsoleInput.h"
#include <iostream>
#include <termios.h>
#include <unistd.h>
#include <fcntl.h>

ConsoleInput::ConsoleInput() {
    setNonBlocking(true);
}

ConsoleInput::~ConsoleInput() {
    setNonBlocking(false);
}

void ConsoleInput::setNonBlocking(bool enable) {
    static struct termios oldt, newt;
    if (enable) {
        tcgetattr(STDIN_FILENO, &oldt);
        newt = oldt;
        newt.c_lflag &= ~(ICANON | ECHO);
        tcsetattr(STDIN_FILENO, TCSANOW, &newt);
        int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
        fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);
    } else {
        tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
        int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
        fcntl(STDIN_FILENO, F_SETFL, flags & ~O_NONBLOCK);
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
