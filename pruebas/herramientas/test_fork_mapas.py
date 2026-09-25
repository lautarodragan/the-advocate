"""Un fork de `parches/manual/` no se puede quedar a medias ni apuntar al mapa
de al lado.

Un fork reemplaza un archivo entero de `data/` —ver
`parches/manual/README.md`—, y sus dos modos de falla no dan error por sí
solos: se ven bien hasta que no.

* **A medias.** Las capas de tiles viven afuera del JSON, así que un `.json`
  sin su `.tiles` deja el build con las capas viejas y los eventos nuevos.
* **Apuntando al mapa equivocado.** El pipeline elige el mapa por el **nombre
  del archivo** y los teleports lo nombran por su **id**: un fork copiado de
  otro mapa y renombrado a medias no falla, manda al jugador a otro lado.

Los dos primeros casos se arman en un directorio temporal, porque son sobre lo
que el mecanismo **rechaza** y un árbol sano no tiene ninguno: sin eso serían
un camino que ninguna prueba ejecuta. Los dos últimos miran los forks que hay
de verdad.
"""

import json
import os
import shutil
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

from render.chipset import UPPER                               # noqa: E402
from render.render_map import build_passability                # noqa: E402
from rpgmaker import fork                                      # noqa: E402
from rpgmaker import lcf                                       # noqa: E402
from rpgmaker import rm2k                                      # noqa: E402

TELEPORT = 10810
# Los comandos cuyo primer parámetro es el id de un evento del mapa. Son los
# que el juego usa; el `10001` que aparece en varios es el héroe y no un
# evento.
NOMBRAN_UN_EVENTO = (10860, 11320, 11330)
# La capa de un evento que está al mismo nivel que el héroe, o sea el que lo
# choca. Es el `layer` de la página.
CAPA_DEL_HEROE = 1
# Qué se le pide a la celda donde cae un teleport: abierta por los cuatro
# lados. Medido el 2026-09-21 sobre las tres entradas al mapa 11 —(26,47) dos
# veces y (15,50)—: las tres dan 15, así que el corte estricto no es un piso
# inventado, es lo que el juego tiene.
PISABLE = rm2k.PASS_ALL


@pytest.fixture
def fork_de_mentira(tmp_path, monkeypatch):
    """Un `parches/manual/` armable a mano, para los casos que el árbol no
    tiene."""
    mapas = tmp_path / "mapas"
    mapas.mkdir()
    monkeypatch.setattr(fork, "MAPAS", str(mapas))
    monkeypatch.setattr(fork, "CHIPSETS", str(tmp_path / "chipsets"))
    return mapas


def _un_mapa_de_verdad():
    """Un mapa cualquiera de `data/`, para copiar de ahí y no inventar uno."""
    return os.path.join(RAIZ, "data", "maps", "Map0011")


def test_fork_a_medias_no_arma(fork_de_mentira):
    """El `.json` sin su `.tiles`: el modo de falla que se ve bien."""
    shutil.copy(_un_mapa_de_verdad() + ".json",
                str(fork_de_mentira / "Map0011.json"))
    with pytest.raises(fork.ForkRoto) as roto:
        fork.mapas()
    assert "a medias" in str(roto.value)


def test_fork_con_las_capas_solas_tampoco_arma(fork_de_mentira):
    """Y al revés, que es el mismo agujero por el otro lado."""
    shutil.copy(_un_mapa_de_verdad() + ".tiles",
                str(fork_de_mentira / "Map0011.tiles"))
    with pytest.raises(fork.ForkRoto):
        fork.mapas()


def test_fork_que_dice_ser_otro_mapa_no_arma(fork_de_mentira):
    """El fork copiado de otro mapa y renombrado a medias."""
    datos = json.load(open(_un_mapa_de_verdad() + ".json", encoding="utf-8"))
    datos["id"] = 12
    with open(str(fork_de_mentira / "Map0011.json"), "w",
              encoding="utf-8") as handle:
        json.dump(datos, handle)
    shutil.copy(_un_mapa_de_verdad() + ".tiles",
                str(fork_de_mentira / "Map0011.tiles"))
    with pytest.raises(fork.ForkRoto) as roto:
        fork.mapas()
    assert "el mapa 12" in str(roto.value)


def test_fork_de_un_mapa_que_no_existe_no_arma(fork_de_mentira):
    """Un nombre mal escrito no hace nada en silencio."""
    for extension in (".json", ".tiles"):
        shutil.copy(_un_mapa_de_verdad() + extension,
                    str(fork_de_mentira / ("Map9999" + extension)))
    with pytest.raises(fork.ForkRoto):
        fork.mapas()


