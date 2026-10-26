#pragma once
#include "../interfaces/IInput.h"

class ConsoleInput : public IInput {
private:
    void setNonBlocking(bool enable);

public:
    ConsoleInput();
    ~ConsoleInput() override;
    Command getCommand() override;
    char getRawChar();
};
