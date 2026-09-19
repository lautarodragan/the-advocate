"""Los encuentros al azar: los datos del juego y la cuenta que los dispara.

Esta prueba **no toca la ROM**, y es a propósito. Lo que cuida son las dos
patas del modelo que la comparación de pixeles no puede ver:

* **las dos simplificaciones**, que hoy son ciertas y mañana pueden no serlo.
  El port no lee el terreno de cada celda ni el `terrain_set` de cada tropa
  porque están medidos: todos los terrenos que pisan los mapas con encuentros
  tienen `encounter_rate` 100 y ninguna tropa filtra por terreno. Si eso
  cambiara —otro volcado del juego, otro juego— el modelo pasaría a ser
  mentira **sin que ningún pixel se mueva**, que es exactamente la forma de
  falla que este repo ya pagó tres veces;
* **la reescritura en enteros**. `Game_Player::UpdateEncounterSteps` compara
  `acumulado / pasos` contra la tabla y tira un flotante; la consola no puede
  hacer ninguna de las dos cosas, así que el conversor precalcula en qué paso
  se cruza cada fila. Que las dos cuentas den lo mismo se comprueba acá, fila
  por fila y paso por paso, y no mirando una pantalla.

Los números que imprime el informe salen de acá: `test_cuantos_mapas` los
cuenta.
"""

import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "tools"))

import eventos                                               # noqa: E402
import lcf                                                   # noqa: E402
from render_map import GAME_DIR                               # noqa: E402

# Los terrenos y el `terrain_set` de cada tropa salen de `db.decode()`, que es
# la base entera como la volcó Ditto: el port no los modela porque no los
# necesita para nada más, y acá se los mira una sola vez.


@pytest.fixture(scope="module")
def juego():
    db = lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))
    tree = lcf.TreeMap(os.path.join(GAME_DIR, "RPG_RT.lmt"))
    return db, tree


def mapas_con_encuentros(tree):
    """Los mapas donde puede salir un encuentro: los que traen tropas propias
    y los que tienen un área colgando."""
    areas = [i for i, t in tree.map_types.items() if t == eventos.TREE_AREA]
    con_area = {tree.map_parents[i] for i in areas if tree.encounters[i]}
    propias = {i for i, t in tree.map_types.items()
               if t == 1 and tree.encounters[i]}
    return sorted(propias | con_area), sorted(propias), sorted(areas)


def tag_de_celda(db, game_map, indice):
    """El terreno de una celda, como `Game_Map::GetTerrainTag`: el índice del
    tile de la capa de abajo adentro de `terrain_data` del chipset."""
    chip = game_map.lower_layer[indice]
    if chip < 3000:
        k = chip // 1000                       # el agua, A/B/C
    elif chip < 4000:
        k = 3 + (chip - 3000) // 50            # los tiles animados
    elif chip < 5000:
        k = 6 + (chip - 4000) // 50            # los autotiles
    else:
        k = 18 + (chip - 5000)                 # las páginas de tiles comunes
    datos = db.chipsets[game_map.chipset_id].terrain
    # "When the terrain is all 1, no terrain data is stored", dice easyrpg.
    return datos[k] if datos and k < len(datos) else 1


def test_todos_los_terrenos_de_esos_mapas_valen_cien(juego):
    """La primera simplificación: el acumulado sube de a 100 siempre.

    Si alguna vez un mapa con encuentros pisa un terreno con otro `rate`, hay
    que leer el terreno celda por celda de los dos lados —o cortar—, y este
    caso es el que lo avisa.
    """
    db, tree = juego
    terrenos = db.decode()["terrains"]
    rate = {i: f.get("encounter_rate", lcf.CAMPOS["Terrain"]["encounter_rate"][1])
            for i, f in terrenos.items()}
    todos, _propias, _areas = mapas_con_encuentros(tree)
    vistos = set()
    for map_id in todos:
        game_map = lcf.Map(os.path.join(GAME_DIR, "Map%04d.lmu" % map_id))
        for i in range(len(game_map.lower_layer)):
            vistos.add(tag_de_celda(db, game_map, i))
    assert vistos, "ningún mapa con encuentros: la medición no midió nada"
    distintos = {t: rate.get(t) for t in sorted(vistos)
                 if rate.get(t) != eventos.ENC_RATE}
    assert not distintos, (
        "estos terrenos de los mapas con encuentros no valen %d: %s. El modelo "
        "de eventos.Encuentros da por sentado que el acumulado sube de a %d"
        % (eventos.ENC_RATE, distintos, eventos.ENC_RATE))


