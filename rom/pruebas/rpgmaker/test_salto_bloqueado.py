"""Un salto que no puede caer igual deja al personaje mirando hacia donde quiso
saltar.

En RM2k el giro es de `Game_Character::Jump`, y va **antes** de `MakeWay`:
fija la dirección, y el `facing` si no está trabado, y recién después pregunta
si la celda de destino se puede pisar. Si no se puede, `SetJumping(false)` y
devuelve falso, pero el giro ya quedó. Con la ruta sin "saltear si no puede",
`UpdateMoveRoute` reintenta el salto cuadro por cuadro con el personaje ya
girado; la ROM lo saltea —ver `step_route` y `ev_route_frame`— y lo único
que se copia es el giro.

Hasta el 2026-09-30 la ROM giraba sólo si el salto podía caer. No lo cubría
ningún caso: apareció leyendo la reja del mapa 12, donde el héroe ya mira
hacia donde salta cuando el salto falla.

Los cuatro casos se bloquean contra el borde del mapa, que `can_fall` rechaza
antes que cualquier otra cosa: así no dependen de qué hay pintado en el mapa 6.
Cada ruta arranca con un `face_*` hacia un costado distinto del salto, para
que "no giró" y "giró" se distingan.
"""


def correr_la_ruta(una, cuadros=90):
    """Corre la ruta del caso y dice si alguien llegó a estar en el aire."""
    volo = False
    for _ in range(cuadros):
        una.correr(1)
        volo = volo or bool(una.byte("route_jump")) or any(
            ranura[13] for ranura in ranuras_ocupadas(una))
    return volo


def ranuras_ocupadas(una):
    """Los bytes de cada ranura de `route_ev` ocupada."""
    base = una.simbolos["route_ev"]
    paso = una.simbolos["ROUTE_EV_STRIDE"]
    crudo = una.consola.ram(base, una.simbolos["ROUTE_EV_MAX"] * paso)
    return [crudo[k * paso:(k + 1) * paso]
            for k in range(una.simbolos["ROUTE_EV_MAX"])
            if crudo[k * paso] != 0xFF]


def hacia_donde_mira_el_evento(una):
    """El +8 de la única ranura ocupada: el mapa 6 no tiene rutas de página,
    así que la única es la del `MoveEvent` del caso."""
    ranuras = ranuras_ocupadas(una)
    assert len(ranuras) == 1, (
        "se esperaba sólo la ranura de la ruta del caso y hay %d: el caso "
        "dejó de reproducir" % len(ranuras))
    return ranuras[0][8]


NOMBRES = {0: "arriba", 1: "derecha", 2: "abajo", 3: "izquierda"}


def nombre(direccion):
    return NOMBRES.get(direccion, "$%02X" % direccion)


def test_el_heroe_gira_aunque_el_salto_no_pueda_caer(partida):
    """Mira arriba, salta dos a la izquierda desde x = 1: cae afuera del mapa.

    RM2k lo deja mirando a la izquierda —y reintenta el salto, que la ROM
    saltea—. Sin el arreglo seguía mirando arriba.
    """
    una = partida(caso="salto-bloqueado-heroe")
    volo = correr_la_ruta(una)
    assert una.palabra("tile_x") == 1, \
        "el héroe no quedó en x = 1: el caso dejó de reproducir"
    assert not volo, "el héroe saltó: el borde del mapa dejó de frenarlo"
    assert una.byte("hero_dir") == una.simbolos["DIR_LEFT"], (
        "el salto a la izquierda no pudo caer y el héroe quedó mirando hacia "
        "%s; RM2k gira antes de mirar si puede caer"
        % nombre(una.byte("hero_dir")))


def test_el_evento_gira_aunque_el_salto_no_pueda_caer(partida):
    """Kersh mira abajo y salta diez hacia arriba desde y = 9: afuera del mapa.

    Es el mismo `Game_Character::Jump`, con su propio armado en la ROM
    (`build_ev_jump`). Sin el arreglo seguía mirando abajo.
    """
    una = partida(caso="salto-bloqueado-evento")
    assert not correr_la_ruta(una), \
        "Kersh saltó: el borde del mapa dejó de frenarlo"
    mira = hacia_donde_mira_el_evento(una)
    assert mira == una.simbolos["DIR_UP"], (
        "el salto hacia arriba no pudo caer y Kersh quedó mirando hacia %s; "
        "RM2k gira antes de mirar si puede caer" % nombre(mira))


def test_el_evento_trabado_no_gira_con_un_salto_que_no_cae(partida):
    """Lo mismo con `lock_facing` antes: `Jump` cambia la dirección, pero el
    `facing` sólo si no está trabado, así que sigue mirando abajo."""
    una = partida(caso="salto-bloqueado-evento-trabado")
    assert not correr_la_ruta(una), \
        "Kersh saltó: el borde del mapa dejó de frenarlo"
    mira = hacia_donde_mira_el_evento(una)
    assert mira == una.simbolos["DIR_DOWN"], (
        "Kersh tiene la dirección trabada mirando abajo y un salto que no "
        "cayó lo dejó mirando hacia %s" % nombre(mira))


def test_el_evento_trabado_no_gira_con_un_salto_que_cae(partida):
    """Y con el salto que sí cae —atravesando paredes, para que caiga seguro—:
    el giro de `Jump` tampoco pasa por arriba del `lock_facing`.

    La ROM lo pasaba por arriba: el giro del salto no miraba el bit de la
    dirección trabada, que el paso sí mira. Salió de escribir el caso de
    arriba.
    """
    una = partida(caso="salto-evento-trabado")
    assert correr_la_ruta(una), \
        "Kersh nunca saltó: el caso dejó de reproducir"
    mira = hacia_donde_mira_el_evento(una)
    assert mira == una.simbolos["DIR_DOWN"], (
        "Kersh tiene la dirección trabada mirando abajo y el salto a la "
        "derecha lo dejó mirando hacia %s" % nombre(mira))
