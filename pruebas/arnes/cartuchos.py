"""Los cartuchos de prueba: se arman una vez, antes de la tanda, y las pruebas
reciben su ruta.

Es el paso 9f. Hasta ahí cada prueba armaba el suyo con `tanda.cartucho` o
`consola.armar`, y la tanda convertía unos doscientos cartuchos casi iguales:
era casi todo el tiempo de una corrida en frío. Desde acá **ninguna prueba
convierte ni ensambla**: `just pruebas` corre esto primero, en serie, y las
pruebas buscan su caso por el nombre en lo que dejó —ver `tanda.rom`—.

    python3 pruebas/arnes/cartuchos.py            arma lo que haga falta
    python3 pruebas/arnes/cartuchos.py --lista    qué caso va en qué cartucho

Un cartucho se rearma sólo si cambió algo de lo que lo arma: los fuentes de la
ROM, las herramientas, los binarios, los flags o lo que dice alguno de sus
casos. Es su sello, y es lo mismo que mira el arnés para negarse a correr
contra un cartucho viejo: ver `viejo`.

**Cómo se agrega un caso**: un archivo en `pruebas/casos/`, y nada más. Entra
solo en el cartucho de pruebas —en el orden alfabético, así que los de atrás
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
                         os.path.join(RAIZ, "rom", "build", "pruebas-unico"))

# Dónde arranca el cartucho de pruebas: el mapa de la mayoría de los casos, y
# el que se midió en el 9e. Un caso que corre en otro lugar llega con el
# `Teleport` con que empieza; ver `mapa_del_caso` en snes_convert.py.
MAPA_DE_ARRANQUE = 6

# Los mapas: los de `demo-ciudad` más los que usan las pruebas, que es la
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
PRUEBAS = "pruebas"


def _con_mapas(arranque, *mas):
    return (["--map-id", str(arranque), "--mapas"]
            + [str(m) for m in MAPAS if m != arranque] + list(mas))


# Los cartuchos, en el orden en que se arman: nombre -> (flags, casos). Los
# casos van en el orden de sus páginas, y el primero es el que corre sin que
# nadie lo pida. `None` son todos los de `pruebas/casos/` menos los de
# `FUERA`.
_DE_PRUEBAS = _con_mapas(MAPA_DE_ARRANQUE, *[
    f for charset, indice in GRAFICOS
    for f in ("--grafico-de-prueba", charset, indice)])

CARTUCHOS = {
    PRUEBAS: (_DE_PRUEBAS, None),
    # El mismo con la pantalla de título delante. El título cambia el
    # arranque del cartucho entero —`consola_cruda`, `reiniciar` y los
    # cuadros de hardware cuentan desde otro lado—, así que no puede ir en el
    # de pruebas. Lleva los mismos mapas y casos a propósito:
    # `test_titulo_es_el_mismo_juego` compara uno contra el otro. El tema de
    # arranque es para las pruebas de música, porque el 6 no trae uno propio.
    "titulo": (_DE_PRUEBAS + ["--con-titulo",
                              "--tema-de-arranque", "escape_newyork"], None),
    # Lo que no entra en el de pruebas o cuida una disposición del cartucho y
    # no una imagen: el actor 21 —con él la pantalla de ranuras junta 462
    # tiles de 448—, los casos con los actores 12 y 13 en el grupo —pueden
    # liderar, y sus sprites en todos los mapas le cambiaban los colores al
    # 13 del de pruebas: decisión de taro, para que el de pruebas no dependa
    # de las peleas—, el héroe por encima de la capa, los encuentros cada 8
    # pasos —`ChangeEncounterSteps` no está hecho, así que el caso no lo
    # puede pedir— y el relleno de mensajes de 33000. Y las dos
    # lluvias: en el 6 del de pruebas corren casos con cronómetro, las gotas
    # caen en la paleta de los dígitos, y ésa `subir_timer_pal` la sube sin
    # teñir. Es un defecto, está en ESTADO.md, y acá se evita no juntándolos.
    "chico": (["--map-id", "6", "--mapas", "74", "1", "2", "5", "21", "255",
               "--heroe-encima", "--encuentros-de-prueba", "8",
               "--relleno-de-mensajes", "33000"],
              ["grupo-21-en-74", "parado-tapado", "grupo-11-12-13",
               "grupo-11-en-255", "batalla", "batalla-item", "batalla-droide",
               "pelea-82-grupo-11-12", "pan-lluvia", "sacudir-lluvia"]),
    # El otro relleno de mensajes, que deja el primer mensaje del 255 encima
    # del borde de banco. No convive con el del chico: los dos corren el mismo
    # mensaje, cada uno a otro lugar. Y el relleno de textos, que en el chico
    # borraba los nombres de la lista "Use Item" de `batalla-item`: es un
    # defecto de la ROM, está en ESTADO.md. Medido que convive con éste: el
    # bloque de mensajes queda en la misma dirección.
    "cruza": (["--map-id", "255", "--relleno-de-mensajes", "32766",
               "--relleno-de-textos", "200"],
              ["grupo-11", "batalla"]),
    # El juego como se juega: arranca en el 4, con cronómetro en todos los
    # mapas. Llegar al 4 con un `Teleport` no es arrancar ahí —la cinemática
    # sale con otra rampa de fundido y otro tinte— y el cronómetro le saca
    # una paleta a cada mapa, que en el de pruebas movía goldens.
    "juego": (_con_mapas(4, "--con-timer",
                         "--tema-de-arranque", "escape_newyork"),
              ["nada", "cartel", "en-2"]),
}

# Los casos que no van en el cartucho de pruebas porque viven en otro.
FUERA = {"grupo-21-en-74", "cartel", "pan-lluvia", "sacudir-lluvia",
         "grupo-11-12-13", "batalla", "batalla-item", "batalla-droide",
         "pelea-82-grupo-11-12"}

# El que corre sin que nadie lo pida, que es la página 0: el grupo de la tanda
# en el mapa de arranque.
PRIMERO = "grupo-11"


def huella():
    """De qué depende un cartucho de prueba, además de sus flags y sus casos.

    Todo lo que participa de armarlo: el fuente de la ROM, el conversor, el
    ensamblador y el modelo. Se mira el contenido y no la fecha: `git
    checkout` de ida y vuelta deja fechas nuevas con el mismo contenido.

    **Los binarios entran por sí mismos** —`ca65` y `ld65`, que ensamblan,
    `tiles`, que convierte las capas, y `gunter`, que codifica las muestras—:
    si no entraran, reinstalarlos no invalidaría nada y las pruebas correrían
    contra ROMs armadas con los viejos, en silencio.

    `gunter` faltaba hasta el 2026-09-20, y era el mismo agujero que el
    párrafo de arriba describe: sus muestras viajan adentro del `.sfc`, así que
    recompilarlo cambiaba la ROM sin cambiar el sello. No se notó porque el
    caché de muestras sí lo miraba —`muestras_brr.version()`— y el `.py` que lo
    llama se tocaba casi siempre en el mismo cambio.
    """
    h = hashlib.sha256()
    partes = ([os.path.join(RAIZ, "rom", "src", "main.s")]
              + ensamblar.binarios()
              + [tiles_bin.binario(), muestras_brr.binario()])
    partes += sorted(glob.glob(os.path.join(RAIZ, "tools", "*", "*.py")))
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
    """Los cartuchos que llevan el caso, el de pruebas primero."""
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


def _archivo(nombre, que):
    return os.path.join(DESTINO, nombre, que)


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
    destino = os.path.join(DESTINO, nombre)
    os.makedirs(destino, exist_ok=True)
    sfc = _archivo(nombre, "prueba.sfc")
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
    args = parser.parse_args()
    if args.lista:
        for nombre in CARTUCHOS:
            casos = casos_de(nombre)
            print("%s (%d): %s" % (nombre, len(casos), " ".join(casos)))
        return
    fuentes = huella()
    for nombre in CARTUCHOS:
        print("%s: %s" % (nombre, "armado" if armar(nombre, fuentes)
                          else "al día"))


if __name__ == "__main__":
    main()
