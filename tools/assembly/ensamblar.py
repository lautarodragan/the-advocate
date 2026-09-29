#!/usr/bin/env python3
"""Builds the ROM: `ca65` + `ld65`, the header checksum and the symbols.

    rm2k-snes-assemble tools/runtime/main.s -I rom/build/release \\
        -o rom/build/release/abl.sfc --simbolos …/abl.sfc.sym

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
GENERADOS = ("mapdata.inc", "musicdata.inc")

# Where the checksum goes in the file: bank 0's `$FFDE`, and its complement at
# `$FFDC`.
CHECKSUM = 0x7FDE
COMPLEMENTO = 0x7FDC

# Run as a script, Python puts this file's folder on `sys.path` and not
# `tools/`: see the same startup in `port/snes_convert.py`.
if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from common import project                                  # noqa: E402

# The repo root: `ca65` and `ld65` run from here, with relative paths.
RAIZ = project.root()

FALTA = """`%s` is missing, from the cc65 project.

It is not packaged in Arch; it is built once and stays on the PATH:

    git clone --depth 1 https://github.com/cc65/cc65.git /extras/ref/cc65
    make -C /extras/ref/cc65 -j8 bin
    ln -s /extras/ref/cc65/bin/ca65 /extras/ref/cc65/bin/ld65 /usr/local/bin/

