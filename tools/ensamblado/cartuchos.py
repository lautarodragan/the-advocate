"""Los cartuchos del juego: `release`, la ROM que se juega y la que corre casi
toda la tanda, y `test-special`, con lo que no entra en ella.
Ninguna prueba arma: corren contra lo que deja esto —ver `tanda.rom`—.

    python3 tools/ensamblado/cartuchos.py            arma lo que haga falta
    python3 tools/ensamblado/cartuchos.py release    sólo ése, con sus pistas
                                                     de MSU-1: `just build`
    python3 tools/ensamblado/cartuchos.py --lista    qué caso va en qué cartucho

Un caso nuevo es un archivo en `pruebas/casos/` y nada más: entra solo en
`release` y se corre con `tanda.partida("<nombre>")`. Empieza con un
`Teleport` al mapa donde tiene que correr: el de arranque es el 4, el
enrutador del juego, cuya cinemática no espera a nadie.
"""

import argparse
import concurrent.futures
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
from port import comprimir                              # noqa: E402

CASOS = os.path.join(RAIZ, "pruebas", "casos")
FUENTE = os.path.join(RAIZ, "rom", "src")

# `tanda.py` lee la misma variable.
DESTINO = os.environ.get("CARTUCHOS",
                         os.path.join(RAIZ, "rom", "build", "tests"))

# Los mapas del juego que lleva `release`: **los de id menor a `MENOR_A`,
# menos `EXCLUIDOS`, más `AGREGADOS`**. Hoy es Lashe City entera y el camino
# principal del capítulo del mundo, hasta el túnel a Paradise. Hasta el
# 2026-09-27 era una lista escrita a mano; la regla y sus valores son de
# `workflow/tasks/*/la-carrera-y-lo-que-sigue.md` y de
# `workflow/tasks/*/el-mundo-y-lo-que-sigue.md` ("La regla de los mapas"), y
# taro pidió que la exclusión se mantenga chica.
#
# "Mapa" es un nodo de tipo 1 del árbol de RM2k. Los ids que faltan entre los
# de la regla sin estar excluidos —el 24, el 25, el 27, el 31 y el 35— son
# áreas: nodos sin `.lmu` que le marcan los encuentros a un rectángulo del
# padre.
#
# **Son valores de acá y no flags del conversor**, a propósito: al conversor le
# sigue llegando la lista entera en `--mapas`. Éste es el único que lo llama;
# `test_horneados` y `test_parches` necesitan la lista sin correrlo; y como el
# sello lleva los flags y no `data/`, un árbol que cambie qué mapas entran deja
# viejo al cartucho sólo si la lista viaja expandida.
#
# El 105, Mountain Path, es el primero del capítulo siguiente, adonde lleva el
# 66 ev18. La demo termina antes: al entrar a Tangle Forest (el 66 ev19, que
# el fork del 66 cambia por el cartel del fin), porque el camino del puente
# al túnel **cruza el bosque** —310, 311, 313 y 312, que sale al oeste del
# 66— y el bosque todavía no entra.
MENOR_A = 105

# Cada uno con su razón, que es lo que hay que revisar antes de sumarle otro.
EXCLUIDOS = {
    # Aura Tutorial: de otro capítulo, cuelga de `Tutorials` (161). Es el que
    # cuesta: trae su tema y dos animaciones.
    58: "el tutorial del aura, de otro capítulo",
    # Overlook Memory: de otro capítulo, cuelga del 219.
    104: "de otro capítulo",
    # Carpetas del árbol —Lashe City, The Rat Tracks, la de la carrera y
    # Northern World—: mapas negros a los que nadie salta.
    15: "carpeta",
    22: "carpeta",
    55: "carpeta",
    65: "carpeta",
    # Security Footage 2 y los tres `Backup`: respaldos de otros mapas a los
    # que nada lleva. Battle Rink Ladder cuelga del 199 y ningún `Teleport`
    # lleva a él.
    46: "inalcanzable",
    75: "inalcanzable",
    96: "inalcanzable",
    97: "inalcanzable",
    98: "inalcanzable",
    # Lo opcional del mundo, que no entra todavía: Yun Town (67, y su armería
    # y su posada) y Drust Camp (68 y sus minas). El 70 y el 73, que también
    # son de Yun Town, entran igual: ya estaban en la ROM como mapas de
    # prueba, y sin el 67 nada lleva a ellos. Ver "Lo que sigue" en
    # `el-mundo-y-lo-que-sigue.md`, el hito 5.
    67: "opcional: Yun Town",
    71: "opcional: Yun Town",
    72: "opcional: Yun Town",
    68: "opcional: Drust Camp",
    103: "opcional: Drust Camp",
}

