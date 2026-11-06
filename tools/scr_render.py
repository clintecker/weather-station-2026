"""Render the TX's bench screens (firmware/stage0-node/App/scr_view.h) to PNG, from a host build of the
firmware's own drawing code, to compare by eye with the approved mockups.

    python3 tools/scr_render.py [OUT_DIR]     (default .superpowers/sdd/2026-11-04-node-oled-and-e2e/renders)
    python3 tools/scr_render.py --digest      every frame's hash, as JSON on stdout
    python3 tools/scr_render.py --update      the same into tests/golden/scr_frames.json, to accept a change

Each screen is drawn with a demo view (the mockups' values) at a few frames, 4 x scale, lit pixels in the
mockups' amber on black (a gray screen, MATRIX, at its 16 levels between them): <screen>-f<frame>.png. tests/test_scr_view.py builds the same library and
uses the view structure defined here.

The digests are the golden test's (tests/test_scr_golden.py): each frame exactly as the TX sends it (frame(): 4096
bytes in the SSD1325's order, turned for the panel), for every screen at every frame (0 to 63 for HOME and the banner,
which animate for ever) in the demo view, and in each state of views() its own screen at every frame and every other
screen at its first and last."""
import ctypes
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT/'firmware/stage0-node/App'
COMMON = ROOT/'firmware/common'
OUT = ROOT/'.superpowers/sdd/2026-11-04-node-oled-and-e2e/renders'
GOLDEN = ROOT/'tests/golden/scr_frames.json'
W, H = 128, 64
SCREENS = ['HOME', 'BURST', 'BANNER', 'AIR', 'PRESSURE', 'POWER', 'RADIO', 'SCOPE', 'VANE', 'RAIN', 'SYSTEM', 'BOOT',
           'HACK', 'FORTUNE', 'FROG', 'MATRIX', 'PINBALL']   # enum scr_id
RAIN_AGE_NONE, RAIN_AGE_MAX_S = 0xFFFFFFFF, 99 * 3600   # App/mod_rain.h
SCR_TX_NONE, SCR_TX_WAIT, SCR_TX_NO_ACK, SCR_TX_ACK = -2, -1, 0, 1
SCR_GAP, SCR_NONE_S = -32768, 0xFFFFFFFF
AIR_HIST, PRESS_HIST, RADIO_HIST = 60, 36, 30

# The screens' sources and their include paths. oled_draw.c is left out: the shim includes it, so a
# test can see every string drawn (the shim's oled_text checks each character against the font).
INCLUDES = ['-I', APP, '-I', COMMON, '-I', ROOT/'firmware']
SOURCES = [APP/'scr_view.c', APP/'scr_calc.c', APP/'scr_home.c', APP/'scr_detail.c', APP/'scr_interludes.c', APP/'scr_rain.c',
           APP/'scr_silly.c', APP/'scr_art.c', APP/'scr_font.c', APP/'scr_kana.c',
           COMMON/'font5x7.c']
FRAME_BYTES = W * H // 2   # the SSD1325's send order (firmware/common/oled_draw.h): column pair, then row
JUNK = 0xA5                # what frame() fills the buffer with before a screen draws
SHIM = r'''
#include <string.h>
#include "scr_view.h"
#include "font5x7.h"
#define oled_text real_oled_text
#include "oled_draw.c"
#undef oled_text
unsigned shim_missing;          /* characters drawn that the font lacks */
char shim_missing_text[64];     /* the last string that had one */
int oled_text(const oled_surf *surf, int x, int y, const char *s, int scale)
{
  for (const char *c = s; *c; c++)
    if (strchr(font5x7_chars, *c) == NULL)
    {
      shim_missing++;
      strncpy(shim_missing_text, s, sizeof shim_missing_text - 1);
    }
  return real_oled_text(surf, x, y, s, scale);
}
unsigned shim_view_size(void) { return (unsigned)sizeof(scr_view_t); }
'''


class WindLive(ctypes.Structure):
    _fields_ = [('speed_cms', ctypes.c_uint16), ('gust_cms', ctypes.c_uint16), ('vane_mv', ctypes.c_uint16),
                ('point', ctypes.c_int8), ('bins', ctypes.c_uint8 * 120), ('nbins', ctypes.c_uint8)]


