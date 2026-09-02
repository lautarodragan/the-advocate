#!/usr/bin/env python3
"""Compila las páginas de evento de RM2k a algo que la ROM pueda ejecutar.

RM2k tiene unos 130 comandos de evento. La ROM entiende un puñado, y va a ir
entendiendo más. La regla que hace que eso sea seguro es una sola:

    **una página se emite sólo si todos sus comandos se pueden ejecutar.**

Si aparece uno que no modelamos, la página no se emite y el evento no hace
nada. Ejecutar la mitad de un script sería peor que no ejecutarlo: dejaría al
juego en un estado que no existe, y la comparación pixel a pixel no lo vería
porque la referencia haría exactamente lo mismo mal.

Los códigos de comando salen de tools/event_codes.py, que se genera desde
liblcf. Nunca de memoria: la primera versión del filtro de puertas los puso a
ojo y tres estaban mal.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- los comandos de RM2k que sabemos ejecutar ------------------------------
END = 10
CONTROL_SWITCHES = 10210
TELEPORT = 10810
TINT_SCREEN = 11030
WAIT = 11410
CHANGE_SAVE_ACCESS = 11930

# Comandos que se aceptan sin hacer nada, porque no hacer nada no se ve. Es el
# mismo criterio que el de las puertas, y hay que aplicarlo con la misma
# desconfianza: si el comando cambia algo que sí dibujamos, no va acá.
MESSAGE_OPTIONS = 10120

IGNORABLES = {
    CHANGE_SAVE_ACCESS,   # habilita o no el menú de guardar, que no existe
    MESSAGE_OPTIONS,      # dónde y cómo se dibuja la ventana de mensaje, que
                          # sin mensajes no se dibuja en ningún lado
}

# --- los opcodes que emitimos -----------------------------------------------
# Uno por comando, con los operandos ya resueltos: la ROM no vuelve a mirar el
# LCF ni conoce sus números.
OP_FIN      = 0x00
OP_SWITCH   = 0x01      # id (word), valor (byte)
OP_TELEPORT = 0x02      # mapa (byte), x (word), y (word)
OP_ESPERAR  = 0x03      # cuadros (byte)
OP_TINTE    = 0x04      # r, g, b, sat (byte cada uno)

# ControlSwitches: el primer parámetro dice de dónde salen los ids y el último
# qué hacer con ellos (liblcf, ControlSwitches::Operation).
SWITCH_UNICO, SWITCH_RANGO, SWITCH_INDIRECTO = 0, 1, 2
SWITCH_ON, SWITCH_OFF, SWITCH_TOGGLE = 0, 1, 2

# Un rango absurdo no se desenrolla: mejor no ejecutar la página que emitir
# miles de opcodes por una línea.
MAX_RANGO = 64

# RM2k mide las esperas en décimas de segundo.
CUADROS_POR_DECIMA = 6

TRIGGER_AUTOMATICO = 3

# El tinte de RM2k va de 0 a 200 con 100 como neutro. En la ROM se guarda tal
# cual y se aplica al subir la paleta.
TINTE_NEUTRO = 100


class NoSePuede(Exception):
    """Esta página tiene algo que la ROM todavía no sabe hacer."""


def compilar_pagina(page, indice_de_mapa):
    """Los comandos de una página como bytes, o None si no se puede.

    `indice_de_mapa` traduce el id de mapa de RM2k al índice en la tabla de la
    ROM, y devuelve None para los mapas que no entraron en el cartucho: un
    teletransporte hacia uno de ésos hace que la página no sea ejecutable, que
    es más honesto que saltar a cualquier lado.
    """
    try:
        return b"".join(_compilar(cmd, indice_de_mapa)
                        for cmd in page.commands) + bytes([OP_FIN])
    except NoSePuede:
        return None


def _compilar(cmd, indice_de_mapa):
    p = cmd.parameters

    if cmd.code == END or cmd.code in IGNORABLES:
        return b""

    if cmd.code == CONTROL_SWITCHES:
        if len(p) < 4 or p[0] not in (SWITCH_UNICO, SWITCH_RANGO):
            raise NoSePuede()       # por variable: hace falta variables
        if p[3] == SWITCH_TOGGLE:
            raise NoSePuede()       # invertir pide leer, y todavía no leemos
        desde, hasta = p[1], p[2]
        if hasta < desde or hasta - desde >= MAX_RANGO:
            raise NoSePuede()
        valor = 1 if p[3] == SWITCH_ON else 0
        out = b""
        for numero in range(desde, hasta + 1):
            out += bytes([OP_SWITCH, numero & 0xFF, numero >> 8, valor])
        return out

    if cmd.code == TELEPORT:
        if len(p) < 3:
            raise NoSePuede()
        destino = indice_de_mapa(p[0])
        if destino is None:
            raise NoSePuede()       # el mapa no entró en la ROM
        return bytes([OP_TELEPORT, destino,
                      p[1] & 0xFF, p[1] >> 8, p[2] & 0xFF, p[2] >> 8])

    if cmd.code == WAIT:
        if len(p) < 1:
            raise NoSePuede()
        cuadros = p[0] * CUADROS_POR_DECIMA
        if cuadros > 255:
            raise NoSePuede()       # una espera larga pide un contador de 16
        return bytes([OP_ESPERAR, cuadros])

    if cmd.code == TINT_SCREEN:
        if len(p) < 4:
            raise NoSePuede()
        if any(not 0 <= v <= 200 for v in p[:4]):
            raise NoSePuede()
        if p[3] != TINTE_NEUTRO:
            # La saturación no es un factor por canal sino una mezcla hacia el
            # gris, y todavía no la hacemos. Aceptar la página y no aplicarla
            # sería el error de siempre: la referencia haría lo mismo mal y la
            # comparación no lo vería.
            raise NoSePuede()
        # La duración se descarta: el tinte se aplica de una. La pantalla que
        # se compara está siempre asentada, así que el valor final es el que
        # importa; lo que se pierde es el degradé de un segundo.
        return bytes([OP_TINTE, p[0], p[1], p[2], p[3]])

    raise NoSePuede()


# --- ejecutar lo compilado --------------------------------------------------
#
# La ROM y la referencia corren el mismo bytecode. Tener el intérprete una sola
# vez del lado de Python no evita que haya dos implementaciones —la otra está en
# main.s— pero sí evita que haya dos *lenguajes*: lo que se ejecuta es el mismo
# programa, y las reglas de selección de página están escritas una vez acá y una
# vez allá, no una vez por llamador.


class Estado:
    """Lo que el intérprete recuerda entre páginas y entre mapas."""

    def __init__(self):
        self.switches = set()
        self.tinte = (TINTE_NEUTRO, TINTE_NEUTRO, TINTE_NEUTRO)
        self.salto = None       # (mapa, x, y) si una página pidió mudarse

    def encendido(self, numero):
        return numero in self.switches


def pagina_activa(paginas, evento, estado):
    """La página de número más alto del evento cuyas condiciones se cumplen.

    Es la regla de RM2k, y es la misma pasada que hace la ROM.
    """
    elegida = None
    for pagina in paginas:
        if pagina["evento"] != evento:
            continue
        if pagina["switch_a"] and not estado.encendido(pagina["switch_a"]):
            continue
        if pagina["switch_b"] and not estado.encendido(pagina["switch_b"]):
            continue
        elegida = pagina
    return elegida


def correr_automaticos(paginas, estado):
    """Corre las páginas automáticas activas del mapa. Devuelve el salto.

    El salto pendiente se borra al entrar, que es el `stz salto_hay` de la ROM:
    sin eso, el primer mapa que teletransporta dejaría el salto puesto y el
    mapa de destino saldría saltando de nuevo al mismo lado sin haber corrido
    ningún evento.
    """
    estado.salto = None
    for evento in sorted({p["evento"] for p in paginas}):
        pagina = pagina_activa(paginas, evento, estado)
        if pagina is None or pagina["trigger"] != TRIGGER_AUTOMATICO:
            continue
        if not pagina["codigo"]:
            continue
        ejecutar(pagina["codigo"], estado)
        if estado.salto:
            return estado.salto
    return None


def ejecutar(codigo, estado):
    """Un opcode por vuelta hasta el FIN, igual que correr_codigo en la ROM."""
    i = 0
    while i < len(codigo):
        op = codigo[i]
        if op == OP_FIN:
            return
        if op == OP_SWITCH:
            numero = codigo[i + 1] | (codigo[i + 2] << 8)
            if codigo[i + 3]:
                estado.switches.add(numero)
            else:
                estado.switches.discard(numero)
            i += 4
        elif op == OP_TELEPORT:
            estado.salto = (codigo[i + 1],
                            codigo[i + 2] | (codigo[i + 3] << 8),
                            codigo[i + 4] | (codigo[i + 5] << 8))
            return              # el resto de la página no corre
        elif op == OP_ESPERAR:
            i += 2              # la espera se saltea, igual que en la ROM
        elif op == OP_TINTE:
            estado.tinte = (codigo[i + 1], codigo[i + 2], codigo[i + 3])
            i += 5
        else:
            raise ValueError("opcode %d que no conozco" % op)


def tenir(palabra, tinte):
    """Un color de 15 bits escalado por el tinte.

    La misma cuenta con enteros que hace la consola con sus unidades de
    multiplicación y división: `canal * valor / 100`, truncado, topado en 31.
    Si acá se hiciera con flotantes o con corrimientos, la comparación pixel a
    pixel fallaría por el redondeo.
    """
    canales = (palabra & 0x1F, (palabra >> 5) & 0x1F, (palabra >> 10) & 0x1F)
    salida = 0
    for numero, (canal, valor) in enumerate(zip(canales, tinte)):
        salida |= min(31, canal * valor // 100) << (numero * 5)
    return salida


def paginas_del_mapa(game_map, indice_de_mapa):
    """Las páginas que la ROM necesita para resolver los eventos automáticos.

    Se emiten *todas* las páginas de un evento que tenga alguna automática, no
    sólo las automáticas: cuál queda activa depende de las condiciones de todas
    ellas, y una página posterior que no sea automática igual gana y le impide
    correr a la de más abajo.
    """
    salida = []
    for numero_evento, event in enumerate(game_map.events):
        if not any(page.trigger == TRIGGER_AUTOMATICO for page in event.pages):
            continue

        # Si alguna página del evento pide una condición que la ROM no sabe
        # evaluar —un ítem, un héroe en el grupo, un cronómetro— entonces no se
        # sabe cuál página está activa, y correr la equivocada es peor que no
        # correr ninguna. El evento entero queda afuera.
        if any(c not in ("switch_a", "switch_b")
               for page in event.pages for c in page.condition.active):
            continue

        grupo = []
        for numero_pagina, page in enumerate(event.pages):
            cond = page.condition
            codigo = None
            if page.trigger == TRIGGER_AUTOMATICO:
                codigo = compilar_pagina(page, indice_de_mapa)
            grupo.append({
                "evento": numero_evento,
                "pagina": numero_pagina,
                "trigger": page.trigger,
                "switch_a": cond.ids["switch_a"] if "switch_a" in cond.active else 0,
                "switch_b": cond.ids["switch_b"] if "switch_b" in cond.active else 0,
                "codigo": codigo,
            })

        # Un evento cuyas páginas automáticas no se pueden compilar no aporta
        # nada: sin código no hay nada que ejecutar y sólo ocuparía tabla.
        if any(p["codigo"] for p in grupo):
            salida += grupo
    return salida
