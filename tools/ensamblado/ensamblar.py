#!/usr/bin/env python3
"""Arma la ROM: `ca65` + `ld65`, el checksum de la cabecera y los símbolos.

    rm2k-snes-assemble rom/src/main.s -I rom/build/release \\
        -o rom/build/release/abl.sfc --simbolos …/abl.sfc.sym

Hasta el 2026-09-16 esto lo hacía `w65`, un ensamblador nuestro. `ca65` y `ld65`
hacen lo mismo salvo tres cosas, y son las que viven acá:

* **El checksum de la cabecera.** Los emuladores no lo miran, pero los menús de
  los flash carts leen la cabecera para saber el mapeo, y con basura pueden
  adivinar mal.
* **La tabla de símbolos, en el formato que leen las pruebas**: una línea por
  símbolo, `nombre valor`, con el valor en decimal. `ld65` la da en su archivo
  de depuración, que trae mucho más.
* **Negarse a armar con un `.inc` generado en `rom/src/`.** `ca65` busca
  los `.include` primero en el directorio del archivo que incluye y recién
  después en los `-I`, así que uno viejo en `rom/src/` taparía al del cartucho
  sin decir nada: la ROM saldría con los datos de otro.

Lo que **no** tiene equivalente es un control que hacía `w65`: que cada salto
llegue a su etiqueta con los registros al ancho que ella declara.

El mapa de memoria no está acá: lo escribe el conversor, `memoria.cfg`, al lado
de los `.inc`. Ver `tools/ensamblado/bancos.py`.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

# Los que escribe el conversor. Si alguno aparece junto a la fuente, tapa al del
# directorio que se pasa con -I.
GENERADOS = ("mapdata.inc", "musicdata.inc")

# Dónde va el checksum en el archivo: `$FFDE` del banco 0, y su complemento en
# `$FFDC`.
CHECKSUM = 0x7FDE
COMPLEMENTO = 0x7FDC

# La raíz del repo: `ca65` y `ld65` corren parados acá, con rutas relativas.
# `realpath` y no `abspath`: `just herramientas` instala este script en el PATH
# como symlink, y lo que importa es dónde está el archivo de verdad.
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

FALTA = """falta `%s`, del proyecto cc65.

No viene empaquetado en Arch; se compila una vez y queda en el PATH:

    git clone --depth 1 https://github.com/cc65/cc65.git /extras/ref/cc65
    make -C /extras/ref/cc65 -j8 bin
    ln -s /extras/ref/cc65/bin/ca65 /extras/ref/cc65/bin/ld65 /usr/local/bin/

Ver "Dónde corre esto" en AGENTS.md."""


# Un `.include` de verdad, no uno citado en un comentario.
INCLUDE = re.compile(r'^\s*\.include\s+"([^"]+)"', re.M)


def fuentes(principal):
    """`principal` y los `.s` que incluye, en el orden en que los lee `ca65`.

    Es la fuente escrita a mano de la ROM: lo que una prueba tiene que leer
    para preguntar "¿la ROM declara tal cosa?". Los `.inc` quedan afuera porque
    son generados —los de `tools/protocol/` y los del cartucho—. Un `.include`
    se busca al lado del archivo que lo hace, que es lo primero que prueba
    `ca65`.
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
    """Todas las `fuentes` pegadas, como si fueran un solo archivo."""
    partes = []
    for ruta in fuentes(principal):
        with open(ruta, encoding="utf-8") as archivo:
            partes.append(archivo.read())
    return "".join(partes)


class FaltaCc65(RuntimeError):
    """No está `ca65` o `ld65`, con qué hacer para tenerlos."""


def binarios():
    """Las rutas de `ca65` y `ld65` del PATH."""
    rutas = []
    for nombre in ("ca65", "ld65"):
        ruta = shutil.which(nombre)
        if ruta is None:
            raise FaltaCc65(FALTA % nombre)
        rutas.append(ruta)
    return rutas


def checksum(rom):
    """Escribe el checksum de la cabecera, en el lugar.

    Es la suma de todos los bytes módulo 65536, con su complemento al lado. La
    fuente deja `$FFFF` y `$0000` en esos cuatro bytes a propósito: como el
    complemento es el checksum invertido, los cuatro suman siempre 510, así que
    la suma no cambia al escribirlos y no hace falta iterar.
    """
    antes = sum(rom) & 0xFFFF
    rom[CHECKSUM:CHECKSUM + 2] = antes.to_bytes(2, "little")
    rom[COMPLEMENTO:COMPLEMENTO + 2] = (antes ^ 0xFFFF).to_bytes(2, "little")
    despues = sum(rom) & 0xFFFF
    if despues != antes:
        raise ValueError("el checksum no se asentó: $%04X contra $%04X, y eso "
                         "quiere decir que la cabecera no traía $FFFF y $0000"
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
    """Los símbolos del archivo de depuración de `ld65`, como {nombre: valor}.

    Las etiquetas de adentro de un `.proc` salen como `proc::etiqueta`, igual
    que las daba `w65`. `ld65` escribe los valores en 32 bits sin signo, así que
    una constante negativa —`IMAGEN_X`— se devuelve a su signo.
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
    """`ruta` relativa a `RAIZ` si está adentro del repo; si no, absoluta."""
    absoluta = os.path.abspath(ruta)
    if os.path.commonpath([absoluta, RAIZ]) != RAIZ:
        return absoluta
    return os.path.relpath(absoluta, RAIZ)


def ensamblar(fuente, incluir, rom, tabla=None):
    """Arma `rom` desde `fuente`, con los generados y el `.cfg` de `incluir`."""
    directorio = os.path.dirname(os.path.abspath(fuente))
    tapan = [n for n in GENERADOS if os.path.exists(os.path.join(directorio, n))]
    if tapan:
        raise RuntimeError(
            "%s tiene %s al lado, y `ca65` lo leería antes que el de %s: la ROM "
            "saldría con los datos de otro cartucho. Son generados; se pueden "
            "borrar." % (fuente, " y ".join(tapan), incluir))
    ca65, ld65 = binarios()
    # Rutas relativas a la raíz y `cwd` ahí, porque `ca65` escribe en el
    # archivo de depuración cada fuente tal como la abrió —el `.include` pegado
    # al directorio del que incluye, o al `-I`—. Con rutas absolutas quedaría
    # la del contenedor, y Mesen2 no encontraría el fuente en el clon del
    # host: busca `file.Name` al lado del `.dbg` y va subiendo de carpeta.
    # Ver "Depurar con Mesen2" en `docs/snes/emulators.md`.
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
                        help="donde están los .inc generados y memoria.cfg")
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
