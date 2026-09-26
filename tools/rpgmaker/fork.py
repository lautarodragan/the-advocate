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

Los ChipSets van aparte y **se suman**, no reemplazan: el mapa 11 estrena uno
propio para poder duplicarle tiles sin tocarle un pixel a los otros seis mapas
que comparten el 10. Un id que ya esté en `data/db/chipsets.json` es un error,
porque un fork que pisa una entrada de la base envejece sin avisar el día que
`just datos` la cambie.

**La imagen del ChipSet no se versiona: se arma.** El arte del juego no es
nuestro para redistribuir —vive en `/extras`, ver `docs/rpgmaker/rtp.md`—, así
que el fork guarda la *receta* —qué bloque se copia adónde— y
`imagen_del_chipset`
la aplica sobre el PNG original dejando el resultado en
`rom/build/parches-manual/`.

La receta tiene cinco operaciones. Dos copian de adentro del propio ChipSet
—`bloques_bajos` y `tiles_altos`— y dos **traen pixeles de afuera**:
`desde_charset` mete una pose de un CharSet en dos tiles altos, que es cómo un
NPC que no hace nada más que estar parado deja de ser un sprite y pasa a ser
mapa —el público del Auditorio, el mapa 18—, y `desde_imagen` mete un PNG que
no es ni ChipSet ni CharSet, escalado y cortado en celdas de 16x16.

