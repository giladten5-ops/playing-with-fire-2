#pragma once

class World;

class IRenderer {
    public:
        virtual ~IRenderer() = default;
        // עדכנו את הממשק כדי שיוכל לקבל נתונים על מצב ה-Sudden Death
        virtual void render(const World& world, int sdTimerTicks = -1, bool sdActive = false) = 0;
};
