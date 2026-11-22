"""The libretro cores the tests run a cartridge on, and where they are.

Two, always: snes9x is the one the goldens are taken with, and bsnes the one
that powers on with WRAM full of garbage, like the console, so a difference
between the two is uninitialised memory. bsnes needs the patch that exposes
its WRAM, `cores/bsnes-wram.patch` beside this package —`README.md` there
says how it is built—, and without it the tick clock cannot read the ROM's
tick.

Where they are belongs to the machine: these are the libretro packages'
paths, and a variable moves each one.
"""

import os

SNES9X = os.environ.get("SNES9X_CORE", "/usr/lib/libretro/snes9x_libretro.so")
BSNES = os.environ.get("BSNES_CORE", "/usr/lib/libretro/bsnes_libretro.so")

# And bsnes with the display-access audit, a third core: the same bsnes with
# `cores/bsnes-display-audit.patch` on top of the WRAM one. With its accurate
# PPU it counts every VRAM, CGRAM and OAM access the console would lose
# because the screen was being drawn: see `retro.Console.watch_the_display`.
# This is where A Blurred Line's `just audit-core`, in the ports, installs
# it by default, and where the-advocate's CI workflow puts it.
AUDIT = os.environ.get("AUDIT_CORE",
                       "/usr/local/lib/libretro/bsnes_audit_libretro.so")
# Its accurate PPU: the core's default is the fast one, which does not
# count.
ACCURATE = {"bsnes_ppu_fast": "OFF"}


def core_name(core):
    """`snes9x`, `bsnes`… out of a core's path."""
    return os.path.basename(core).split("_")[0]
