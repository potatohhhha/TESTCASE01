#include "limit.h"

int limit_value(int x, int min, int max) {
    if (x < min) return min;
    if (x > max) return max;
    return x;
}
