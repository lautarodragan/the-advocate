"""Los cartuchos del juego: `release`, la ROM que se juega, y los de la tanda.
Se arman una vez, antes de la tanda, y las pruebas reciben su ruta.

Vive en `tools/` desde el 2026-09-24, cuando pasó a armar también `release`:
hasta ahí estaba en `pruebas/arnes/`, porque nació como parte del arnés.

Es el paso 9f. Hasta ahí cada prueba armaba el suyo con `tanda.cartucho` o
`consola.armar`, y la tanda convertía unos doscientos cartuchos casi iguales:
era casi todo el tiempo de una corrida en frío. Desde acá **ninguna prueba
convierte ni ensambla**: `just pruebas` corre esto primero, en serie, y las
pruebas buscan su caso por el nombre en lo que dejó —ver `tanda.rom`—.

    python3 tools/ensamblado/cartuchos.py            arma lo que haga falta
    python3 tools/ensamblado/cartuchos.py release    sólo ése: `just build`
    python3 tools/ensamblado/cartuchos.py --lista    qué caso va en qué cartucho

Un cartucho se rearma sólo si cambió algo de lo que lo arma: los fuentes de la
ROM, las herramientas, los binarios, los flags o lo que dice alguno de sus
casos. Es su sello, y es lo mismo que mira el arnés para negarse a correr
contra un cartucho viejo: ver `viejo`.

**Cómo se agrega un caso**: un archivo en `pruebas/casos/`, y nada más. Entra
solo en `test-main` —en el orden alfabético, así que los de atrás
cambian de página, y eso no le importa a nadie: la prueba lo pide por el
nombre— y la prueba lo corre con `tanda.partida("<nombre>")`. Si corre en otro
mapa que el de arranque, empieza con un `Teleport` a su mapa y a su celda.
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

# Dónde quedan. La variable es para correr la tanda contra otros —los de otro
# worktree, por ejemplo—; `tanda.py` lee la misma.
DESTINO = os.environ.get("CARTUCHOS",
                         os.path.join(RAIZ, "rom", "build", "tests"))

# Dónde arranca `test-main`: el mapa de la mayoría de los casos, y
# el que se midió en el 9e. Un caso que corre en otro lugar llega con el
# `Teleport` con que empieza; ver `mapa_del_caso` en snes_convert.py.
MAPA_DE_ARRANQUE = 6

# Los mapas: los de `release` más los que usan las pruebas, que es la
# regla de taro del 2026-09-16 —cada mapa que se suma al proyecto se suma para
# todos los builds—. Afuera queda el 66: la ventana no le entra en la VRAM.
MAPAS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20,
         21, 23, 26, 28, 29, 30, 32, 33, 34, 36, 52, 70, 73, 74, 119, 121, 133,
         255, 261, 269, 348)

# Los gráficos que las rutas de los casos le ponen a alguien con la orden 34
# o con `ChangeSpriteAssociation`. Van al banco de los mapas donde corre algún
# caso.
GRAFICOS = (("Future1", "0"), ("nobodyhere", "0"))

# El cartucho de las pruebas, el que lleva todo lo que entra.
PRUEBAS = "test-main"


def _con_mapas(arranque, *mas):
    return (["--map-id", str(arranque), "--mapas"]
            + [str(m) for m in MAPAS if m != arranque] + list(mas))


# Los cartuchos, en el orden en que se arman: nombre -> (flags, casos). Los
# casos van en el orden de sus páginas, y el primero es el que corre sin que
# nadie lo pida. `None` son todos los de `pruebas/casos/` menos los de
# `FUERA`.
_DE_PRUEBAS = _con_mapas(MAPA_DE_ARRANQUE, "--sin-titulo", "--sin-timer", *[
    f for charset, indice in GRAFICOS
    for f in ("--grafico-de-prueba", charset, indice)])

# **La ROM que taro juega**: la cadena entera de la apertura hasta Lashe City,
# con pantalla de título, en `rom/build/release/abl.sfc`, que es donde él la
# busca. Se arma con `just build release`, y `just pruebas` la arma sola.
#
# **Es un cartucho más desde el 2026-09-24**, y a propósito: las pruebas que
# juegan —el recorrido, la pantalla de título, las escenas de la apertura—
# corren sobre ella y no sobre un parecido. Hasta ese día corrían sobre
# `juego`, que tenía otros once mapas y cuatro páginas de prueba, así que la
# ROM que taro juega no la miraba ninguna prueba. No lleva casos: una ROM que
# se entrega no puede llevar páginas de prueba. Tampoco comparte directorio
# con los demás, y su archivo se llama `abl.sfc`: el MSU-1 busca sus pistas
# por el nombre del `.sfc`.
#
# Es una sola y **siempre con título**: hasta el 2026-09-20 eran dos, con y sin,
# y la de sin no la jugaba nadie. Es la misma decisión que dejó un solo `.sfc`
# por build en `/shared/builds/`; está en AGENTS.md.
#
# **Con el grupo de verdad, el 10**, y no con el 11 del banco de pruebas. El
# juego arranca con DummyHero y la apertura del mapa 1 lo da por sentado: con
# Kersh ya en el grupo la página automática no corre, y queda Kersh sobre negro,
# sin música y sin cámara. La referencia hace lo mismo, así que no sería un bug
# de la ROM: sería una ROM mal armada.
#
# Con cronómetro, para hacerle lugar al rojo de los dígitos. La lista de
# mapas es **el subárbol de "Lashe City" que entra**: el camino a la fábrica, el auditorio y el Director, Sector 30 y los Rat Tracks,
# Sector 27 con sus dos negocios y el galpón, la fuga del 27 y el auto, y la
# misión de los Neon Viper.
#
# **Lo que quedó afuera, y por qué**, porque acá es donde se va a mirar:
#
#   la persecución en auto   casi ninguna de sus páginas automáticas compila:
#                            leen la posición del auto con un `ControlVars` de
#                            clase 6 —coordenadas de un personaje—, que la ROM no
#                            hace, y el 49 además tiene un `KeyInputProc`. Sin
#                            eso el auto no dobla y el tráfico no aparece. De
#                            paso, sus tres mapas de 500x40 no entraban en los
#                            2 MB del cartucho. Ver
#                            `wishlist/la-carrera-en-release.md`.
#   los sectores con auto    a dónde lleva la elección del mapa 36. El **38 no
#                            entra en ningún reparto de VRAM**: sus tiles de
#                            fondo y de sprite más la ventana no entran en los
#                            64 KB. Y la elección del 36 es una sola página: o
#                            compilan los cuatro destinos o no compila ninguno.
RELEASE = "release"
_DE_RELEASE = ["--grupo", "10", "--map-id", "4", "--mapas",
               "1", "2", "3", "5", "6", "7", "8", "9", "10", "11", "12", "13",
               "14", "16", "17", "18", "19", "20", "21", "23", "26", "28",
               "29", "30", "32", "33", "34", "36"]

CARTUCHOS = {
    PRUEBAS: (_DE_PRUEBAS, None),
    # Lo que no entra en `test-main` o cuida una disposición del cartucho y
    # no una imagen: los casos con los actores 12 y 13 en el grupo —pueden
    # liderar, y sus sprites en todos los mapas le cambiaban los colores al
    # 13 de `test-main`: decisión de taro, para que `test-main` no dependa
    # de las peleas—, el héroe por encima de la capa, los encuentros cada 8
    # pasos —`ChangeEncounterSteps` no está hecho, así que el caso no lo
    # puede pedir—, el relleno de textos de 200, que corre los índices de la
    # batalla más allá del 255 y vive acá porque `batalla-item` es el caso que
    # lo mira, y el **borde de banco** del bloque de textos.
    #
    # El borde lo pone el caso `empujon`, que es una página de puro texto: los
    # textos de las páginas de prueba van delante de los de los mapas, así que
    # su tamaño es lo que elige dónde cae el borde adentro del bloque. Con el
    # empujón medido, el primer cuadro del 255 queda **encima** del borde
    # —empieza en un banco y termina en el otro— y el segundo entero del otro
    # lado, que son las dos cosas que prueba `test_texto`. Va **al final** de
    # la lista para no correrle la página a ningún otro caso.
    #
    # Hasta el 2026-09-20 eso lo hacían dos `--relleno-de-mensajes`, y hacían
    # falta dos cartuchos porque cada relleno ponía el **mismo** cuadro en otro
    # lugar. Con un empujón solo los dos cuadros caen en lugares distintos, así
    # que el segundo cartucho —`cruza`— se fue.
    #
    # Las dos lluvias estuvieron acá hasta el 2026-09-20 y volvieron al de
    # pruebas: caían en la paleta de los dígitos del cronómetro, que
    # `subir_timer_pal` sube sin teñir, y salían grises en una pantalla
    # teñida. Hoy `gotas_de_lluvia` saltea esa paleta.
    "test-special": (["--map-id", "6", "--mapas", "74", "1", "2", "5", "21", "255",
               "--sin-titulo", "--sin-timer",
               "--heroe-encima", "--encuentros-de-prueba", "8",
               "--relleno-de-textos", "200"],
              ["parado-tapado", "grupo-11-12-13",
               "grupo-11-en-255", "batalla", "batalla-item", "batalla-droide",
               "pelea-82-grupo-11-12", "empujon"]),
    RELEASE: (_DE_RELEASE, []),
}

# Los casos que no van en `test-main` porque viven en otro.
FUERA = {"grupo-11-12-13", "batalla", "batalla-item", "batalla-droide",
         "pelea-82-grupo-11-12",
         # Y el empujón, que sólo hace falta en `test-special`, donde se mide el
         # borde de banco. Hasta el 2026-09-24 además no cabía acá: el
         # operando de `OP_MESSAGE` contaba de a un byte y el bloque llegaba a
         # 64 KB. Hoy cuenta de a dos —ver `MENSAJES_PASO`—, pero meterlo
         # correría el bloque de todos los casos de este cartucho.
         "empujon"}

# El que corre sin que nadie lo pida, que es la página 0: el grupo de la tanda
# en el mapa de arranque.
PRIMERO = "grupo-11"


def huella():
    """De qué depende un cartucho de prueba, además de sus flags y sus casos.

    Todo lo que participa de armarlo: el fuente de la ROM, el conversor, el
    ensamblador y el modelo. Se mira el contenido y no la fecha: `git
    checkout` de ida y vuelta deja fechas nuevas con el mismo contenido.

    **Los binarios entran por sí mismos** —`ca65` y `ld65`, que ensamblan,
    `voodoo`, que convierte las capas, y `gunter`, que codifica las muestras—:
    si no entraran, reinstalarlos no invalidaría nada y las pruebas correrían
    contra ROMs armadas con los viejos, en silencio.

    `gunter` faltaba hasta el 2026-09-20, y era el mismo agujero que el
    párrafo de arriba describe: sus muestras viajan adentro del `.sfc`, así que
    recompilarlo cambiaba la ROM sin cambiar el sello. No se notó porque el
    caché de muestras sí lo miraba —`muestras_brr.version()`— y el `.py` que lo
    llama se tocaba casi siempre en el mismo cambio.

    **Y `juego/` faltaba hasta el 2026-09-22**, que es el mismo agujero otra
    vez y el que más caro salió: un fork cambia el mapa y su ChipSet, o sea lo
    que se dibuja, sin tocar ni `main.s` ni un `.py`. Tocar la receta del Hover
    Tram y volver a correr la tanda daba el cartucho **de antes**, en silencio,
    y eso mandó a documentar como divergencia de la ROM algo que era
    simplemente una ROM vieja. `data/` no entra: lo regenera `just datos` y no
    lo editamos a mano.
    """
    h = hashlib.sha256()
    partes = ([os.path.join(RAIZ, "rom", "src", "main.s")]
              + ensamblar.binarios()
              + [tiles_bin.binario(), muestras_brr.binario()])
    partes += sorted(glob.glob(os.path.join(RAIZ, "tools", "*", "*.py")))
    partes += sorted(glob.glob(os.path.join(RAIZ, "juego", "*", "*")))
    for ruta in partes:
        with open(ruta, "rb") as archivo:
            h.update(archivo.read())
    return h.hexdigest()[:16]


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
    """Los cartuchos que llevan el caso, `test-main` primero."""
    return [n for n in CARTUCHOS if caso in casos_de(n)]


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
    """Dónde queda el cartucho: `release` en el suyo, y los de la tanda en
    DESTINO sin el `test-` del nombre —`rom/build/tests/main`—. Lo que
    las pruebas escriben mientras corren no va acá sino a
    `pruebas/snapshots/`: los cartuchos son salida del build y entrada de la
    tanda, las capturas son salida de las pruebas."""
    if nombre == RELEASE:
        return os.path.join(RAIZ, "rom", "build", RELEASE)
    return os.path.join(DESTINO, nombre.replace("test-", "", 1))


def rom_de(nombre):
    """El `.sfc` del cartucho. El de `release` se llama como el juego."""
    return os.path.join(directorio(nombre),
                        "abl.sfc" if nombre == RELEASE else "prueba.sfc")


def _archivo(nombre, que):
    return os.path.join(directorio(nombre), que)


def viejo(nombre, fuentes=None):
    """Por qué el cartucho no sirve, o None si está al día."""
    if nombre not in CARTUCHOS:
        return "no existe"
    try:
        with open(_archivo(nombre, "sello.txt")) as archivo:
            if archivo.read() == sello(nombre, fuentes):
                return None
    except OSError:
        return "no está armado"
    return "se armó con otros fuentes, otros flags u otros casos"


def manifiesto(nombre):
    """(los casos, si cada uno empieza con un `Teleport`), por página."""
    casos = casos_de(nombre)
    return casos, [_salta(texto) for _n, texto in _contenido(casos)]


def _salta(texto):
    """Si el caso —el JSON de su archivo— empieza con un `Teleport`.

    El arnés lo necesita para esperar la llegada: ver
    `Partida._esperar_la_llegada`. Mirar si la ROM está fundiendo no alcanza,
    porque hay mapas que funden solos al entrar.
    """
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
                  "-o", _archivo(nombre, "mapdata.inc")] + flags + de_casos)
    hecho = subprocess.run(convertir, cwd=RAIZ, capture_output=True,
                           text=True)
    with open(_archivo(nombre, "conversor.log"), "w") as archivo:
        archivo.write(hecho.stdout + hecho.stderr)
    if hecho.returncode:
        sys.stderr.write(hecho.stdout[-3000:] + hecho.stderr)
        sys.exit("%s: el conversor falló; todo está en %s"
                 % (nombre, _archivo(nombre, "conversor.log")))
    # El mismo envoltorio que usan las recetas: `ca65` + `ld65`.
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


if __name__ == "__main__":
    main()