La quinta, `podar`, no dibuja: **borra lo que el mapa no usa**. El ChipSet de
un fork es privado de su mapa, y lo que se gana no son pixeles sino **índices
de paleta**: el PNG es indexado y tiene 256, que es el techo contra el que
choca `desde_imagen`.
"""

import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FORK = os.path.join(REPO, "parches", "manual")
MAPAS = os.path.join(FORK, "mapas")
CHIPSETS = os.path.join(FORK, "chipsets")
# Dónde caen las imágenes armadas. Es un directorio de build como cualquier
# otro: se puede borrar, y se rehace solo.
GENERADO = os.path.join(REPO, "rom", "build", "parches-manual")


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
    partes = [MAPAS, REPO]
    for entrada in sorted(os.listdir(MAPAS)):
        try:
            estado = os.stat(os.path.join(MAPAS, entrada))
            partes.append((entrada, estado.st_mtime_ns, estado.st_size))
        except OSError:
            partes.append((entrada, None, None))
        base = os.path.splitext(entrada)[0]
        partes.append(os.path.isfile(os.path.join(REPO, "data", "maps",
                                                  base + ".json")))
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


def _paleta(imagen):
    """Los colores de un PNG indexado, como tuplas RGB y por índice."""
    crudo = imagen.getpalette() or []
    return [tuple(crudo[i * 3:i * 3 + 3]) for i in range(len(crudo) // 3)]


# El agua y los tiles animados comparten este rectángulo del ChipSet; el resto
# de la mitad izquierda son los doce autotiles de terreno, y la derecha, los
# tiles comunes. Ver `render/chipset.py`, que es de donde salen los offsets.
CAJA_AGUA = (0, 0, 96, 128)


# Los comandos que eligen un tile **en tiempo de ejecución**: con uno de éstos
# adentro, las capas del mapa dejan de decir qué se dibuja y el podado no puede
# saber qué guardar. Ninguno de los dos mapas forkeados de hoy los usa, así que
# `podar` se planta en vez de adivinar: perder arte en silencio es justo lo que
# este archivo existe para evitar.
COMANDOS_QUE_ELIGEN_TILES = {
    11710: "ChangeMapTileset",
    11750: "TileSubstitution",
}


def _lo_que_dibuja(map_id):
    """Qué partes del ChipSet usa ese mapa: agua, autotiles y ranuras comunes.

    Sale del mapa **ya forkeado**, que es lo que lo hace self-checking: si el
    fork empieza a dibujar una ranura nueva, esta cuenta la ve sola y el podado
    la respeta sin que haya que acordarse de anotarla en ningún lado.

    Y no alcanza con las dos capas. **Un evento sin CharSet se dibuja con un
    tile de la página alta** —ver `rm2k.nombre_de_tile`: así están hechas las
    puertas y buena parte del decorado— y ese tile no aparece en ninguna capa.
    Podando sin contarlos, el mapa 32 perdía la ranura 13 y la ROM salía con
    78 bytes distintos: lo cobró la comparación byte por byte, no una prueba.
    """
    from rpgmaker import lcf

    mapa = lcf.Map(os.path.join(REPO, "data", "maps", "Map%04d.json" % map_id))
    agua = False
    terrenos, comunes = set(), set()
    for capa in (mapa.lower_layer, mapa.upper_layer):
        for tile in capa:
            if tile < 4000:
                agua = True              # agua (0..2999) y animados (3000..)
            elif tile < 5000:
                terrenos.add((tile - 4000) // 50)
            elif tile < 10000:
                comunes.add(tile - 5000)
            else:
                comunes.add(144 + tile - 10000)
    for evento in mapa.events:
        for pagina in evento.pages:
            if not pagina.character_name:
                comunes.add(144 + pagina.character_index)
            for comando in pagina.commands:
                nombre = COMANDOS_QUE_ELIGEN_TILES.get(comando.code)
                if nombre:
                    raise ForkRoto(
                        "el mapa %d usa %s, que elige un tile en tiempo de "
                        "ejecución: con eso las capas no dicen qué se dibuja y "
                        "podar el ChipSet le borraría arte que el mapa sí usa"
                        % (map_id, nombre))
    return agua, terrenos, comunes


def podar(imagen, map_id):
    """Borra del ChipSet todo lo que ese mapa no dibuja.

    Un ChipSet del fork es **privado de su mapa** —ver
    `parches/manual/README.md`—, así que ningún otro puede pedirle un tile que
    éste no use: lo que no se dibuja es peso muerto. Y el peso que importa no
    son los pixeles sino los **índices de paleta**: el PNG es indexado y tiene
    256, que es el techo contra el que choca `desde_imagen` al traer un dibujo
    de afuera. Podando el ChipSet 1 se pasa de 122 índices libres a 174, y ésa
    es la diferencia entre que el Hover Tram entre y no entre.

    No puede cambiar lo que se ve —borra tiles que el mapa no nombra— y eso acá
    se demuestra, no se supone: la ROM sale byte por byte igual con el ChipSet
    podado mientras el mapa siga dibujando lo mismo.
    """
    from PIL import Image

    from render.chipset import caja_de_comun, caja_de_terreno

    agua, terrenos, comunes = _lo_que_dibuja(map_id)
    if not agua:
        imagen.paste(Image.new("P", (CAJA_AGUA[2], CAJA_AGUA[3])),
                     CAJA_AGUA[:2])
    for n in range(12):
        if n not in terrenos:
            imagen.paste(Image.new("P", (48, 64)), caja_de_terreno(n)[:2])
    for i in range(288):
        if i not in comunes:
            imagen.paste(Image.new("P", (16, 16)), caja_de_comun(i)[:2])


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
                    "están usados y el dibujo que entra trae colores que no "
                    "tiene. Si el ChipSet no se está podando, `podar` es lo "
                    "que libera los índices que el mapa no usa")
            self.donde[color] = self.libres.pop(0)
            self.colores[self.donde[color]] = color
        return self.donde[color]

    def aplicar(self, imagen):
        imagen.putpalette([canal for color in self.colores for canal in color])


def _a_quince(color):
    """El color redondeado a los 15 bits que la consola muestra de verdad.

    No pierde nada que el cartucho pudiera dibujar —el asignador cuantiza con
    `>>3` igual— y **es lo que hace entrar el dibujo**: los 206 colores del
    Hover Tram son 148 a 15 bits, contra los 174 índices que el ChipSet podado
    deja libres. Sin esto no entra.

    Que el PNG del ChipSet quede con colores que el arte original no tiene no
    es un problema: esa imagen **no se versiona, se arma** —ver
    `parches/manual/README.md`—, así que es un intermedio del build y no el
    arte del juego, que sigue intacto en su `Picture/`.
    """
    return tuple((canal >> 3) << 3 for canal in color)


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
    `rom/build/parches-manual/ChipSet/` con el nombre que la entrada de la
    base pide.
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
    # Primero el podado, porque libera índices de paleta que las operaciones
    # de abajo van a necesitar, y porque lee el mapa **forkeado**: las ranuras
    # que el fork estrena ya están en sus capas, así que las respeta.
    if "podar" in receta:
        podar(imagen, receta["podar"])
    for desde, hasta in receta.get("bloques_bajos", []):
        imagen.paste(imagen.crop(caja_de_terreno(desde)),
                     caja_de_terreno(hasta)[:2])
    for desde, hasta in receta.get("tiles_altos", []):
        # El tile alto `u` es el común 144 + u: los 144 primeros son la capa
        # baja. Ver `caja_de_comun`.
        imagen.paste(imagen.crop(caja_de_comun(144 + desde)),
                     caja_de_comun(144 + hasta)[:2])

    # Las ranuras que `desde_imagen` va a pisar se vacían **antes** de mirar la
    # paleta. Si no, sus colores de hoy siguen contando como usados y se quedan
    # con los índices que el dibujo nuevo necesita: el podado las conserva
    # porque el mapa forkeado las nombra, pero lo que el mapa dibuja ahí es el
    # dibujo que está por entrar, no el que había. Sin esto el Hover Tram se
    # queda sin índices y el build se planta.
    for entrada in (receta.get("desde_imagen") or {}).get("celdas", []):
        if len(entrada) <= 3:      # las que componen sobre otra ranura, no
            imagen.paste(Image.new("P", (TILE, TILE)),
                         caja_de_comun(144 + entrada[2])[:2])

    # Las dos operaciones que traen pixeles de afuera comparten **una sola**
    # paleta: cada `_Paleta` reparte los índices libres desde cero, así que dos
    # se pisarían los índices y la segunda `aplicar` borraría los colores de la
    # primera.
    paleta = (_Paleta(imagen)
              if receta.get("desde_charset") or receta.get("desde_imagen")
              else None)

    if receta.get("desde_charset"):
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

    if receta.get("desde_imagen"):
        una = receta["desde_imagen"]
        ruta = buscar(una["carpeta"], una["imagen"])
        if ruta is None:
            raise ForkRoto("no está %s/%s, que el ChipSet %d hornea"
                           % (una["carpeta"], una["imagen"],
                              datos["chipset"]["id"]))
        fuente = Image.open(ruta)
        fuente.load()
        desde = _paleta(fuente)
        # RM2k escala las imágenes con **vecino más cercano**, y el 65% del
        # Hover Tram calza así al 97,3% contra la captura del juego original:
        # ahí se comprobó de una vez el escalado, el anclaje y la posición.
        escala = una.get("escala", 100)
        ancho = fuente.width * escala // 100
        alto = fuente.height * escala // 100
        chica = fuente.resize((ancho, alto), Image.NEAREST).load()
        # Dónde cae el pixel (0,0) del dibujo adentro de su primera celda: la
        # imagen no tiene por qué estar alineada a la grilla de 16, y la del
        # tram no lo está.
        dx, dy = una.get("desfase", (0, 0))
        # Colores del dibujo que se tratan como transparentes además del
        # índice 0. Existe para los defectos del arte original: un pixel
        # pintado **casi** del color de la clave pero no igual, que RM2k dibuja
        # y se ve como un punto suelto. Es una divergencia declarada, así que
        # va escrita en la receta y no escondida acá.
        transparentes = {tuple(c) for c in una.get("transparentes", [])}
        for entrada in una["celdas"]:
            columna, fila, ranura = entrada[:3]
            # El cuarto elemento, si está, es la ranura de la que sale el
            # fondo: el dibujo se compone **encima** de ella en vez de pisarla.
            # Lo pide la pared de la terraza del mapa 32, donde nueve pixeles
            # de la punta del tram caen sobre una celda que ya dibuja algo.
            tile = (imagen.crop(caja_de_comun(144 + entrada[3]))
                    if len(entrada) > 3 else Image.new("P", (TILE, TILE)))
            pixeles = tile.load()
            for y in range(TILE):
                for x in range(TILE):
                    px, py = columna * TILE + x - dx, fila * TILE + y - dy
                    if not (0 <= px < ancho and 0 <= py < alto):
                        continue
                    indice = chica[px, py]
                    if indice and desde[indice] not in transparentes:
                        pixeles[x, y] = paleta.indice(_a_quince(desde[indice]))
            imagen.paste(tile, caja_de_comun(144 + ranura)[:2])

    if paleta is not None:
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
