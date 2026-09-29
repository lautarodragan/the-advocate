"""`parches/manual/`: lo nuestro, que manda sobre el volcado de `data/`.

`data/` es el juego tal como lo escribió su autor —el volcado de Ditto, que es
derivado y se regenera entero con `just datos`—. Un **fork** es un archivo
nuestro que el pipeline usa **en lugar** del de `data/`: no describe cambios,
es el archivo entero. Hoy lo pide el mapa 11, al que le rediseñamos el
minijuego de las piedras; el porqué está en
`workflow/done/el-mapa-11-se-rediseno.md` y el qué, en
`parches/manual/README.md`.

Tres cosas que este módulo hace cumplir, y las tres son el mismo miedo:

* **un mapa forkeado es todo o nada.** Las capas de tiles viven afuera del
  JSON, así que un `Map0011.json` sin su `Map0011.tiles` dejaría el build con
  las capas viejas y los eventos nuevos, y eso **se ve bien hasta que no**;
* **el id de adentro es el del nombre.** Un fork mal nombrado —o copiado de
  otro mapa— no falla: pisa el mapa equivocado, y los teleports caen adentro de
  una pared;
* **un fork de mapa reemplaza a uno que existe.** Un nombre mal escrito no
  hace nada, en silencio, y eso es peor que un error.

Y una que **no** hace: el fork no toca el juego original ni `data/`. `unpack`
escribe en `data/` y nunca acá, así que el diff contra el original se computa
cuando haga falta y no se pierde nunca.

Los mapas que el juego no tiene van aparte, en `nuevos/`, con la regla dada
vuelta —no pueden pisar uno que exista— y su nodo del árbol adentro: ver
`nuevos`.

Los ChipSets van aparte y **se suman**, no reemplazan: el mapa 11 estrena uno
propio para poder duplicarle tiles sin tocarle un pixel a los otros seis mapas
que comparten el 10. Un id que ya esté en `data/db/chipsets.json` es un error,
porque un fork que pisa una entrada de la base envejece sin avisar el día que
`just datos` la cambie.

La imagen de esos ChipSets la arma `render/chipset_del_fork.py`.
"""

import json
import os

from comun import proyecto

FORK = proyecto.parches_manual()
MAPAS = os.path.join(FORK, "mapas")
CHIPSETS = os.path.join(FORK, "chipsets")
# Los mapas que el juego no tiene: ver `nuevos`.
NUEVOS = os.path.join(FORK, "nuevos")
# Los del juego, contra los que se valida que un fork pise uno y un mapa nuevo
# no.
DEL_JUEGO = os.path.join(proyecto.data(), "maps")


class ForkRoto(Exception):
    """El fork está a medias o se contradice: el build no sigue."""


def _nombre(map_id):
    return "Map%04d" % map_id


def mapas():
    """{map_id: (json, tiles)} de los mapas forkeados, ya validado.

    Se valida entero en cada llamada y no sólo el mapa que se pide: un fork a
    medias tiene que romper el build lo arme quien lo arme, y no sólo cuando
    toca cargar justo ese mapa.

    Lo validado se recuerda mientras el directorio no cambie —los nombres,
    fechas y tamaños de sus archivos, y si están los originales—: cada
    `lcf.Map` pasa por acá, y leer los JSON de los forks enteros para mirarles
    el id eran ~2 ms por mapa, unas novecientas veces por conversión. Un fork
    roto no se recuerda: sigue rompiendo en cada llamada.
    """
    huella = _huella()
    if huella in _validados:
        return dict(_validados[huella])
    encontrados = _validar()
    _validados[huella] = dict(encontrados)
    return encontrados


_validados = {}


def _huella():
    """Lo que tiene que cambiar para que el fork validado deje de valer."""
    if not os.path.isdir(MAPAS):
        return None
    partes = [MAPAS, DEL_JUEGO]
    for entrada in sorted(os.listdir(MAPAS)):
        try:
            estado = os.stat(os.path.join(MAPAS, entrada))
            partes.append((entrada, estado.st_mtime_ns, estado.st_size))
        except OSError:
            partes.append((entrada, None, None))
        base = os.path.splitext(entrada)[0]
        partes.append(os.path.isfile(os.path.join(DEL_JUEGO, base + ".json")))
    return tuple(partes)


def _validar():
    encontrados = {}
    if not os.path.isdir(MAPAS):
        return encontrados
    for entrada in sorted(os.listdir(MAPAS)):
        base, extension = os.path.splitext(entrada)
        if extension not in (".json", ".tiles"):
            raise ForkRoto("%s: en parches/manual/mapas/ sólo van .json y "
                           ".tiles" % entrada)
        if not (base.startswith("Map") and base[3:].isdigit()):
            raise ForkRoto("%s: el nombre tiene que ser MapNNNN" % entrada)
        map_id = int(base[3:])
        if map_id in encontrados:
            continue
        pareja = (os.path.join(MAPAS, base + ".json"),
                  os.path.join(MAPAS, base + ".tiles"))
        falta = [p for p in pareja if not os.path.isfile(p)]
        if falta:
            raise ForkRoto(
                "el fork del mapa %d está a medias: falta %s. Las capas viven "
                "afuera del JSON, así que media pieza deja el build con las "
                "capas de un mapa y los eventos de otro"
                % (map_id, ", ".join(os.path.basename(p) for p in falta)))
        original = os.path.join(DEL_JUEGO, base + ".json")
        if not os.path.isfile(original):
            raise ForkRoto(
                "el fork nombra al mapa %d y en data/ no hay ninguno: un fork "
                "reemplaza un mapa del juego, no agrega uno" % map_id)
        with open(pareja[0], encoding="utf-8") as handle:
            adentro = json.load(handle).get("id")
        if adentro != map_id:
            raise ForkRoto(
                "%s dice adentro que es el mapa %r: el id y el nombre del "
                "archivo tienen que ser el mismo, porque el pipeline elige el "
                "mapa por el nombre y los teleports por el id"
                % (entrada, adentro))
        encontrados[map_id] = pareja
    return encontrados


