#!/usr/bin/env python3
"""Builds the ROM: `ca65` + `ld65`, the header checksum and the symbols.

    rm2k-snes-assemble tools/runtime/main.s -I rom/build/release \\
        -o rom/build/release/abl.sfc --symbols …/abl.sfc.sym

Until 2026-09-16 this was done by `w65`, an assembler of ours. `ca65` and
`ld65` do the same except for three things, and those are what live here:

* **The header checksum.** Emulators do not look at it, but flash cart menus
  read the header to learn the mapping, and with garbage they may guess
  wrong.
* **The symbol table, in the format the tests read**: one line per symbol,
  `name value`, with the value in decimal. `ld65` gives it in its debug file,
  which carries much more.
* **Refusing to build with a generated `.inc` in `tools/runtime/`.** `ca65`
  looks up `.include`s first in the directory of the including file and only
  then in the `-I`s, so a stale one in `tools/runtime/` would shadow the
  cartridge's without saying anything: the ROM would come out with another
  one's data.

What has **no** equivalent is a check `w65` used to do: that each jump reaches
its label with the registers at the width the label declares.

The memory map is not here: the converter writes it, `memoria.cfg`, next to
the `.inc` files. See `tools/assembly/banks.py`.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

# The ones the converter writes. If any shows up next to the source, it
# shadows the one in the directory passed with -I.
GENERATED = ("mapdata.inc", "musicdata.inc")

# Where the checksum goes in the file: bank 0's `$FFDE`, and its complement at
# `$FFDC`.
CHECKSUM = 0x7FDE
COMPLEMENT = 0x7FDC

# Run as a script, Python puts this file's folder on `sys.path` and not
# `tools/`: see the same startup in `port/snes_convert.py`.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from common import project                                  # noqa: E402

# The repo root: `ca65` and `ld65` run from here, with relative paths.
ROOT = project.root()

MISSING = """`%s` is missing, from the cc65 project.

It is not packaged in Arch; it is built once and stays on the PATH:

    git clone --depth 1 https://github.com/cc65/cc65.git /extras/ref/cc65
    make -C /extras/ref/cc65 -j8 bin
    ln -s /extras/ref/cc65/bin/ca65 /extras/ref/cc65/bin/ld65 /usr/local/bin/