def test_fork_el_id_de_adentro_es_el_del_nombre():
    """Sobre los forks de verdad: es lo que `fork.mapas()` exige al leerlos."""
    for map_id, (ruta_json, _) in fork.mapas().items():
        datos = json.load(open(ruta_json, encoding="utf-8"))
        assert datos["id"] == map_id
        assert os.path.basename(ruta_json) == "Map%04d.json" % map_id


def test_fork_no_le_cambia_el_tamano_al_mapa():
    """Un fork que redimensiona corre todas las celdas del juego un lugar."""
    for map_id, (ruta_json, _) in fork.mapas().items():
        nuestro = json.load(open(ruta_json, encoding="utf-8"))
        suyo = json.load(open(os.path.join(RAIZ, "data", "maps",
                                           "Map%04d.json" % map_id),
                              encoding="utf-8"))
        assert (nuestro["width"], nuestro["height"]) \
            == (suyo["width"], suyo["height"])


def test_fork_no_borra_un_evento_que_otro_nombra():
    """Borrar eventos es la mitad de lo que hace un fork, y el que se borra de
    más **no falla**: la cinemática le manda un `MoveEvent` a un id que ya no
    existe y sigue como si nada, con el que se movía quieto en su lugar.

    El público del Auditorio se horneó porque ninguna de sus páginas lo toca;
    esto es lo que lo comprueba cada vez y no una sola.
    """
    for map_id, (ruta_json, _) in fork.mapas().items():
        datos = json.load(open(ruta_json, encoding="utf-8"))
        hay = {evento["id"] for evento in datos["events"]}
        for evento in datos["events"]:
            for pagina in evento["pages"]:
                for cmd in pagina["event_commands"]:
                    if cmd["code"] not in NOMBRAN_UN_EVENTO:
                        continue
                    quien = cmd["parameters"][0]
                    assert quien in hay or quien >= 10000, (
                        "el fork del mapa %d borró el evento %d y el %d lo "
                        "sigue nombrando" % (map_id, quien, evento["id"]))


def test_fork_donde_borro_un_evento_del_piso_la_celda_sigue_cerrada():
    """Un evento en la capa del héroe **es una pared**, y el tile que lo
    reemplaza tiene que serlo también.

    Es lo que el horneado se lleva puesto sin avisar: el público del Auditorio
    era 31 eventos que tapaban su banqueta, y de tiles sueltos la celda queda
    abierta y el jugador camina por encima de la gente. La pasabilidad del
    ChipSet forkeado es lo único que lo sostiene.
    """
    for map_id, _ in fork.mapas().items():
        datos, _ = _original(map_id)
        game_map = lcf.Map("Map%04d.lmu" % map_id)
        vivos = {evento.id for evento in game_map.events}
        base = lcf.Database(os.path.join(RAIZ, "data", "db", "RPG_RT.ldb"))
        pasa = rm2k.passability_map(
            game_map, build_passability(base.chipsets[game_map.chipset_id]))
        for evento in datos["events"]:
            if evento["id"] in vivos:
                continue
            if evento["pages"][0]["layer"] != CAPA_DEL_HEROE:
                continue
            celda = pasa[evento["y"] * game_map.width + evento["x"]]
            assert celda & rm2k.PASS_ALL == 0, (
                "el fork del mapa %d borró el evento %d de (%d,%d) y la celda "
                "quedó abierta: da %d"
                % (map_id, evento["id"], evento["x"], evento["y"], celda))


def _teleports_al(map_id):
    """Todas las celdas desde las que el juego entra a ese mapa.

    Se mira el juego entero —los 328 mapas y los eventos comunes— y no sólo
    los vecinos: un teleport puede estar en cualquier lado, y el que rompe el
    juego es justamente el que nadie estaba mirando.
    """
    destinos = set()

    def mirar(comandos):
        for cmd in comandos:
            p = cmd["parameters"]
            if cmd["code"] == TELEPORT and len(p) >= 3 and p[0] == map_id:
                destinos.add((p[1], p[2]))

    mapas = os.path.join(RAIZ, "data", "maps")
    for nombre in sorted(os.listdir(mapas)):
        if not nombre.endswith(".json"):
            continue
        datos = json.load(open(os.path.join(mapas, nombre), encoding="utf-8"))
        for evento in datos["events"]:
            for pagina in evento["pages"]:
                mirar(pagina["event_commands"])
    comunes = json.load(open(os.path.join(RAIZ, "data", "db",
                                          "commonevents.json"),
                             encoding="utf-8"))
    for comun in comunes:
        mirar(comun["event_commands"])
    return destinos


