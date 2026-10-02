"""Los cartuchos del juego, como los ve el que los arma.

Las pruebas no arman nada, y tampoco saben cómo se arma: le preguntan a
`rm2k-snes-cartridges` —con `--list --json`— qué cartuchos hay, dónde está
cada uno, qué casos lleva en qué página y si está al día, y a
`rm2k-snes-space` y `rm2k-snes-assemble` lo que miden ellos. Así el arnés
no importa nada del armado: si mañana el que arma cambia de lenguaje o de
repo, esto sigue igual mientras la salida diga lo mismo. Hasta el
2026-09-29 las pruebas importaban el armado de Python, y veinte archivos
dependían de cómo estaba escrito por dentro.

**Se pregunta una vez por proceso**: la respuesta no cambia mientras corre
la tanda —no se toca ningún fuente mientras corren las pruebas, ver
AGENTS.md—, y lo que dice de "al día" es de cuando se preguntó, igual que
antes lo era de cuando el arnés leía cada cartucho.
"""

import functools
import json
import subprocess

import lugares

# El cartucho que se juega y que corre casi toda la tanda. El archivo de
# proyecto tiene que declararlo con este nombre: lo exige el que arma.
RELEASE = "release"


def _correr(*comando):
    hecho = subprocess.run(comando, capture_output=True, text=True)
    if hecho.returncode:
        raise AssertionError("%s falló:\n%s" % (" ".join(comando),
                                                 hecho.stderr))
    return hecho.stdout


def _con_el_proyecto(ejecutable, *args):
    """El ejecutable, con este proyecto y con dónde van los cartuchos de
    prueba si `CARTUCHOS` lo mueve."""
    donde = (["--test-cartridges", lugares.CARTUCHOS_DE_PRUEBA]
             if lugares.CARTUCHOS_DE_PRUEBA else [])
    return _correr(ejecutable, "--project", lugares.ABL, *donde, *args)


@functools.lru_cache(maxsize=None)
def lista():
    """Todo lo que `rm2k-snes-cartridges --list --json` dice de los
    cartuchos, leído una vez."""
    return json.loads(_con_el_proyecto("rm2k-snes-cartridges", "--list",
                                       "--json"))


def nombres():
    """Los cartuchos, en el orden del archivo de proyecto."""
    return [c["name"] for c in lista()["cartridges"]]


def cartucho(nombre):
    """Lo que se sabe de un cartucho: `directory`, `rom`, `msu`, `flags`,
    `cases`, `teleports`, `without_title`, `stale`…"""
    for uno in lista()["cartridges"]:
        if uno["name"] == nombre:
            return uno
    raise AssertionError("no hay un cartucho %r: hay %s"
                         % (nombre, ", ".join(nombres())))


def directorio(nombre):
    return cartucho(nombre)["directory"]


def rom_de(nombre):
    return cartucho(nombre)["rom"]


def msu_de(nombre):
    """El `.msu` al lado de la ROM, con su nombre."""
    return cartucho(nombre)["msu"]


def viejo(nombre):
    """Por qué el cartucho no sirve —no está armado, o se armó con otros
    fuentes, flags o casos—, o None si está al día."""
    return cartucho(nombre)["stale"]


def casos_de(nombre):
    """Los casos del cartucho, en el orden de sus páginas."""
    return cartucho(nombre)["cases"]


def manifiesto(nombre):
    """(los casos, si cada uno empieza con un `Teleport`), por página."""
    uno = cartucho(nombre)
    return uno["cases"], uno["teleports"]


def sin_titulo(nombre):
    """Si el cartucho arranca sin pantalla de título, derecho en el mapa."""
    return cartucho(nombre)["without_title"]


def donde_esta(caso):
    """Los cartuchos que llevan el caso: primero el que lleva todos."""
    return lista()["where_is"].get(caso, [])


def todos_los_casos():
    return lista()["all_cases"]


def carpeta_de_casos():
    """Donde están los casos, un JSON por caso: `[paths] cases`."""
    return lista()["cases_dir"]


def raiz():
    """Donde corren `ca65` y `ld65`: las rutas de los fuentes que quedan en
    el `.dbg` son relativas a esto."""
    return lista()["root"]


def runtime():
    """El motor en ensamblador, que se arma junto con los datos de cada
    cartucho."""
    return lista()["runtime"]


# --- Los mapas y los casos que decide el archivo de proyecto ---------------

def mapas():
    """Los que lleva `release`: los del juego y los de prueba."""
    return lista()["maps"]["all"]


def mapas_del_juego():
    """Los de la regla, en el orden de la tabla de la ROM, y los agregados."""
    return lista()["maps"]["game"]


def mapas_de_prueba():
    return lista()["maps"]["test"]


def con_mapa_de_debug():
    """Si el mapa de debug va en el cartucho: `[debug] debug_map`."""
    return lista()["with_debug_map"]


def mapa_de_debug():
    return lista()["debug_map"]


def entrada_al_mapa_de_debug():
    """El caso que lleva al mapa de debug: la página 0 cuando va."""
    return lista()["debug_map_entry"]


def juego_de_verdad():
    """El caso que no hace nada: la página 0 de la entrega limpia."""
    return lista()["real_game"]


def casos_de_release(con_mapa_de_debug):
    """Los casos de `release` con el mapa de debug o sin él, sin armarlo."""
    clave = "with_debug_map" if con_mapa_de_debug else "without_debug_map"
    return lista()["release_cases"][clave]


# --- Lo que miden los otros dos -------------------------------------------

@functools.lru_cache(maxsize=None)
def espacio(nombre):
    """Lo que `rm2k-snes-space` mide del cartucho, como diccionario: `bank0`,
    `bank1`, `bank_far2`, `bss`, `zeropage`, `texts`, `texts_cap`…"""
    return json.loads(_con_el_proyecto("rm2k-snes-space", "--json",
                                       nombre))[nombre]


@functools.lru_cache(maxsize=None)
def mapa_de_memoria():
    """Los números del mapa de memoria con que se arma: el tamaño de un
    banco, cuántos hay, cuánto se le da a la pila."""
    return json.loads(_correr("rm2k-snes-assemble", "--memory-map"))


def pila():
    """Los bytes que se le reservan a la pila, bajando desde `$1FFF`."""
    return mapa_de_memoria()["stack"]


def fuentes(principal):
    """`principal` y los `.s` que incluye, en el orden en que los lee
    `ca65`."""
    return _correr("rm2k-snes-assemble", "--sources", principal).splitlines()
