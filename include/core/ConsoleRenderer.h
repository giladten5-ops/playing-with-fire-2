#pragma once
#include "../interfaces/IRenderer.h"
#include "World.h"

class ConsoleRenderer : public IRenderer {
    public:
        void render(const World& world, int sdTimerTicks = -1, bool sdActive = false) override;
};
