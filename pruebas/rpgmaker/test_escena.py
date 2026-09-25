"""La escena de la pelea, compuesta en la consola: que sea la que tiene que ser,
y que un enemigo muerto desaparezca.

La tanda de pixeles —las goldens de `batalla*`— mira la pantalla entera y dice
**que** cambió algo; esto dice **qué**. Se compara contra una composición hecha
de este lado desde el juego, con las mismas reglas que tools/port/escena.py
escribe y ninguna de las rutinas de la ROM: el fondo que le toca a la pelea, los
battlers convertidos de sus PNG, sus esquinas desde las posiciones del LDB y las
paletas repartidas en el orden de la tropa. Si la ROM corre mal un battler que
no cae en el borde de un tile, se equivoca de paleta o de fondo, o pone a uno
arriba del que no es, algún pixel no da.

Se mira dos veces lo mismo: **la escena en la WRAM**, que es lo que compuso la
ROM, y **la pantalla**, que es lo que llegó a la VRAM. La pantalla sólo en las
filas que el texto no toca: arriba de la escena van los renglones de los
enemigos, uno por enemigo.
"""

import os

from rpgmaker import lcf
from port import escena
from port import batalla as modelo
from render.render_map import GAME_DIR

from consola import en_la_rom, en_la_wram
from batalla import Pelea, en_el_droide, modelo_de

# El encuentro al azar de Sector 27: la celda cae adentro del área 31, y con esa
# semilla sale la tropa 100 —un DecayingShambler y dos AlleyMuck, que se tapan
# entre ellos—. Es la escena más cargada de las que el PoC lleva, y la única
# donde borrar a uno obliga a volver a poner a los otros dos recortados.
SECTOR_27 = (28, 20, 30)
# Cuánto mide un renglón de texto de la pelea, en pixeles: las letras son de dos
# tiles de alto. La pantalla se compara desde abajo de los renglones de los
# enemigos, que van encima de la escena.
RENGLON = 16
SEMILLA_TROPA_100 = 22
TROPA_100 = 100


def db():
    return lcf.Database(os.path.join(GAME_DIR, "RPG_RT.ldb"))


def _byte(una, nombre, k=0):
    return una.consola.ram(en_la_wram(una.simbolos[nombre]) + k, 1)[0]


