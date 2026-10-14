"""Worst-case stack estimate from GCC call graphs (-fcallgraph-info=su).

    python3 tools/stack_report.py firmware/stage0-node/build/tx [--limit 2048]

Reads every *.ci file under the build directory: one node per function with its own frame size,
one edge per call. Computes the deepest path from main and from every interrupt handler.

Rules (conservative where the graph is incomplete):
- Only direct calls are followed (exact frame sums). A call through a pointer (callback, the
  Radio.* table, sequencer tasks, timer callbacks) can reach any function whose address is taken
  (a non-call relocation outside debug sections, from objdump -r) and that is linked (nm of .elf).
- D_main = deepest direct chain from main; D_cb = deepest direct chain from any address-taken
  function; D_irq = deepest direct chain from any interrupt handler.
- Assumption: at most two pointer hops on one stack (main loop -> task -> driver), true for this
  firmware's sequencer + SubGHz_Phy design. Interrupts may nest two deep and each may make one hop.
- Estimate = D_main + 2*D_cb + 2*(D_irq + D_cb) + 2 x 32 B exception frames (soft-float M4).
- Functions without call-graph data (prebuilt newlib/libgcc) count 0 bytes and are listed.
- Direct recursion cannot be bounded: reported, fails the check (known bounded cycles allowed).
Exit status 1 if the estimate exceeds --limit, or on recursion or dynamic frames.
"""
import argparse
import functools
import os
import math
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_TOOLCHAIN = os.environ.get('TOOLCHAIN') or str(Path.home()/'.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin')

NODE = re.compile(r'node: \{ title: "([^"]+)" label: "([^"]*)"')
EDGE = re.compile(r'edge: \{ sourcename: "([^"]+)" targetname: "([^"]+)"')
SIZE = re.compile(r'\\n(\d+) bytes \(([a-z,]+)\)')
EXCEPTION_FRAME = 32
INDIRECT = '__indirect_call'
# Recursion that is known to be bounded, with the reason. Counted as one extra level.
BOUNDED_RECURSION = {
    # ST radio.c: RadioSetPublicNetwork sets Current = Previous before calling RadioSetModem, whose
    # LoRa branch only calls back when they differ, so the cycle runs at most once (depth 2).
    frozenset({'RadioSetPublicNetwork', 'RadioSetModem'}),
    # Mbed TLS 3.6.6: CCM drives its inner cipher in ECB mode (ccm.c, mbedtls_ccm_setkey), and
    # mbedtls_cipher_update only calls back into CCM for MBEDTLS_MODE_CCM_STAR_NO_TAG (cipher.c), so
    # these graph cycles cannot happen at run time.
    frozenset({'mbedtls_ccm_crypt', 'mbedtls_cipher_update', 'mbedtls_ccm_update'}),
    frozenset({'mbedtls_cipher_update', 'mbedtls_ccm_update'}),
}


def load(build):
    frames, kinds, edges, defined_in = {}, {}, {}, {}
    for ci in sorted(Path(build).rglob('*.ci')):
        text = ci.read_text(errors='replace')
        for title, label in NODE.findall(text):
            m = SIZE.search(label)
            if m:
                frames[title] = int(m[1]); kinds[title] = m[2]
                defined_in.setdefault(title.split(':')[-1], []).append(title)
        for src, dst in EDGE.findall(text):
            edges.setdefault(src, set()).add(dst)
    return frames, kinds, edges, defined_in


def resolve(name, frames, defined_in):
    """Map a call target to defined function titles (a global may be defined in another file)."""
    if name in frames:
        return [name]
    return defined_in.get(name.split(':')[-1], [])


@functools.lru_cache(maxsize=None)
def nm_lines(elf, toolchain):
    """`arm-none-eabi-nm` of the .elf, run once per (elf, toolchain)."""
    return subprocess.run([str(Path(toolchain)/'arm-none-eabi-nm'), str(elf)], capture_output=True,
                          text=True, check=True).stdout.splitlines()


def address_taken(build, toolchain):
    """Function names whose address is taken (non-call relocations outside debug sections) and that
    survive linking into the .elf."""
    tool = lambda name: str(Path(toolchain)/f'arm-none-eabi-{name}')
    elf = next(Path(build).glob('*.elf'))
    linked = {line.split()[-1] for line in nm_lines(elf, toolchain)
              if len(line.split()) == 3 and line.split()[1] in 'Tt'}
    taken = set()
    for obj in Path(build).rglob('*.o'):
        out = subprocess.run([tool('objdump'), '-r', str(obj)], capture_output=True, text=True).stdout
        section = ''
        for line in out.splitlines():
            if line.startswith('RELOCATION RECORDS FOR ['):
                section = line[len('RELOCATION RECORDS FOR ['):-2]
                continue
            parts = line.split()
            if len(parts) != 3 or section.startswith('.debug') or section.startswith('.ARM'):
                continue
            if parts[1] in ('R_ARM_THM_CALL', 'R_ARM_THM_JUMP24', 'R_ARM_CALL', 'R_ARM_JUMP24'):
                continue
            name = parts[2].split('+')[0]
            if name.startswith('.text.'):
                name = name[len('.text.'):]
            taken.add(name)
    return taken & linked


