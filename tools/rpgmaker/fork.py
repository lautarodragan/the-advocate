"""`juego/`: lo nuestro, que manda sobre el volcado de `data/`.

`data/` es el juego tal como lo escribió su autor —el volcado de Ditto, que es
derivado y se regenera entero con `just datos`—. Un **fork** es un archivo
nuestro que el pipeline usa **en lugar** del de `data/`: no describe cambios,
es el archivo entero. Hoy lo pide el mapa 11, al que le rediseñamos el
minijuego de las piedras; el porqué está en
`workflow/tareas/el-mapa-11-no-entra-en-el-cuadro.md` y el qué, en
`juego/README.md`.

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

Los ChipSets van aparte y **se suman**, no reemplazan: el mapa 11 estrena uno
propio para poder duplicarle tiles sin tocarle un pixel a los otros seis mapas
que comparten el 10. Un id que ya esté en `data/db/chipsets.json` es un error,
porque un fork que pisa una entrada de la base envejece sin avisar el día que
`just datos` la cambie.

**La imagen del ChipSet no se versiona: se arma.** El arte del juego no es
nuestro para redistribuir —vive en `/extras`, ver `assets/README.md`—, así que
el fork guarda la *receta* —qué bloque se copia adónde— y `imagen_del_chipset`
la aplica sobre el PNG original dejando el resultado en `rom/build/juego/`.
"""

import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FORK = os.path.join(REPO, "juego")
MAPAS = os.path.join(FORK, "mapas")
CHIPSETS = os.path.join(FORK, "chipsets")
# Dónde caen las imágenes armadas. Es un directorio de build como cualquier
# otro: se puede borrar, y se rehace solo.
GENERADO = os.path.join(REPO, "rom", "build", "juego")


class ForkRoto(Exception):
    """El fork está a medias o se contradice: el build no sigue."""


def _nombre(map_id):
    return "Map%04d" % map_id


def mapas():
    """{map_id: (json, tiles)} de los mapas forkeados, ya validado.

    Se valida entero en cada llamada y no sólo el mapa que se pide: un fork a
    medias tiene que romper el build lo arme quien lo arme, y no sólo cuando
    toca cargar justo ese mapa.
    """
    encontrados = {}
    if not os.path.isdir(MAPAS):
        return encontrados
    for entrada in sorted(os.listdir(MAPAS)):
        base, extension = os.path.splitext(entrada)
        if extension not in (".json", ".tiles"):
            raise ForkRoto("%s: en juego/mapas/ sólo van .json y .tiles"
                           % entrada)
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
        original = os.path.join(REPO, "data", "maps", base + ".json")
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


def chipsets():
    """{id: entrada} de los ChipSets que el fork agrega a la base."""
    nuevos = {}
    if not os.path.isdir(CHIPSETS):
        return nuevos
    for entrada in sorted(os.listdir(CHIPSETS)):
        base, extension = os.path.splitext(entrada)
        if extension != ".json" or not base.isdigit():
            raise ForkRoto("%s: en juego/chipsets/ van NNNN.json" % entrada)
        with open(os.path.join(CHIPSETS, entrada), encoding="utf-8") as handle:
            datos = json.load(handle)
        if datos["chipset"]["id"] != int(base):
            raise ForkRoto(
                "%s dice adentro que es el ChipSet %d: el id y el nombre del "
                "archivo tienen que ser el mismo"
                % (entrada, datos["chipset"]["id"]))
        nuevos[int(base)] = datos
    return nuevos


def imagen_del_chipset(datos, buscar):
    """Arma el PNG de un ChipSet forkeado y devuelve su ruta.

    `buscar(nombre)` es quien encuentra el ChipSet original; el resultado cae
    en `rom/build/juego/ChipSet/` con el nombre que la entrada de la base
    pide. Se reescribe siempre —armarlo son dos copias de rectángulos— y se
    mueve al lugar de una, así que dos builds a la vez no se dejan un PNG a
    medio escribir.
    """
    from PIL import Image

    from render.chipset import caja_de_comun, caja_de_terreno

    receta = datos["imagen"]
    origen = buscar(receta["base"])
    if origen is None:
        raise ForkRoto("no está el ChipSet %r, del que sale el %d"
                       % (receta["base"], datos["chipset"]["id"]))
    # Sin convertir a RGBA: los ChipSets son PNG indexados y el color 0 es el
    # color key. Convertirlos acá tiraba la paleta, y el PNG que salía tenía
    # los tiles vacíos **opacos**: se ve, y se ve mal.
    imagen = Image.open(origen)
    imagen.load()
    for desde, hasta in receta["bloques_bajos"]:
        imagen.paste(imagen.crop(caja_de_terreno(desde)),
                     caja_de_terreno(hasta)[:2])
    for desde, hasta in receta["tiles_altos"]:
        # El tile alto `u` es el común 144 + u: los 144 primeros son la capa
        # baja. Ver `caja_de_comun`.
        imagen.paste(imagen.crop(caja_de_comun(144 + desde)),
                     caja_de_comun(144 + hasta)[:2])

    destino = os.path.join(GENERADO, "ChipSet",
                           datos["chipset"]["chipset_name"] + ".png")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    provisorio = "%s.%d.png" % (destino, os.getpid())
    imagen.save(provisorio)
    os.replace(provisorio, destino)
    return destino


def imagenes(buscar):
    """Arma las imágenes de todos los ChipSets del fork. Devuelve el
    directorio donde quedaron, para meterlo en la búsqueda de recursos."""
    for datos in chipsets().values():
        imagen_del_chipset(datos, buscar)
    return GENERADO
