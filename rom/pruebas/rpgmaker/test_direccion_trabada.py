"""Lo que tiene la dirección trabada no mira hacia donde camina.

RM2k tiene dos cosas que traban la dirección, y en easyrpg las dos terminan en
el mismo `lock_facing`:

* las órdenes 26 y 27 de una ruta —`SetFacingLocked`—, que valen igual para el
  héroe que para un evento y **quedan puestas cuando la ruta termina**: sólo
  las saca un 27, o en un evento el cambio de página;
* el tipo de animación de la página —`IsDirectionFixedAnimationType`: 2, 3 y
  4—, que `SetAnimationType` copia a la traba.

`Game_Character::Move` cambia la dirección y llama a `UpdateFacing`, que con la
traba no toca el `facing`, que es lo que se dibuja. El pad del héroe pasa por
el mismo `Move`, así que tampoco gira. Los `face_*` de una ruta, en cambio,
escriben el `facing` directo y sí giran.

Lo vio taro en la SNES, el 2026-09-30, en los vehículos, que tienen CharSets
hechos para no girar: cada fila es otro vehículo o el mismo de otro color. El
auto de la carrera (mapas 49 a 54) es el héroe con 13 y 26; el tram de Lashe
City (mapa 9, EV27) y los de la agencia (mapa 28, EV11 y EV12) son eventos con
"gráfico fijo" que una ruta forzada mueve.
"""


def ranura_del_evento(una, evento):
    """Los bytes de la ranura de `route_ev` del evento, por su número de RM2k."""
    base = una.simbolos["route_ev"]
    paso = una.simbolos["ROUTE_EV_STRIDE"]
    crudo = una.consola.ram(base, una.simbolos["ROUTE_EV_MAX"] * paso)
    ranuras = [crudo[k * paso:(k + 1) * paso]
               for k in range(una.simbolos["ROUTE_EV_MAX"])
               if crudo[k * paso] == evento - 1]
    assert len(ranuras) == 1, \
        "el evento %d no tiene ranura: el caso dejó de reproducir" % evento
    return ranuras[0]


NOMBRES = {0: "arriba", 1: "derecha", 2: "abajo", 3: "izquierda"}


def nombre(direccion):
    return NOMBRES.get(direccion, "$%02X" % direccion)


def test_el_pad_no_gira_al_heroe_trabado(partida):
    """La ruta lo pone mirando a la derecha y lo traba; el pad, después de la
    ruta, lo hace caminar para arriba y para abajo sin girarlo.

    Es el auto de la carrera: sin el arreglo, cada flecha le ponía la fila de
    esa dirección, que en ese CharSet es otro auto.
    """
    una = partida(caso="traba-heroe")
    una.correr(30)
    assert una.byte("hero_dir") == una.simbolos["DIR_RIGHT"], \
        "la ruta no dejó al héroe mirando a la derecha: el caso dejó de reproducir"
    for flecha in ("down", "up", "left"):
        una.sostener(20, flecha)
        una.soltar()
        una.correr(20)
        assert una.byte("hero_dir") == una.simbolos["DIR_RIGHT"], (
            "con la dirección trabada mirando a la derecha, la flecha %s lo "
            "dejó mirando hacia %s" % (flecha, nombre(una.byte("hero_dir"))))


def test_el_pad_igual_camina_con_la_direccion_trabada(partida):
    """La traba es del dibujo y no del paso: el héroe trabado camina hacia
    donde apunta la flecha, que es `Move(dir)` con `SetDirection`."""
    una = partida(caso="traba-heroe")
    una.correr(30)
    y0 = una.palabra("tile_y")
    una.sostener(20, "up")
    una.soltar()
    una.correr(20)
    assert una.palabra("tile_y") < y0, \
        "el héroe trabado no subió con la flecha arriba"


def test_la_ruta_no_gira_al_heroe_trabado_hasta_el_27(partida):
    """13, 26, abajo, izquierda, 27, arriba: los dos pasos trabados lo dejan
    mirando a la derecha, y el de después del 27 lo gira hacia arriba."""
    una = partida(caso="traba-heroe-ruta")
    vistas = []
    for _ in range(120):
        una.correr(1)
        if 2 <= una.byte("route_i") <= 4:
            vistas.append(una.byte("hero_dir"))
    assert vistas, "la ruta nunca pasó por los pasos trabados"
    giros = sorted({nombre(d) for d in vistas} - {"derecha"})
    assert not giros, (
        "con la dirección trabada, los pasos de la ruta lo hicieron mirar "
        "hacia %s" % ", ".join(giros))
    assert una.byte("hero_dir") == una.simbolos["DIR_UP"], (
        "después del 27 el paso hacia arriba tenía que girarlo y quedó "
        "mirando hacia %s" % nombre(una.byte("hero_dir")))


def test_el_evento_de_grafico_fijo_no_gira_con_una_ruta_forzada(partida):
    """El tram del mapa 9 tiene "gráfico fijo", mirando a la izquierda, y la
    ruta lo baja dos celdas: tiene que seguir dibujándose como lo pone su
    página.

    `ROUTE_EV_NO_FACE` es eso: "como dice la página". Sin el arreglo, la ranura
    que la ruta forzada le toma nace sin el bit de dirección fija —sólo lo
    traía la ruta propia de la página, y el tram no tiene— y el paso lo ponía
    mirando abajo.
    """
    una = partida(caso="tram-fijo")
    una.correr(90)
    ranura = ranura_del_evento(una, 27)
    assert ranura[7] == 0 and ranura[5] >= ranura[4], \
        "la ruta del tram no terminó: el caso dejó de reproducir"
    assert ranura[8] in (una.simbolos["ROUTE_EV_NO_FACE"],
                         una.simbolos["DIR_LEFT"]), (
        "el tram tiene gráfico fijo mirando a la izquierda y la ruta lo dejó "
        "mirando hacia %s" % nombre(ranura[8]))
