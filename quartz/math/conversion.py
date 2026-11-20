import math as _math
from quartz.math.matrix import Matrix
from quartz.math.vector import Vector


def axis_conversion(from_forward="Y", from_up="Z", to_forward="Y", to_up="Z"):
    def axis_vec(s):
        s = s.upper()
        sign = -1 if s.startswith("-") else 1
        letter = s.lstrip("-")
        base = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}[letter]
        return tuple(sign * v for v in base)

    f_from = axis_vec(from_forward)
    u_from = axis_vec(from_up)
    f_to = axis_vec(to_forward)
    u_to = axis_vec(to_up)

    def cross(a, b):
        return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

    def norm(a):
        return (a[0]**2+a[1]**2+a[2]**2)**0.5

    rf = cross(u_from, f_from)
    n = norm(rf)
    if n == 0:
        raise ValueError("Invalid axis arguments passed, can't use up/forward on the same axis")
    rf = (rf[0]/n, rf[1]/n, rf[2]/n)
    uf = cross(f_from, rf)
    n = norm(uf)
    if n > 0:
        uf = (uf[0]/n, uf[1]/n, uf[2]/n)
    rt = cross(u_to, f_to)
    n = norm(rt)
    if n == 0:
        raise ValueError("Invalid axis arguments passed, can't use up/forward on the same axis")
    rt = (rt[0]/n, rt[1]/n, rt[2]/n)
    ut = cross(f_to, rt)
    n = norm(ut)
    if n > 0:
        ut = (ut[0]/n, ut[1]/n, ut[2]/n)

    def mat_cols(c0, c1, c2):
        return [[c0[0], c1[0], c2[0]],
                [c0[1], c1[1], c2[1]],
                [c0[2], c1[2], c2[2]]]
    F = mat_cols(rf, uf, f_from)
    T = mat_cols(rt, ut, f_to)
    FT = [[F[0][0], F[1][0], F[2][0]],
          [F[0][1], F[1][1], F[2][1]],
          [F[0][2], F[1][2], F[2][2]]]
    M = [[sum(T[i][k]*FT[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return Matrix(M)


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