See "Dónde corre esto" in AGENTS.md."""


# A real `.include`, not one quoted in a comment.
INCLUDE = re.compile(r'^\s*\.include\s+"([^"]+)"', re.M)


def sources(main_file):
    """`main_file` and the `.s` files it includes, in the order `ca65` reads
    them.

    It is the ROM's hand-written source: what a test has to read to ask "does
    the ROM declare such a thing?". The `.inc` files are left out because
    they are generated —those of `tools/protocol/` and the cartridge's—. An
    `.include` is looked up next to the file that does it, which is the first
    thing `ca65` tries.
    """
    directory = os.path.dirname(os.path.abspath(main_file))
    paths = [main_file]
    with open(main_file, encoding="utf-8") as handle:
        text = handle.read()
    for name in INCLUDE.findall(text):
        if name.endswith(".s"):
            paths += sources(os.path.join(directory, name))
    return paths


def source_text(main_file):
    """All the `sources` glued together, as if they were a single file."""
    parts = []
    for path in sources(main_file):
        with open(path, encoding="utf-8") as handle:
            parts.append(handle.read())
    return "".join(parts)


class MissingCc65(RuntimeError):
    """`ca65` or `ld65` is missing, with what to do to get them."""


def binaries():
    """The paths of `ca65` and `ld65` on the PATH."""
    paths = []
    for name in ("ca65", "ld65"):
        path = shutil.which(name)
        if path is None:
            raise MissingCc65(MISSING % name)
        paths.append(path)
    return paths


def checksum(rom):
    """Writes the header checksum, in place.

    It is the sum of all the bytes modulo 65536, with its complement next to
    it. The source leaves `$FFFF` and `$0000` in those four bytes on purpose:
    since the complement is the inverted checksum, the four always add up to
    510, so the sum does not change when they are written and there is no
    need to iterate.
    """
    before = sum(rom) & 0xFFFF
    rom[CHECKSUM:CHECKSUM + 2] = before.to_bytes(2, "little")
    rom[COMPLEMENT:COMPLEMENT + 2] = (before ^ 0xFFFF).to_bytes(2, "little")
    after = sum(rom) & 0xFFFF
    if after != before:
        raise ValueError("the checksum did not settle: $%04X against $%04X, which "
                         "means the header did not carry $FFFF and $0000"
                         % (after, before))
    return before


def _fields(line):
    """`sym\tid=0,name="x",val=0x1` → {"id": "0", "name": "x", "val": "0x1"}."""
    fields = {}
    for pair in line.rstrip("\n").split("\t", 1)[1].split(","):
        key, _, value = pair.partition("=")
        fields[key] = value.strip('"')
    return fields


def symbols(dbg):
    """The symbols in `ld65`'s debug file, as {name: value}.

    Labels inside a `.proc` come out as `proc::label`, the same as `w65` gave
    them. `ld65` writes the values as unsigned 32 bits, so a negative
    constant —`IMAGEN_X`— is given back its sign.
    """
    scopes, syms = {}, []
    with open(dbg) as handle:
        for line in handle:
            if line.startswith("scope\t"):
                c = _fields(line)
                scopes[c["id"]] = (c["name"], c.get("parent"))
            elif line.startswith("sym\t"):
                c = _fields(line)
                if c.get("type") in ("lab", "equ") and "val" in c:
                    syms.append(c)
    table = {}
    for c in syms:
        parts, scope = [c["name"]], c.get("scope")
        while scope is not None and scope in scopes:
            name, scope = scopes[scope]
            if name:
                parts.insert(0, name)
        value = int(c["val"], 16)
        if value >= 1 << 31:
            value -= 1 << 32
        table["::".join(parts)] = value
    return table


def _relative(path):
    """`path` relative to `ROOT` if it is inside the repo; otherwise,
    absolute."""
    absolute = os.path.abspath(path)
    if os.path.commonpath([absolute, ROOT]) != ROOT:
        return absolute
    return os.path.relpath(absolute, ROOT)


def assemble(source, include, rom, table=None):
    """Builds `rom` from `source`, with the generated files and the `.cfg` in
    `include`."""
    directory = os.path.dirname(os.path.abspath(source))
    shadowing = [n for n in GENERATED if os.path.exists(os.path.join(directory, n))]
    if shadowing:
        raise RuntimeError(
            "%s has %s next to it, and `ca65` would read it before the one in %s: "
            "the ROM would come out with another cartridge's data. They are "
            "generated; they can be deleted." % (source, " and ".join(shadowing), include))
    ca65, ld65 = binaries()
    # Paths relative to the root and `cwd` there, because `ca65` writes each
    # source into the debug file just as it opened it —the `.include` joined
    # to the including file's directory, or to the `-I`—. With absolute paths
    # the container's would stay, and Mesen2 would not find the source in the
    # host's clone: it looks for `file.Name` next to the `.dbg` and climbs up
    # folder by folder. See "Debugging with Mesen2" in
    # `docs/snes/emulators.md`.
    source_r, include_r = _relative(source), _relative(include)
    rom_r = _relative(rom)
    obj, dbg = rom_r + ".o", rom_r + ".dbg"
    subprocess.run([ca65, "-g", "--cpu", "65816", "-I", include_r, source_r,
                    "-o", obj], check=True, cwd=ROOT)
    subprocess.run([ld65, "-C", os.path.join(include_r, "memoria.cfg"),
                    obj, "-o", rom_r, "--dbgfile", dbg], check=True,
                   cwd=ROOT)
    dbg = os.path.join(ROOT, dbg)
    with open(rom, "r+b") as handle:
        data = bytearray(handle.read())
        checksum(data)
        handle.seek(0)
        handle.write(data)
    if table:
        with open(table, "w") as handle:
            for name, value in sorted(symbols(dbg).items()):
                handle.write("%s %d\n" % (name, value))
    print("%s -> %s (%d bytes)" % (source, rom, len(data)))
    return rom


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source")
    parser.add_argument("-I", dest="include", required=True,
                        help="where the generated .inc files and memoria.cfg are")
    parser.add_argument("-o", dest="rom", required=True)
    parser.add_argument("--symbols")
    args = parser.parse_args()
    try:
        assemble(args.source, args.include, args.rom, args.symbols)
    except (MissingCc65, RuntimeError) as error:
        sys.exit(str(error))
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)


if __name__ == "__main__":
    main()