def mapa(map_id):
    """(json, tiles) del fork de ese mapa, o None si no lo hay."""
    return mapas().get(map_id)


def nuevos():
    """{map_id: (json, tiles, nodo)} de los mapas que el juego **no tiene**.

    Es la regla de `mapas` dada vuelta, y por eso viven en otra carpeta: un
    fork reemplaza un mapa que existe y un mapa nuevo **no puede** pisar uno
    que exista. Mezclarlos en `mapas/` le sacaría a los dos su red: un fork
    con el nombre mal escrito pasaría por mapa nuevo, y un mapa nuevo con el
    id de uno del juego lo taparía sin avisar.

    Un mapa que no existe tampoco tiene nodo en el árbol —`data/maps.json`—,
    que es de donde salen su nombre, su padre, su música y sus encuentros. Así
    que lo trae él: el campo `arbol` del JSON es el nodo entero, en la misma
    vista resuelta que el volcado, y `lcf.TreeMap` lo suma. Hoy es uno solo,
    el mapa de debug: ver `tools/ensamblado/cartuchos.py`.

    Lo validado se recuerda igual que en `mapas`, y por lo mismo: cada
    `lcf.Map` pregunta acá.
    """
    huella = _huella_de_nuevos()
    if huella not in _nuevos_validados:
        _nuevos_validados[huella] = _validar_nuevos()
    return dict(_nuevos_validados[huella])


_nuevos_validados = {}


def _huella_de_nuevos():
    if not os.path.isdir(NUEVOS):
        return (NUEVOS, None)
    partes = [NUEVOS, DEL_JUEGO]
    for entrada in sorted(os.listdir(NUEVOS)):
        estado = os.stat(os.path.join(NUEVOS, entrada))
        base = os.path.splitext(entrada)[0]
        partes.append((entrada, estado.st_mtime_ns, estado.st_size,
                       os.path.isfile(os.path.join(DEL_JUEGO, base + ".json"))))
    return tuple(partes)


def _validar_nuevos():
    encontrados = {}
    if not os.path.isdir(NUEVOS):
        return encontrados
    for entrada in sorted(os.listdir(NUEVOS)):
        base, extension = os.path.splitext(entrada)
        if extension not in (".json", ".tiles"):
            raise ForkRoto("%s: en parches/manual/nuevos/ sólo van .json y "
                           ".tiles" % entrada)
        if not (base.startswith("Map") and base[3:].isdigit()):
            raise ForkRoto("%s: el nombre tiene que ser MapNNNN" % entrada)
        map_id = int(base[3:])
        if map_id in encontrados:
            continue
        pareja = (os.path.join(NUEVOS, base + ".json"),
                  os.path.join(NUEVOS, base + ".tiles"))
        falta = [p for p in pareja if not os.path.isfile(p)]
        if falta:
            raise ForkRoto("el mapa nuevo %d está a medias: falta %s"
                           % (map_id, ", ".join(os.path.basename(p)
                                                for p in falta)))
        if os.path.isfile(os.path.join(DEL_JUEGO, base + ".json")):
            raise ForkRoto(
                "el mapa nuevo %d ya existe en data/: un mapa nuevo no pisa "
                "uno del juego; si es para cambiarlo, es un fork y va en "
                "parches/manual/mapas/" % map_id)
        with open(pareja[0], encoding="utf-8") as handle:
            datos = json.load(handle)
        nodo = datos.get("arbol")
        if datos.get("id") != map_id or not nodo or nodo.get("id") != map_id:
            raise ForkRoto(
                "%s: el id de adentro, el del nodo `arbol` y el del nombre "
                "del archivo tienen que ser el mismo" % entrada)
        encontrados[map_id] = pareja + (nodo,)
    return encontrados


def nuevo(map_id):
    """(json, tiles) del mapa nuevo con ese id, o None si no lo hay."""
    hallado = nuevos().get(map_id)
    return hallado[:2] if hallado else None


def chipsets():
    """{id: entrada} de los ChipSets que el fork agrega a la base."""
    nuevos = {}
    if not os.path.isdir(CHIPSETS):
        return nuevos
    for entrada in sorted(os.listdir(CHIPSETS)):
        base, extension = os.path.splitext(entrada)
        if extension != ".json" or not base.isdigit():
            raise ForkRoto("%s: en parches/manual/chipsets/ van NNNN.json"
                           % entrada)
        with open(os.path.join(CHIPSETS, entrada), encoding="utf-8") as handle:
            datos = json.load(handle)
        if datos["chipset"]["id"] != int(base):
            raise ForkRoto(
                "%s dice adentro que es el ChipSet %d: el id y el nombre del "
                "archivo tienen que ser el mismo"
                % (entrada, datos["chipset"]["id"]))
        nuevos[int(base)] = datos
    return nuevos
