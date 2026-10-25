#pragma once

class IPushable {
public:
    virtual ~IPushable() = default;
    virtual void push(int dx, int dy) = 0;
};