def stack_symbols(build, toolchain):
    """Reserved stack (_Min_Stack_Size) and the free RAM the stack can really grow into."""
    elf = next(Path(build).glob('*.elf'))
    syms = {}
    for line in nm_lines(elf, toolchain):
        parts = line.split()
        if len(parts) == 3:
            syms[parts[2]] = int(parts[0], 16)
    free = syms['_estack'] - syms['_end'] - syms['_Min_Heap_Size']
    return syms['_Min_Stack_Size'], free


def analyse(build, toolchain=DEFAULT_TOOLCHAIN):
    frames, kinds, edges, defined_in = load(build)
    roots_irq = [f for f in frames if f.split(':')[-1].endswith(('_IRQHandler', '_Handler'))]
    taken = address_taken(build, toolchain)
    callbacks = [f for f in frames if f.split(':')[-1] in taken and f not in roots_irq]
    memo, missing, recursion = {}, set(), []

    def depth(f, stack):
        """Deepest direct-call stack below f (pointer calls are accounted for separately), and
        the lowest stack index at which a cycle was cut below f (len(stack) or more: none open).
        A result computed while a cycle through a caller still on the stack was cut short is
        partial (the caller's other callees were not counted on that path), so it is not
        memoised: reused from another path it would understate the depth."""
        if f in memo:
            return (*memo[f], math.inf)
        if f in stack:
            at = stack.index(f)
            cycle = stack[at:]
            if frozenset(c.split(':')[-1] for c in cycle) in BOUNDED_RECURSION:
                return frames[f], [f], at          # one extra level of the bounded cycle
            # Unbounded recursion is reported as an error; its partial results may be memoised
            # (not doing so is factorial in the cycle size).
            recursion.append(' -> '.join(c.split(':')[-1] for c in cycle + [f]))
            return 0, [f], math.inf
        best, path, cut = 0, [], math.inf
        for d in edges.get(f, ()):
            if d == INDIRECT:
                continue
            cands = resolve(d, frames, defined_in)
            if not cands:
                missing.add(d.split(':')[-1])
            for c in cands:
                cost, p, c_cut = depth(c, stack + [f])
                cut = min(cut, c_cut)
                if cost > best:
                    best, path = cost, p
        result = (frames[f] + best, [f] + path)
        if cut >= len(stack):                      # no cut through a caller still open
            memo[f] = result
            cut = math.inf
        return (*result, cut)

    mains = [f for f in frames if f.split(':')[-1] == 'main']
    main_cost, main_path = depth(mains[0], [])[:2] if mains else (0, [])
    cb = max(((depth(c, [])[0], c) for c in callbacks), default=(0, '-'))
    irq = sorted(((depth(r, [])[0], r) for r in roots_irq), reverse=True)
    worst_irq = irq[0] if irq else (0, '-')
    second_irq = irq[1] if len(irq) > 1 else (0, '-')
    estimate = main_cost + 2 * cb[0] + 2 * (worst_irq[0] + cb[0]) + 2 * EXCEPTION_FRAME
    dynamic = [f for f, k in kinds.items() if 'dynamic' in k]
    return dict(main_cost=main_cost, main_path=main_path, irq=irq, estimate=estimate, cb=cb,
                missing=sorted(missing - {INDIRECT}), recursion=recursion, dynamic=dynamic,
                worst_irq=worst_irq, second_irq=second_irq)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('build')
    ap.add_argument('--limit', type=int, help='bytes; default = the linker _Min_Stack_Size read from the .elf')
    ap.add_argument('--toolchain', default=DEFAULT_TOOLCHAIN, help='directory with arm-none-eabi-nm/objdump')
    a = ap.parse_args(argv)
    r = analyse(a.build, a.toolchain)
    reserved, free = stack_symbols(a.build, a.toolchain)
    if a.limit is None:
        a.limit = reserved
    print(f'stack reserved by the linker: {reserved} B; RAM the stack can actually reach: {free} B')
    short = lambda f: f.split(':')[-1]
    print(f"deepest path from main: {r['main_cost']} B: " + ' > '.join(short(f) for f in r['main_path'][:14])
          + (' > ...' if len(r['main_path']) > 14 else ''))
    print(f"deepest callback (address-taken) chain: {r['cb'][0]} B from {short(r['cb'][1])}; "
          f"deepest interrupt: {r['worst_irq'][0]} B ({short(r['worst_irq'][1])})")
    print(f"estimate (D_main + 2 D_cb + 2 (D_irq + D_cb) + 2 x {EXCEPTION_FRAME} B): {r['estimate']} B "
          f"of {a.limit} B limit ({100 * r['estimate'] / a.limit:.0f} %)")
    if r['missing']:
        print('no call-graph data (counted as 0 B): ' + ', '.join(r['missing']))
    bad = False
    if r['recursion']:
        bad = True; print('ERROR unbounded recursion: ' + '; '.join(sorted(set(r['recursion']))))
    if r['dynamic']:
        bad = True; print('ERROR dynamic stack frames: ' + ', '.join(r['dynamic']))
    if r['estimate'] > a.limit:
        bad = True; print('ERROR estimate exceeds the limit')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
