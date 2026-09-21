"""El fork de `juego/` no se puede quedar a medias ni apuntar al mapa de al lado.

Un fork reemplaza un archivo entero de `data/` —ver `juego/README.md`—, y sus
dos modos de falla no dan error por sí solos: se ven bien hasta que no.

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
    """Un `juego/` armable a mano, para los casos que el árbol no tiene."""
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
