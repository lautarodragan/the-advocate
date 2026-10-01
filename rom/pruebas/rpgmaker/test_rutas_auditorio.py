"""Los dos que entran caminando al auditorio, el mapa 18.

`WalkIn1` y `WalkIn2` son los eventos 16 y 9. La página 1 del evento 36,
automática con el switch 77, los planta en la puerta con
`ChangeEventLocation`, prende el switch que los pasa a su página 2 y les manda
la ruta con `MoveEvent`: suben por el pasillo y se sientan, el 16 en (13,10)
y el 9 en (6,8), que es donde estaban.

Su página 1 dibuja `Future2` en el índice 7, que **es un hueco de la hoja**:
no tiene un pixel. La 2 dibuja el índice 6, el que se ve caminar en el RPG_RT
—capturado con Wine el 2026-09-30—. Como caminan, la fila del NPC se queda
con un solo gráfico —ver `divergencias/un-evento-que-camina-no-cambia-de-grafico.md`—,
y hasta el 2026-09-30 se quedaba con el de la página 1: caminaban por el
pasillo, pero invisibles.

Se mira por la RAM dónde está cada uno, y por la pantalla que se vea algo
donde la ROM dice que lo dibuja.
"""

import pytest

from tanda import partida

CASO = "grupo-11-en-18"
SWITCH_DE_LA_ESCENA = 77
TICKS = 220             # las dos rutas enteras, con holgura

# Índice en la tabla de eventos del mapa —el fork del 18 deja seis: 1, 9,
# 16, 19, 36 y 37—, celda donde los planta la escena, una del camino y
# celda donde los deja la ruta.
WALK_IN_1 = (2, (10, 14), (10, 11), (13, 10))
WALK_IN_2 = (1, (8, 14), (8, 11), (6, 8))

# Lo que se compara de un objeto: su caja de 32x32. Un personaje de RM2k es
# de 24x32, así que caminando cambia bastante más que esto.
PIXELES_DE_UN_PERSONAJE = 100


def _objeto(p, indice):
    """(x, y) en pantalla del objeto de la fila del evento, o None si la ROM
    no lo pone en la OAM."""
    s = p.simbolos
    fila = None
    for y in range(0, p.palabra("npc_total"), s["NPC_STRIDE"]):
        b = p.consola.ram(s["npc_buf"] + y, s["NPC_STRIDE"])
        if b[8] == indice:
            fila = b
    assert fila is not None, "el evento %d no tiene fila de NPC" % indice
    if not fila[14]:
        return None
    oam = p.consola.ram(s["oam"], 512)
    for k in range(128):
        x, y, tile, attr = oam[k * 4:k * 4 + 4]
        if y < 224 and tile == fila[6] and (attr & 1) == (fila[7] & 1):
            return (x, y)
    return None


def _distintos(a, b, caja):
    return sum(1 for u, v in zip(a.crop(caja).getdata(), b.crop(caja).getdata())
               if u != v)


@pytest.fixture(scope="module")
def escena():
    """Cada tick: dónde está cada uno, dónde lo dibuja y la pantalla."""
    p = partida(CASO)
    p.prender(SWITCH_DE_LA_ESCENA)
    ticks = []
    for _ in range(TICKS):
        p.correr(1)
        ticks.append({
            "celdas": {ev[0]: p.evento(ev[0]) for ev in (WALK_IN_1, WALK_IN_2)},
            "objetos": {ev[0]: _objeto(p, ev[0]) for ev in (WALK_IN_1, WALK_IN_2)},
            "imagen": p.imagen().convert("RGB"),
        })
    return ticks


@pytest.mark.parametrize("evento", (WALK_IN_1, WALK_IN_2),
                         ids=("WalkIn1", "WalkIn2"))
def test_terminan_donde_los_deja_la_ruta(escena, evento):
    indice, puerta, camino, asiento = evento
    celdas = [t["celdas"][indice] for t in escena]
    assert puerta in celdas, (
        "el evento no pasó por la puerta, donde lo planta "
        "`ChangeEventLocation`: %s" % sorted(set(celdas)))
    assert camino in celdas, (
        "el evento no pasó por %s, en el medio del pasillo: %s"
        % (camino, sorted(set(celdas))))
    assert celdas[-1] == asiento, celdas[-1]


@pytest.mark.parametrize("evento", (WALK_IN_1, WALK_IN_2),
                         ids=("WalkIn1", "WalkIn2"))
def test_se_ven_caminar(escena, evento):
    """Mientras sube por el pasillo, donde la ROM pone su objeto la pantalla
    tiene que ser distinta de la del primer tick, cuando ahí no había nadie.
    Con el gráfico del hueco de la hoja el objeto está y no dibuja nada, así
    que las dos dan iguales.

    Contra el primer tick y no contra el último: al final ya está el mensaje
    de Talan, que tapa el pasillo y daría distinto con o sin nadie."""
    indice, _, camino, _ = evento
    vacio = escena[0]["imagen"]
    vistos = []
    for t in escena:
        if t["celdas"][indice] != camino:
            continue
        objeto = t["objetos"][indice]
        assert objeto is not None, (
            "en %s la ROM no pone el objeto del evento en la OAM" % (camino,))
        x, y = objeto
        caja = (x, y, min(x + 32, 256), min(y + 32, 224))
        vistos.append(_distintos(t["imagen"], vacio, caja))
    assert vistos and max(vistos) >= PIXELES_DE_UN_PERSONAJE, (
        "subiendo por %s no se ve: pixeles distintos del pasillo vacío, "
        "tick por tick, %s" % (camino, vistos))
