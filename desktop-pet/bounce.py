"""Ballistic bounce with velocity-dependent stretch and grounded squash."""
import math

CYCLE=1.65
HEIGHT=82.0


def smooth(t):
    return t*t*(3-2*t)


def notification_bounce(age):
    """Return bottom-anchor vertical offset and volume-preserving X/Y scales."""
    t=age%CYCLE
    if t<.22:  # anticipation: sink and widen before takeoff
        sy=1-.10*smooth(t/.22)
        return 0,1/sy,sy
    if t<1.20:
        u=(t-.22)/.98
        y=-4*HEIGHT*u*(1-u)
        speed=abs(2*u-1)
        sy=.99+.10*speed**2  # restrained stretch; near-normal shape at apex
        if u<.08:
            sy=.90+(sy-.90)*smooth(u/.08)
        return y,1/sy,sy
    if t<1.33:  # impact squash is fast, keeps the feet planted
        sy=1.09-(1.09-.88)*smooth((t-1.20)/.13)
        return 0,1/sy,sy
    u=(t-1.33)/.32
    sy=.88+(1-.88)*smooth(u)+.025*math.sin(math.pi*u)
    return 0,1/sy,sy