class RailLive(ctypes.Structure):
    _fields_ = [('fitted', ctypes.c_int), ('ok', ctypes.c_int), ('ma_x100', ctypes.c_int32), ('mv', ctypes.c_int32)]


class PowerLive(ctypes.Structure):
    _fields_ = [('batt_ok', ctypes.c_int), ('batt_ma_x100', ctypes.c_int32), ('out_mv', ctypes.c_int32),
                ('gauge_ok', ctypes.c_int), ('vcell_mv', ctypes.c_uint16), ('soc_pct_x10', ctypes.c_uint16),
                ('charging', ctypes.c_int), ('charger', ctypes.c_uint8), ('rail', RailLive * 3)]


class RainHist(ctypes.Structure):
    _fields_ = [('tips', ctypes.c_uint32), ('last_age_s', ctypes.c_uint32), ('per_min', ctypes.c_uint8 * 60)]


class View(ctypes.Structure):
    i, u8, u16, u32, i32 = ctypes.c_int, ctypes.c_uint8, ctypes.c_uint16, ctypes.c_uint32, ctypes.c_int32
    _fields_ = [('air_ok', i), ('box_ok', i), ('press_ok', i), ('uv_ok', i),
                ('air_c', i32), ('air_rh', i32), ('box_c', i32), ('box_rh', i32), ('press_dhpa', i32), ('uv_counts', i32),
                ('wind', WindLive), ('rain', RainHist), ('power', PowerLive),
                ('last_seq', u32), ('last_age_s', u32), ('last_acked', i), ('ack_rssi', ctypes.c_int16),
                ('ack_snr', ctypes.c_int8), ('pending', ctypes.c_uint), ('extra_frames', ctypes.c_uint),
                ('reports', ctypes.c_uint),
                ('cipher', u8 * 96), ('cipher_len', u8),
                ('sf', u8), ('bw_khz_div125', u8), ('freq_khz', u32),
                ('flash_pct', u8), ('ram_pct', u8), ('stack_pct', u8), ('journal_pct', u8), ('airtime_pct', u8),
                ('station', u16), ('epoch', u32), ('modules', ctypes.c_uint), ('modules_active', ctypes.c_uint),
                ('key_ok', i), ('utc', u32), ('since_exchange_s', u32), ('air_n', u8), ('press_n', u8), ('radio_n', u8),
                ('air_hist', ctypes.c_int16 * AIR_HIST), ('press_hist', ctypes.c_int16 * PRESS_HIST),
                ('radio_rssi', ctypes.c_int16 * RADIO_HIST), ('radio_snr', ctypes.c_int16 * RADIO_HIST)]


def build(directory, cc=('cc', '-std=c11', '-Wall', '-Wextra', '-Werror')):
    """Compile the screens into a shared library in directory and load it."""
    shim = Path(directory)/'scr_shim.c'
    shim.write_text(SHIM)
    lib_path = Path(directory)/'scr_view.so'
    subprocess.run([*cc, '-shared', '-fPIC', *map(str, INCLUDES), *map(str, SOURCES), str(shim), '-o', str(lib_path)],
                   check=True)
    lib = ctypes.CDLL(str(lib_path))
    lib.scr_draw.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(View)]
    lib.scr_frames.argtypes = [ctypes.c_int]
    lib.scr_frames.restype = ctypes.c_uint
    lib.oled_get.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.oled_get.restype = ctypes.c_uint
    lib.oled_text.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.shim_view_size.restype = ctypes.c_uint
    return lib


