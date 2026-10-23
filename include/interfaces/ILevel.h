#pragma once

class World;

class ILevel {
    public:
        virtual ~ILevel() = default;
        virtual void generate(World& world) = 0;
};