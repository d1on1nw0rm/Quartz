import math as _math


def clamp(value, min=0.0, max=1.0):
    if value < min:
        return min
    if value > max:
        return max
    return value


def lerp(from_value, to_value, factor):
    return from_value + (to_value - from_value) * factor


def smoothstep(from_value, to_value, value):
    if from_value == to_value:
        return 0.0 if value < from_value else 1.0
    t = (value - from_value) / (to_value - from_value)
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return t * t * (3.0 - 2.0 * t)
