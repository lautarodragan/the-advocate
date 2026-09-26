"""Lo que la victoria cuenta: "N EXP" y una página por cada actor que subió.

`ProcessSceneActionVictory` de `Scene_Battle_Rpg2k`: la primera página es el
término de la victoria y la experiencia ganada, y después cada actor que subió
de nivel tiene la suya, con "<nombre> LEVEL <n> achieved!" y una línea por
habilidad aprendida. Acá van en los cuatro renglones del grupo —ver
`batalla_victoria.s`—.

No se compara contra una golden sino **contra el texto**: se lee el tilemap de
la pantalla, `texto_buf`, y se traduce cada celda con la tabla de glifos del
cartucho. Así la prueba dice qué renglón está mal y con qué letras, y los
renglones esperados salen de `pantallas.renglon_de_*`, que es el armado de
`game_message_terms.cpp` y lo mismo con que el conversor cobra que entren. Los
niveles y las habilidades salen de `experiencia.sumar` y del LDB, no de acá.
"""

from port import experiencia
from port import pantallas
from port import titulo

from batalla import GRUPO, Pelea, en_el_droide
from consola import en_la_rom, en_la_wram
import datos
from test_experiencia_dibujo import ARDEN, poner_exp

TROPA_DROIDE = 82
KERSH, CORE, MANTA = GRUPO


def glifos(una):
    """Las dos celdas de cada letra blanca, al carácter: la tabla
    `item_glifo_celdas` del cartucho, cuatro bytes por letra. Las dos, porque
    hay letras que comparten la de arriba —la "h" y la "b"—."""
    with open(una.sfc, "rb") as archivo:
        rom = archivo.read()
    base = en_la_rom(una.simbolos["item_glifo_celdas"])
    de = {}
    for n in range(titulo.ITEM_CARACTERES):
        b = rom[base + 4 * n:base + 4 * n + 4]
        de.setdefault((b[0] | (b[1] << 8), b[2] | (b[3] << 8)),
                      chr(titulo.ITEM_PRIMER_CARACTER + n))
    return de


def renglones(una, fila0, cuantos):
    """Los renglones de texto de la pantalla de la pelea desde la fila
    `fila0` del tilemap, de a dos filas cada uno, sin los espacios del final.
    Una celda que no es ninguna letra sale como '#'."""
    de = glifos(una)
    buf = una.consola.ram(en_la_wram(una.simbolos["texto_buf"]), 64 * 28)
    salida = []
    for r in range(cuantos):
        fila = fila0 + 2 * r
        letras = []
        for col in range(32):
            i = fila * 64 + 2 * col
            celda = (buf[i] | (buf[i + 1] << 8),
                     buf[i + 64] | (buf[i + 65] << 8))
            letras.append(" " if celda == (0, 0) else de.get(celda, "#"))
        salida.append("".join(letras).rstrip())
    return salida


def ventana(una):
    """Lo que dice la ventana de la victoria: los cuatro renglones del grupo,
    desde la columna del mensaje, y los dos de abajo, que tienen que quedar
    vacíos."""
    arriba = renglones(una, pantallas.BA_PAG_MSG_FILA0, 4)
    abajo = renglones(una, pantallas.BA_MSG_FILA1, 2)
    col = pantallas.BA_PAG_MSG_COL
    assert all(r[:col].strip() == "" for r in arriba), arriba
    return [r[col:] for r in arriba], abajo


def ganar_hasta_el_fin(una, grupo):
    """Pelea atacando hasta que la pantalla queda en la del fin, **sin
    cerrarla**. Cuántos órdenes da cada turno lo dice la RAM: los actores del
    grupo que siguen en pie."""
    pelea = Pelea(una).abrir()
    for _ in range(30):
        if pelea.modo() == "FIN":
            return pelea
        vivos = sum(1 for k in range(len(grupo))
                    if pelea.hp_del_combatiente(k) > 0)
        pelea.turno(vivos)
    raise AssertionError("la pelea no terminó")


def paginas(una, pelea, tope=10):
    """Cada página de la victoria —sus cuatro renglones— hasta que la pelea
    se cierra, apretando A entre una y otra."""
    vistas = []
    for _ in range(tope):
        if not pelea.abierta():
            return vistas
        assert pelea.modo() == "FIN"
        arriba, abajo = ventana(una)
        assert abajo == ["", ""], \
            "el renglón del mensaje de la pelea tendría que estar vacío: %r" \
            % abajo
        vistas.append([r for r in arriba if r] if any(arriba) else [])
        pelea.tocar_cuadros()
        for _ in range(10):
            if not pelea.abierta():
                break
            una.consola.correr(1)
    raise AssertionError("la victoria no se cerró en %d páginas" % tope)


def primera_pagina(term, exp):
    return (pantallas.renglones_de_la_victoria(term["victoria"])
            + [pantallas.renglon_de_experiencia(term, exp)])