def test_fork_los_teleports_que_entran_siguen_cayendo_en_celdas_pisables():
    """La que rompe el juego de verdad, y el id no cubre.

    Mover una pared en el fork no falla en ningún lado: falla el día que
    alguien entra al mapa y aparece adentro de ella.
    """
    forkeados = fork.mapas()
    if not forkeados:
        pytest.skip("no hay ningún mapa forkeado")
    base = lcf.Database(os.path.join(RAIZ, "data", "db", "RPG_RT.ldb"))
    for map_id in forkeados:
        game_map = lcf.Map("Map%04d.lmu" % map_id)
        flags = build_passability(base.chipsets[game_map.chipset_id])
        pasa = rm2k.passability_map(game_map, flags)
        destinos = _teleports_al(map_id)
        assert destinos, "nadie entra al mapa %d: revisar el barrido" % map_id
        for x, y in sorted(destinos):
            celda = pasa[y * game_map.width + x] & rm2k.PASS_ALL
            assert celda == PISABLE, (
                "el mapa %d recibe un teleport en (%d,%d) y ahí la celda da "
                "%d" % (map_id, x, y, celda))


def _original(map_id):
    """El mapa tal como está en `data/`: el JSON y sus dos capas.

    Se lee a mano y no con `lcf.Map`, que es justamente quien aplica el fork:
    acá hace falta el de antes para compararlo contra el de después.
    """
    base = os.path.join(RAIZ, "data", "maps", "Map%04d" % map_id)
    datos = json.load(open(base + ".json", encoding="utf-8"))
    capas = lcf.capas(base + ".tiles", datos, datos["width"], datos["height"])
    return datos, capas


def _altos_del_original(map_id):
    """Los tiles de la página alta que el mapa **sin forkear** dibuja."""
    _, (_, arriba) = _original(map_id)
    return {t - UPPER for t in arriba if t >= UPPER}


def _destinos_altos(receta):
    """Las ranuras de la página alta que la receta de la imagen pisa."""
    destinos = [hasta for _, hasta in receta.get("tiles_altos", [])]
    for una in receta.get("desde_charset", []):
        destinos += [una["cabeza"], una["cuerpo"]]
    # `desde_imagen` compone **sobre** la ranura que nombra su cuarto
    # elemento, así que ésa no se pisa: se conserva y se le dibuja encima.
    for entrada in (receta.get("desde_imagen") or {}).get("celdas", []):
        if len(entrada) <= 3:
            destinos.append(entrada[2])
    return destinos


def test_fork_no_pisa_una_ranura_que_su_mapa_dibuja_con_el_arte_de_antes():
    """Armar la imagen del ChipSet **pisa** ranuras de la página alta, y
    ninguna puede ser una que el mapa ya estuviera dibujando.

    No da error por sí solo, que es lo de siempre: el mapa sigue armando, con
    una celda que ahora dibuja otra cosa. El ChipSet es privado de sus mapas
    forkeados, así que las demás ranuras son de uso libre.
    """
    por_chipset = {}
    for map_id, (ruta_json, _) in fork.mapas().items():
        datos = json.load(open(ruta_json, encoding="utf-8"))
        por_chipset.setdefault(datos["chipset_id"], []).append(map_id)
    for numero, datos in fork.chipsets().items():
        pisadas = set(_destinos_altos(datos["imagen"]))
        for map_id in por_chipset.get(numero, []):
            chocan = pisadas & _altos_del_original(map_id)
            assert not chocan, (
                "el ChipSet %d pisa las ranuras altas %s y el mapa %d las "
                "dibujaba" % (numero, sorted(chocan), map_id))


def test_fork_un_tile_duplicado_hereda_la_pasabilidad_de_su_origen():
    """La receta de la imagen y la entrada de la base tienen que decir lo
    mismo: un tile que se copia pixel por pixel y se pisa distinto es un tile
    que se ve igual y no se juega igual.

    El **terreno** sí cambia, y es justamente para eso que se duplica.

    Vale para lo que se copia de adentro del ChipSet, y no para lo que entra
    de un CharSet: ahí no hay origen del que heredar nada, y cómo se pisa la
    celda es justamente la decisión —ver
    `test_fork_donde_borro_un_evento_del_piso_la_celda_sigue_cerrada`—.
    """
    for numero, datos in fork.chipsets().items():
        entrada, receta = datos["chipset"], datos["imagen"]
        for desde, hasta in receta.get("tiles_altos", []):
            assert entrada["passable_data_upper"][hasta] \
                == entrada["passable_data_upper"][desde], (
                    "ChipSet %d: el tile alto %d copia al %d y no se pisa "
                    "igual" % (numero, hasta, desde))
        for desde, hasta in receta.get("bloques_bajos", []):
            # El índice de un bloque de autotile de terreno en las tablas de
            # la base son los 6 bloques de agua y animados, y después él.
            assert entrada["passable_data_lower"][6 + hasta] \
                == entrada["passable_data_lower"][6 + desde], (
                    "ChipSet %d: el bloque bajo %d copia al %d y no se pisa "
                    "igual" % (numero, hasta, desde))