def demo_view():
    """The mockups' values (design spec, layout C; oledmock/gen.py)."""
    v = View(air_ok=1, box_ok=1, press_ok=1, uv_ok=1, air_c=2314, air_rh=5080, box_c=2290, box_rh=5220,
             press_dhpa=9830, uv_counts=0, last_seq=1233, last_age_s=58, last_acked=SCR_TX_ACK,
             ack_rssi=-41, ack_snr=13, sf=7, bw_khz_div125=4, freq_khz=915000,
             flash_pct=51, ram_pct=38, stack_pct=69, journal_pct=2, airtime_pct=4, station=17, epoch=42,
             modules=8, modules_active=8, key_ok=1)
    v.wind.speed_cms, v.wind.gust_cms, v.wind.vane_mv, v.wind.point = 130, 270, 1486, 2
    bins = [(i // 2) % 2 + (2 if 40 <= i < 56 else 0) + (1 if i % 7 == 3 and i < 100 else 0) for i in range(120)]
    v.wind.bins[:] = bins
    v.wind.nbins = 120
    rain(v, 2, 240, {55: 1, 29: 1})   # the mockup's: a tip 4 min ago, one half an hour before
    v.power.batt_ok, v.power.batt_ma_x100, v.power.out_mv = 1, 3760, 3850
    v.power.gauge_ok, v.power.vcell_mv, v.power.soc_pct_x10, v.power.charging = 1, 3850, 780, 1
    cipher = bytes.fromhex('A4C123B1612DD2C17149D43953 6BA6F0FB23C6F5DA404E4FB440034DD512C9791E558E96B50AC2F86702'
                           .replace(' ', ''))
    cipher += bytes((i * 37 + 11) & 0xFF for i in range(77 - len(cipher)))
    v.cipher[:len(cipher)] = cipher
    v.cipher_len = len(cipher)
    v.utc, v.since_exchange_s = NOON_UTC, 26
    v.power.charger = 0x03   # power good, charging
    v.power.rail[0].fitted, v.power.rail[0].ok, v.power.rail[0].ma_x100, v.power.rail[0].mv = 1, 1, 4210, 3300
    v.power.rail[1].fitted = 1                                   # solar: fitted, not answering yet
    v.power.rail[2].fitted, v.power.rail[2].ok, v.power.rail[2].ma_x100, v.power.rail[2].mv = 1, 1, 21500, 5050
    history(v, 'air', [2290 + round(40 * math.sin(i / 9)) + i for i in range(60)])
    history(v, 'press', [9810 + i // 2 for i in range(36)])
    radio(v, [(-41 - (i * 7) % 9, 13 - (i * 5) % 7) if i % 11 != 6 else None for i in range(30)])
    return v


NOON_UTC = 1793901600   # 2026-11-05 18:00 UTC: noon at the bench (SCR_UTC_OFFSET_MIN -360)
NIGHT_UTC = NOON_UTC + 12 * 3600


def history(view, name, samples):
    """The view's air or press history: samples oldest first, None a gap."""
    arr = getattr(view, f'{name}_hist')
    arr[:len(samples)] = [SCR_GAP if x is None else x for x in samples]
    setattr(view, f'{name}_n', len(samples))
    return view


def radio(view, frames):
    """The view's last frames: (rssi, snr) for an ACK, None for none."""
    view.radio_rssi[:len(frames)] = [SCR_GAP if f is None else f[0] for f in frames]
    view.radio_snr[:len(frames)] = [SCR_GAP if f is None else f[1] for f in frames]
    view.radio_n = len(frames)
    return view


def weather(view, c=None, rh=None, wind_cms=None, tips10=0, utc=None):
    """The view with the air, the wind, the tips of the last minutes (all in the newest) and the time set."""
    if c is not None:
        view.air_c = c
    if rh is not None:
        view.air_rh = rh
    if wind_cms is not None:
        view.wind.speed_cms = wind_cms
    view.rain.per_min[:] = [0] * 59 + [tips10]
    if utc is not None:
        view.utc = utc
    return view


def home_views():
    """HOME in each icon's weather, and with parts and the link missing."""
    absent = demo_view()
    absent.air_ok = absent.press_ok = 0
    absent.last_acked = SCR_TX_NONE
    noack = weather(demo_view())
    noack.last_acked, noack.wind.speed_cms, noack.wind.point = SCR_TX_NO_ACK, 30, 2
    return {'sun': weather(demo_view(), 2190, 4600, 0), 'moon': weather(demo_view(), 1210, 6200, 120, utc=NIGHT_UTC),
            'cloud': weather(demo_view(), 1480, 9100, 260), 'rain': weather(demo_view(), 1130, 9600, 310, tips10=3),
            'snow': weather(demo_view(), -420, 8000, 150), 'wind': weather(demo_view(), 1720, 5500, 820),
            'absent': absent, 'noack': noack}


def rain(view, tips, age_s, per_min):
    """The view's rain history: tips since boot, the last one's age (RAIN_AGE_NONE: none), and the tips of
    minutes as {index: tips}, 59 this minute."""
    view.rain.tips, view.rain.last_age_s = tips, age_s
    view.rain.per_min[:] = [per_min.get(i, 0) for i in range(60)]
    return view


def rain_views():
    """No rain since boot; a light shower easing off; a heavy burst under way."""
    shower = {i: t for i, t in zip(range(22, 52), [1, 0, 1, 1, 2, 1, 2, 3, 2, 2, 3, 4, 3, 2, 3, 2, 1, 2, 1, 1, 0, 1,
                                                    1, 0, 0, 1, 0, 0, 0, 1])}
    burst = {i: t for i, t in zip(range(38, 60), [1, 1, 2, 1, 2, 3, 2, 4, 5, 4, 6, 7, 9, 8, 11, 12, 10, 9, 13, 11,
                                                   8, 6])}
    return {'dry': rain(demo_view(), 0, RAIN_AGE_NONE, {}),
            'shower': rain(demo_view(), sum(shower.values()) + 3, 8 * 60 + 20, shower),
            'burst': rain(demo_view(), sum(burst.values()) + 61, 3, burst)}


def unpack(frame, rotate180=0):
    """A frame in send order as {(x, y): level} of its lit pixels, turned back if it was sent turned."""
    out = {}
    for i, b in enumerate(frame):
        cp, y = divmod(i, H)
        for x, level in ((2 * cp, b >> 4), (2 * cp + 1, b & 15)):
            if level:
                out[(W - 1 - x, H - 1 - y) if rotate180 else (x, y)] = level
    return out


class Surf(ctypes.Structure):
    """An oled_surf (firmware/common/oled_draw.h) over a frame of its own, cleared: pass byref(surf)."""
    _fields_ = [('px', ctypes.c_void_p), ('rot180', ctypes.c_uint8), ('ink', ctypes.c_uint8)]

    def __init__(self, rot180=0, ink=15):
        self.buf = ctypes.create_string_buffer(FRAME_BYTES)
        super().__init__(ctypes.addressof(self.buf), rot180, ink)

    def levels(self):
        """{(x, y): level} of the lit pixels, as drawn (turned back if the surface is turned)."""
        return unpack(self.buf.raw, self.rot180)


def frame(lib, screen, frame, view):
    """The frame as the TX sends it (App/oled_app.c): 4096 bytes in the SSD1325's order, turned for the panel. The
    buffer starts as junk, as the send buffer holds the last frame: a screen that does not clear shows."""
    surf = Surf(1)
    ctypes.memset(surf.buf, JUNK, FRAME_BYTES)
    lib.scr_draw(ctypes.byref(surf), SCREENS.index(screen), frame, ctypes.byref(view))
    return surf.buf.raw


def shade(lib, screen, frame_no, view):
    """What to render: {(x, y): level} of the lit pixels, the right way up."""
    return unpack(frame(lib, screen, frame_no, view), 1)


def draw(lib, screen, frame_no, view):
    """The screen's lit pixels, at any level: a set of (x, y)."""
    return set(shade(lib, screen, frame_no, view))


def png(pixels, path, scale=4):
    """pixels: a set of lit (x, y), or {(x, y): level 0-15}, in the mockups' amber on black."""
    from PIL import Image   # requirements-dev.txt
    bg, lit = (5, 7, 10), (244, 231, 161)
    img = Image.new('RGB', (W * scale, H * scale), bg)
    levels = pixels if isinstance(pixels, dict) else dict.fromkeys(pixels, 15)
    for (x, y), level in levels.items():
        colour = tuple(round(b + (f - b) * level / 15) for b, f in zip(bg, lit))
        img.paste(colour, (x * scale, y * scale, x * scale + scale, y * scale + scale))
    img.save(path)


# The frames worth a look: each step of each screen's animation.
FRAMES = {'HOME': [0, 2, 4, 6], 'BURST': [0, 1, 8, 15], 'BANNER': [0], 'AIR': [0, 7], 'PRESSURE': [7], 'POWER': [7],
          'RADIO': [0, 7], 'SCOPE': [0], 'VANE': [0, 1, 63], 'RAIN': [0], 'SYSTEM': [0, 63], 'BOOT': [0, 30, 62],
          'HACK': [0, 4, 12, 16, 18, 20, 21], 'FORTUNE': [0, 6, 30], 'FROG': [0, 20, 40, 44, 60], 'MATRIX': [0, 1, 2, 3, 4, 5],
          'PINBALL': [0, 20, 32, 33, 63]}


def views():
    """The extra states worth a look: {name: (screen, frame, view)}."""
    out = {}
    waiting = demo_view()
    waiting.last_acked, waiting.last_seq, waiting.extra_frames = SCR_TX_WAIT, 1234, 0
    out['banner-sending'] = ('BANNER', 0, waiting)
    noack = demo_view()
    noack.last_acked, noack.extra_frames = SCR_TX_NO_ACK, 3
    out['banner-noack-backlog'] = ('BANNER', 0, noack)
    for name, v in home_views().items():
        out[f'home-{name}'] = ('HOME', 0, v)
        if name in ('rain', 'snow', 'wind', 'moon'):
            out[f'home-{name}-f06'] = ('HOME', 6, v)
    for name, v in rain_views().items():
        out[f'rain-{name}'] = ('RAIN', 0, v)
    gappy = history(demo_view(), 'air', [None] * 20 + [2100 + 3 * i for i in range(25)] + [None] * 3 + [2200] * 7)
    out['air-gaps'] = ('AIR', 7, gappy)
    fresh = demo_view()
    fresh.air_n = fresh.press_n = fresh.radio_n = 0
    fresh.since_exchange_s = SCR_NONE_S
    for screen in ('AIR', 'PRESSURE', 'RADIO'):
        out[f'{screen.lower()}-empty'] = (screen, 7, fresh)
    falling = history(demo_view(), 'press', [10040 - 2 * i for i in range(36)])
    falling.press_dhpa = 9968
    out['pressure-falling'] = ('PRESSURE', 7, falling)
    steady = history(demo_view(), 'press', [10130 + (i % 3) for i in range(36)])
    steady.press_dhpa = 10133
    out['pressure-steady'] = ('PRESSURE', 7, steady)
    phase_a = demo_view()
    phase_a.power.charger, phase_a.power.gauge_ok = 0, 0
    for r in phase_a.power.rail:
        r.fitted = r.ok = r.ma_x100 = r.mv = 0
    out['power-phase-a'] = ('POWER', 7, phase_a)
    for name, v in home_views().items():
        if name in ('rain', 'snow', 'moon', 'noack'):
            out[f'frog-{name}'] = ('FROG', 44, v)
            out[f'fortune-{name}'] = ('FORTUNE', 63, v)
    for f in (2, 3):
        out[f'matrix-rain-f{f:02d}'] = ('MATRIX', f, weather(demo_view(), tips10=7))
    other = demo_view()
    other.last_seq = 1500
    out['pinball-seq1500-f40'] = ('PINBALL', 40, other)
    return out


ENDLESS = ('HOME', 'BANNER')   # they animate for ever: digested over 64 frames


def digests(lib):
    """{'<state>/<screen>/<frame>': the first 16 hex digits of the sent frame's SHA-256} (see the docstring)."""
    demo = demo_view()
    demo.last_seq = 1234   # as main() renders it
    states = {'demo': (None, demo), **{name: (screen, v) for name, (screen, _, v) in views().items()}}
    out = {}
    for state, (own, view) in states.items():
        for i, screen in enumerate(SCREENS):
            n = 64 if screen in ENDLESS else lib.scr_frames(i)
            for f in (range(n) if own in (None, screen) else sorted({0, n - 1})):
                out[f'{state}/{screen}/{f:02d}'] = hashlib.sha256(frame(lib, screen, f, view)).hexdigest()[:16]
    return out


def main(argv):
    if len(argv) > 1 and argv[1] in ('--digest', '--update'):
        with tempfile.TemporaryDirectory() as tmp:
            text = json.dumps(digests(build(tmp)), indent=0, sort_keys=True) + '\n'
        if argv[1] == '--digest':
            sys.stdout.write(text)
        else:
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(text)
            print(GOLDEN)
        return 0
    out = Path(argv[1]) if len(argv) > 1 else OUT
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        lib = build(tmp)
        view = demo_view()
        view.last_seq = 1234   # the mockups' burst and banner
        written = []
        for screen, frames in FRAMES.items():
            for frame in frames:
                path = out/f'{screen.lower()}-f{frame:02d}.png'
                png(shade(lib, screen, frame, view), path)
                written.append(path)
        for name, (screen, frame, v) in views().items():
            png(shade(lib, screen, frame, v), out/f'{name}.png')
            written.append(out/f'{name}.png')
    for path in written:
        print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
