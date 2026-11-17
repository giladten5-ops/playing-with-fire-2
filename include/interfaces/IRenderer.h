#pragma once

class World;

class IRenderer {
    public:
        virtual ~IRenderer() = default;
        // Render world state along with Sudden Death timer and active status
        virtual void render(const World& world, int sdTimerTicks = -1, bool sdActive = false) = 0;
};
