#pragma once

enum class Command {
    NONE,
    UP,
    DOWN,
    LEFT,
    RIGHT,
    PLACE_BOMB,
    QUIT
};

class IInput {
    public:
        virtual ~IInput() = default;
        virtual Command getCommand() = 0;
};