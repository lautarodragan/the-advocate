"""Los forks de `parches/manual/`: lo que los de este juego tienen que
cuidar para que el juego siga jugándose.

Un fork reemplaza un archivo entero de `data/` —ver
`parches/manual/README.md`—, y sus modos de falla no dan error por sí solos:
se ven bien hasta que no. Lo que vale para cualquier fork —que no quede a
medias, que el id de adentro sea el del nombre, que reemplace un mapa que
existe, que un mapa nuevo no tape uno del juego, qué hace cada operación de
la receta de un ChipSet— lo mira el conversor en cada armado, y sus pruebas
están con él: `fork.rs` y `chipsets.rs` en `rm2k-snes-convert`. Hasta el
2026-10-02 estaban acá, armadas en un directorio temporal.

Lo que queda acá mira los forks que hay de verdad: que no cambien el tamaño
del mapa, no borren un evento que otro nombra, no abran una celda donde había
gente, no tapen un teleport, no pisen arte que el mapa dibuja.
"""

import json
import os
import shutil

import pytest

from common import project                                      # noqa: E402
import conversor  # noqa: E402
from render_map import build_passability  # noqa: E402
import fork  # noqa: E402
import lcf  # noqa: E402
import rm2k# noqa: E402

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


# Los mapas nuevos, `parches/manual/nuevos/`: la regla de los forks dada
# vuelta. Ver `fork.new_maps`.

def _un_mapa_de_verdad():
    """Un mapa cualquiera de `data/`, para copiar de ahí y no inventar uno."""
    return os.path.join(project.data(), "maps", "Map0011")


@pytest.fixture
def nuevos_de_mentira(tmp_path, monkeypatch):
    nuevos = tmp_path / "nuevos"
    nuevos.mkdir()
    monkeypatch.setattr(fork, "new_maps_folder", lambda: str(nuevos))
    return nuevos


def _un_mapa_nuevo(directorio, map_id, id_del_nodo=None):
    """Un mapa de `data/` copiado como si fuera nuevo, con el nodo del 11."""
    datos = json.load(open(_un_mapa_de_verdad() + ".json", encoding="utf-8"))
    datos["id"] = map_id
    arbol = json.load(open(os.path.join(project.data(), "maps.json"),
                           encoding="utf-8"))["maps"]
    datos["arbol"] = dict(next(n for n in arbol if n["id"] == 11),
                          id=map_id if id_del_nodo is None else id_del_nodo)
    base = directorio / ("Map%04d" % map_id)
    with open(str(base) + ".json", "w", encoding="utf-8") as handle:
        json.dump(datos, handle)
    shutil.copy(_un_mapa_de_verdad() + ".tiles", str(base) + ".tiles")


def test_un_mapa_nuevo_se_lee_como_cualquiera(nuevos_de_mentira):
    """`lcf.Map` lo lee y `lcf.TreeMap` le suma el nodo."""
    _un_mapa_nuevo(nuevos_de_mentira, 9998)
    assert lcf.Map("Map9998.lmu").width == lcf.Map("Map0011.lmu").width
    assert lcf.TreeMap("RPG_RT.lmt").map_names[9998] \
        == lcf.TreeMap("RPG_RT.lmt").map_names[11]


def test_fork_el_id_de_adentro_es_el_del_nombre():
    """Sobre los forks de verdad: es lo que `fork.maps()` exige al leerlos."""
    for map_id, (ruta_json, _) in fork.maps().items():
        datos = json.load(open(ruta_json, encoding="utf-8"))
        assert datos["id"] == map_id
        assert os.path.basename(ruta_json) == "Map%04d.json" % map_id


def test_fork_no_le_cambia_el_tamano_al_mapa():
    """Un fork que redimensiona corre todas las celdas del juego un lugar."""
    for map_id, (ruta_json, _) in fork.maps().items():
        nuestro = json.load(open(ruta_json, encoding="utf-8"))
        suyo = json.load(open(os.path.join(project.data(), "maps",
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
    for map_id, (ruta_json, _) in fork.maps().items():
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
    for map_id, _ in fork.maps().items():
        datos, _ = _original(map_id)
        game_map = lcf.Map("Map%04d.lmu" % map_id)
        vivos = {evento.id for evento in game_map.events}
        base = lcf.Database(os.path.join(project.data(), "db", "RPG_RT.ldb"))
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

    mapas = os.path.join(project.data(), "maps")
    for nombre in sorted(os.listdir(mapas)):
        if not nombre.endswith(".json"):
            continue
        datos = json.load(open(os.path.join(mapas, nombre), encoding="utf-8"))
        for evento in datos["events"]:
            for pagina in evento["pages"]:
                mirar(pagina["event_commands"])
    comunes = json.load(open(os.path.join(project.data(), "db",
                                          "commonevents.json"),
                             encoding="utf-8"))
    for comun in comunes:
        mirar(comun["event_commands"])
    return destinos


def test_fork_los_teleports_que_entran_siguen_cayendo_en_celdas_pisables():
    """La que rompe el juego de verdad, y el id no cubre.

    Mover una pared en el fork no falla en ningún lado: falla el día que
    alguien entra al mapa y aparece adentro de ella.

    Lo que se le pide al fork es no cerrar una celda que el original dejaba
    pisar, y no más: el 36 —la pantalla negra del auto— recibe a `DummyHero`
    en celdas que ya en el juego original no se pisan, y ahí nadie camina.
    """
    forkeados = fork.maps()
    if not forkeados:
        pytest.skip("no hay ningún mapa forkeado")
    base = lcf.Database(os.path.join(project.data(), "db", "RPG_RT.ldb"))
    for map_id in forkeados:
        game_map = lcf.Map("Map%04d.lmu" % map_id)
        flags = build_passability(base.chipsets[game_map.chipset_id])
        pasa = rm2k.passability_map(game_map, flags)
        datos, (abajo, arriba) = _original(map_id)
        antes = [rm2k.cell_passability(
            build_passability(base.chipsets[datos["chipset_id"]]),
            abajo[i], arriba[i]) for i in range(len(abajo))]
        destinos = _teleports_al(map_id)
        assert destinos, "nadie entra al mapa %d: revisar el barrido" % map_id
        for x, y in sorted(destinos):
            if antes[y * game_map.width + x] & rm2k.PASS_ALL != PISABLE:
                continue
            celda = pasa[y * game_map.width + x] & rm2k.PASS_ALL
            assert celda == PISABLE, (
                "el mapa %d recibe un teleport en (%d,%d) y ahí la celda da "
                "%d" % (map_id, x, y, celda))


def _original(map_id):
    """El mapa tal como está en `data/`: el JSON y sus dos capas.

    Se lee a mano y no con `lcf.Map`, que es justamente quien aplica el fork:
    acá hace falta el de antes para compararlo contra el de después.
    """
    base = os.path.join(project.data(), "maps", "Map%04d" % map_id)
    datos = json.load(open(base + ".json", encoding="utf-8"))
    capas = lcf.layers(base + ".tiles", datos, datos["width"], datos["height"])
    return datos, capas


def _altos_del_original(map_id):
    """Los tiles de la página alta que el mapa **sin forkear** dibuja."""
    _, (_, arriba) = _original(map_id)
    return {t - rm2k.UPPER_BASE for t in arriba if t >= rm2k.UPPER_BASE}


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
    for map_id, (ruta_json, _) in fork.maps().items():
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
        # Donde el conversor deja las imágenes que arma: el primer lugar
        # donde se buscan.
        armadas = conversor.contexto_de_mapa(11)["search_dirs"][0]
        ruta = os.path.join(armadas, "ChipSet",
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
