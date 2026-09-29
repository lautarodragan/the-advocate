#!/usr/bin/env python3
"""How much space each cartridge has left: it prints it and does not write
it down.

    rm2k-snes-space                  every cartridge
    rm2k-snes-space release          only that one
    rm2k-snes-space DIR/abl.sfc      a ROM built separately

It is `just espacio`. Everything comes from what the build left next to the
ROM —`ld65`'s `.dbg` and the converter's `memoria.cfg`—, so it neither
relinks nor assembles anything. Until 2026-09-27 this was measured by hand,
linking a `.res N` against the recipe's `.o` (see "Trampas del entorno" in
AGENTS.md), and the numbers that got written down went stale on their own.

What it prints, and where each thing comes from:

* **Data banks**: the `BANKnn` from `banks.FIRST_BANK`, against the ones
  that fit in the `.cfg`. A "used" bank is one that has something; the
  "free" ones are those that come after the last used one. **It is the
  number that matters**, and not a percentage: the packing leaves gaps, and
  banks `$7E`/`$7F` are not ROM.
* **Gaps**: what is left over inside the used ones. With `banks.py`'s
  packing almost all of it is the end of the last one; see `resolve`.
* **Bank 0**: the `.cfg`'s `ROM` area minus `CODE` and `TABLES`, which share
  it.
* **Bank 1**: what the `.align $8000` in `header.s` pads, which is what
  closes `FAR`. It is recognized by the source line and not by the position:
  if `FAR` filled the bank exactly, there would be no padding and it would
  give zero.
* **BSS and ZEROPAGE**: their `.cfg` areas minus what they take.
* **Texts**: `MESSAGES_BYTES` against `MESSAGES_CAP`, which the converter
  emits next to the block; see `events.MESSAGES_STEP`.
"""

import argparse
import os
import re
import sys

# `realpath` and not `abspath`: `just install` installs this script on
# the PATH as a symlink, and what matters is where the real file is.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from common import environment                              # noqa: E402
from common import project                              # noqa: E402
from assembly import banks                           # noqa: E402
from assembly import assemble                        # noqa: E402

FIELD = re.compile(r'(\w+)=("[^"]*"|[^,\s]+)')


def _records(dbg, kind):
    """The `kind` lines of the `.dbg`, as dictionaries."""
    with open(dbg) as handle:
        for line in handle:
            if line.startswith(kind + "\t"):
                yield {k: v.strip('"') for k, v in FIELD.findall(line)}


def _areas(cfg):
    """{area: size} from the `MEMORY` of an `ld65` `.cfg`."""
    with open(cfg) as handle:
        text = handle.read()
    return {name: int(size, 16) for name, size in
            re.findall(r"^\s*(\w+):\s*start = \$[0-9A-F]+, size = \$([0-9A-F]+)",
                       text, re.M)}


def _far_padding(dbg):
    """How much the `.align $8000` in `header.s` pads, in bytes."""
    with open(os.path.join(project.runtime(), "header.s")) as handle:
        lines = [n + 1 for n, l in enumerate(handle)
                 if l.split(";")[0].strip().startswith(".align")]
    files = {f["id"] for f in _records(dbg, "file")
             if f["name"].endswith("header.s")}
    spans = set()
    for line in _records(dbg, "line"):
        if line["file"] in files and int(line["line"]) in lines \
                and "span" in line:
            spans.update(line["span"].split("+"))
    return sum(int(s["size"], 0) for s in _records(dbg, "span")
               if s["id"] in spans)


def measure(sfc):
    """What `show` prints, as a dictionary, for the ROM `sfc`."""
    dbg = sfc + ".dbg"
    areas = _areas(os.path.join(os.path.dirname(sfc), "memoria.cfg"))
    used = {s["name"]: int(s["size"], 0) for s in _records(dbg, "seg")}
    data_banks = [b for b in range(banks.FIRST_BANK, banks.BANKS)
                  if banks.segment_of(b) in areas]
    used_banks = [b for b in data_banks if used.get(banks.segment_of(b))]
    last = max(used_banks) if used_banks else banks.FIRST_BANK - 1
    gaps = [banks.BANK_SIZE - used.get(banks.segment_of(b), 0)
            for b in data_banks if b <= last]
    symbols = assemble.symbols(dbg)
    return {
        "banks": len(data_banks),
        "first": data_banks[0],
        "last": last,
        "free": len([b for b in data_banks if b > last]),
        "gaps": sum(gaps),
        "largest_gap": max(gaps, default=0),
        "bank0": areas["ROM"] - used.get("CODE", 0) - used.get("TABLES", 0),
        "bank1": _far_padding(dbg),
        "bss": areas["RAM"] - used.get("BSS", 0),
        "zeropage": areas["ZP"] - used.get("ZEROPAGE", 0),
        "texts": symbols.get("MESSAGES_BYTES"),
        "texts_cap": symbols.get("MESSAGES_CAP"),
    }


def _b(n):
    return "{:,}".format(n).replace(",", ".") + " B"


def show(name, sfc):
    m = measure(sfc)
    # A ROM built separately is named by its path; a cartridge, by its name.
    print(name if os.path.isfile(name)
          else "%s  (%s)" % (name, os.path.relpath(sfc, project.root())))
    print("  data banks       %d of %d used, $%02X-$%02X; %d free after them"
          % (m["last"] - m["first"] + 1, m["banks"], m["first"],
             m["last"], m["free"]))
    print("  gaps             %s in the used ones, the largest %s"
          % (_b(m["gaps"]), _b(m["largest_gap"])))
    print("  bank 0           %s" % _b(m["bank0"]))
    print("  bank 1           %s" % _b(m["bank1"]))
    print("  BSS              %s" % _b(m["bss"]))
    print("  ZEROPAGE         %s" % _b(m["zeropage"]))
    if m["texts"] is None:
        print("  texts            the ROM does not say how long they are")
    else:
        print("  texts            %s of %s; %s left"
              % (_b(m["texts"]), _b(m["texts_cap"]),
                 _b(m["texts_cap"] - m["texts"])))


def main():
    project.from_command_line()
    from assembly import cartridges
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    project.add_argument(parser)
    environment.add_arguments(parser, "test_cartridges")
    parser.add_argument("which_ones", nargs="*", metavar="CARTRIDGE",
                        help="a cartridge from cartridges.py or the path of a "
                             "built ROM; with nothing, every cartridge")
    args = parser.parse_args()
    environment.from_arguments(args, "test_cartridges")
    first = True
    for which in args.which_ones or list(cartridges.CARTRIDGES):
        if which in cartridges.CARTRIDGES:
            reason = cartridges.stale(which)
            if reason:
                sys.exit("%s: %s; `just espacio` builds it first"
                         % (which, reason))
            sfc = cartridges.rom_of(which)
        elif os.path.isfile(which):
            sfc = os.path.abspath(which)
        else:
            sys.exit("%r is neither a cartridge (%s) nor a built ROM"
                     % (which, ", ".join(cartridges.CARTRIDGES)))
        if not first:
            print()
        first = False
        show(which, sfc)


if __name__ == "__main__":
    main()
