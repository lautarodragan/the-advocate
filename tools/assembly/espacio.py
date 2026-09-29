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
* **Bank 0**: the `.cfg`'s `ROM` area minus `CODE` and `TABLAS`, which share
  it.
* **Bank 1**: what the `.align $8000` in `cabecera.s` pads, which is what
  closes `FAR`. It is recognized by the source line and not by the position:
  if `FAR` filled the bank exactly, there would be no padding and it would
  give zero.
* **BSS and ZEROPAGE**: their `.cfg` areas minus what they take.
* **Texts**: `MENSAJES_BYTES` against `MENSAJES_TOPE`, which the converter
  emits next to the block; see `eventos.MENSAJES_PASO`.
"""

import argparse
import os
import re
import sys

# `realpath` and not `abspath`: `just herramientas` installs this script on
# the PATH as a symlink, and what matters is where the real file is.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from common import environment                              # noqa: E402
from common import project                              # noqa: E402
from assembly import banks                           # noqa: E402
from assembly import assemble                        # noqa: E402

CAMPO = re.compile(r'(\w+)=("[^"]*"|[^,\s]+)')


def _registros(dbg, clase):
    """The `clase` lines of the `.dbg`, as dictionaries."""
    with open(dbg) as archivo:
        for linea in archivo:
            if linea.startswith(clase + "\t"):
                yield {k: v.strip('"') for k, v in CAMPO.findall(linea)}


def _areas(cfg):
    """{area: size} from the `MEMORY` of an `ld65` `.cfg`."""
    with open(cfg) as archivo:
        texto = archivo.read()
    return {nombre: int(tam, 16) for nombre, tam in
            re.findall(r"^\s*(\w+):\s*start = \$[0-9A-F]+, size = \$([0-9A-F]+)",
                       texto, re.M)}


def _relleno_de_far(dbg):
    """How much the `.align $8000` in `cabecera.s` pads, in bytes."""
    with open(os.path.join(project.runtime(), "cabecera.s")) as archivo:
        lineas = [n + 1 for n, l in enumerate(archivo)
                  if l.split(";")[0].strip().startswith(".align")]
    archivos = {f["id"] for f in _registros(dbg, "file")
                if f["name"].endswith("cabecera.s")}
    spans = set()
    for linea in _registros(dbg, "line"):
        if linea["file"] in archivos and int(linea["line"]) in lineas \
                and "span" in linea:
            spans.update(linea["span"].split("+"))
    return sum(int(s["size"], 0) for s in _registros(dbg, "span")
               if s["id"] in spans)


def medir(sfc):
    """What `mostrar` prints, as a dictionary, for the ROM `sfc`."""
    dbg = sfc + ".dbg"
    areas = _areas(os.path.join(os.path.dirname(sfc), "memoria.cfg"))
    usado = {s["name"]: int(s["size"], 0) for s in _registros(dbg, "seg")}
    datos = [b for b in range(banks.FIRST_BANK, banks.BANKS)
             if banks.segment_of(b) in areas]
    ocupados = [b for b in datos if usado.get(banks.segment_of(b))]
    ultimo = max(ocupados) if ocupados else banks.FIRST_BANK - 1
    huecos = [banks.BANK_SIZE - usado.get(banks.segment_of(b), 0)
              for b in datos if b <= ultimo]
    simbolos = assemble.symbols(dbg)
    return {
        "bancos": len(datos),
        "primero": datos[0],
        "ultimo": ultimo,
        "libres": len([b for b in datos if b > ultimo]),
        "huecos": sum(huecos),
        "hueco_mayor": max(huecos, default=0),
        "banco0": areas["ROM"] - usado.get("CODE", 0) - usado.get("TABLAS", 0),
        "banco1": _relleno_de_far(dbg),
        "bss": areas["RAM"] - usado.get("BSS", 0),
        "zeropage": areas["ZP"] - usado.get("ZEROPAGE", 0),
        "textos": simbolos.get("MENSAJES_BYTES"),
        "textos_tope": simbolos.get("MENSAJES_TOPE"),
    }


def _b(n):
    return "{:,}".format(n).replace(",", ".") + " B"


def mostrar(nombre, sfc):
    m = medir(sfc)
    # A ROM built separately is named by its path; a cartridge, by its name.
    print(nombre if os.path.isfile(nombre)
          else "%s  (%s)" % (nombre, os.path.relpath(sfc, project.root())))
    print("  data banks       %d of %d used, $%02X-$%02X; %d free after them"
          % (m["ultimo"] - m["primero"] + 1, m["bancos"], m["primero"],
             m["ultimo"], m["libres"]))
    print("  gaps             %s in the used ones, the largest %s"
          % (_b(m["huecos"]), _b(m["hueco_mayor"])))
    print("  bank 0           %s" % _b(m["banco0"]))
    print("  bank 1           %s" % _b(m["banco1"]))
    print("  BSS              %s" % _b(m["bss"]))
    print("  ZEROPAGE         %s" % _b(m["zeropage"]))
    if m["textos"] is None:
        print("  texts            the ROM does not say how long they are")
    else:
        print("  texts            %s of %s; %s left"
              % (_b(m["textos"]), _b(m["textos_tope"]),
                 _b(m["textos_tope"] - m["textos"])))


def main():
    project.from_command_line()
    from assembly import cartuchos
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    project.add_argument(parser)
    environment.add_arguments(parser, "test_cartridges")
    parser.add_argument("cuales", nargs="*", metavar="CARTRIDGE",
                        help="a cartridge from cartuchos.py or the path of a "
                             "built ROM; with nothing, every cartridge")
    args = parser.parse_args()
    environment.from_arguments(args, "test_cartridges")
    primero = True
    for cual in args.cuales or list(cartuchos.CARTUCHOS):
        if cual in cartuchos.CARTUCHOS:
            porque = cartuchos.viejo(cual)
            if porque:
                sys.exit("%s: %s; `just espacio` builds it first"
                         % (cual, porque))
            sfc = cartuchos.rom_de(cual)
        elif os.path.isfile(cual):
            sfc = os.path.abspath(cual)
        else:
            sys.exit("%r is neither a cartridge (%s) nor a built ROM"
                     % (cual, ", ".join(cartuchos.CARTUCHOS)))
        if not primero:
            print()
        primero = False
        mostrar(cual, sfc)


if __name__ == "__main__":
    main()
