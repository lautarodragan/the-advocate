#!/usr/bin/env python3
"""Los cartuchos del juego: `release`, la ROM que se juega y la que corre casi
toda la tanda, y `test-special`, con lo que no entra en ella.
Ninguna prueba arma: corren contra lo que deja esto —ver `tanda.rom`—.

    rm2k-snes-cartridges            arma lo que haga falta
    rm2k-snes-cartridges release    sólo ése, con sus pistas de MSU-1:
                                    `just build`
    rm2k-snes-cartridges --lista    qué caso va en qué cartucho

Un caso nuevo es un archivo en `rom/pruebas/casos/` y nada más: entra solo en
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

# `realpath` y no `abspath`: `just herramientas` instala este script en el PATH
# como symlink, y lo que importa es dónde está el archivo de verdad.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from audio import muestras_brr                          # noqa: E402
from comun import perillas                              # noqa: E402
from comun import proyecto                              # noqa: E402
from ensamblado import ensamblar                        # noqa: E402
from port import tiles_bin                              # noqa: E402
from port import comprimir                              # noqa: E402

RAIZ = proyecto.raiz()
CASOS = proyecto.casos()
FUENTE = proyecto.runtime()

DESTINO = proyecto.cartuchos_de_prueba()

# **Qué lleva cada cartucho es del juego, y está en su archivo de proyecto**
# —`proyecto.archivo_de_proyecto()`, con los porqués de cada valor como
# comentarios—: qué mapas entran, cuáles se excluyen, qué cartuchos hay y qué
# casos lleva cada uno. Hasta el 2026-09-29 estaba escrito acá. Lo que queda
# en este archivo es el mecanismo que lo lee y arma; los nombres de módulo
# —`MENOR_A`, `CARTUCHOS`, `FUERA`…— son los de antes, porque la tanda los lee.
#
# **Los mapas son valores del archivo y no flags del conversor**, a propósito:
# al conversor le sigue llegando la lista entera en `--mapas`. Éste es el único
# que lo llama; `test_horneados` y `test_parches` necesitan la lista sin
# correrlo; y como el sello lleva los flags y no `rom/data/`, un árbol que
# cambie qué mapas entran deja viejo al cartucho sólo si la lista viaja
# expandida.
MENOR_A = perillas.valor("maps", "below", tipo=int)
EXCLUIDOS = frozenset(perillas.valor("maps", "excluded", tipo=list))
AGREGADOS = tuple(perillas.valor("maps", "added", tipo=list))


def el_mapa_de_debug():
    """El id del mapa de debug: el único mapa nuevo de
    `rom/parches/manual/nuevos/` —ver `fork.nuevos`—. Sale de ahí y no del
    archivo de proyecto para no escribir el número dos veces."""
    from rpgmaker import fork
    nuevos = sorted(fork.nuevos())
    if len(nuevos) != 1:
        sys.exit("el mapa de debug es el único mapa nuevo de %s, y hay %d: %s"
                 % (fork.NUEVOS, len(nuevos), nuevos))
    return nuevos[0]


# El mapa de debug, que el juego no tiene, entra detrás de los agregados.
CON_MAPA_DE_DEBUG = perillas.valor("debug", "debug_map", tipo=bool)
MAPA_DE_DEBUG = el_mapa_de_debug()
if CON_MAPA_DE_DEBUG:
    AGREGADOS += (MAPA_DE_DEBUG,)

# Los HP de los enemigos en la pelea: pasa `--hp-de-enemigos` al conversor en
# todos los cartuchos.
CON_HP_DE_ENEMIGOS = perillas.valor("debug", "enemy_hp", tipo=bool)
_DE_TODOS = ["--hp-de-enemigos"] if CON_HP_DE_ENEMIGOS else []


def mapas_de_la_regla(menor_a=MENOR_A, excluidos=EXCLUIDOS,
                      agregados=AGREGADOS):
    """Los mapas del juego en el orden en que van a `--mapas`: los de la regla
    de menor a mayor, y después los agregados. **El orden es el de la tabla de
    la ROM**, así que cambiarlo la mueve: ver `orden_de_mapas` en
    snes_convert.py.

    El árbol es el del volcado de `rom/data/`, que es el que lee el conversor: por
    eso la ruta cae adentro de `rom/data/` y no del juego —ver `lcf.volcado`—."""
    from rpgmaker import lcf
    arbol = lcf.TreeMap(os.path.join(lcf.DATOS, "RPG_RT.lmt"))
    de_la_regla = [m for m in range(1, menor_a)
                   if arbol.map_types.get(m) == 1 and m not in excluidos]
    return tuple(de_la_regla + [m for m in agregados if m not in de_la_regla])


MAPAS_DEL_JUEGO = mapas_de_la_regla()

# Y los que sólo existen por la tanda. `parches.revisar` los lee de acá para no
# pedirles parche versionado.
MAPAS_DE_PRUEBA = tuple(perillas.valor("maps", "test", tipo=list))

MAPAS = MAPAS_DEL_JUEGO + MAPAS_DE_PRUEBA

# El cartucho que se juega: el que lleva la ROM con el nombre del juego, sus
# pistas de MSU-1, y todos los casos. El archivo lo tiene que declarar.
RELEASE = "release"


def _cartucho(nombre):
    """(los flags del conversor, los casos o None si son todos) de un
    cartucho del archivo. Los flags salen en el orden de siempre —el grupo, el
    mapa de arranque, los mapas, los gráficos, lo demás—, porque van al sello
    tal cual."""
    def clave(k, tipo):
        return perillas.valor("cartridges", nombre, k, tipo=tipo)
    arranque = clave("start_map", int)
    grupo = clave("party", list)
    mapas = clave("maps", (str, list))
    if isinstance(mapas, str):
        if mapas != "game":
            sys.exit("%s: maps de %s es una lista o \"game\", y es %r"
                     % (proyecto.archivo_de_proyecto(), nombre, mapas))
        mapas = MAPAS
    casos = clave("cases", (str, list))
    if isinstance(casos, str):
        if casos != "all":
            sys.exit("%s: cases de %s es una lista o \"all\", y es %r"
                     % (proyecto.archivo_de_proyecto(), nombre, casos))
        casos = None
    flags = ((["--grupo"] + [str(a) for a in grupo] if grupo else [])
             + ["--map-id", str(arranque), "--mapas"]
             + [str(m) for m in mapas if m != arranque]
             + [f for charset, indice in clave("test_graphics", list)
                for f in ("--grafico-de-prueba", charset, indice)]
             + clave("flags", list) + _DE_TODOS)
    return flags, casos


CARTUCHOS = {nombre: _cartucho(nombre)
             for nombre in perillas.valor("cartridges", tipo=dict)}
if RELEASE not in CARTUCHOS or CARTUCHOS[RELEASE][1] is not None:
    sys.exit("%s: falta [cartridges.%s], con cases = \"all\""
             % (proyecto.archivo_de_proyecto(), RELEASE))

# Los casos que `release` no lleva, porque ahí cambiarían las imágenes de los
# demás.
FUERA = set(perillas.valor("cartridges", RELEASE, "excluded_cases",
                           tipo=list))

# La página 0 es la de la partida de verdad, salvo con el mapa de debug, que es
# la que lleva ahí: ver `[cases]` en el archivo.
LA_PARTIDA_DE_VERDAD = perillas.valor("cases", "real_game", tipo=str)
ENTRADA_AL_MAPA_DE_DEBUG = perillas.valor("cases", "debug_map_entry",
                                          tipo=str)


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
    entran los binarios y `rom/parches/manual/`, que la cambian sin tocar ningún
    fuente.
    `rom/data/` no, que lo regenera `just datos`. Se mira el contenido y no la fecha, que `git checkout` cambia.
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
    # Todo `tools/runtime/`, y no sólo lo que `main.s` incluye hoy: un archivo que
    # se agrega y se incluye en el mismo cambio tiene que dejar viejo al cartucho.
    partes = (sorted(r for r in glob.glob(os.path.join(fuente, "**"),
                                          recursive=True) if os.path.isfile(r))
              + ensamblar.binarios()
              + [tiles_bin.binario(), muestras_brr.binario(),
                 comprimir.binario()])
    # Menos las pruebas de las herramientas, que no arman nada: con ellas
    # adentro, editar una prueba dejaba viejos a todos los cartuchos.
    pruebas = os.path.join(proyecto.herramientas(), "pruebas", "")
    partes += sorted(r for r in glob.glob(os.path.join(proyecto.herramientas(),
                                                       "*", "*.py"))
                     if not r.startswith(pruebas))
    partes += sorted(glob.glob(os.path.join(proyecto.parches_manual(), "*",
                                            "*")))
    # Y el archivo de proyecto, entero: lo leen el conversor y la música, y
    # no sólo lo que llega a los flags del sello.
    partes.append(proyecto.archivo_de_proyecto())
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
    """Lo que las pruebas escriben no va acá sino a `rom/pruebas/snapshots/`."""
    if nombre == RELEASE:
        return os.path.join(proyecto.build(), RELEASE)
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
            os.path.relpath(os.path.join(CASOS, caso + ".json"), RAIZ)]
    orden = ([sys.executable, os.path.join(proyecto.herramientas(), "port",
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
    ensamblar.ensamblar(os.path.join(FUENTE, "main.s"),
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