def test_ninguna_tropa_queda_afuera_por_el_terreno(juego):
    """La segunda: `GetEncountersAt` acepta todas las tropas de la lista.

    En RM2k una tropa puede decir en qué terrenos aparece, y vacío quiere decir
    "en todos". **Doce de las tropas de este juego lo dicen**, así que la
    simplificación no se sostiene por ahí: se sostiene porque ninguna de ellas
    excluye un terreno que su mapa pise de verdad. Eso es lo que se mide acá,
    mapa por mapa y celda por celda, y no que el `terrain_set` esté vacío.

    Hasta el 2026-09-14 esta prueba decía lo segundo y **no medía nada**: leía
    el `terrain_set` del chunk 0x13 de la base, que es `animations` y no
    `troops` —el de las tropas es el 0x0F—, así que preguntaba por un chunk que
    ninguna animación tiene y siempre daba vacío. Lo destapó la mudanza a los
    JSON de Ditto, que ya no se leen por número de chunk. Es el caso de manual
    del repo: un camino que ninguna prueba ejecuta, con la prueba puesta.
    """
    db, tree = juego
    crudas = db.decode()["troops"]
    todos, _propias, areas = mapas_con_encuentros(tree)

    # Qué tropas puede sacar cada mapa: las suyas y las de sus áreas.
    tropas_de = {}
    for map_id in todos:
        tropas = set(tree.encounters[map_id])
        for area in areas:
            if tree.map_parents[area] == map_id:
                tropas |= set(tree.encounters[area])
        tropas_de[map_id] = sorted(tropas)
    assert any(tropas_de.values()), "ninguna tropa: la medición no midió nada"

    afuera = []
    for map_id, tropas in tropas_de.items():
        game_map = lcf.Map(os.path.join(GAME_DIR, "Map%04d.lmu" % map_id))
        terrenos = {tag_de_celda(db, game_map, i)
                    for i in range(len(game_map.lower_layer))}
        for tropa in tropas:
            conjunto = crudas.get(tropa, {}).get("terrain_set") or []
            if not conjunto:
                continue
            for terreno in sorted(terrenos):
                permitido = (conjunto[terreno - 1]
                             if 0 < terreno <= len(conjunto) else True)
                if not permitido:
                    afuera.append((map_id, tropa, terreno))
    assert not afuera, (
        "estas tropas no salen en un terreno que su mapa pisa, y el port las "
        "saca igual —(mapa, tropa, terreno)—: %s" % afuera)


def test_ningun_mapa_tiene_tropas_propias_y_areas(juego):
    """Lo que hace que el orden de las zonas no pueda cambiar qué tropa sale.

    `GetEncountersAt` recorre el árbol por índice y va juntando las tropas del
    mapa y las de sus áreas en ese orden; `zonas_de_encuentro` pone la del mapa
    primero. Mientras ningún mapa tenga las dos cosas, los dos órdenes dan la
    misma lista.
    """
    _db, tree = juego
    todos, propias, areas = mapas_con_encuentros(tree)
    con_area = {tree.map_parents[i] for i in areas if tree.encounters[i]}
    assert not (set(propias) & con_area)
    assert len(todos) == len(propias) + len(con_area)


def test_cuantos_mapas(juego):
    """Los números del juego, clavados: si cambian, cambió el volcado.

    Están acá y no en un comentario porque son los que deciden el alcance: 53
    mapas de 328 pueden tener un encuentro, y de los 29 de `demo-ciudad` son
    cinco.
    """
    _db, tree = juego
    todos, propias, areas = mapas_con_encuentros(tree)
    assert len(areas) == 23
    assert len(propias) == 33
    assert len(todos) == 53
    demo = [4, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20,
            21, 23, 26, 28, 29, 30, 32, 33, 34, 36]
    assert [m for m in demo if m in todos] == [20, 21, 26, 28, 32]


