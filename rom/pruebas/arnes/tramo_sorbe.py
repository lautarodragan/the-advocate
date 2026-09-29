"""Del mundo a Sorbe y a Tasgarde, lo que el capítulo usa: la rama de Wick,
los actores y los mapas, y cómo se juega de a un cuadro de hardware pasando
mensajes y peleas —`jugar`— con los encuentros apagados.

Vivía en `abl/test_recorrido_sorbe_golden.py` hasta el 2026-09-29, y de ahí
lo importaba `abl/test_recorrido_capitulo_golden.py`.
"""

from consola import en_la_wram

# La rama de Wick: el 162 es "le dijo que no", y con él la llegada al mundo
# prende el 239 y Talan renguea hasta la casa de Vago.
RECHAZO_A_WICK = 162

TALAN, ARDEN, DUMMY, DALIA, EL_AUTO = 14, 15, 10, 21, 22

EL_MUNDO, SORBE, LA_MONTANA, LA_CASA_DE_VAGO = 66, 69, 76, 81

ENTRADA_A_TASGARDE = (93, 4)

# En la casa de Vago: el tobillo curado, y la historia contada.
TOBILLO_CURADO = 267
CONTO_LA_HISTORIA = 252

# El viaje de Dalia: lo prende la automática 14 al terminar.
DALIA_LLEGO = 278

BOTON_CADA = 9       # cuadros de hardware entre toques de A en una pelea


def sin_encuentros(p):
    """El mapa los vuelve a prender en cada carga: se apagan después de
    llegar."""
    p.consola.write_ram(en_la_wram(p.simbolos["ENC_BASE"]), [0, 0])


def jugar(r, que, hasta, tope=60000, fotos=None, momentos=None):
    """Juega de a un cuadro de hardware hasta que `hasta(partida)`: pasa cada
    mensaje con A cuando terminó de componerse, y en una pelea toca A cada
    `BOTON_CADA` cuadros —que pasa los mensajes y elige atacar—.

    De a cuadros y no de a ticks porque la pelea no hace correr `ticks`, y
    una espera por ticks se planta ahí. `fotos` es {nombre: cond}: la primera
    vez que un mensaje está compuesto con `cond(partida)` verdadera, se saca
    esa foto antes de cerrarlo. `momentos` es lo mismo en cualquier cuadro,
    haya mensaje o no."""
    p = r.p
    pendientes = dict(fotos or {})
    momentos = dict(momentos or {})
    for cuadro in range(tope):
        if hasta(p):
            return r
        for nombre, cond in list(momentos.items()):
            if cond(p):
                r.foto(nombre, asentar=False)
                del momentos[nombre]
        if p.byte("menu_open"):
            p.consola.hold(*(("a",) if cuadro % BOTON_CADA < 2 else ()))
            p._un_cuadro()
            continue
        if p.byte("msg_open") and p.byte("msg_state") != 1:
            for nombre, cond in list(pendientes.items()):
                if cond(p):
                    r.foto(nombre, asentar=False)
                    del pendientes[nombre]
            p.consola.hold("a")
            p._un_cuadro()
            p._un_cuadro()
            p.consola.hold()
            for _ in range(60):
                if not p.byte("msg_open"):
                    break
                p._un_cuadro()
            continue
        p.consola.hold()
        p._un_cuadro()
    raise AssertionError("jugando %s no se llegó en %d cuadros. %s"
                         % (que, tope, r.estado()))


def en_pelea_hace(cuadros):
    """Una condición de `momentos`: la pelea lleva `cuadros` de hardware
    abierta, que es cuando la escena ya está dibujada."""
    visto = [0]

    def cond(p):
        visto[0] = visto[0] + 1 if p.byte("menu_open") else 0
        return visto[0] >= cuadros
    return cond