def test_podar_conserva_las_ranuras_que_solo_nombra_un_evento():
    """Podar el ChipSet borra lo que el mapa no dibuja, y **un evento sin
    CharSet dibuja con un tile de la página alta** que no está en ninguna capa.

    Es el que se escapó: el mapa 32 perdía la ranura 13 —la de una página de
    `EV0023`— y la ROM salía con 78 bytes de gráficos en cero. No lo cobró
    ninguna prueba, lo cobró comparar la ROM byte por byte, y por eso esta
    prueba existe.
    """
    forkeados = fork.mapas()
    chipsets = fork.chipsets()
    mirados = 0
    for map_id, (ruta_json, _) in forkeados.items():
        datos = json.load(open(ruta_json, encoding="utf-8"))
        receta = chipsets.get(datos["chipset_id"], {}).get("imagen", {})
        if "podar" not in receta:
            continue
        mirados += 1
        _, _, comunes = fork._lo_que_dibuja(map_id)
        mapa = lcf.Map(os.path.join(RAIZ, "data", "maps",
                                    "Map%04d.json" % map_id))
        for evento in mapa.events:
            for pagina in evento.pages:
                if not pagina.character_name:
                    assert 144 + pagina.character_index in comunes, (
                        "el mapa %d dibuja un evento con el tile alto %d y el "
                        "podado no lo conserva"
                        % (map_id, pagina.character_index))
    assert mirados, "ningún ChipSet forkeado poda: la prueba no miró nada"


def test_podar_se_planta_si_el_mapa_elige_tiles_en_caliente(tmp_path):
    """Con `ChangeMapTileset` o `TileSubstitution` adentro, las capas dejan de
    decir qué dibuja el mapa, así que el podado no puede saber qué guardar.

    Se planta en vez de adivinar: perder arte en silencio es justo lo que este
    archivo existe para evitar. Ningún mapa forkeado los usa, así que el camino
    se ejercita metiéndole el comando a un fork de mentira.
    """
    map_id = next(iter(fork.mapas()))
    ruta_json, ruta_tiles = fork.mapas()[map_id]
    datos = json.load(open(ruta_json, encoding="utf-8"))
    codigo, nombre = sorted(fork.COMANDOS_QUE_ELIGEN_TILES.items())[0]
    datos["events"][0]["pages"][0].setdefault("event_commands", []).append(
        {"code": codigo, "indent": 0, "string": "", "parameters": [0]})

    mapas_antes = fork.MAPAS
    fork.MAPAS = str(tmp_path)
    try:
        with open(os.path.join(tmp_path, "Map%04d.json" % map_id), "w",
                  encoding="utf-8") as handle:
            json.dump(datos, handle)
        shutil.copy(ruta_tiles, os.path.join(tmp_path,
                                             "Map%04d.tiles" % map_id))
        with pytest.raises(fork.ForkRoto) as caida:
            fork._lo_que_dibuja(map_id)
    finally:
        fork.MAPAS = mapas_antes
    assert nombre in str(caida.value)


