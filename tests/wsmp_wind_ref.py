"""Reference computations for the WSMP wind module, written from docs/module-protocol.md and the
SparkFun SEN-15901 datasheet, independent of firmware/stage0-node/App/mod_wind.c."""
import math

UMS_PER_HZ = 666_980          # 1.492 mph per Hz = 0.66698 m/s per Hz (registry, module type 6)
GUST_BINS = 12                # 3 s of 250 ms bins
GUST_S = 3
# SEN-15901 vane resistances (datasheet table), clockwise from north in 22.5 degree steps.
VANE_OHM = [33_000, 6_570, 8_200, 891, 1_000, 688, 2_200, 1_410, 3_900, 3_140, 16_000, 14_120, 120_000,
            42_120, 64_900, 21_880]
PULL_UP_OHM, SUPPLY_MV = 10_000, 3_300


def vane_mv(position):
    """The vane output with the 10 kOhm pull-up to 3.3 V."""
    r = VANE_OHM[position]
    return round(SUPPLY_MV * r / (r + PULL_UP_OHM))


def gust_centi(bins):
    """The largest 3-s running mean of the pulse bins, in 0.01 m/s, rounded half up."""
    best = max(sum(bins[i:i + GUST_BINS]) for i in range(len(bins) - GUST_BINS + 1))
    return (best * UMS_PER_HZ * 2 + GUST_S * 10_000) // (2 * GUST_S * 10_000)


def unit_vector_centi(position):
    """(east, north) of the direction the wind comes from, x 100, rounded to the nearest integer."""
    a = math.radians(22.5 * position)
    return round(100 * math.sin(a)), round(100 * math.cos(a))
