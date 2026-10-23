#pragma once
#include "../interfaces/IInput.h"

class ConsoleInput : public IInput {
    private:
        void setNonBlocking(bool enable);
    public:
        ConsoleInput();
        ~ConsoleInput();
        Command getCommand() override;
};