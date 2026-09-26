"""Los cartuchos del juego: `release`, la ROM que se juega, y los de la tanda.
Ninguna prueba arma: corren contra lo que deja esto —ver `tanda.rom`—.

    python3 tools/ensamblado/cartuchos.py            arma lo que haga falta
    python3 tools/ensamblado/cartuchos.py release    sólo ése, con sus pistas
                                                     de MSU-1: `just build`
    python3 tools/ensamblado/cartuchos.py --lista    qué caso va en qué cartucho

Un caso nuevo es un archivo en `pruebas/casos/` y nada más: entra solo en
`test-main` y se corre con `tanda.partida("<nombre>")`. Si no corre en el mapa
de arranque, empieza con un `Teleport`.
"""

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

from audio import muestras_brr                          # noqa: E402
from ensamblado import ensamblar                        # noqa: E402
from port import tiles_bin                              # noqa: E402

CASOS = os.path.join(RAIZ, "pruebas", "casos")
FUENTE = os.path.join(RAIZ, "rom", "src")

# `tanda.py` lee la misma variable.
DESTINO = os.environ.get("CARTUCHOS",
                         os.path.join(RAIZ, "rom", "build", "tests"))

MAPA_DE_ARRANQUE = 6

# Cada mapa que se suma al proyecto se suma a todos los cartuchos. El 66 no:
# la ventana no le entra en la VRAM.
MAPAS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20,
         21, 23, 26, 28, 29, 30, 32, 33, 34, 36, 52, 70, 73, 74, 119, 121, 133,
         255, 261, 269, 348)

# Los que los casos ponen con la orden 34 o `ChangeSpriteAssociation`.
GRAFICOS = (("Future1", "0"), ("nobodyhere", "0"))

PRUEBAS = "test-main"


def _con_mapas(arranque, *mas):
    return (["--map-id", str(arranque), "--mapas"]
            + [str(m) for m in MAPAS if m != arranque] + list(mas))


_DE_PRUEBAS = _con_mapas(MAPA_DE_ARRANQUE, "--sin-titulo", "--sin-timer", *[
    f for charset, indice in GRAFICOS
    for f in ("--grafico-de-prueba", charset, indice)])

# La ROM que se juega, y la que usan las pruebas que juegan. Sin casos: no se
# entrega una ROM con páginas de prueba. El grupo es el 10 y no el 11 de las
# pruebas porque la apertura del mapa 1 no corre con Kersh ya en el grupo.
#
# Los mapas son lo de Lashe City que entra. Afuera quedan la persecución en
# auto, por `ControlVars` de clase 6 —ver `wishlist/la-carrera-en-release.md`—,
# y los sectores con auto: la elección del 36 es una sola página que compila
# con sus cuatro destinos o con ninguno, y los cuatro son de la etapa de Lashe
# City. El 38 ya entra en la VRAM —`LAYOUT_VENTANA_AMBOS`—; hasta el
# 2026-09-25 no entraba.
RELEASE = "release"
_DE_RELEASE = ["--grupo", "10", "--map-id", "4", "--mapas",
               "1", "2", "3", "5", "6", "7", "8", "9", "10", "11", "12", "13",
               "14", "16", "17", "18", "19", "20", "21", "23", "26", "28",
               "29", "30", "32", "33", "34", "36"]

CARTUCHOS = {
    PRUEBAS: (_DE_PRUEBAS, None),
    # Lo que en `test-main` cambiaría las imágenes de los demás: los sprites
    # de los actores 12 y 13, los flags y el relleno de textos. `empujon`
    # tiene el tamaño medido que deja el texto de `grupo-11-en-255` sobre el
    # borde de banco —ver `test_texto`—, y va último para no correrle la
    # página a nadie.
    "test-special": (["--map-id", "6", "--mapas", "74", "1", "2", "5", "21", "255",
               "--sin-titulo", "--sin-timer",
               "--heroe-encima", "--encuentros-de-prueba", "8",
               "--relleno-de-textos", "200"],
              ["parado-tapado", "grupo-11-12-13",
               "grupo-11-en-255", "batalla", "batalla-item", "batalla-droide",
               "pelea-82-grupo-11-12", "empujon"]),
    RELEASE: (_DE_RELEASE, []),
}

FUERA = {"grupo-11-12-13", "batalla", "batalla-item", "batalla-droide",
         "pelea-82-grupo-11-12",
         # Acá correría el bloque de textos de todos los casos.
         "empujon"}