# El tutorial del droide no cuelga de Lashe City sino de `Tutorials`, pero salta
# ahí la página del 48 que mete a AG7-17 en el grupo. Y el puente del norte
# (259) y lo que hay debajo (255), que es donde se prende el 849 que deja
# cruzarlo: el final del camino principal antes del túnel.
#
# Y el mapa de debug, que el juego no tiene: ver `CON_MAPA_DE_DEBUG`.
AGREGADOS = (164, 259, 255)

# **El mapa de debug**: un cuarto con una puerta a cada punto clave del juego
# —cada una deja el estado de alguien que jugó hasta ahí— y un NPC por
# compañero que lo suma o lo saca del grupo. Lo pidió taro el 2026-09-27, y
# "Begin the Story" arranca ahí. Es un mapa nuevo de `parches/manual/nuevos/`
# —ver `fork.nuevos`—, con un id que el juego no usa, y lo que hace cada
# puerta está en los comentarios de sus páginas.
#
# **Para una entrega limpia, `CON_MAPA_DE_DEBUG = False`**: el mapa sale del
# cartucho y la página 0 vuelve a ser `nada`, o sea que "Begin the Story"
# arranca en el mapa 4 como el juego. La tanda no depende de este valor: las
# pruebas que juegan desde el título eligen `LA_PARTIDA_DE_VERDAD`, que es la
# página 0 de la entrega limpia —ver `tanda.partida`—, y las del mapa de debug
# se saltean sin él.
CON_MAPA_DE_DEBUG = True
MAPA_DE_DEBUG = 900
if CON_MAPA_DE_DEBUG:
    AGREGADOS += (MAPA_DE_DEBUG,)


def mapas_de_la_regla(menor_a=MENOR_A, excluidos=EXCLUIDOS,
                      agregados=AGREGADOS):
    """Los mapas del juego en el orden en que van a `--mapas`: los de la regla
    de menor a mayor, y después los agregados. **El orden es el de la tabla de
    la ROM**, así que cambiarlo la mueve: ver `orden_de_mapas` en
    snes_convert.py.

    El árbol es el del volcado de `data/`, que es el que lee el conversor: por
    eso la ruta cae adentro de `data/` y no del juego —ver `lcf.volcado`—."""
    from rpgmaker import lcf
    arbol = lcf.TreeMap(os.path.join(lcf.DATOS, "RPG_RT.lmt"))
    de_la_regla = [m for m in range(1, menor_a)
                   if arbol.map_types.get(m) == 1 and m not in excluidos]
    return tuple(de_la_regla + [m for m in agregados if m not in de_la_regla])


# Los sectores con auto —37, 38, 47 y 48— entran los cuatro juntos: la elección
# del 36 es una sola página que compila con sus cuatro destinos o con ninguno.
# Una exclusión no los puede separar.
#
# La demo termina en el mundo, el 66, al entrar a Tangle Forest: el fork del
# 66 cambia ese `Teleport` por el cartel del fin. Los lugares del mundo cuyo
# destino no está —Yun Town, Drust Camp, el bosque en llamas— no hacen nada,
# porque sus páginas no compilan.
MAPAS_DEL_JUEGO = mapas_de_la_regla()

# Y los que sólo existen por la tanda: situaciones que ningún mapa del juego
# que entra ejercita. `parches.revisar` los lee de acá para no pedirles parche
# versionado.
MAPAS_DE_PRUEBA = (119, 121, 133, 261, 269, 348)

MAPAS = MAPAS_DEL_JUEGO + MAPAS_DE_PRUEBA

# Los que los casos ponen con la orden 34 o `ChangeSpriteAssociation`.
GRAFICOS = (("Future1", "0"), ("nobodyhere", "0"))

# La ROM que se juega, y la que corre la tanda: con título, cronómetro, todos
# los mapas y todos los casos. Hasta el 2026-09-25 eran dos, `release` y
# `test-main`, y se juntaron —ver `workflow/tasks/*/juntar-release-y-test-main.md`—:
# lo que se entrega es lo que se prueba. El grupo es el 10 y no el 11 de las
# pruebas porque la apertura del mapa 1 no corre con Kersh ya en el grupo; el
# 11 lo pone el caso `grupo-11`.
#
# **Los mapas y las páginas de prueba van en la ROM que se juega**, a
# propósito, inalcanzables: los mapas porque ningún `Teleport` del juego lleva
# a ellos, y las páginas por `PRIMERO`.
RELEASE = "release"
_DE_RELEASE = (["--grupo", "10", "--map-id", "4", "--mapas"]
               + [str(m) for m in MAPAS if m != 4]
               + [f for charset, indice in GRAFICOS
                  for f in ("--grafico-de-prueba", charset, indice)])

