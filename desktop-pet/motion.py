"""Continuous motion in logical pixels. No character image is altered."""
import math


def pose(state, elapsed, transition_age):
    x, y = 0.0, math.sin(elapsed * 2) * 1.2
    if state == 'running':
        phase = elapsed * 5
        x = math.sin(phase) * 7
        y = -abs(math.sin(phase)) * 10
    elif state == 'waiting':
        x = math.sin(elapsed * 1.5) * 2
    elif state == 'review':
        x = math.sin(elapsed * 2.5) * 3
        y = math.cos(elapsed * 2.5) * 2
    elif state == 'failed' and transition_age < .65:
        x = math.sin(transition_age * 45) * 6 * (1-transition_age/.65)
    elif state == 'idle' and 0 <= transition_age < .8:
        y = -math.sin(math.pi*transition_age/.8) * 14
    elif state == 'disconnected':
        x, y = 0, 3
    return x, y