PRIMERO = "grupo-11"


def huella():
    """De qué depende un cartucho, además de sus flags y sus casos.

    Lo que cambie la ROM y no esté acá la deja vieja en silencio: por eso
    entran los binarios y `parches/manual/`, que la cambian sin tocar ningún
    fuente.
    `data/` no, que lo regenera `just datos`. Se mira el contenido y no la fecha, que `git checkout` cambia.
    """
    h = hashlib.sha256()
    for ruta in archivos_de_la_huella():
        with open(ruta, "rb") as archivo:
            h.update(archivo.read())
    return h.hexdigest()[:16]


def archivos_de_la_huella(fuente=FUENTE):
    """Los archivos que lee `huella`, en orden. `fuente` es un parámetro sólo
    para que una prueba pueda pasarle un árbol armado a mano."""
    # Todo `rom/src/`, y no sólo lo que `main.s` incluye hoy: un archivo que
    # se agrega y se incluye en el mismo cambio tiene que dejar viejo al cartucho.
    partes = (sorted(r for r in glob.glob(os.path.join(fuente, "**"),
                                          recursive=True) if os.path.isfile(r))
              + ensamblar.binarios()
              + [tiles_bin.binario(), muestras_brr.binario()])
    partes += sorted(glob.glob(os.path.join(RAIZ, "tools", "*", "*.py")))
    partes += sorted(glob.glob(os.path.join(RAIZ, "parches", "manual", "*",
                                            "*")))
    return partes


def todos_los_casos():
    return sorted(os.path.splitext(os.path.basename(r))[0]
                  for r in glob.glob(os.path.join(CASOS, "*.json")))


def casos_de(nombre):
    """Los casos del cartucho, en el orden de sus páginas."""
    casos = CARTUCHOS[nombre][1]
    if casos is None:
        return [PRIMERO] + [n for n in todos_los_casos()
                            if n not in FUERA and n != PRIMERO]
    return list(casos)


def donde_esta(caso):
    """Los cartuchos que llevan el caso: primero el que lleva todos, después
    los demás por nombre.

    **No sale del orden de `CARTUCHOS`**, a propósito: un caso que está en
    dos —`parado-tapado`— corre en el primero, y con el diccionario en otro
    orden corría en el chico y movía su golden sin que nadie tocara el caso.
    """
    return sorted((n for n in CARTUCHOS if caso in casos_de(n)),
                  key=lambda n: (CARTUCHOS[n][1] is not None, n))


def _contenido(casos):
    contenido = []
    for caso in casos:
        with open(os.path.join(CASOS, caso + ".json"), encoding="utf-8") as a:
            contenido.append((caso, a.read()))
    return contenido


def sello(nombre, fuentes=None):
    """Lo que tiene que decir el sello del cartucho para que esté al día."""
    flags, _casos = CARTUCHOS[nombre]
    return "%s\n%r" % (fuentes or huella(),
                       (flags, _contenido(casos_de(nombre))))


def directorio(nombre):
    """Lo que las pruebas escriben no va acá sino a `pruebas/snapshots/`."""
    if nombre == RELEASE:
        return os.path.join(RAIZ, "rom", "build", RELEASE)
    return os.path.join(DESTINO, nombre.replace("test-", "", 1))


def rom_de(nombre):
    # El MSU-1 busca sus pistas por el nombre del `.sfc`.
    return os.path.join(directorio(nombre),
                        "abl.sfc" if nombre == RELEASE else "prueba.sfc")


def msu_de(nombre):
    """El `.msu` del cartucho: lo escribe el conversor, con los fondos de
    batalla que el MSU-1 le sirve a la ROM —ver tools/port/msu_datos.py—, y es
    también lo que enciende el MSU-1 para las pistas. Al lado del `.sfc` y con
    su nombre, que es donde lo buscan el emulador y el FX Pak."""
    return os.path.splitext(rom_de(nombre))[0] + ".msu"


def _archivo(nombre, que):
    return os.path.join(directorio(nombre), que)


