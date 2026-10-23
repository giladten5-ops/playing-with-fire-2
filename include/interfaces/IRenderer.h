#pragma once

class World;

class IRenderer {
    public:
        virtual ~IRenderer() = default;
        virtual void render(const World& world) = 0;
};