def _indices(crudo):
    """Los 512 tiles de 8bpp de la escena, como índices de CGRAM fila por fila."""
    filas = [[0] * escena.ANCHO for _ in range(escena.ALTO)]
    for t in range(escena.TILES):
        tx, ty = t % escena.TILES_X, t // escena.TILES_X
        base = t * 64
        for y in range(8):
            planos = [crudo[base + (p // 2) * 16 + y * 2 + (p % 2)]
                      for p in range(8)]
            fila = filas[ty * 8 + y]
            for x in range(8):
                bit = 0x80 >> x
                fila[tx * 8 + x] = sum(1 << p for p in range(8)
                                       if planos[p] & bit)
    return filas


def _bufer(una, nombre):
    return _indices(una.consola.ram(en_la_wram(una.simbolos[nombre]),
                                    escena.TILES * 64))


def _esperada(una, base, tropa, vivos):
    """La escena como la tendría que haber compuesto la ROM, desde el juego.

    `vivos` son los lugares de la tropa que tienen que verse. La paleta de cada
    battler es la del orden en que aparece en la tropa **entera**, vivos o no:
    se reparte al empezar la pelea y no se mueve.
    """
    limpio = _bufer(una, "ESC_LIMPIO")
    miembros = base.troops[tropa].members
    posiciones = base.troops[tropa].posiciones
    claves, puestos = [], []
    for k, (enemigo, centro) in enumerate(zip(miembros, posiciones)):
        e = base.enemies[enemigo]
        info = escena.battler(e.battler_name, e.battler_hue, GAME_DIR)
        if info["clave"] not in claves:
            claves.append(info["clave"])
        paleta = escena.BATTLER_PALETA + claves.index(info["clave"])
        if k in vivos:
            x, y = escena.posicion(centro, info)
            # El orden de dibujo de `Sprite_Battler::ResetZ`, escrito acá de
            # nuevo y no pedido a `escena.orden_de_dibujo`: el borde de abajo
            # en RM2k y, a igual borde, arriba el de menor lugar.
            z = (centro[1] + info["alto_rm"] // 2, -k)
            puestos.append((z, (info, paleta, x, y)))
    puestos = [p for _z, p in sorted(puestos, key=lambda zp: zp[0])]
    return limpio, escena.componer(limpio, puestos)


def _colores(una):
    """La CGRAM de la escena, leída de las tablas que el conversor dejó en el
    cartucho: índice -> color de 15 bits."""
    with open(una.sfc, "rb") as archivo:
        rom = archivo.read()
    s = una.simbolos

    def color(donde):
        w = rom[donde] | (rom[donde + 1] << 8)
        return (w & 31, (w >> 5) & 31, (w >> 10) & 31)

    colores = {}
    fondo = _byte(una, "ESC_FONDO")
    base = en_la_rom(s["fondo_cgram"]) + fondo * escena.COLORES * 2
    for i in range(escena.COLORES):
        colores[escena.CGRAM_BASE + i] = color(base + 2 * i)
    for j in range(_byte(una, "ESC_PAL_N")):
        b = _byte(una, "ESC_PAL_BAT", j)
        base = en_la_rom(s["battler_cgram"]) + b * 32
        for c in range(16):
            colores[(escena.BATTLER_PALETA + j) * 16 + c] = color(base + 2 * c)
    return colores


def _pantalla_distinta(una, esperada, desde):
    """Cuántos pixeles de la pantalla, de la fila `desde` al final de la
    escena, no son los de `esperada`."""
    colores = _colores(una)
    imagen = una.consola.imagen()
    malos = 0
    for y in range(desde, escena.ALTO):
        for x in range(escena.ANCHO):
            r, g, b = imagen.getpixel((x, y))[:3]
            if (r >> 3, g >> 3, b >> 3) != colores[esperada[y][x]]:
                malos += 1
    return malos


def _distintos(a, b):
    return sum(1 for fa, fb in zip(a, b) for x, y in zip(fa, fb) if x != y)


def _esperar(una, tope=400):
    for _ in range(tope):
        if una.byte("menu_abierto"):
            return
        una.consola.correr(1)
    raise AssertionError("la pelea no se abrió")


def _hasta_subido(una, enemigo, tope=60):
    """Los cuadros que hagan falta para que la ROM borre al enemigo y suba sus
    celdas: el bit de `ESC_VIS` apagado y nada pendiente."""
    for _ in range(tope):
        una.consola.correr(1)
        vis = _byte(una, "ESC_VIS")
        pendiente = _byte(una, "ESC_SUB_N") | _byte(una, "ESC_SUB_N", 1)
        if not vis & (1 << enemigo) and not pendiente:
            una.consola.correr(2)
            return
    raise AssertionError(
        "el enemigo %d murió y la ROM no lo borró en %d cuadros: ESC_VIS "
        "quedó en $%02X" % (enemigo, tope, _byte(una, "ESC_VIS")))


def en_sector_27(partida):
    """El encuentro al azar de la tropa 100, forzado: la celda adentro del área
    y el pedido de `ENC_PIDE`, que es lo que deja el contador de pasos."""
    una = partida()
    una.ir_al_mapa(*SECTOR_27)
    s = una.simbolos
    una.consola.escribir_ram(en_la_wram(s["ENC_SEM"]),
                             [SEMILLA_TROPA_100 & 0xFF, SEMILLA_TROPA_100 >> 8])
    una.consola.escribir_ram(en_la_wram(s["ENC_PIDE"]), [1])
    _esperar(una)
    una.consola.correr(3)
    tropa = una.palabra("BA_TROPA")
    assert tropa == TROPA_100, (
        "con la semilla %d el encuentro de Sector 27 tenía que ser la tropa %d "
        "y fue la %d: la prueba no mide lo que dice" % (
            SEMILLA_TROPA_100, TROPA_100, tropa))
    return una


def test_escena_un_encuentro_al_azar_hereda_el_fondo_del_mapa(partida):
    """`Game_Map::SetupBattle`: el área 31 no trae fondo y Sector 27 sí.

    Hasta el 2026-09-21 una pelea al azar no tenía fondo; ahora es el del mapa,
    subiendo por el árbol como RM2k. Se compara el fondo limpio que quedó en la
    WRAM contra el de `ABLBackdropSJ03` convertido de este lado.
    """
    una = en_sector_27(partida)
    assert _byte(una, "ESC_FONDO") != 0xFF, "la pelea al azar quedó sin fondo"
    fondo = escena.fondo("ABLBackdropSJ03", GAME_DIR)
    limpio = _bufer(una, "ESC_LIMPIO")
    assert _distintos(limpio, fondo["indices"]) == 0, \
        "el fondo de la pelea no es el de Sector 27"


def test_escena_compuesta_es_la_del_juego(partida):
    """Los tres battlers de la tropa 100 sobre su fondo, pixel por pixel.

    Los tres caen corridos adentro de su tile —90, 114 y 21 no son múltiplos de
    ocho— y se tapan: el AlleyMuck de la derecha le pisa medio cuerpo al
    Shambler. Es el camino de los ocho corrimientos y el del orden.
    """
    una = en_sector_27(partida)
    base = db()
    n = len(base.troops[TROPA_100].members)
    _limpio, esperada = _esperada(una, base, TROPA_100, set(range(n)))
    compuesta = _bufer(una, "ESC_ESCENA")
    assert _distintos(compuesta, esperada) == 0, (
        "la escena que compuso la ROM difiere de la del juego en %d pixeles"
        % _distintos(compuesta, esperada))
    malos = _pantalla_distinta(una, esperada, RENGLON * n)
    assert malos == 0, (
        "la escena está bien en la WRAM y la pantalla difiere en %d pixeles: "
        "algo no llegó a la VRAM o a la CGRAM" % malos)


def test_escena_un_enemigo_muerto_desaparece(partida):
    """Las celdas que tapaba vuelven a ser las del fondo, y los otros dos siguen.

    Se lo mata escribiendo sus HP en cero, que es lo que ve `escena_tick`: la
    pelea del droide de abajo lo mata peleando. El del medio es el que más
    obliga: los otros dos lo tocan por los dos lados, así que borrarlo es
    volver a poner a ambos recortados a sus celdas, y en el orden de la tropa.
    """
    una = en_sector_27(partida)
    base = db()
    n = len(base.troops[TROPA_100].members)
    muerto = 1
    s = una.simbolos
    donde = s["BA_UNO"] + (s["BA_GRUPO_MAX"] + muerto) * s["BA_BYTES"]
    una.consola.escribir_ram(en_la_wram(donde), [0, 0])
    _hasta_subido(una, muerto)
    limpio, esperada = _esperada(una, base, TROPA_100,
                                 set(range(n)) - {muerto})
    compuesta = _bufer(una, "ESC_ESCENA")
    assert _distintos(compuesta, esperada) == 0, (
        "después de borrar al enemigo %d la escena difiere de la del juego en "
        "%d pixeles" % (muerto, _distintos(compuesta, esperada)))
    malos = _pantalla_distinta(una, esperada, RENGLON * n)
    assert malos == 0, (
        "la escena se recompuso en la WRAM pero la pantalla sigue distinta en "
        "%d pixeles: las celdas no se subieron" % malos)
    # Y que el caso distinga algo: sin el borrado, lo que tapaba se vería.
    _l, con_todos = _esperada(una, base, TROPA_100, set(range(n)))
    assert _distintos(con_todos, esperada) > 500, \
        "el enemigo borrado casi no tapaba nada: el caso no mide nada"


def test_escena_el_droide_muerto_peleando_desaparece(partida):
    """La pelea del droide jugada hasta ganar: donde estaba, queda el fondo.

    Es el camino de verdad —el golpe que lo mata, y no los HP escritos desde
    afuera— y el de la victoria, que es cuando el último enemigo se va.
    """
    una = en_el_droide(partida)
    pelea = Pelea(una).abrir()
    esperado = modelo_de(db())
    while esperado.resultado is None:
        pelea.turno(len(esperado.vivos(esperado.actores)))
        esperado.jugar_turno(
            [(modelo.ORDEN_ATACAR, 0)] * len(esperado.vivos(esperado.actores)))
    assert pelea.byte("BA_RESULT") == modelo.VICTORIA
    _hasta_subido(una, 0)
    limpio = _bufer(una, "ESC_LIMPIO")
    assert _distintos(_bufer(una, "ESC_ESCENA"), limpio) == 0, \
        "el droide murió y la escena no volvió a ser el fondo"
    assert _pantalla_distinta(una, limpio, RENGLON * 2) == 0, \
        "el droide murió y en la pantalla se sigue viendo"