def test_desde_imagen_trae_el_png_a_quince_bits_y_compone_sobre_su_base(tmp_path):
    """`desde_imagen` mete un PNG que no es un ChipSet en las ranuras altas.

    Las tres cosas que tiene que hacer bien, y que si se rompen no dan error:

    * **escalar con vecino más cercano**, que es lo que hace RM2k;
    * **redondear a 15 bits**, que es lo que la consola muestra y lo que hace
      entrar el dibujo en los 256 índices del PNG indexado;
    * **componer sobre la ranura que se le nombre** en vez de pisarla, que es
      lo que deja viva una pared donde el dibujo sólo apoya unos pixeles.
    """
    from PIL import Image
    from render.chipset import caja_de_comun

    # Un ChipSet de mentira, con la ranura alta 5 pintada de su único color.
    base = Image.new("P", (480, 256))
    base.putpalette([0, 0, 0] + [7, 7, 7] + [0, 0, 0] * 254)
    base.paste(Image.new("P", (16, 16), 1), caja_de_comun(144 + 5)[:2])
    ruta_chip = tmp_path / "base.png"
    base.save(ruta_chip)

    # Y un dibujo de 32x32 cuya mitad de arriba a la izquierda tiene un color
    # que **no** es múltiplo de 8, para que el redondeo a 15 bits se note.
    dibujo = Image.new("P", (32, 32))
    dibujo.putpalette([255, 0, 255] + [250, 130, 66] + [0, 0, 0] * 254)
    dibujo.paste(Image.new("P", (16, 16), 1), (0, 0))
    ruta_dibujo = tmp_path / "dibujo.png"
    dibujo.save(ruta_dibujo)

    datos = {
        "chipset": {"id": 999, "chipset_name": "salida"},
        "imagen": {
            "base": "base",
            "desde_imagen": {
                "carpeta": "Picture", "imagen": "dibujo", "escala": 50,
                "desfase": [0, 0],
                # La 6 se pisa entera; la 7 compone sobre el dibujo de la 5.
                "celdas": [[0, 0, 6], [0, 0, 7, 5]],
            },
        },
    }

    def buscar(carpeta, nombre):
        return str(ruta_chip if carpeta == "ChipSet" else ruta_dibujo)

    anterior = fork.GENERADO
    fork.GENERADO = str(tmp_path / "build")
    try:
        salida = Image.open(fork.imagen_del_chipset(datos, buscar))
        salida.load()
    finally:
        fork.GENERADO = anterior
    paleta = salida.getpalette()

    def color(ranura, x, y):
        indice = salida.crop(caja_de_comun(144 + ranura)).load()[x, y]
        return indice, tuple(paleta[indice * 3:indice * 3 + 3])

    # Al 50% el dibujo de 32x32 queda de 16x16: sus 8x8 de arriba a la
    # izquierda pintados y el resto transparente.
    indice, rgb = color(6, 0, 0)
    assert indice, "el dibujo cayó en el índice 0, que es el transparente"
    assert rgb == (248, 128, 64), "no redondeó a 15 bits: %s" % (rgb,)
    assert color(6, 12, 12)[0] == 0, "lo transparente del dibujo pintó algo"

    # La 7 arranca del dibujo de la 5 y el nuevo la tapa **sólo donde pinta**:
    # donde el dibujo es transparente tiene que seguir el color de la 5.
    assert color(7, 0, 0)[1] == (248, 128, 64), "no compuso encima"
    assert color(7, 12, 12)[1] == (7, 7, 7), "componer borró la base"


def test_los_colores_declarados_transparentes_no_llegan_al_chipset():
    """Un color que la receta declara transparente no puede quedar en el PNG.

    Es una **divergencia declarada**: el arte original del Hover Tram trae dos
    pixeles pintados casi del color de la clave pero no igual, que RM2k dibuja
    y se ven rosas. Taro decidió que en el port van transparentes.

    Y la prueba existe porque el error ya se cometió: cuál de los dos pixeles
    sobrevive **depende de la escala** —al 65% es uno y al 56% el otro—, así
    que la receta llegó a nombrar uno solo y el otro se coló igual. El PNG
    salió con el rosa adentro y nada lo dijo.
    """
    from PIL import Image

    mirados = 0
    for numero, datos in fork.chipsets().items():
        declarados = {tuple(c) for c in
                      (datos["imagen"].get("desde_imagen") or {})
                      .get("transparentes", [])}
        if not declarados:
            continue
        mirados += 1
        ruta = os.path.join(fork.GENERADO, "ChipSet",
                            datos["chipset"]["chipset_name"] + ".png")
        if not os.path.isfile(ruta):
            pytest.skip("el PNG del ChipSet %d no está armado" % numero)
        imagen = Image.open(ruta)
        imagen.load()
        paleta = imagen.getpalette() or []
        usados = set(imagen.tobytes())
        # A 15 bits, porque `desde_imagen` redondea los colores al entrar.
        prohibidos = {tuple((c >> 3) << 3 for c in d) for d in declarados}
        for indice in usados:
            color = tuple(paleta[indice * 3:indice * 3 + 3])
            assert color not in prohibidos, (
                "el ChipSet %d declara transparentes %s y uno quedó en el PNG, "
                "en el índice %d" % (numero, sorted(declarados), indice))
    assert mirados, "ninguna receta declara colores transparentes"