CARTUCHOS = {
    RELEASE: (_DE_RELEASE, None),
    # Lo que en `release` cambiaría las imágenes de los demás: los sprites
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
}

FUERA = {"grupo-11-12-13", "batalla", "batalla-item", "batalla-droide",
         "pelea-82-grupo-11-12",
         # Acá correría el bloque de textos de todos los casos.
         "empujon"}

# La página 0 **no pide nada** y corre siempre, en el mapa de arranque, al
# empezar: es la que corre en la partida de verdad. La k pide que
# `VARIABLE_DE_CASO` valga al menos k, y el juego no toca esa variable, así que
# con `nada` —ningún comando: la página sólo prende el switch que la apaga— los
# casos quedan apagados en la ROM que se juega. El arnés elige los demás
# escribiendo la variable. Con cualquier otro caso acá, el juego lo correría
# al empezar: hasta el 2026-09-25 era `grupo-11`, que mete a Kersh en el grupo
# y rompe la apertura.
#
# **Con el mapa de debug, la página 0 es la que lleva ahí** —un `Teleport` y
# Talan en el grupo, para que el héroe se vea—, y `nada` pasa a ser una página
# más, la que el arnés elige para jugar el juego como arranca sin él.
LA_PARTIDA_DE_VERDAD = "nada"
ENTRADA_AL_MAPA_DE_DEBUG = "mapa-de-debug"


def primero(con_mapa_de_debug=CON_MAPA_DE_DEBUG):
    """El caso de la página 0: lo que corre "Begin the Story"."""
    return (ENTRADA_AL_MAPA_DE_DEBUG if con_mapa_de_debug
            else LA_PARTIDA_DE_VERDAD)


def fuera(con_mapa_de_debug=CON_MAPA_DE_DEBUG):
    """Los casos que `release` no lleva. Sin el mapa, tampoco su entrada: su
    `Teleport` lleva a un mapa que no está, y el conversor se planta."""
    return FUERA | (set() if con_mapa_de_debug
                    else {ENTRADA_AL_MAPA_DE_DEBUG})


PRIMERO = primero()


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
    # Y el techo de cada tema, que cambia los streams: por sus valores y no
    # por el archivo, porque `just techos` lo reescribe con lo que midió —el
    # pico, la huella de la mezcla— después de armar, y eso no cambia la ROM.
    from audio import snes_music
    h.update(repr(sorted(snes_music.leer_techos().items())).encode())
    return h.hexdigest()[:16]


def archivos_de_la_huella(fuente=FUENTE):
    """Los archivos que lee `huella`, en orden. `fuente` es un parámetro sólo
    para que una prueba pueda pasarle un árbol armado a mano."""
    # Todo `rom/src/`, y no sólo lo que `main.s` incluye hoy: un archivo que
    # se agrega y se incluye en el mismo cambio tiene que dejar viejo al cartucho.
    partes = (sorted(r for r in glob.glob(os.path.join(fuente, "**"),
                                          recursive=True) if os.path.isfile(r))
              + ensamblar.binarios()
              + [tiles_bin.binario(), muestras_brr.binario(),
                 comprimir.binario()])
    partes += sorted(glob.glob(os.path.join(RAIZ, "tools", "*", "*.py")))
    partes += sorted(glob.glob(os.path.join(RAIZ, "parches", "manual", "*",
                                            "*")))
    return partes


def todos_los_casos():
    return sorted(os.path.splitext(os.path.basename(r))[0]
                  for r in glob.glob(os.path.join(CASOS, "*.json")))


def casos_de(nombre, con_mapa_de_debug=CON_MAPA_DE_DEBUG):
    """Los casos del cartucho, en el orden de sus páginas. `con_mapa_de_debug`
    es un parámetro sólo para que una prueba mire la entrega limpia sin
    armarla."""
    casos = CARTUCHOS[nombre][1]
    if casos is None:
        cero = primero(con_mapa_de_debug)
        return [cero] + [n for n in todos_los_casos()
                         if n not in fuera(con_mapa_de_debug) and n != cero]
    return list(casos)