def test_los_umbrales_dicen_lo_mismo_que_la_division(juego):
    """La reescritura en enteros, fila por fila.

    Allá: `ratio = acumulado / pasos` entera, y se sube de fila mientras
    `ratio >= fila`. Acá: se sube mientras `n >= umbral[fila]`, con el umbral
    precalculado por el conversor. Tienen que decidir lo mismo para todos los
    `encounter_steps` del juego y para toda caminata razonable.
    """
    _db, tree = juego
    pasos_posibles = sorted({p for p in tree.encounter_steps.values() if p > 0}
                            | {1, 2, 8, 25})
    for pasos in pasos_posibles:
        umbrales = eventos.enc_umbrales_de_paso(pasos)
        for n in range(0, 400):
            ratio = (eventos.ENC_RATE * n) // pasos
            for fila, (minimo, _pmod) in enumerate(eventos.ENC_TABLA[1:]):
                assert (ratio >= minimo) == (n >= umbrales[fila]), (
                    pasos, n, fila)


def test_la_chance_es_la_de_la_formula():
    """`enc_umbral` contra `(1 / pasos) * pmod`, en 1/65536.

    La cuenta de allá es flotante y la de acá es un corrimiento sobre
    `65536 // pasos`, así que la diferencia es el truncado de esa división y
    nada más. Se exige eso: menos de una parte en `pasos` de distancia.
    """
    for pasos in (8, 25, 35, 40, 55, 65, 70, 75, 80, 85):
        base = eventos.enc_base(pasos)
        for fila, (_minimo, corrimiento) in enumerate(eventos.ENC_TABLA):
            pmod = 2.0 ** corrimiento if corrimiento > 0 else 1 / 2 ** -corrimiento
            exacta = pmod / pasos
            umbral = eventos.enc_umbral(base, fila)
            if umbral is None:
                assert exacta >= 1, (pasos, fila, exacta)
                continue
            assert abs(umbral / 65536.0 - exacta) < (1 + pmod) / 65536.0


def test_apagados_no_tiran_azar():
    """`encounter_steps` 0 vuelve antes de `PercentChance`, sin tocar el azar.

    No es un detalle: el azar de los encuentros es una sola corriente, así que
    un mapa apagado que igual tirara un número correría la secuencia y la
    referencia y la ROM dejarían de coincidir en el mapa siguiente.
    """
    apagado = eventos.Encuentros(0, [(0, 0, 10, 10, [1])])
    semilla = apagado.semilla
    for _ in range(50):
        assert not apagado.paso()
    assert apagado.semilla == semilla
    # Y un mapa sin zonas, aunque traiga pasos: no hay contra qué pelear.
    sin_zonas = eventos.Encuentros(25, [])
    for _ in range(50):
        assert not sin_zonas.paso()


def test_el_area_tapa_con_el_rectangulo_semiabierto(juego):
    """`l <= x < r`, que es lo que dice `Rect::IsOutOfBounds`.

    Se prueba con el área 24, la de Sector 30: (35,20)-(100,68). Un pixel de
    más o de menos acá es una franja del mapa donde el encuentro sale o no
    sale, y jugando no se distingue de "todavía no me tocó".
    """
    _db, tree = juego
    zonas = eventos.zonas_de_encuentro(tree, 20, 100, 100)
    enc = eventos.Encuentros(80, zonas)
    assert enc.candidatas(35, 20)          # la esquina de arriba a la izquierda
    assert enc.candidatas(99, 67)          # la de abajo a la derecha
    assert not enc.candidatas(34, 20)
    assert not enc.candidatas(35, 19)
    assert not enc.candidatas(100, 67)
    assert not enc.candidatas(99, 68)


def test_el_paso_ocho_del_caso_de_la_tanda(juego):
    """El caso `encuentro`, del lado de la referencia.

    Si esto cambia —otra semilla, otra cuenta— el caso de la tanda pasa a
    comparar contra otra tropa y hay que rehacer su caso de la tanda. Vale
    la pena que lo diga una prueba y no un rojo de la tanda a los diez minutos.
    """
    _db, tree = juego
    zonas = eventos.zonas_de_encuentro(tree, 21, 50, 50)
    enc = eventos.Encuentros(8, zonas)
    x, y = 25, 25
    for paso in range(1, 20):
        y -= 1
        if enc.paso():
            assert (paso, enc.elegir(x, y)) == (8, 96)
            return
    pytest.fail("no salió ningún encuentro en veinte pasos")