See "Dónde corre esto" in AGENTS.md."""


# A real `.include`, not one quoted in a comment.
INCLUDE = re.compile(r'^\s*\.include\s+"([^"]+)"', re.M)


def fuentes(principal):
    """`principal` and the `.s` files it includes, in the order `ca65` reads
    them.

    It is the ROM's hand-written source: what a test has to read to ask "does
    the ROM declare such a thing?". The `.inc` files are left out because
    they are generated —those of `tools/protocol/` and the cartridge's—. An
    `.include` is looked up next to the file that does it, which is the first
    thing `ca65` tries.
    """
    directorio = os.path.dirname(os.path.abspath(principal))
    rutas = [principal]
    with open(principal, encoding="utf-8") as archivo:
        texto = archivo.read()
    for nombre in INCLUDE.findall(texto):
        if nombre.endswith(".s"):
            rutas += fuentes(os.path.join(directorio, nombre))
    return rutas


def texto_de_la_fuente(principal):
    """All the `fuentes` glued together, as if they were a single file."""
    partes = []
    for ruta in fuentes(principal):
        with open(ruta, encoding="utf-8") as archivo:
            partes.append(archivo.read())
    return "".join(partes)


class FaltaCc65(RuntimeError):
    """`ca65` or `ld65` is missing, with what to do to get them."""


def binarios():
    """The paths of `ca65` and `ld65` on the PATH."""
    rutas = []
    for nombre in ("ca65", "ld65"):
        ruta = shutil.which(nombre)
        if ruta is None:
            raise FaltaCc65(FALTA % nombre)
        rutas.append(ruta)
    return rutas


def checksum(rom):
    """Writes the header checksum, in place.

    It is the sum of all the bytes modulo 65536, with its complement next to
    it. The source leaves `$FFFF` and `$0000` in those four bytes on purpose:
    since the complement is the inverted checksum, the four always add up to
    510, so the sum does not change when they are written and there is no
    need to iterate.
    """
    antes = sum(rom) & 0xFFFF
    rom[CHECKSUM:CHECKSUM + 2] = antes.to_bytes(2, "little")
    rom[COMPLEMENTO:COMPLEMENTO + 2] = (antes ^ 0xFFFF).to_bytes(2, "little")
    despues = sum(rom) & 0xFFFF
    if despues != antes:
        raise ValueError("the checksum did not settle: $%04X against $%04X, which "
                         "means the header did not carry $FFFF and $0000"
                         % (despues, antes))
    return antes


def _campos(linea):
    """`sym\tid=0,name="x",val=0x1` → {"id": "0", "name": "x", "val": "0x1"}."""
    campos = {}
    for par in linea.rstrip("\n").split("\t", 1)[1].split(","):
        clave, _, valor = par.partition("=")
        campos[clave] = valor.strip('"')
    return campos


def simbolos(dbg):
    """The symbols in `ld65`'s debug file, as {name: value}.

    Labels inside a `.proc` come out as `proc::label`, the same as `w65` gave
    them. `ld65` writes the values as unsigned 32 bits, so a negative
    constant —`IMAGEN_X`— is given back its sign.
    """
    scopes, syms = {}, []
    with open(dbg) as archivo:
        for linea in archivo:
            if linea.startswith("scope\t"):
                c = _campos(linea)
                scopes[c["id"]] = (c["name"], c.get("parent"))
            elif linea.startswith("sym\t"):
                c = _campos(linea)
                if c.get("type") in ("lab", "equ") and "val" in c:
                    syms.append(c)
    tabla = {}
    for c in syms:
        partes, scope = [c["name"]], c.get("scope")
        while scope is not None and scope in scopes:
            nombre, scope = scopes[scope]
            if nombre:
                partes.insert(0, nombre)
        valor = int(c["val"], 16)
        if valor >= 1 << 31:
            valor -= 1 << 32
        tabla["::".join(partes)] = valor
    return tabla


def _relativa(ruta):
    """`ruta` relative to `RAIZ` if it is inside the repo; otherwise,
    absolute."""
    absoluta = os.path.abspath(ruta)
    if os.path.commonpath([absoluta, RAIZ]) != RAIZ:
        return absoluta
    return os.path.relpath(absoluta, RAIZ)


def ensamblar(fuente, incluir, rom, tabla=None):
    """Builds `rom` from `fuente`, with the generated files and the `.cfg` in
    `incluir`."""
    directorio = os.path.dirname(os.path.abspath(fuente))
    tapan = [n for n in GENERADOS if os.path.exists(os.path.join(directorio, n))]
    if tapan:
        raise RuntimeError(
            "%s has %s next to it, and `ca65` would read it before the one in %s: "
            "the ROM would come out with another cartridge's data. They are "
            "generated; they can be deleted." % (fuente, " and ".join(tapan), incluir))
    ca65, ld65 = binarios()
    # Paths relative to the root and `cwd` there, because `ca65` writes each
    # source into the debug file just as it opened it —the `.include` joined
    # to the including file's directory, or to the `-I`—. With absolute paths
    # the container's would stay, and Mesen2 would not find the source in the
    # host's clone: it looks for `file.Name` next to the `.dbg` and climbs up
    # folder by folder. See "Debugging with Mesen2" in
    # `docs/snes/emulators.md`.
    fuente_r, incluir_r = _relativa(fuente), _relativa(incluir)
    rom_r = _relativa(rom)
    objeto, dbg = rom_r + ".o", rom_r + ".dbg"
    subprocess.run([ca65, "-g", "--cpu", "65816", "-I", incluir_r, fuente_r,
                    "-o", objeto], check=True, cwd=RAIZ)
    subprocess.run([ld65, "-C", os.path.join(incluir_r, "memoria.cfg"),
                    objeto, "-o", rom_r, "--dbgfile", dbg], check=True,
                   cwd=RAIZ)
    dbg = os.path.join(RAIZ, dbg)
    with open(rom, "r+b") as archivo:
        datos = bytearray(archivo.read())
        checksum(datos)
        archivo.seek(0)
        archivo.write(datos)
    if tabla:
        with open(tabla, "w") as archivo:
            for nombre, valor in sorted(simbolos(dbg).items()):
                archivo.write("%s %d\n" % (nombre, valor))
    print("%s -> %s (%d bytes)" % (fuente, rom, len(datos)))
    return rom


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fuente")
    parser.add_argument("-I", dest="incluir", required=True,
                        help="where the generated .inc files and memoria.cfg are")
    parser.add_argument("-o", dest="rom", required=True)
    parser.add_argument("--simbolos")
    args = parser.parse_args()
    try:
        ensamblar(args.fuente, args.incluir, args.rom, args.simbolos)
    except (FaltaCc65, RuntimeError) as error:
        sys.exit(str(error))
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)


if __name__ == "__main__":
    main()
