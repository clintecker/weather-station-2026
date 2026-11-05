"""Render the TX's bench screens (firmware/stage0-node/App/scr_view.h) to PNG, from a host build of the
firmware's own drawing code, to compare by eye with the approved mockups.

    python3 tools/scr_render.py [OUT_DIR]     (default .superpowers/sdd/2026-11-04-node-oled-and-e2e/renders)

Each screen is drawn with a demo view (the mockups' values) at a few frames, 4 x scale, lit pixels in the
mockups' amber on black: <screen>-f<frame>.png. tests/test_scr_view.py builds the same library and
uses the view structure defined here."""
import ctypes
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT/'firmware/stage0-node/App'
COMMON = ROOT/'firmware/common'
OUT = ROOT/'.superpowers/sdd/2026-11-04-node-oled-and-e2e/renders'
W, H = 128, 64
SCREENS = ['NORMAL', 'BURST', 'BANNER', 'SCOPE', 'VANE', 'RAIN', 'SYSTEM', 'BOOT', 'HACK']   # enum scr_id
RAIN_AGE_NONE, RAIN_AGE_MAX_S = 0xFFFFFFFF, 99 * 3600   # App/mod_rain.h
SCR_TX_NONE, SCR_TX_WAIT, SCR_TX_NO_ACK, SCR_TX_ACK = -2, -1, 0, 1

# The screens' sources and their include paths. oled_fb.c is left out: the shim includes it, so a
# test can see every string drawn (the shim's oled_text checks each character against the font).
INCLUDES = ['-I', APP, '-I', COMMON, '-I', ROOT/'firmware']
SOURCES = [APP/'scr_view.c', APP/'scr_interludes.c', APP/'scr_rain.c', APP/'scr_art.c', COMMON/'oled_draw.c', COMMON/'font5x7.c']
SHIM = r'''
#include <string.h>
#include "scr_view.h"
#include "font5x7.h"
#define oled_text real_oled_text
#include "oled_fb.c"
#undef oled_text
unsigned shim_missing;          /* characters drawn that the font lacks */
char shim_missing_text[64];     /* the last string that had one */
int oled_text(oled_fb *fb, int x, int y, const char *s, int scale)
{
  for (const char *c = s; *c; c++)
    if (strchr(font5x7_chars, *c) == NULL)
    {
      shim_missing++;
      strncpy(shim_missing_text, s, sizeof shim_missing_text - 1);
    }
  return real_oled_text(fb, x, y, s, scale);
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
                ('key_ok', i)]


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
    return v


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


def draw(lib, screen, frame, view):
    """The screen's pixels: a set of (x, y)."""
    fb = ctypes.create_string_buffer(W * H // 8)
    lib.scr_draw(fb, SCREENS.index(screen), frame, ctypes.byref(view))
    return {(x, y) for y in range(H) for x in range(W) if lib.oled_get(fb, x, y)}


def png(pixels, path, scale=4):
    from PIL import Image   # requirements-dev.txt
    img = Image.new('RGB', (W * scale, H * scale), (5, 7, 10))
    for x, y in pixels:
        img.paste((244, 231, 161), (x * scale, y * scale, x * scale + scale, y * scale + scale))
    img.save(path)


# The frames worth a look: each step of each screen's animation.
FRAMES = {'NORMAL': [0], 'BURST': [0, 1, 8, 15], 'BANNER': [0], 'SCOPE': [0], 'VANE': [0, 1, 63], 'RAIN': [0], 'SYSTEM': [0, 63],
          'BOOT': [0, 30, 62], 'HACK': [0, 4, 12, 16, 18, 20, 21]}


def main(argv):
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
                png(draw(lib, screen, frame, view), path)
                written.append(path)
        waiting = demo_view()
        waiting.last_acked, waiting.last_seq, waiting.extra_frames = SCR_TX_WAIT, 1234, 0
        png(draw(lib, 'BANNER', 0, waiting), out/'banner-sending.png')
        noack = demo_view()
        noack.last_acked, noack.extra_frames = SCR_TX_NO_ACK, 3
        png(draw(lib, 'BANNER', 0, noack), out/'banner-noack-backlog.png')
        absent = demo_view()
        absent.air_ok = absent.box_ok = absent.press_ok = absent.uv_ok = 0
        absent.power.batt_ok = absent.power.gauge_ok = 0
        png(draw(lib, 'NORMAL', 0, absent), out/'normal-absent.png')
        written += [out/'banner-sending.png', out/'banner-noack-backlog.png', out/'normal-absent.png']
        for name, v in rain_views().items():
            png(draw(lib, 'RAIN', 0, v), out/f'rain-{name}.png')
            written.append(out/f'rain-{name}.png')
    for path in written:
        print(path)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
