"""`juego/`: lo nuestro, que manda sobre el volcado de `data/`.

`data/` es el juego tal como lo escribió su autor —el volcado de Ditto, que es
derivado y se regenera entero con `just datos`—. Un **fork** es un archivo
nuestro que el pipeline usa **en lugar** del de `data/`: no describe cambios,
es el archivo entero. Hoy lo pide el mapa 11, al que le rediseñamos el
minijuego de las piedras; el porqué está en
`workflow/done/el-mapa-11-se-rediseno.md` y el qué, en
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

La receta tiene tres operaciones, y la tercera **trae pixeles de afuera del
ChipSet**: `desde_charset` mete una pose de un CharSet en dos tiles altos, que
es cómo un NPC que no hace nada más que estar parado deja de ser un sprite y
pasa a ser mapa. Lo pide el público del Auditorio —el mapa 18—; el porqué está
en `workflow/done/el-publico-del-auditorio-se-horneo.md`.
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


def _paleta(imagen):
    """Los colores de un PNG indexado, como tuplas RGB y por índice."""
    crudo = imagen.getpalette() or []
    return [tuple(crudo[i * 3:i * 3 + 3]) for i in range(len(crudo) // 3)]


class _Paleta:
    """La paleta del ChipSet mientras se le agregan colores de un CharSet.

    Los dos PNG son indexados y **sus índices no quieren decir lo mismo**:
    copiar los bytes de uno adentro del otro da un sprite con los colores del
    ChipSet, que es basura que se ve. Así que se copia por color, y el que no
    esté se agrega en un índice que el ChipSet no use.

    El índice 0 queda afuera de la búsqueda **en las dos puntas**: es el color
    key, y un color del sprite que dé igual al del índice 0 del ChipSet tiene
    que ocupar un índice propio o el sprite saldría con un agujero.
    """

    def __init__(self, imagen):
        self.colores = _paleta(imagen)
        while len(self.colores) < 256:
            self.colores.append((0, 0, 0))
        usados = set(imagen.tobytes())
        self.donde = {}
        for indice in sorted(usados):
            if indice:
                self.donde.setdefault(self.colores[indice], indice)
        self.libres = [i for i in range(1, 256) if i not in usados]

    def indice(self, color):
        if color not in self.donde:
            if not self.libres:
                raise ForkRoto(
                    "el ChipSet se quedó sin índices de paleta: los 256 ya "
                    "están usados y el CharSet trae colores que no tiene")
            self.donde[color] = self.libres.pop(0)
            self.colores[self.donde[color]] = color
        return self.donde[color]

    def aplicar(self, imagen):
        imagen.putpalette([canal for color in self.colores for canal in color])


def _pose(imagen, receta):
    """El cuadro de 24x32 de una pose, recortado del CharSet.

    Un CharSet son 8 personajes de 4x2, cada uno con sus 12 poses: 3 patrones
    de caminata por 4 direcciones. Ver `render/charset.py`.
    """
    from render.charset import SPRITE_HEIGHT, SPRITE_WIDTH

    x = (receta["personaje"] % 4) * 72 + receta["patron"] * SPRITE_WIDTH
    y = (receta["personaje"] // 4) * 128 + receta["direccion"] * SPRITE_HEIGHT
    return imagen.crop((x, y, x + SPRITE_WIDTH, y + SPRITE_HEIGHT))


def imagen_del_chipset(datos, buscar):
    """Arma el PNG de un ChipSet forkeado y devuelve su ruta.

    `buscar(carpeta, nombre)` es quien encuentra los originales —el ChipSet
    del que sale, y los CharSets que se hornean—; el resultado cae en
    `rom/build/juego/ChipSet/` con el nombre que la entrada de la base pide.
    Se reescribe siempre —armarlo son copias de rectángulos— y se mueve al
    lugar de una, así que dos builds a la vez no se dejan un PNG a medio
    escribir.
    """
    from PIL import Image

    from render.charset import OFFSET_X, SPRITE_WIDTH
    from render.chipset import TILE, caja_de_comun, caja_de_terreno

    receta = datos["imagen"]
    origen = buscar("ChipSet", receta["base"])
    if origen is None:
        raise ForkRoto("no está el ChipSet %r, del que sale el %d"
                       % (receta["base"], datos["chipset"]["id"]))
    # Sin convertir a RGBA: los ChipSets son PNG indexados y el color 0 es el
    # color key. Convertirlos acá tiraba la paleta, y el PNG que salía tenía
    # los tiles vacíos **opacos**: se ve, y se ve mal.
    imagen = Image.open(origen)
    imagen.load()
    for desde, hasta in receta.get("bloques_bajos", []):
        imagen.paste(imagen.crop(caja_de_terreno(desde)),
                     caja_de_terreno(hasta)[:2])
    for desde, hasta in receta.get("tiles_altos", []):
        # El tile alto `u` es el común 144 + u: los 144 primeros son la capa
        # baja. Ver `caja_de_comun`.
        imagen.paste(imagen.crop(caja_de_comun(144 + desde)),
                     caja_de_comun(144 + hasta)[:2])

    if receta.get("desde_charset"):
        paleta = _Paleta(imagen)
        for una in receta["desde_charset"]:
            hoja = buscar("CharSet", una["charset"])
            if hoja is None:
                raise ForkRoto("no está el CharSet %r, que el ChipSet %d "
                               "hornea" % (una["charset"],
                                           datos["chipset"]["id"]))
            fuente = Image.open(hoja)
            fuente.load()
            desde = _paleta(fuente)
            pose = list(_pose(fuente, una).tobytes())
            # El sprite se dibuja en `(x*16 - 4, y*16 - 16)`, así que sus
            # columnas 4 a 19 caen clavadas en la celda y su mitad de arriba
            # cae en la celda de arriba: de ahí salen los dos tiles.
            columna = -OFFSET_X
            for mitad, ranura in (("cabeza", una["cabeza"]),
                                  ("cuerpo", una["cuerpo"])):
                alto = 0 if mitad == "cabeza" else TILE
                pixeles = []
                for fila in range(alto, alto + TILE):
                    for x in range(columna, columna + TILE):
                        indice = pose[fila * SPRITE_WIDTH + x]
                        pixeles.append(0 if not indice
                                       else paleta.indice(desde[indice]))
                tile = Image.new("P", (TILE, TILE))
                tile.putdata(pixeles)
                imagen.paste(tile, caja_de_comun(144 + ranura)[:2])
        paleta.aplicar(imagen)

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
