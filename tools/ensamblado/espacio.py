#!/usr/bin/env python3
"""Cuánto espacio le queda a cada cartucho: lo imprime y no lo escribe.

    rm2k-snes-space                  todos los cartuchos
    rm2k-snes-space release          sólo ése
    rm2k-snes-space DIR/abl.sfc      una ROM armada aparte

Es `just espacio`. Todo sale de lo que dejó el armado al lado de la ROM —el
`.dbg` de `ld65` y el `memoria.cfg` del conversor—, así que no relinkea ni
ensambla nada. Hasta el 2026-09-27 esto se medía a mano, linkeando un `.res N`
contra el `.o` de la receta (ver "Trampas del entorno" en AGENTS.md), y los
números que quedaban escritos envejecían solos.

Lo que imprime, y de dónde sale cada cosa:

* **Bancos de datos**: los `BANKnn` desde `bancos.PRIMER_BANCO`, contra los que
  entran en el `.cfg`. Un banco "usado" es uno que tiene algo; los "libres"
  son los que vienen detrás del último usado. **Es el número que manda**, y
  no un porcentaje: el acomodo deja huecos, y los bancos `$7E`/`$7F` no son
  ROM.
* **Huecos**: lo que sobra adentro de los usados. Con el acomodo de
  `bancos.py` casi todo es el final del último; ver `resolver`.
* **Banco 0**: el área `ROM` del `.cfg` menos `CODE` y `TABLAS`, que la
  comparten.
* **Banco 1**: lo que rellena el `.align $8000` de `cabecera.s`, que es lo
  que cierra `FAR`. Se reconoce por la línea del fuente y no por la posición:
  si `FAR` llenara el banco justo, no habría relleno y daría cero.
* **BSS y ZEROPAGE**: sus áreas del `.cfg` menos lo que ocupan.
* **Textos**: `MENSAJES_BYTES` contra `MENSAJES_TOPE`, que emite el conversor
  al lado del bloque; ver `eventos.MENSAJES_PASO`.
"""

import argparse
import os
import re
import sys

# `realpath` y no `abspath`: `just herramientas` instala este script en el PATH
# como symlink, y lo que importa es dónde está el archivo de verdad.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from comun import proyecto                              # noqa: E402
from ensamblado import bancos                           # noqa: E402
from ensamblado import ensamblar                        # noqa: E402

CAMPO = re.compile(r'(\w+)=("[^"]*"|[^,\s]+)')


def _registros(dbg, clase):
    """Las líneas `clase` del `.dbg`, como diccionarios."""
    with open(dbg) as archivo:
        for linea in archivo:
            if linea.startswith(clase + "\t"):
                yield {k: v.strip('"') for k, v in CAMPO.findall(linea)}


def _areas(cfg):
    """{área: tamaño} del `MEMORY` de un `.cfg` de `ld65`."""
    with open(cfg) as archivo:
        texto = archivo.read()
    return {nombre: int(tam, 16) for nombre, tam in
            re.findall(r"^\s*(\w+):\s*start = \$[0-9A-F]+, size = \$([0-9A-F]+)",
                       texto, re.M)}


def _relleno_de_far(dbg):
    """Cuánto rellena el `.align $8000` de `cabecera.s`, en bytes."""
    with open(os.path.join(proyecto.runtime(), "cabecera.s")) as archivo:
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
    """Lo que imprime `mostrar`, como diccionario, para la ROM `sfc`."""
    dbg = sfc + ".dbg"
    areas = _areas(os.path.join(os.path.dirname(sfc), "memoria.cfg"))
    usado = {s["name"]: int(s["size"], 0) for s in _registros(dbg, "seg")}
    datos = [b for b in range(bancos.PRIMER_BANCO, bancos.BANCOS)
             if bancos.segmento_de(b) in areas]
    ocupados = [b for b in datos if usado.get(bancos.segmento_de(b))]
    ultimo = max(ocupados) if ocupados else bancos.PRIMER_BANCO - 1
    huecos = [bancos.BANCO - usado.get(bancos.segmento_de(b), 0)
              for b in datos if b <= ultimo]
    simbolos = ensamblar.simbolos(dbg)
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
    # Una ROM armada aparte se nombra por su ruta; un cartucho, por su nombre.
    print(nombre if os.path.isfile(nombre)
          else "%s  (%s)" % (nombre, os.path.relpath(sfc, proyecto.raiz())))
    print("  bancos de datos  %d de %d usados, $%02X-$%02X; %d libres detrás"
          % (m["ultimo"] - m["primero"] + 1, m["bancos"], m["primero"],
             m["ultimo"], m["libres"]))
    print("  huecos           %s en los usados, el mayor de %s"
          % (_b(m["huecos"]), _b(m["hueco_mayor"])))
    print("  banco 0          %s" % _b(m["banco0"]))
    print("  banco 1          %s" % _b(m["banco1"]))
    print("  BSS              %s" % _b(m["bss"]))
    print("  ZEROPAGE         %s" % _b(m["zeropage"]))
    if m["textos"] is None:
        print("  textos           la ROM no dice cuánto miden")
    else:
        print("  textos           %s de %s; quedan %s"
              % (_b(m["textos"]), _b(m["textos_tope"]),
                 _b(m["textos_tope"] - m["textos"])))


def main():
    from ensamblado import cartuchos
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("cuales", nargs="*", metavar="CARTUCHO",
                        help="un cartucho de cartuchos.py o la ruta de una "
                             "ROM armada; sin nada, todos los cartuchos")
    args = parser.parse_args()
    primero = True
    for cual in args.cuales or list(cartuchos.CARTUCHOS):
        if cual in cartuchos.CARTUCHOS:
            porque = cartuchos.viejo(cual)
            if porque:
                sys.exit("%s: %s; `just espacio` lo arma antes"
                         % (cual, porque))
            sfc = cartuchos.rom_de(cual)
        elif os.path.isfile(cual):
            sfc = os.path.abspath(cual)
        else:
            sys.exit("%r no es un cartucho (%s) ni una ROM armada"
                     % (cual, ", ".join(cartuchos.CARTUCHOS)))
        if not primero:
            print()
        primero = False
        mostrar(cual, sfc)


if __name__ == "__main__":
    main()
