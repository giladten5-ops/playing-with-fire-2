#pragma once
#include "../interfaces/IRenderer.h"
#include "World.h"

class ConsoleRenderer : public IRenderer {
    public:
        void render(const World& world) override;
};