def pagina_de_nivel(term, base, actor, antes, despues):
    """El renglón del nivel y los de las habilidades que enseñan los niveles
    que pasó, nivel por nivel, en el orden de la tabla del LDB."""
    nombres = [base.skills[s].name
               for nivel in range(antes + 1, despues + 1)
               for n, s in base.actors[actor].skills if n == nivel]
    return ([pantallas.renglon_de_nivel(term, base.actors[actor].name,
                                        despues)]
            + [pantallas.renglon_de_habilidad(term, h) for h in nombres])


def test_la_victoria_dice_la_experiencia_y_se_cierra(partida):
    """El grupo de la intro en sus niveles del LDB: el droide no alcanza para
    que nadie suba, así que hay una sola página —la victoria partida en dos
    renglones y "90 EXP"— y la A que sigue cierra la pelea.

    El término del ABL son 36 letras y la ventana tiene 31: sin partirlo se
    pasaba al renglón de abajo, cortado a la mitad de "victory!"."""
    una = en_el_droide(partida)
    base = datos.base()
    term = pantallas.terminos_batalla(base)
    ganada = experiencia.exp_de_la_tropa(base, TROPA_DROIDE)
    for actor in GRUPO:
        nivel = experiencia.nivel_inicial(base.actors[actor])
        exp = experiencia.exp_inicial(base.actors[actor])
        assert experiencia.sumar(base.actors[actor], nivel, exp, ganada)[0] \
            == nivel, "el caso quiere que nadie suba: el %d sube" % actor
    pelea = ganar_hasta_el_fin(una, GRUPO)
    assert paginas(una, pelea) == [primera_pagina(term, ganada)]


def test_el_que_sube_tiene_su_pagina_y_el_que_no_no(partida):
    """Arden sube del 3 al 6 y aprende una habilidad en cada nivel; Kersh
    queda en el suyo; Manta sube uno y no aprende nada. Las páginas son la de
    la victoria, la de Arden y la de Manta, en el orden del grupo, y **ninguna
    de Kersh**.

    Lurk In Shadows, la del 5, es de las que la pelea no sabe ofrecer —no
    está en la lista de habilidades de la pantalla— y la victoria la cuenta
    igual, que es lo que hace RM2k."""
    una = en_el_droide(partida)
    base = datos.base()
    term = pantallas.terminos_batalla(base)
    ganada = experiencia.exp_de_la_tropa(base, TROPA_DROIDE)
    grupo = (ARDEN, KERSH, MANTA)
    una.poner_grupo(*grupo)
    lista = experiencia.lista_de(base.actors[ARDEN])
    exp_arden = lista[5] - 50
    poner_exp(una, ARDEN, exp_arden, 3)
    nivel_m = experiencia.nivel_inicial(base.actors[MANTA])
    exp_m = experiencia.lista_de(base.actors[MANTA])[nivel_m] - 10
    poner_exp(una, MANTA, exp_m, nivel_m)
    assert experiencia.sumar(base.actors[ARDEN], 3, exp_arden, ganada)[0] == 6
    assert experiencia.sumar(base.actors[MANTA], nivel_m, exp_m,
                             ganada)[0] == nivel_m + 1
    nivel_k = experiencia.nivel_inicial(base.actors[KERSH])
    assert experiencia.sumar(base.actors[KERSH], nivel_k,
                             experiencia.exp_inicial(base.actors[KERSH]),
                             ganada)[0] == nivel_k
    pelea = ganar_hasta_el_fin(una, grupo)
    vivos = {grupo[k] for k in range(len(grupo))
             if pelea.hp_del_combatiente(k) > 0}
    assert vivos == set(grupo), "el caso quiere a los tres en pie: %r" % vivos
    assert paginas(una, pelea) == [
        primera_pagina(term, ganada),
        pagina_de_nivel(term, base, ARDEN, 3, 6),
        pagina_de_nivel(term, base, MANTA, nivel_m, nivel_m + 1),
    ]


def test_las_habilidades_que_no_entran_siguen_en_otra_pagina(partida):
    """Arden del 3 al 9: seis habilidades, y la ventana tiene cuatro
    renglones. La primera página lleva el nivel y tres; la segunda, las otras
    tres, sin repetir el nivel. Es lo que hace la ventana de RM2k con un
    mensaje de más de cuatro renglones."""
    una = en_el_droide(partida)
    base = datos.base()
    term = pantallas.terminos_batalla(base)
    ganada = experiencia.exp_de_la_tropa(base, TROPA_DROIDE)
    grupo = (ARDEN, KERSH)
    una.poner_grupo(*grupo)
    exp_arden = experiencia.lista_de(base.actors[ARDEN])[8] - 50
    poner_exp(una, ARDEN, exp_arden, 3)
    assert experiencia.sumar(base.actors[ARDEN], 3, exp_arden, ganada)[0] == 9
    esperada = pagina_de_nivel(term, base, ARDEN, 3, 9)
    assert len(esperada) == 7, "el caso quiere seis habilidades: %r" % esperada
    pelea = ganar_hasta_el_fin(una, grupo)
    assert pelea.hp_del_combatiente(0) > 0, "Arden tiene que quedar en pie"
    assert paginas(una, pelea) == [
        primera_pagina(term, ganada), esperada[:4], esperada[4:]]
