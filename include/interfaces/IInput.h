#pragma once
#include <vector>

enum class Command {
    NONE,
    UP,
    DOWN,
    LEFT,
    RIGHT,
    PLACE_BOMB,
    QUIT
};

struct PlayerCommand {
    int playerId;
    Command command;
};

class IInput {
public:
    virtual ~IInput() = default;
    virtual Command getCommand() = 0;
    virtual std::vector<PlayerCommand> pollCommands() = 0;
};