def viejo(nombre, fuentes=None):
    """Por qué el cartucho no sirve, o None si está al día."""
    if nombre not in CARTUCHOS:
        return "no existe"
    try:
        with open(_archivo(nombre, "sello.txt")) as archivo:
            sellado = archivo.read()
    except OSError:
        return "no está armado"
    if sellado != sello(nombre, fuentes):
        return "se armó con otros fuentes, otros flags u otros casos"
    # Lo escribe el conversor junto con la ROM y no entra en el sello: sin él
    # el cartucho andaría, pero la prueba del MSU-1 no tendría qué leer.
    if not os.path.isfile(msu_de(nombre)):
        return "no tiene su .msu"
    return None


def manifiesto(nombre):
    """(los casos, si cada uno empieza con un `Teleport`), por página."""
    casos = casos_de(nombre)
    return casos, [_salta(texto) for _n, texto in _contenido(casos)]


def _salta(texto):
    """Si el caso empieza con un `Teleport`: el arnés espera la llegada, y
    mirar si la ROM está fundiendo no alcanza, porque hay mapas que funden
    solos al entrar."""
    comandos = json.loads(texto).get("event_commands") or [{}]
    return comandos[0].get("code") == "Teleport"


def armar(nombre, fuentes):
    """Convierte y ensambla el cartucho, si no está al día. Dice si lo armó."""
    if not viejo(nombre, fuentes):
        return False
    flags, _casos = CARTUCHOS[nombre]
    destino = directorio(nombre)
    os.makedirs(destino, exist_ok=True)
    sfc = rom_de(nombre)
    # Los casos van al final: detrás de un `--caso`, cualquier flag del
    # cartucho sería de ese caso, y el conversor lo rechaza.
    de_casos = []
    for k, caso in enumerate(casos_de(nombre)):
        de_casos += (["--caso"] if k else []) + [
            "--comandos-de-prueba",
            os.path.join("pruebas", "casos", caso + ".json")]
    convertir = ([sys.executable, os.path.join(RAIZ, "tools", "port",
                                               "snes_convert.py"),
                  "-o", _archivo(nombre, "mapdata.inc"),
                  "--msu", msu_de(nombre)] + flags + de_casos)
    hecho = subprocess.run(convertir, cwd=RAIZ, capture_output=True,
                           text=True)
    with open(_archivo(nombre, "conversor.log"), "w") as archivo:
        archivo.write(hecho.stdout + hecho.stderr)
    if hecho.returncode:
        sys.stderr.write(hecho.stdout[-3000:] + hecho.stderr)
        sys.exit("%s: el conversor falló; todo está en %s"
                 % (nombre, _archivo(nombre, "conversor.log")))
    ensamblar.ensamblar(os.path.join(RAIZ, "rom", "src", "main.s"),
                        destino, sfc, sfc + ".sym")
    with open(_archivo(nombre, "sello.txt"), "w") as archivo:
        archivo.write(sello(nombre, fuentes))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lista", action="store_true",
                        help="qué caso va en qué cartucho, sin armar nada")
    parser.add_argument("nombres", nargs="*", metavar="CARTUCHO",
                        help="sólo éstos; sin nombres, todos. Es lo que usa "
                             "`just build test-main`")
    args = parser.parse_args()
    for nombre in args.nombres:
        if nombre not in CARTUCHOS:
            sys.exit("no hay un cartucho %r: los que hay son %s"
                     % (nombre, ", ".join(CARTUCHOS)))
    if args.lista:
        for nombre in CARTUCHOS:
            casos = casos_de(nombre)
            print("%s (%d): %s" % (nombre, len(casos), " ".join(casos)))
        return
    fuentes = huella()
    for nombre in args.nombres or CARTUCHOS:
        print("%s: %s" % (nombre, "armado" if armar(nombre, fuentes)
                          else "al día"))
        if nombre == RELEASE:
            pistas()


def pistas():
    """Las pistas de MSU-1 al lado de la ROM que se juega: `release` las lleva
    siempre, así que no hay otra manera de tener la ROM con pistas.

    Van fuera del sello y se miran aunque la ROM esté al día: no dependen del
    cartucho sino del MIDI, del soundfont y del sintetizador, y `msu.armar` ya
    sabe cuáles están —ver `clave_de_la_pista`—. Que estén al lado no cambia
    la tanda: el arnés le esconde las pistas al core, ver `retro.Consola`.
    """
    from audio import msu       # fluidsynth y ffmpeg, sólo para `release`
    hechas, estaban = msu.armar(rom_de(RELEASE), charlar=False)
    print("%s: pistas de MSU-1, %d hechas y %d que ya estaban"
          % (RELEASE, hechas, estaban))


if __name__ == "__main__":
    main()
