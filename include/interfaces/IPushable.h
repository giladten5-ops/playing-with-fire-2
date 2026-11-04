#pragma once

class IPushable {
public:
    virtual ~IPushable() = default;
    virtual void push(int dx, int dy, int pusherId = -1) = 0;
};
