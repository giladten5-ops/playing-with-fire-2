#pragma once
#include "../interfaces/IInput.h"
#include <termios.h>
#include <vector>

class ConsoleInput : public IInput {
private:
    struct termios m_oldTermios{};
    bool m_isNonBlocking = false;
    void setNonBlocking(bool enable);

public:
    ConsoleInput();
    ~ConsoleInput() override;
    Command getCommand() override;
    std::vector<PlayerCommand> pollCommands() override;
    char getRawChar();
};