def sin_titulo(nombre):
    """Si el cartucho arranca sin pantalla de título, directo en el mapa."""
    return "--sin-titulo" in CARTUCHOS[nombre][0]


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
    convertir(nombre, directorio(nombre), rom_de(nombre))
    with open(_archivo(nombre, "sello.txt"), "w") as archivo:
        archivo.write(sello(nombre, fuentes))
    return True


def convertir(nombre, destino, sfc, extra=()):
    """Convierte y ensambla el cartucho en `destino`, sin sello y aunque esté
    al día. `extra` son flags de más para el conversor: `tools/audio/techos.py`
    arma así una copia de `release` con otro volumen, sin tocar la de verdad."""
    flags, _casos = CARTUCHOS[nombre]
    os.makedirs(destino, exist_ok=True)
    log = os.path.join(destino, "conversor.log")
    # Los casos van al final: detrás de un `--caso`, cualquier flag del
    # cartucho sería de ese caso, y el conversor lo rechaza.
    de_casos = []
    for k, caso in enumerate(casos_de(nombre)):
        de_casos += (["--caso"] if k else []) + [
            "--comandos-de-prueba",
            os.path.join("pruebas", "casos", caso + ".json")]
    orden = ([sys.executable, os.path.join(RAIZ, "tools", "port",
                                           "snes_convert.py"),
              "-o", os.path.join(destino, "mapdata.inc"),
              "--msu", os.path.splitext(sfc)[0] + ".msu"]
             + flags + list(extra) + de_casos)
    hecho = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True)
    with open(log, "w") as archivo:
        archivo.write(hecho.stdout + hecho.stderr)
    if hecho.returncode:
        sys.stderr.write(hecho.stdout[-3000:] + hecho.stderr)
        sys.exit("%s: el conversor falló; todo está en %s" % (nombre, log))
    ensamblar.ensamblar(os.path.join(RAIZ, "rom", "src", "main.s"),
                        destino, sfc, sfc + ".sym")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lista", action="store_true",
                        help="qué caso va en qué cartucho, sin armar nada")
    parser.add_argument("nombres", nargs="*", metavar="CARTUCHO",
                        help="sólo éstos; sin nombres, todos. Es lo que usa "
                             "`just build release`")
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
    nombres = args.nombres or list(CARTUCHOS)
    # Los cartuchos y las pistas se arman a la vez, en hilos: cada uno escribe
    # en su directorio, y lo pesado corre en subprocesos —el conversor,
    # `ca65`, fluidsynth—. Lo que comparten es el caché en disco, que escribe
    # aparte y renombra. Lo que se imprime sigue en el orden de siempre.
    #
    # Las pistas, **detrás de `release`** y no a la par: son las de sus
    # temas, que el conversor deja en su `musica.json`. Mientras tanto se
    # arman los demás cartuchos.
    with concurrent.futures.ThreadPoolExecutor(len(nombres) + 1) as hilos:
        armados = {nombre: hilos.submit(armar, nombre, fuentes)
                   for nombre in nombres}
        hechas = (hilos.submit(pistas, armados[RELEASE])
                  if RELEASE in nombres else None)
        for nombre in nombres:
            print("%s: %s" % (nombre, "armado" if armados[nombre].result()
                              else "al día"))
            if nombre == RELEASE:
                print(hechas.result())


def pistas(armado=None):
    """Las pistas de MSU-1 al lado de la ROM que se juega: `release` las lleva
    siempre, así que no hay otra manera de tener la ROM con pistas.

    Van fuera del sello y se miran aunque la ROM esté al día: cuáles son lo
    dice el cartucho —su `musica.json`—, pero cómo suena cada una depende del
    MIDI, del soundfont y del sintetizador, y `msu.armar` ya sabe cuáles están
    —ver `clave_de_la_pista`—. Que estén al lado no cambia
    la tanda: el arnés le esconde las pistas al core, ver `retro.Consola`.
    Devuelve la línea que lo cuenta, que `main` imprime en su lugar.
    """
    if armado is not None:
        armado.result()         # el `musica.json` que dice cuáles son
    from audio import msu       # fluidsynth y ffmpeg, sólo para `release`
    hechas, estaban = msu.armar(rom_de(RELEASE), charlar=False)
    return ("%s: pistas de MSU-1, %d hechas y %d que ya estaban"
            % (RELEASE, hechas, estaban))


if __name__ == "__main__":
    main()
