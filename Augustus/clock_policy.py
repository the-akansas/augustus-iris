"""Bounded approved look-ahead. No speculative ticks beyond the grant.

The look-ahead is measured in play time, not ticks: at a 400ms ping a guest's
progress report and the next grant can be two or three seconds old, and a fixed
tick budget is only ~3s at the fastest speeds. Six seconds of play absorbs that
without the leading city ever touching the grant edge in normal play.
"""
import math
CREDIT_TICKS = 64
MAX_CREDIT_TICKS = 512  # must match MP_CLOCK_CREDIT_TICKS in src/multiplayer/clock.h
CREDIT_SECONDS = 6.0
# A city whose last progress report is older than this stops the shared clock.
FRESH_SECONDS = 5.0
# Milliseconds per tick for room speed 0..100 in steps of 10 (src/multiplayer/clock.c).
TICK_MS = (702, 502, 352, 242, 162, 112, 82, 57, 37, 22, 16)

def credit_for_speed(speed):
    ms = TICK_MS[max(0, min(100, int(speed))) // 10]
    return max(CREDIT_TICKS, min(MAX_CREDIT_TICKS, math.ceil(CREDIT_SECONDS * 1000 / ms)))
