#!/usr/bin/env python3
"""Compila las páginas de evento de RM2k a algo que la ROM pueda ejecutar.

RM2k tiene unos 130 comandos de evento. La ROM entiende un puñado, y va a ir
entendiendo más. La regla que hace que eso sea seguro es una sola:

    **una página se emite sólo si todos sus comandos se pueden ejecutar.**

Si aparece uno que no modelamos, la página no se emite y el evento no hace
nada. Ejecutar la mitad de un script sería peor que no ejecutarlo: dejaría al
juego en un estado que no existe, y la comparación pixel a pixel no lo vería
porque la referencia haría exactamente lo mismo mal.

Los códigos de comando salen de tools/rpgmaker/event_codes.py, que se genera desde
liblcf. Nunca de memoria: la primera versión del filtro de puertas los puso a
ojo y tres estaban mal.
"""

import math
import os

from rpgmaker import rm2k

# Los números de los opcodes, sus largos y su layout. **No se declaran acá**:
# salen de `tools/protocol/events.toml`, que es de los dos lados —de esto y del
# intérprete en rom/src/interprete*.s— y de ninguno. Ver tools/protocol/README.md.
from port.event_opcodes import *   # noqa: F401,F403
from port.event_opcodes import OPCODE_SIZE, opcode_size  # noqa: F401

# --- los comandos de RM2k que sabemos ejecutar ------------------------------
END = 10
CONTROL_SWITCHES = 10210
TELEPORT = 10810
TINT_SCREEN = 11030
WAIT = 11410
CHANGE_SAVE_ACCESS = 11930
# Abrir el menú de guardar: la pantalla de ranuras, que congela el juego
# mientras se ve y no cuesta ningún tick. Ver `OP_SAVE`.
OPEN_SAVE_MENU = 11910
CHANGE_PARTY_MEMBERS = 10330
PLAY_BGM = 11510
# Apagar el tema que esté sonando, en tantos milisegundos.
# `Game_Interpreter::CommandFadeOutBGM` llama a `BgmFade` y devuelve **true**
# en el mismo cuadro: no bloquea a la página, así que no cuesta un cuadro ni
# mueve nada de lo que se compara.
FADE_OUT_BGM = 11520
MOVE_EVENT = 11330
# Plantar un evento en una celda. Es `CommandChangeEventLocation`: `MoveTo`,
# que pone la celda y deja el paso en cero, y nada más —la dirección sólo la
# toca RM2k3, y este juego es RM2k—. La cinemática de apertura lo usa seis
# veces para traer a Core, a Manta y al droide a escena.
CHANGE_EVENT_LOCATION = 10860
TRADE_EVENT_LOCATIONS = 10870
# Cambiar un tile del mapa por otro, en todas las celdas donde esté:
# `CommandTileSubstitution`. Es por **número de tile** y no por celda, y por
# eso en la ROM es una tabla chica que traduce bloques mientras se dibuja, y no
# una escritura sobre la grilla —que vive en la ROM y no se puede escribir—.
# Cuál bloque va a cuál lo resuelve el conversor: ver `Sustituciones`.
TILE_SUBSTITUTION = 11750
# El terreno de una celda a una variable: `CommandStoreTerrainID`. El terreno
# sale del tile de la capa de **abajo** —"RPG_RT always uses the terrain of the
# first lower tile"— así que la capa alta no lo cambia.
STORE_TERRAIN_ID = 10910
SHAKE_SCREEN = 11050
FLASH_SCREEN = 11040
# Correr la cámara sin el héroe: `CommandPanScreen`. De sus cuatro operaciones
# el juego usa dos —112 `pan` y 21 `reset`, y ni un `lock` ni un `unlock`— así
# que ésas son las que compilan.
PAN_SCREEN = 11060
PAN_FIJAR, PAN_SOLTAR, PAN_CORRER, PAN_VOLVER = 0, 1, 2, 3
# Las unidades de la cámara adentro de RM2k: `SCREEN_TILE_SIZE`, o sea 1/16 de
# pixel, con una celda de 16 pixeles valiendo 256. No es capricho quedarse con
# ellas: la velocidad 2 mueve la cámara **medio pixel por cuadro**, y en
# pixeles enteros eso no se puede contar.
PAN_UNIDAD = 256
PAN_ARRIBA, PAN_DERECHA, PAN_ABAJO, PAN_IZQUIERDA = 0, 1, 2, 3
# Hacia dónde corre la cámara con cada dirección, en (dx, dy) por unidad.
PAN_SENTIDO = {PAN_ARRIBA: (0, -1), PAN_DERECHA: (1, 0),
               PAN_ABAJO: (0, 1), PAN_IZQUIERDA: (-1, 0)}
PAN_VEL_MIN, PAN_VEL_MAX = 1, 6


def bytes_de_pan(operacion, direccion, distancia, velocidad, esperar):
    """El OP_PAN de un `PanScreen`, o None si no se puede.

    La dirección y la distancia se resuelven acá a un desplazamiento con signo
    en 1/16 de pixel, y la velocidad a su paso por cuadro: son cuentas fijas y
    la ROM no tiene por qué repetirlas. Lo que sí queda para la consola son los
    cuadros que la página espera.
    """
    dx, dy = (0, 0) if operacion == PAN_VOLVER else PAN_SENTIDO[direccion]
    dx *= distancia * PAN_UNIDAD
    dy *= distancia * PAN_UNIDAD
    if not (-0x8000 <= dx < 0x8000 and -0x8000 <= dy < 0x8000):
        return None
    return bytes([OP_PAN, operacion,
                  dx & 0xFF, (dx >> 8) & 0xFF,
                  dy & 0xFF, (dy >> 8) & 0xFF,
                  paso_de_pan(velocidad), 1 if esperar else 0])


def paso_de_pan(velocidad):
    """Cuánto corre la cámara por cuadro, en 1/16 de pixel.

    Es `data()->pan_speed = 2 << speed` de `Game_Player::StartPan`, con la
    velocidad topada entre 1 y 6 como hace `CommandPanScreen`. El juego usa de
    la 2 a la 6: de medio pixel por cuadro a ocho.
    """
    return 2 << min(PAN_VEL_MAX, max(PAN_VEL_MIN, velocidad))


LUGAR_CONSTANTE = 0         # p[1]: 0 es la celda escrita, 1 la lee de variables
LUGAR_POR_VARIABLE = 1      # y no hay una tercera: `CommandChangeEventLocation`
                            # tiene dos ramas y nada más

# Un cuadro de texto. RM2k emite un `ShowMessage` con la primera línea y un
# `ShowMessage_2` por cada una de las que siguen del mismo cuadro: son un solo
# comando —una ventana, una espera del jugador— y quien los cuente por separado
# mide cualquier cosa. Ya pasó: contándolos aparte, los cuadros de texto
# parecían destrabar tres páginas en vez de cincuenta y cinco.
SHOW_MESSAGE = 10110
SHOW_MESSAGE_2 = 20110

# Los códigos de escape que el texto de este juego usa: `\|` es una pausa y `\^`
# cierra el cuadro sin esperar a que el jugador apriete nada. Los dos son
# tiempo y no texto, y desde el 2026-09-13 los dos se hacen: viajan en la
# cabecera del cuadro —ver `mensaje_bytes`— y los leen igual el intérprete de
# la ROM y el de acá abajo.
#
# Se hacen de verdad y no borrándolos calladito, que era la tentación barata:
# con `\^` el cuadro se cierra solo, así que la ROM quedaría esperando un A que
# RM2k nunca pidió y la página entera pasaría a durar lo que tarde el jugador.
#
# **Cualquier otro escape sigue sin compilar**, y eso es a propósito: los tres
# `\V` de los eventos comunes —el valor de una variable metido en el texto—
# piden componer el texto al abrirlo, que es otra cosa. Dibujarlos como dos
# letras se vería.
ESCAPE = "\\"
ESCAPE_PAUSA = "|"
ESCAPE_CERRAR = "^"

# Lo que cuesta un `\|`. **No es un segundo**: es el `SetWaitForNonPrintable(61)`
# de `window_message.cpp`, con su comentario al lado —"Despite documentation
# saying 1 second, RPG_RT waits for 61 frames"—. Son 61 y no 60, y esa
# diferencia es exactamente la clase de número que no se puede poner de
# memoria.
CUADROS_DE_PAUSA = 61

# Cuántas pausas entran en la cabecera del cuadro. El máximo que usa el juego
# son tres seguidas (`\|\|\|\^`, dos veces, en el mapa 108); más que quince no
# entra en el nibble alto y la página no compila en vez de durar de menos.
PAUSAS_MAX = 15


def cola_de_escapes(lineas):
    r"""Las líneas sin su cola de escapes, cuántas pausas trae y si se cierra sola.

    En los 328 mapas los dos escapes aparecen **siempre como una cola al final
    de la última línea del cuadro** —medido: 40 cuadros, y ni uno con un escape
    en el medio ni en una línea que no sea la última—, así que eso es lo único
    que se acepta. Uno en el medio sigue sin compilar, que es lo honesto: con la
    ventana dibujándose de golpe, una pausa a mitad del texto no se puede
    modelar sin inventar cuánto texto había dibujado.

    La cola puede llevar espacios entre medio —pasa una sola vez, en el
    `RunDirectorScene` del mapa 98, que escribe `\| \| \| \^`— y se los come:
    un espacio al final de un renglón no dibuja un solo pixel, así que sacarlo
    da la misma pantalla de los dos lados.
    """
    lineas = list(lineas)
    pausas = 0
    autocierre = False
    if lineas:
        texto = lineas[-1]
        i = corte = len(texto)
        escapes = 0
        while i > 0:
            if i >= 2 and texto[i - 2] == ESCAPE \
                    and texto[i - 1] in (ESCAPE_PAUSA, ESCAPE_CERRAR):
                i -= 2
                corte = i
                escapes += 1
            elif texto[i - 1] == " ":
                i -= 1
            else:
                break
        if escapes:
            cola = texto[corte:]
            pausas = cola.count(ESCAPE + ESCAPE_PAUSA)
            autocierre = ESCAPE + ESCAPE_CERRAR in cola
            lineas[-1] = texto[:corte]
    if any(ESCAPE in t for t in lineas) or pausas > PAUSAS_MAX:
        raise NoSePuede()
    return tuple(lineas), pausas, autocierre


# Una ruta forzada de MoveEvent. Los parámetros son (a quién, frecuencia, un
# bitmask de repetición, si es salteable) y de ahí en adelante los comandos de
# la ruta, con los códigos de `rpg::MoveCommand::Code` de liblcf.
#
# Se aceptan los cuatro de girar, los cuatro de mover y la espera. Los de mover
# entraron últimos porque en RM2k el personaje camina celda por celda a lo largo
# de varios cuadros, y eso hay que compararlo *mientras* camina: comparar sólo
# dónde termina deja pasar el ciclo de animación entero. Un movimiento bloqueado
# se saltea, que es la decisión de modelo que comparten los dos lados —RM2k
# reintentaría para siempre y una prueba colgada no dice nada—.
RUTA_HEROE = 10001
RUTA_ESTE_EVENTO = 10005                    # "este evento", el dueño de la página
# Del 10002 al 10004 son los vehículos —barco, nave, avión—, que acá no existen.
RUTA_MIRAR = {12: 0, 13: 1, 14: 2, 15: 3}   # face_up/right/down/left
RUTA_MOVER = {n: n for n in range(8)}      # los cuatro move_* y las
                                           # cuatro diagonales: el código
                                           # de la orden **es** la
                                           # dirección. Ver RUTA_DIAGONALES
RUTA_ESPERAR = 23

# Cuánto cuesta un `wait` adentro de una ruta forzada. **No es un cuadro**: en
# RM2k es `SetMaxStopCountForWait`, que da `20 + (1 << (8 - frecuencia))`, y con
# la frecuencia 8 —la única que este repo acepta, ver `RUTA_FRECUENCIA`— son
# veinte. Acá valía uno, en la ROM y en la referencia a la vez, así que la
# comparación daba cero: es el mismo error que el hard light del tinte.
CUADROS_DE_ESPERA_DE_RUTA = 20

# La frecuencia con la que se camina una ruta forzada. Manda dos cosas: cuánto
# se espera entre una orden y la siguiente —`1 << (9 - frecuencia)` cuadros, y
# cero con 8— y cuánto dura un `wait`. Sólo se acepta la 8, que es la que usan
# 3463 de las 3509 rutas del juego y **todas** las de las páginas que compilan;
# con cualquier otra hay que modelar la espera entre órdenes, y desde el
# 2026-09-04 está: es el contador de parada de RM2k. Después de cada orden el
# personaje se queda quieto `max_stop_count` cuadros —`SetMaxStopCountForStep`
# tras un paso, `ForTurn` tras un giro, `ForWait` en un `wait`— y con la 8 los
# dos primeros dan cero, que es por lo que el modelo de "girar es gratis y los
# pasos van seguidos" era exacto sin saberlo. El juego usa la 2, la 3, la 4, la
# 7 y la 8; la 1 daría 256 cuadros tras cada paso, que no entran en el byte de
# espera de la ROM, y no la usa nadie: se rechaza.
RUTA_FRECUENCIA = 8
RUTA_FRECUENCIA_MIN = 2


def frecuencia_minima(frecuencia, ordenes, repite=False):
    """La frecuencia más baja por la que pasa una ruta con las órdenes 30 y 31.

    Es lo que decide si la ruta se puede compilar: con la frecuencia 1 la
    espera tras un paso son 256 cuadros y el byte de `ruta_tras_paso` no los
    tiene, así que una ruta que baje hasta ahí se rechaza entera.

    `ordenes` son códigos pelados, sin los operandos: los dos que llaman acá lo
    hacen con lo que devolvió `decodificar_ruta`, que ya los separó. No es lo
    mismo que una ruta compilada, donde la 34 arrastra un byte que hay que
    saltear.

    Con `repite` se recorren las órdenes nueve veces y no una. No es por las
    dudas: la frecuencia se topa en 8 y en 1, así que una ruta que se repita y
    baje más de lo que sube termina en 1 sí o sí, y nueve pasadas alcanzan para
    que llegue desde cualquier punto de partida.
    """
    actual = minima = frecuencia
    for _ in range(9 if repite else 1):
        for orden in ordenes:
            if orden == RUTA_FREC_MAS:
                actual = min(RUTA_FRECUENCIA, actual + 1)
            elif orden == RUTA_FREC_MENOS:
                actual = max(1, actual - 1)
            minima = min(minima, actual)
    return minima


def espera_tras_paso(frecuencia):
    """`GetMaxStopCountForStep`: los cuadros quieto después de un paso."""
    return 0 if frecuencia >= 8 else 1 << (9 - frecuencia)


def espera_tras_giro(frecuencia):
    """`GetMaxStopCountForTurn`: los cuadros quieto después de un giro. El
    `wait` son `CUADROS_DE_ESPERA_DE_RUTA` más esto."""
    return 0 if frecuencia >= 8 else 1 << (8 - frecuencia)


# Encarar al héroe: `GetDirectionToCharacter`. Manda el eje con más distancia,
# y en empate el vertical; sobre la misma celda mira abajo. Sólo sobre eventos:
# el héroe encarándose a sí mismo no lo usa ninguna página.
RUTA_ENCARAR_HEROE = 21

# Y moverse hacia el héroe: `move_towards_hero`. No es una orden nueva sino dos
# que ya existen pegadas —en `UpdateMoveRoute` es `TurnTowardCharacter(hero)` y
# después `Move(GetDirection())`—, o sea la 21 y un `move_*` en el mismo
# cuadro, con el mismo costo de paso que cualquier otro.
#
# Es la orden que más destraba de las que faltaban, y por lejos: medido sobre
# el juego entero, **+31 páginas**, contra +1 de las otras nueve juntas —al
# azar, huyendo del héroe, hacia adelante y los cinco giros en el lugar—. Se
# usa 267 veces en rutas forzadas de cuatro mapas, el 9, el 11, el 38 y el 166;
# el 9 es la pelea de los Lazer Teeth.
#
# Sólo sobre eventos, como la 21: el héroe yendo hacia sí mismo no lo pide
# ninguna ruta del juego —medido, cero— y no querría decir nada.
RUTA_HACIA_HEROE = 9

# Girar sin moverse —`turn_90_degree_right` y sus hermanas— sigue afuera, y no
# por costo: RM2k gira sobre la dirección que el personaje ya tenía, y para un
# evento que todavía no giró ésa es la de su página, que la ruta no lee.

# El salto: lo que hay entre las dos se suma como desplazamiento y el personaje
# lo hace de un tirón, en arco.
RUTA_SALTO_INICIO, RUTA_SALTO_FIN = 24, 25

# Atravesar paredes, y parar o seguir la animación de caminata.
RUTA_ATRAVESAR_ON, RUTA_ATRAVESAR_OFF = 36, 37
RUTA_ANIM_PARAR, RUTA_ANIM_SEGUIR = 38, 39
# Fijar y soltar hacia dónde mira —`lock_facing`—, y subir y bajar la
# velocidad de a uno, entre 1 y 6. Entraron el 2026-09-05 con las rutas
# propias de las páginas: los droides del mapa 2 las usan.
RUTA_FIJAR_DIR, RUTA_SOLTAR_DIR = 26, 27
RUTA_VEL_MAS, RUTA_VEL_MENOS = 28, 29
# Las cuatro de arriba, **sobre el héroe**, no se compilan: ver `traducir`.
# Sobre el héroe se tiran fijar y soltar la mirada; subir y bajar la velocidad
# **se hacen** desde el 2026-09-10 —el Tram Officer lo pide, y 170 rutas del
# juego—, y quedan: RM2k repone la frecuencia al terminar la ruta y la
# velocidad no, así que el pad camina después a la velocidad que dejó la ruta.
RUTA_HEROE_AFUERA = {RUTA_FIJAR_DIR, RUTA_SOLTAR_DIR}
# Subir y bajar la frecuencia a mitad de una ruta:
# `increase/decrease_movement_frequence`, que RM2k topa en 8 y en 1. Las usa
# **una sola ruta de todo el juego** —la que sacude a Manta en la escena del
# Emitter Room, que baja dos veces de 8 a 6— y sin ellas esa página no compila.
RUTA_FREC_MAS, RUTA_FREC_MENOS = 30, 31
# Cambiar el gráfico a mitad de una ruta. Es la **única orden con operando**:
# el bytecode lleva detrás el índice del CharSet en `Graficos`. Sólo sobre
# eventos; sobre el héroe no se compila, ver `traducir`.
RUTA_CAMBIAR_GRAFICO = 34

# Cuánto avanza un paso por cuadro según la velocidad, de 256 por celda: es el
# `1 << (1 + GetMoveSpeed())` de `Game_Character::UpdateMovement`. La 4 es la
# del héroe, 32 por cuadro, o sea dos pixeles y ocho cuadros por celda; la 3
# son dieciséis cuadros y la 2 treinta y dos, a medio pixel por cuadro.
PASO_POR_VELOCIDAD = (4, 8, 16, 32, 64, 128)

# Un salto dura lo que tarda `remaining_step` en bajar de 256 a 0 a
# `jump_speed[move_speed - 1]` por cuadro. Con la velocidad 4 —la de este
# juego— son 24 por cuadro, o sea once cuadros, y **no depende de la
# distancia**: saltar cinco celdas cuesta lo mismo que saltar en el lugar.
SALTO_PASO = 256
SALTO_VELOCIDAD = 24

# Las cuatro diagonales de ruta, cada una con sus dos componentes: primero la
# vertical y después la horizontal. Son `move_upright`, `move_downright`,
# `move_downleft` y `move_upleft`.
#
# Las caminan **sólo los eventos**. De las 26 rutas del juego que las usan
# ninguna es del héroe, así que la ROM no las tiene sobre él: caminar en
# diagonal con el pad no existe y darle un paso diagonal al héroe pediría
# duplicar `try_up` y sus tres hermanas para nada. El conversor rechaza la
# página que lo intente —ver MOVE_EVENT en `traducir`—, que es lo que impide
# que la ROM camine otra cosa en silencio.
RUTA_DIAGONALES = {4: (0, 1), 5: (2, 1), 6: (2, 3), 7: (0, 3)}


# Las órdenes de ruta que sabemos caminar, en un solo lugar.
RUTA_ORDENES = (set(RUTA_MIRAR) | set(RUTA_MOVER)
                | {RUTA_ESPERAR, RUTA_SALTO_INICIO, RUTA_SALTO_FIN,
                   RUTA_ATRAVESAR_ON, RUTA_ATRAVESAR_OFF,
                   RUTA_ANIM_PARAR, RUTA_ANIM_SEGUIR, RUTA_ENCARAR_HEROE,
                   RUTA_HACIA_HEROE,
                   RUTA_FIJAR_DIR, RUTA_SOLTAR_DIR, RUTA_VEL_MAS, RUTA_VEL_MENOS,
                   RUTA_FREC_MAS, RUTA_FREC_MENOS, RUTA_CAMBIAR_GRAFICO})


# Las órdenes que llevan algo detrás, y qué. Los números son los de
# `rpg::MoveCommand::Code` en liblcf.
RUTA_SWITCH_ON, RUTA_SWITCH_OFF = 32, 33
# RUTA_CAMBIAR_GRAFICO, la 34, está más arriba: la necesita `RUTA_ORDENES`.
# Subir y bajar la transparencia de a un octavo. Se aceptan y se tiran, como
# el sonido: la SNES no atenúa un sprite por partes sin color math, y las ocho
# rutas del juego que lo usan —las cuatro pantallas del mapa 2, que se atenúan
# mientras Manta hackea— son un fundido decorativo dentro de una escena de 78
# comandos que sin esto no compilaba. No cuestan cuadros: en `UpdateMoveRoute`
# van por la rama que no toca el contador de parada.
RUTA_TRANSPARENCIA = (40, 41)
# El sonido va adentro de la ruta y se acepta sin hacerlo —PlaySound sí suena
# desde el 2026-09-11, pero la ruta no tiene cómo pedirlo—: no se ve. Se tira al
# compilar, así que el bytecode sigue siendo un byte por orden y no cuesta ni
# un cuadro, que es lo que hace RM2k —no toca el contador de parada—.
RUTA_SONIDO = 35


def decodificar_ruta(parametros):
    """Las órdenes de una ruta forzada, con lo que cada una arrastre.

    Devuelve una lista de `(codigo, extras)`. Hace falta porque **la ruta no es
    una lista de códigos**: tres órdenes traen operandos metidos en el mismo
    chorro de enteros, y dos de ellas un texto —el nombre del CharSet, el del
    sonido— con un entero por letra. Recorrerla plana funcionaba mientras la
    primera orden desconocida cortara todo; en cuanto una de ésas se acepta, las
    letras del texto se leerían como órdenes.

    Los enteros vienen en el formato de RM2k: siete bits por entero y el bit 7
    dice que sigue. Es `Game_Interpreter_Shared::DecodeMove` y `DecodeInt`.

    Quedarse sin datos en el medio de un operando es una ruta rota y no
    compila; quedarse sin datos entre una orden y la siguiente es el final
    normal. La diferencia importa: confundirlas dejaba afuera 258 páginas que
    están perfectamente bien.
    """
    ordenes = []
    i = 0
    n = len(parametros)

    def entero():
        nonlocal i
        valor = 0
        while True:
            if i >= n:
                raise NoSePuede()
            x = parametros[i]
            i += 1
            valor = (valor << 7) | (x & 0x7F)
            if not x & 0x80:
                return valor

    def texto():
        nonlocal i
        largo = entero()
        if i + largo > n:
            raise NoSePuede()
        letras = "".join(chr(c & 0xFF) for c in parametros[i:i + largo])
        i += largo
        return letras

    while i < n:
        codigo = parametros[i]
        i += 1
        if codigo in (RUTA_SWITCH_ON, RUTA_SWITCH_OFF):
            extras = [entero()]
        elif codigo == RUTA_CAMBIAR_GRAFICO:
            extras = [texto(), entero()]
        elif codigo == RUTA_SONIDO:
            extras = [texto(), entero(), entero(), entero()]
        else:
            extras = []
        ordenes.append((codigo, extras))
    return ordenes

# "Esperá a que terminen las rutas". En RM2k espera a que **ninguna** quede
# pendiente, ni la del héroe ni la de ningún evento: es
# `Game_Map::IsAnyMovePending` en `Game_Interpreter::Update`, y no una espera
# por el evento que se acaba de mandar a caminar.
PROCEED_WITH_MOVEMENT = 11340

# Un destello sobre un personaje: `Game_Character::Flash`. Los parámetros son a
# quién, r, g y b de 0 a 31, la potencia, cuántas **décimas de segundo** dura, y
# si la página espera a que termine.
#
# Lo de las décimas no es un detalle: `CommandFlashSprite` hace
# `event->Flash(r, g, b, p, tenths * DEFAULT_FPS / 10)` y, si espera,
# `SetupWait(tenths)`, que es la misma espera del comando Wait. O sea que el
# tiempo sale gratis: es un OP_DELAY detrás.
FLASH_SPRITE = 11320

# Cómo consume el tiempo una ruta forzada, y es una decisión de modelo que los
# dos lados tienen que compartir: girar es instantáneo —se pasa al comando
# siguiente en el mismo cuadro—, esperar consume un cuadro, y moverse arranca un
# paso de una celda, que la ROM recorre a WALK_SPEED = 2 pixeles por cuadro como
# cualquier otro paso. Un movimiento bloqueado se saltea: la alternativa de RM2k
# es reintentar para siempre, y una prueba colgada no le dice nada a nadie.

# ChangePartyMembers: el primer parámetro dice si agrega o saca, el segundo de
# dónde sale el id del actor, y el tercero el id. De liblcf y de
# `Game_Interpreter::CommandChangePartyMember` en easyrpg-player.
GRUPO_AGREGAR, GRUPO_SACAR = 0, 1
GRUPO_ID_FIJO = 0
GRUPO_MAX = 4           # `Game_Party::AddActor` no agrega si ya hay cuatro

# Comandos que se aceptan sin hacer nada, porque no hacer nada no se ve. Es el
# mismo criterio que el de las puertas, y hay que aplicarlo con la misma
# desconfianza: si el comando cambia algo que sí dibujamos, no va acá.
MESSAGE_OPTIONS = 10120

IGNORABLES = {
    MESSAGE_OPTIONS,      # dónde y cómo se dibuja la ventana de mensaje, que
                          # sin mensajes no se dibuja en ningún lado
}

# Y esto es otra cosa, y la diferencia importa. Los de arriba no hacen nada
# porque no hay nada que hacer: el menú de guardar no existe y las ventanas de
# mensaje tampoco. Los de acá **sí** hacen algo y nosotros no lo hacemos; se
# aceptan igual porque lo que dejan sin hacer no aparece en la pantalla que se
# compara, y a cambio dejan correr páginas que si no quedarían afuera enteras.
#
# Es una deuda, no una equivalencia, y por eso está en una lista aparte con
# nombre propio: quien agregue algo acá tiene que poder decir qué se rompe.
#
# PlayBGM cambia el tema que suena. La ROM sube un solo banco de muestras al
# SPC700 al arrancar, así que cambiar de tema en caliente pide varios bancos en
# el cartucho y volver a subir en mitad del juego; es una feature de audio, no
# un comando más. Lo que se pierde: una página que cambie la música deja la que
# venía sonando. La pantalla no lo nota. Ver "Lo que falta" en README.md.
# WeatherEffects prende o apaga la lluvia. Se acepta sin dibujarla, y la deuda
# es de las grandes, así que va con todas las letras.
#
# **En modo 3 no queda capa donde ponerla.** BG1 son los ocho bits del mapa y
# BG2 la capa de encima más la ventana de mensaje; no hay una tercera. Con
# objetos tampoco: la lluvia de RM2k son hasta 100 hilos de 6x24 repartidos por
# toda la pantalla, y la consola dibuja 34 tiles de sprite por línea —un objeto
# de 32x32 se lleva cuatro—, así que una lluvia que cubra la pantalla revienta
# el presupuesto en casi todas las líneas. Nuestra propia referencia marca esas
# líneas como no comparables, así que la prueba dejaría de medir justo ahí.
#
# Y aunque entrara: cada gota va con su propia transparencia —`alpha = min((5 +
# fuerza) * t, 255)` en `Weather::DrawParticles`— y la consola tiene una sola
# operación de color para toda la pantalla, no una por objeto. Las posiciones
# además salen de un generador de números al azar que habría que reproducir.
#
# Lo que se pierde, medido sobre una captura de EasyRPG de la apertura: hilos
# diagonales finos de 24 pixeles de alto, que entre dos cuadros seguidos mueven
# el 3,9% de la pantalla. Se ven sobre todo en las zonas oscuras.
#
# Se acepta porque **es lo único que traba la cinemática de apertura**. Sin
# esto la ROM no arranca la historia; con esto arranca, sin lluvia.
#
# **Desde el 2026-09-11 la lluvia se dibuja**: ver OP_WEATHER. La nieve, la
# niebla y la tormenta de arena siguen sin dibujarse, y apagan la lluvia.
WEATHER_EFFECTS = 11070

# PlaySound toca un efecto: una puerta, un golpe, el Insta-Shave de Talan.
# Suena desde el 2026-09-11 (ver OP_SOUND); hasta ahí se aceptaba sin
# tocarlo, y era la deuda más barata de todas las que hay acá: **no se
# ve**. La pantalla que se compara es exactamente la misma con y sin sonido.
#
# Lo que costaba hacerlo era la ARAM: la ROM sube **un solo banco de muestras**
# al SPC700 al arrancar. Se resolvió metiendo los efectos en ese mismo banco,
# con lo que la música deja libre; este juego usa 116 efectos distintos y en
# la demo entran 5, así que el resto se sigue aceptando callado.
#
# Cuánto destraba, medido y no supuesto: **+10 páginas de tecla de acción y +6
# automáticas**. Es mucho menos de lo que parece: `PlaySound` es el comando que
# corta *primero* en 349 páginas, pero casi todas están cortadas además por otra
# cosa. Es exactamente la trampa que la tabla de orden de `README.md` ya tiene
# anotada, y vale la pena que quede escrita también acá.
#
# Lo que sí destraba es concreto: el Insta-Shave del pad de Talan toca cuatro
# efectos antes de su mensaje, así que sin esto esa rama no corre.
#
# **Desde el 2026-09-11 suenan**: ver OP_SOUND.
PLAY_SOUND = 11550

# `ShowBattleAnimation` sobre el mapa —`CommandShowBattleAnimation`, 11210—:
# la animación de batalla se dibuja encima del personaje, con sus propios
# gráficos y su propio sonido. La ROM no lleva animaciones de batalla, así que
# la orden se acepta y no se hace nada: lo que se pierde es el dibujo. En la
# apertura es la explosión con la que CORE rompe la puerta de seguridad del
# mapa 2; la página que la pide sigue con un `FlashScreen`, que sí se ve, y con
# el mensaje "CORE performs FURY PUNCH!". Con la orden cortando, esa página no
# corría y el juego se quedaba sin el pasillo al ascensor.
SHOW_BATTLE_ANIMATION = 11210

# `ChangeItems` (10320) y `ChangeGold` (10310): dan y quitan objetos y dinero.
# Se aceptan sin hacerlos porque **nadie lee el inventario**: no hay menú, no
# hay batallas, y `ConditionalBranch` sólo sabe preguntar por switches. El día
# que exista una de esas tres cosas, esto vuelve a la lista de lo que corta.
#
# Cuánto destraba, medido: `ChangeItems` +5 páginas automáticas y `ChangeGold`
# +1. Lo que importa no es el número sino cuál: la página del "1 year earlier"
# —mapa 4, evento 1, página 3— arranca con siete `ChangeItems` seguidos, y es
# la que continúa la historia después del recuerdo de CORE y MANTA.
CHANGE_GOLD = 10310
CHANGE_ITEMS = 10320

# `ShowPicture` (11110), `MovePicture` (11120) y `ErasePicture` (11130): una
# imagen encima de todo, movida y borrada.
#
# **Desde el 2026-09-12 se hace una**: el cartel del "One year previously", y
# cualquier otro que entre en el mismo molde. Ver `Imagenes`, OP_PICTURE y
# workflow/tasks/done/show-picture-phase-1.md. Los que no entran —los 27 de
# los 34 que el juego tiene— se siguen aceptando sin hacerse, y lo que sigue
# vale para ésos.
#
# En modo 3 las dos capas de fondo están ocupadas por el mapa, así que una
# imagen encima pide una decisión de video, no un opcode más. Pero hay un
# atajo que este juego habilita y conviene tener anotado: **las cinemáticas
# tiñen a negro antes de mostrar el cartel**, o sea que el mapa es invisible
# mientras dura y la imagen podría tomar prestada una capa entera en vez de
# componerse encima. Eso no sirve para los sistemas custom del juego, que las
# usan sobre el mapa, pero sí para los carteles.
#
# Cuánto destraba, medido: +8 páginas automáticas los tres juntos. La que
# importa es la del "1 year earlier", donde la imagen es el cartel de "One
# year previous": aceptándola, el jugador ve negro donde va el cartel y la
# escena sigue hasta Talan's Pad.
SHOW_PICTURE = 11110
MOVE_PICTURE = 11120
ERASE_PICTURE = 11130

# Los dos códigos de comando de las variables, que se usan más abajo y en la
# lista de acá: ver "las variables de RM2k".
CONTROL_VARS = 10220
CALL_EVENT = 12330
# Y la tienda: `OpenShop`. Cuarenta y tres en el juego, ninguna con las ramas
# de "compró"/"no compró". Del 2026-09-10 a la noche al 11 se aceptó sin abrir
# nada, para que los vendedores de Lashe City Interiors —EV0021 y EV0023—
# contestaran; desde el 11 abre la tienda de verdad: ver OP_SHOP.
OPEN_SHOP = 10720

# Y la posada: `ShowInn`, con sus tres ramas. El juego tiene 18 páginas con
# una y ninguna usa las ramas —medido el 2026-09-20—, así que se compila el
# comando solo: ver `_compilar_posada`.
SHOW_INN = 10730
INN_STAY, INN_NO_STAY, INN_END = 20730, 20731, 20732

# `ChangeSystemBGM` (10660): cambia el tema que el sistema usa para pelear,
# para ganar, para la posada. El juego lo usa **130 veces en 25 mapas** y
# siempre de a pares —el 0 y el 1, o sea `battle_music` y `battle_end_music`—:
# cada zona tiene su música de pelea.
#
# Se acepta sin hacerlo, y la deuda es concreta: **una pelea en esos mapas
# suena con el tema del LDB en vez del de la zona**. No es "no suena": suena el
# que `AUDIO_BATALLA` trae de la base, que es el que el paquete de audio del
# mapa ya lleva, así que nada queda mudo y nada pide una muestra que no esté.
# Y no cambia un pixel, así que la tanda mide lo mismo con esto y sin esto.
#
# Cuánto destraba, medido sobre las 5603 páginas disparables del juego:
# **+24**. Hacerlo de verdad no es este comando sino una feature de audio: el
# tema del sistema pasaría a ser estado que viaja en la partida, y los temas
# que nombran esas 130 apariciones tendrían que entrar en el paquete de audio
# de sus mapas. Hoy el peor paquete son 54945 de 63831 B de ARAM; agregarle un
# tema de pelea a veinticinco mapas pide lugar en esos paquetes: ver
# workflow/decisiones/un-solo-banco-de-muestras.md.
CHANGE_SYSTEM_BGM = 10660

# `ChangeHeroTitle` (10620): el "título" de un actor, que en RM2k es el texto
# que la pantalla de estado muestra debajo del nombre. Ocho apariciones en todo
# el juego y **todas sobre Talan**: "Fugitive", "Limping", "Defender".
#
# Se acepta sin hacerlo porque **este port no muestra el título en ninguna
# parte**: el conversor emite del actor su nombre y su equipo inicial, y nada
# más —no hay pantalla de estado—. O sea que hacerlo de verdad no es este
# comando sino esa pantalla, y mientras no exista el dato no tendría dónde
# verse. Guardarlo igual sería estado que viaja en la partida sin que nadie lo
# lea.
#
# Lo que destraba: **+5 páginas**, y entre ellas la del `RunDirectorScene` del
# mapa 19, que es automática. Con ella sin compilar la escena del director no
# arrancaba: taro llegó a la oficina el 2026-09-13, el discurso corrió entero,
# el teletransporte de vuelta funcionó, y ahí no pasaba nada más.
CHANGE_HERO_TITLE = 10620

# `ChangeEncounterSteps` (11740): cada cuántos pasos hay un encuentro al azar.
# Diecinueve apariciones en nueve mapas, y trece de ellas lo ponen en **cero**,
# que en RM2k es apagarlos.
#
# Se acepta sin hacerlo porque **no hay encuentros al azar**: el juego los ata
# al mapa y a las *áreas* —nodos del árbol sin `.lmu`, con un rectángulo y su
# propia lista de tropas— y este port no lee ni una cosa ni la otra. O sea que
# acá no hay una deuda parcial: el número que el comando guarda no lo lee
# nadie, y el día que los encuentros existan este renglón tiene que salir de
# esta lista **junto con** ellos, no antes.
#
# Cuánto destraba, medido: **+14 páginas**. Y **no se acepta**, que es la parte
# que hay que leer entera, porque el número solo diría lo contrario:
#
# * Las trece que lo ponen en cero están **apagando algo que todavía no pasa**.
#   Lo que se ganaría es lo que esas páginas hacen además.
# * Está en nueve mapas —el 66, el 81, el 121, del 152 al 156 y el 165— y
#   ninguno está cerca de los primeros diez minutos. **Esta razón caducó el
#   2026-09-25**: el objetivo pasó a ser el juego entero, así que la próxima
#   vez que se mire esta lista hay que ver si lo demás alcanza para el no.
# * Y se midió lo que cuesta: aceptándolo, la automática
#   `DaliaGoingToTasgarde` del mapa 66 pasa a compilar, y esa página desarma el
#   grupo y le fuerza al héroe una ruta de sesenta pasos. El mapa 66 era el
#   de una ROM de prueba, y con la cinemática despierta se caían dos casos de
#   `test_condicional.py`. **Ese freno se fue el 2026-09-17**: la ventana pasó
#   a ser obligatoria, el 66 no la puede llevar, y las pruebas se mudaron a
#   otros mapas. Lo que queda es el primer punto.
#
# O sea: `ChangeEncounterSteps` entra en `ACEPTADOS_SIN_HACER` el día que los
# encuentros al azar existan, **junto con** ellos y no antes: el juego los ata al mapa y a las
# *áreas*, que son nodos del árbol sin `.lmu`, con un rectángulo y su propia
# lista de tropas, y este port no lee ni una cosa ni la otra.

ACEPTADOS_SIN_HACER = {
    # CallEvent **ya no está acá**: desde el 2026-09-12 se compila en línea,
    # ver `_compilar_llamada`. Lo que quedó de aquello es que una llamada cuyo
    # blanco no compila se saltea igual que antes, y eso se decide ahí adentro
    # y no en esta lista: el comando en sí ya no es una deuda entera.
    SHOW_PICTURE,
    MOVE_PICTURE,
    ERASE_PICTURE,
    CHANGE_SYSTEM_BGM,
    CHANGE_HERO_TITLE,
}


class Temas:
    """Los temas que los `PlayBGM` del juego piden, numerados en el orden en
    que aparecen.

    Es el hermano de `Mensajes`: el bytecode lleva un índice y no un nombre, y
    quien resuelve el índice es el conversor. La ROM lleva **los primeros
    `TEMA_TOTAL`**, que son los que entraron en la ARAM: las muestras las
    comparten todos y el banco compartido vive en los 64 KB del SPC700, que se
    suben una sola vez al arrancar. Un índice más alto es un tema que no entró
    y no suena.

    Numerarlos a todos y no sólo a los que entran es lo que hace que el
    bytecode no dependa de cuáles se eligieron. Hasta el 2026-09-06 entraba uno
    solo y esto ya estaba escrito así; el día que entraron cuatro no hubo que
    recompilar nada distinto.
    """

    def __init__(self):
        self.nombres = []
        # Y los efectos de `PlaySound`, de la misma manera: cada combinación
        # de efecto, volumen, tempo y paneo es una entrada, y el bytecode lleva
        # su índice. Viven acá y no aparte porque es lo que el conversor y la
        # referencia ya se pasan de compilación en compilación.
        self.sonidos = []
        # Y quién pide qué: el conversor pone en `mapa` el índice del mapa que
        # está compilando, y cada tema y cada efecto quedan anotados en el
        # suyo, en el orden en que aparecen. Es lo que arma el paquete de
        # audio de cada mapa: ver `paquete_cargar` en rom/src/paquete_de_audio.s.
        # Y a qué mapas de la ROM salta cada uno —`destinos`, índices de la
        # tabla de mapas—, que es de dónde sale qué tema puede venir sonando
        # al cargar un paquete: ver `temas_heredados` en snes_convert.py.
        self.mapa = None
        self.por_mapa = {}

    def _anotar(self, que, valor):
        if self.mapa is None:
            return
        lista = self.por_mapa.setdefault(
            self.mapa, {"temas": [], "sonidos": [], "destinos": []})[que]
        if valor not in lista:
            lista.append(valor)

    def indice(self, nombre):
        if nombre not in self.nombres:
            self.nombres.append(nombre)
        self._anotar("temas", self.nombres.index(nombre))
        return self.nombres.index(nombre)

    def destino(self, mapa):
        self._anotar("destinos", mapa)

    def sonido(self, nombre, volumen, tempo, balance):
        clave = (nombre, volumen, tempo, balance)
        if clave not in self.sonidos:
            self.sonidos.append(clave)
        self._anotar("sonidos", nombre)
        return self.sonidos.index(clave)

class Graficos:
    """Los gráficos a los que las rutas cambian con la orden 34, numerados en
    el orden en que aparecen.

    Hermano de `Temas` y de `Mensajes`, con una diferencia que importa: es **por
    mapa**. Lo que la ROM necesita de un gráfico —sus doce poses y su paleta—
    vive en el banco de sprites, y el banco es de cada mapa; dos mapas que
    cambien al mismo CharSet lo numeran cada uno por su cuenta.

    El bytecode lleva el índice y no el nombre, como con los temas y los
    mapas: quien lo resuelve es el conversor, y la ROM no vuelve a mirar el
    LCF.

    `asociaciones` rompe a medias lo de "por mapa", y hay que entender por qué:
    son los gráficos que `ChangeSpriteAssociation` le puede poner a un actor, y
    ése **sobrevive al cambio de mapa** —todas las veces que el juego lo usa,
    el comando va pegado a un teletransporte y lo que se ve es el gráfico del
    otro lado—. O sea que su índice no puede significar una cosa acá y otra
    allá. Se resuelve reservándoles las primeras ranuras de la tabla de
    **todos** los mapas de la ROM, en el mismo orden: ver `asociaciones_de`,
    que es la pasada previa que las junta, y `Imagenes.elegir`, que es el
    mismo patrón.
    """

    def __init__(self, asociaciones=()):
        self.pares = list(asociaciones)

    def indice(self, charset, index):
        par = (charset, index)
        if par not in self.pares:
            self.pares.append(par)
        return self.pares.index(par)


# `ChangeSpriteAssociation`: le cambia el CharSet a un **actor**, no a un
# evento. En RM2k es `actor->SetSprite(...)` más un `ResetGraphic()` sobre
# `Game_Player`, así que se ve enseguida si ese actor está liderando y queda
# guardado para cuando lidere.
#
# Los parámetros son [actor, índice dentro del CharSet, transparente] y el
# nombre va en `string`. Un cuarto parámetro es el bitfield que dice cuáles de
# los tres salen de una variable —`ValueOrVariableBitfield(com, 3, ...)`—: este
# juego no lo usa en ninguna de sus 212 apariciones y acá se rechaza, que es lo
# de siempre.
CHANGE_SPRITE_ASSOCIATION = 10630


def asociaciones_de(game_maps, extra=()):
    """Los (CharSet, índice) que algún `ChangeSpriteAssociation` nombra.

    Es la pasada previa de `Graficos`: le reserva a cada uno la misma ranura en
    la tabla de gráficos de todos los mapas de la ROM, porque el gráfico que el
    comando le pone a un actor **cruza el teletransporte** y su índice tiene que
    querer decir lo mismo de los dos lados del salto.

    Se miran **todas** las páginas y no sólo las que compilan, a propósito: si
    dependiera de qué compila, la lista dependería de si la ROM lleva ventana de
    mensaje —igual que `lideres_posibles`— y las dos pasadas del conversor
    numerarían distinto. Reservar una ranura de más cuesta las doce poses de un
    CharSet en el banco de sprites y nada más.

    En este juego son dos pares —`Future3:0` y `BLVehicles:2`— y sólo si la ROM
    lleva alguno de los mapas 49, 50, 52 o 54, que son la persecución en auto.

    `extra` son los comandos de las páginas de prueba, que van detrás.
    """
    pares = []
    comandos = [cmd for game_map in game_maps for evento in game_map.events
                for page in evento.pages for cmd in page.commands]
    for cmd in comandos + list(extra):
        if cmd.code != CHANGE_SPRITE_ASSOCIATION:
            continue
        p = list(cmd.parameters)
        if len(p) != 3 or p[2]:
            continue        # los que `_compilar` va a rechazar
        par = (cmd.string, p[1])
        if par not in pares:
            pares.append(par)
    return pares


# --- los opcodes que emitimos -----------------------------------------------
# Uno por comando, con los operandos ya resueltos: la ROM no vuelve a mirar el
# LCF ni conoce sus números.
#
# **Los números y los layouts están en `tools/protocol/events.toml`**, no acá: esto
# es lo que hay que saber de cada uno y que una declaración no puede decir.
#
# OP_SWITCH: id (word), valor (byte)
#
# OP_TELEPORT: mapa (word), x (word), y (word). El mapa iba en un
#     byte y eso le ponía **al formato** un techo de 256
#     mapas: el juego tiene 328. Hoy no molesta —las
#     demos llevan 29— pero era un techo escrito, y
#     sacarlo cuando todavía es barato es más barato que
#     sacarlo el día que una demo se pase.
#
# OP_DELAY: cuadros (word): la cinemática espera seis
#     segundos, o sea 360, y no entran en un byte
#
# OP_TINT: r, g, b, sat (byte cada uno)
#
# OP_PARTY: operación (byte), actor (byte)
#
# OP_ROUTE: blanco (byte), frecuencia (byte), cuántos comandos (byte), y los
#     comandos. El blanco es 0 para el héroe, y si no el
#     índice del evento en la tabla del mapa más uno.
#
#     **El índice no es el id de RM2k.** 39 mapas de este
#     juego tienen huecos en la numeración de eventos, así
#     que una ruta apuntada al id 8 movería al que esté
#     octavo en la lista, que puede ser cualquier otro. Lo
#     traduce el conversor, que es el único que ve el mapa.
#
# OP_MESSAGE: desplazamiento (word) dentro del bloque `mensajes`:
#     abre esa ventana y bloquea la página hasta que el
#     jugador apriete A
#
# OP_WAIT_ROUTES: sin operandos: la página no sigue hasta que no quede
#     ninguna ruta forzada corriendo
#
# OP_FLASH: blanco (byte), r, g, b, potencia (byte cada uno, de 0
#     a 31) y cuántos cuadros dura (byte)
#
# OP_PLACE: blanco (byte, como en OP_ROUTE: el índice del evento
#     más uno), x (word), y (word). Planta al evento en la
#     celda y le corta el paso en curso; no toca su ruta ni
#     hacia dónde mira, que es lo que hace `MoveTo`.
#
# OP_SWAP: dos blancos (byte cada uno, como en OP_PLACE): los
#     dos eventos se cambian de celda entre sí, cada uno
#     con `MoveTo`, que es `CommandTradeEventLocations`.
#
# OP_SHAKE: fuerza (byte), velocidad (byte), cuadros (word):
#     `ShakeOnce`. Con cero cuadros es `ShakeEnd`: la
#     pantalla vuelve a su lugar. La cuenta es `sacudida_tick` en rom/src/camara.s.
#
# OP_FLASH_SCREEN: r, g, b, fuerza (byte cada uno, 0..31) y cuadros
#     (byte): `FlashOnce`, el destello de la pantalla
#     entera. La cuenta es `destello_tick` en rom/src/destello_de_pantalla.s.
#
# OP_IF: tipo (byte), operando (word), polaridad (byte),
#     destino (word):
#     `ConditionalBranch` con condición de switch. Si no se
#     cumple, el cursor salta al destino, que es el `else`
#     o el `end` de esa misma rama. La polaridad es la de
#     RM2k al revés y a propósito: allá `parameters[2] == 0`
#     quiere decir "tiene que estar prendido", así que acá
#     0 es "prendido" y 1 es "apagado", igual que el dato.
#
#     El destino es **absoluto** dentro de la página, no
#     relativo: el cursor de la ROM es un índice de 16 bits
#     en el mismo array, así que asignarlo es todo el salto.
#
# OP_GOTO: destino (word): el salto sin condición que se emite
#     donde estaba el `else`, para que la rama de arriba se
#     saltee la de abajo.
#
# OP_SAVE: sin operandos: la partida a la SRAM del cartucho.
#     Es `OpenSaveMenu`, pero sin menú: hay una sola ranura
#     y el evento la pisa. Lo que se guarda lo dice
#     `partida_tabla` en rom/src/banco1.s, que es el único lugar donde
#     está escrito. No cuesta un cuadro: en RM2k el menú
#     bloquea, y acá no hay nada que mirar.
#
# OP_GOLD: signo (byte: 0 suma, 1 resta) y monto de 24 bits. Es
#     `ChangeGold`, y va en tres bytes porque el tope de
#     RM2k son 999999 y el juego usa el valor entero: hay un
#     comando que da exactamente eso.
#
#     La ROM recorta a [0, ORO_MAX] como
#     `Game_Party::GainGold`. Todavía no hay dónde mostrarlo
#     —el menú no existe— pero sí quién lo pregunta: la rama
#     de oro de `ConditionalBranch`.
#
# OP_CHOICE: cuántas opciones (byte), qué hace cancelar (byte), y
#     después una entrada por opción: el cuadro de texto
#     (word) y el destino (word). Es `ShowChoice`.
#
#     **Un cuadro de texto por opción, no uno solo.** Los
#     cuadros llevan las mismas líneas y se diferencian en
#     dónde está el cursor, así que mover el cursor es
#     recomponer la ventana con otro desplazamiento y no
#     dibujar nada nuevo. Cuesta unas decenas de bytes por
#     elección y ahorra un tile de sprite, una paleta y todo
#     el código de dibujarlo: en la consola no hay dónde
#     poner un cursor que no sea un sprite, y los sprites de
#     este mapa ya están repartidos entre los personajes.
#
#     El destino es absoluto dentro de la página, como el de
#     OP_IF, y el cuerpo de cada opción termina en un OP_GOTO
#     al final de la elección.
#
# OP_PAN: operación (byte: PAN_CORRER o PAN_VOLVER), cuánto se
#     corre el destino en x y en y (word con signo cada
#     uno, en 1/16 de pixel), el paso por cuadro (byte) y
#     si la página espera (byte).
#
#     La dirección y la distancia vienen resueltas a un
#     desplazamiento con signo, y la velocidad a su paso:
#     son cuentas fijas y el conversor las hace una vez.
#     Lo que **no** se puede resolver acá son los cuadros
#     que la página espera: salen de lo que le falta al pan
#     cuando el comando corre, y con uno todavía en curso
#     eso no es lo que este comando pidió. Ver `GetPanWait`
#     y el comentario de `CommandPanScreen` sobre el
#     máximo.
#
# OP_FADE_BGM: paso (word): cuánto baja por cuadro el volumen del
#     tema, en 1/65536 de lo que estuviera sonando.
#
#     Va el paso y no los milisegundos que trae RM2k
#     porque el 65816 no divide sin hardware y la cuenta
#     es siempre la misma: `ceil(65536 / cuadros)`. Es la
#     misma clase de número que el índice de mapa de un
#     teletransporte —resuelto por el conversor para que
#     la ROM no lo vuelva a mirar—, y lo hace
#     `paso_de_fundido`.
#
# OP_BGM: el índice del tema en `Temas` (byte). La ROM toca
#     los que llevó —los primeros `TEMA_TOTAL`— y con
#     cualquier otro no hace nada. Ver `Temas`.
#
# OP_TIMER: operación (byte), segundos (word), visible (byte).
#     Los cinco bytes son fijos aunque cada operación use
#     dos: así el intérprete lo saltea sin mirar cuál es,
#     que es lo que hace `recorrer_codigo` del conversor.

# El operando es un desplazamiento y no un texto, y eso es lo que hace que
# entre. Una página de mensaje ya compuesta son ~240 tiles de 4bpp, o sea
# 7,5 KB, y emitir una por cada cuadro de texto del juego no entra ni cerca en
# un cartucho de 256 KB: los 2895 cuadros serían 21 MB. Lo que se emite es el
# texto —un byte por letra— y lo compone el 65816 en caliente, con la fuente en
# la ROM, que es la salida de FF6. Los mismos 2895 cuadros son 180 KB de texto,
# y un mapa solo bastante menos.
#
# Dieciséis bits alcanzan porque el bloque tiene que entrar en un banco de
# 32 KB: lo lee `lda [msg_ptr], y` con un puntero que se incrementa de a un
# byte y **no** arrastra al byte de banco, así que `bloque()` lo emite con
# `.bloque`, que rellena para que no cruce. Si algún día no entra, lo que hay
# que agrandar es el puntero, no el operando.

# TimerOperation. Los parámetros son (operación, de dónde salen los segundos,
# segundos, visible, en batalla): liblcf, TimerOperation::Operation.
TIMER_OPERATION = 10230
TIMER_PONER, TIMER_ARRANCAR, TIMER_PARAR = 0, 1, 2
TIMER_SEGUNDOS_FIJOS = 0        # el otro valor los saca de una variable
# `Game_Party::SetTimer` guarda `segundos * 60 + 59`, no `segundos * 60`. Los
# 59 de más son lo que hace que el primer segundo se vea entero: sin ellos el
# cronómetro mostraría el valor pedido durante un solo cuadro.
TIMER_CUADROS_DE_MAS = 59

# ControlSwitches: el primer parámetro dice de dónde salen los ids y el último
# qué hacer con ellos (liblcf, ControlSwitches::Operation).
SWITCH_UNICO, SWITCH_RANGO, SWITCH_INDIRECTO = 0, 1, 2
SWITCH_ON, SWITCH_OFF, SWITCH_TOGGLE = 0, 1, 2

# Un rango absurdo no se desenrolla: mejor no ejecutar la página que emitir
# miles de opcodes por una línea.
MAX_RANGO = 64

# RM2k mide las esperas en décimas de segundo.
CUADROS_POR_DECIMA = 6
CUADROS_POR_SEGUNDO = 60        # DEFAULT_FPS: es con lo que cuenta el cronómetro

# Un paso son dieciséis pixeles a WALK_SPEED = 2 por cuadro.
CELDA_PX = 16
WALK_SPEED = 2
CUADROS_POR_CELDA = CELDA_PX // WALK_SPEED

# --- el fundido de los teletransportes -------------------------------------
#
# RM2k funde a negro y vuelve en **cada** teletransporte, cambie de mapa o no:
# en `Scene_Map::UpdateStage2` de easyrpg-player el `TeleportParams` sale
# siempre con `erase_screen = true`, y `Scene_Map::StartPendingTeleport` pide
# la transición que diga la base. La de A Blurred Line es `transition_out = 0`
# y `transition_in = 0`, que en la tabla de `Game_System::GetTransition` son
# `TransitionFadeOut` y `TransitionFadeIn`, y `Transition::GetDefaultFrames`
# les da **35 cuadros** a cada una. Mientras la transición corre el juego está
# congelado: `Scene::MainFunction` ve `IsAsyncPending()` y llama a
# `Player::Update(false)`, que no actualiza la escena.
FUNDIDO_CUADROS = 35
FUNDIDO_TOTAL = FUNDIDO_CUADROS * 2

# De esos 35, la rampa son 24 y los otros 11 son negro liso. La consola no
# puede fundir de otra manera: el brillo maestro de INIDISP tiene dieciséis
# pasos y nada más, así que estirar la rampa sobre los 35 cuadros no da un
# fundido más fino, sólo repite pasos. Y el negro del final no es relleno: **es
# donde se carga el mapa**. La carga escribe VRAM y CGRAM por DMA y cuesta seis
# o siete cuadros, que hasta ahora la referencia no modelaba y dejaban a los
# dos lados desalineados para siempre después de un salto; adentro del negro no
# se ven y no corren el reloj, porque el fundido se cuenta en cuadros de
# hardware y no en vueltas del lazo. Entre que el mapa se carga —cuadro 24— y
# que la rampa de vuelta sale del cero —cuadro 47— hay 23 cuadros de margen.
FUNDIDO_RAMPA = 24
FUNDIDO_NEGRO = FUNDIDO_CUADROS - FUNDIDO_RAMPA
BRILLO_MAX = 15


def paso_de_fundido(milisegundos):
    """Cuánto baja por cuadro el volumen del tema, en 1/65536.

    RM2k mide el `FadeOutBGM` en milisegundos y la ROM cuenta cuadros, así que
    la conversión se hace acá una sola vez: el 65816 no divide sin pedírselo al
    hardware, y el divisor del hardware es de ocho bits —los 5000 ms de la
    puerta del mapa 3 son 300 cuadros y no entran—.

    El nivel arranca en 65535 y baja de a `paso`; se redondea para arriba para
    que el fundido termine **dentro** de los cuadros que pide y no uno después.
    """
    cuadros = max(1, milisegundos * CUADROS_POR_SEGUNDO // 1000)
    return min(0xFFFF, -(-0x10000 // cuadros))


def rampa_de_fundido():
    """El brillo de INIDISP en cada cuadro de la rampa, de negro a lleno.

    Es una recta redondeada sobre los dieciséis pasos que tiene el brillo
    maestro. La ROM no la calcula: el conversor la emite en `mapdata.inc` como
    `fundido_rampa`, para que el número viva en un solo lado.
    """
    ultimo = FUNDIDO_RAMPA - 1
    return [(BRILLO_MAX * s + ultimo // 2) // ultimo
            for s in range(FUNDIDO_RAMPA)]


# Qué dispara una página. Los de `rpg::EventPage::Trigger` de liblcf.
TRIGGER_ACCION = 0          # el jugador aprieta la tecla de acción enfrente
TRIGGER_TOCA_HEROE = 1      # el héroe camina encima
# El 2 es la colisión —el evento camina contra el héroe—, y acá no se nombra.
TRIGGER_AUTOMATICO = 3
TRIGGER_PARALELO = 4

# Los que la ROM sabe disparar. El resto de las páginas de un evento se emiten
# igual —hacen falta para saber cuál está activa— pero sin código.
TRIGGERS = (TRIGGER_ACCION, TRIGGER_TOCA_HEROE, TRIGGER_AUTOMATICO,
            TRIGGER_PARALELO)

# GIRO. Un evento con gráfico **gira hacia el héroe** cuando él lo dispara,
# salvo que tenga la dirección fija: es el
# `SetFacing(GetDirectionToCharacter(GetPlayer()))` de
# `Game_Event::ScheduleForegroundExecution`. Desde el 2026-09-11 se hace, de los
# dos lados —antes contestaba mirando para donde estaba—. Las reglas, que la
# ROM sigue en `giro_disparar` y compañía:
#
# * Gira si su página gira —CharSet y animación que no fija la dirección,
#   `pagina["gira"]`— y no tiene una ruta: con ruta, adónde mira lo decide
#   ella. Los que caminan solos tienen ruta siempre, así que no giran; en RM2k
#   se pausan mientras corre su página y sí, y eso no está modelado.
# * Mira hacia el héroe mientras dura **la página de ese evento**, y al
#   terminar vuelve a su pose: el `UpdateFacing` de `OnFinishForegroundEvent`.
# * Un refresco que le cambia la página lo deshace si la nueva no gira o dibuja
#   otra cosa; con el mismo gráfico sigue girado, como en `RefreshPage`. Si la
#   nueva trae otro CharSet con la misma dirección y columna, RM2k lo deja
#   girado con el dibujo nuevo y acá se deshace: declarado.
# * Una ruta que lo agarra lo deshace, y cargar un mapa también.
#
# En la consola un quieto comparte su ranura de VRAM con los demás quietos de
# la misma pose, así que para girar se muda a **la ranura de giro** del mapa
# —una sola, porque gira uno a la vez— y ahí se le sube la pose desde las doce
# de su gráfico, que por esto van al cartucho. El que camina o anima quieto
# gira en su propia ranura.
#
# Los tipos de animación con la dirección fija son los `fixed_*` de
# `rpg::EventPage::AnimType`, más `spin`, que gira solo y tampoco obedece.
ANIM_FIJAS = (2, 3, 4, 5)

# Sólo los eventos que están en la capa del héroe se disparan con la tecla de
# acción: es el `GetLayer() == Layers_same` de `CheckEventTriggerThere`.
LAYER_MISMA = 1

# El tinte de RM2k va de 0 a 200 con 100 como neutro. En la ROM se guarda tal
# cual y se aplica al subir la paleta.
TINTE_NEUTRO = 100


class NoSePuede(Exception):
    """Esta página tiene algo que la ROM todavía no sabe hacer."""


class Eventos:
    """Los eventos del mapa, como los ve el compilador.

    Existe por una razón que se midió y que si no se paga cara: **el id de
    evento de RM2k no es el índice de la tabla de la ROM**. 39 mapas de este
    juego tienen huecos en la numeración —eventos borrados en el editor— así
    que una ruta apuntada al id 8 movería al que esté octavo en la lista, que
    puede ser cualquier otro. La traducción se hace acá, una sola vez, y el
    bytecode no vuelve a ver un id de RM2k.

    `mio` es el evento dueño de la página que se está compilando, que es a
    quién apunta "este evento".
    """

    def __init__(self, game_map, mio=None):
        self.indices = {ev.id: n for n, ev in enumerate(game_map.events)}
        # Las páginas de cada evento, por id, para `CallEvent`: llamar a un
        # evento del mapa compila su página en el lugar. Van las páginas y no
        # sus comandos porque el número que trae la llamada es el de la
        # página, y en RM2k empieza en uno.
        self.paginas = {ev.id: ev.pages for ev in game_map.events}
        # Visible es tener gráfico en la página activa, que es la misma regla
        # que usa `collect_npcs` para decidir qué entra en la tabla de la ROM.
        self.visibles = {ev.id for ev in game_map.events
                         if ev.active_page() is not None
                         and ev.active_page().character_name}
        # Con qué personaje se dibuja cada uno, para saber cuáles comparten
        # paleta. En la consola el destello se hace sobre la paleta del
        # personaje, así que dos eventos con el mismo gráfico destellarían
        # juntos: ver `_compilar`.
        self.grafico = {}
        for ev in game_map.events:
            page = ev.active_page()
            if page is not None and page.character_name:
                self.grafico[ev.id] = (page.character_name,
                                       page.character_index)
        # Qué variables mira alguna condición de página de este mapa: es el
        # `map_cache` de `Game_Map::RefreshEvent`, que se llena con
        # `pg.condition.variable_id` de cada página. Lo lee
        # `escritura_pide_refresco`. Medido sobre los 328 mapas: como mucho
        # **una** por mapa, y 314 no tienen ninguna.
        self.vars_observadas = {pg.condition.ids["variable"]
                                for ev in game_map.events for pg in ev.pages
                                if "variable" in pg.condition.active}
        # De qué mapa es, para saber cuándo una página se va de él: ver
        # `afuera`.
        self.map_id = getattr(game_map, "map_id", None)
        # Cómo se traduce una `TileSubstitution` a pares de bloques de la ROM.
        # Lo pone el conversor sobre el mapa, porque depende de cómo quedaron
        # los bloques —que es cosa de la consola— y no de RM2k. Sin él el
        # comando no compila, que es lo que pasa en cualquier ROM armada sin
        # pasar por `snes_convert`.
        self.sustituciones = getattr(game_map, "sustituciones", None)
        self.mio = mio

    def comparte_grafico(self, quien):
        """Si este evento dibuja con el mismo personaje que otro del mapa."""
        cual = self.grafico.get(quien)
        return cual is not None and sum(1 for g in self.grafico.values()
                                        if g == cual) > 1

    def para(self, id_evento):
        otro = Eventos.__new__(Eventos)
        otro.indices, otro.visibles = self.indices, self.visibles
        otro.grafico, otro.mio = self.grafico, id_evento
        otro.paginas = self.paginas
        otro.vars_observadas = self.vars_observadas
        otro.map_id = self.map_id
        otro.sustituciones = self.sustituciones
        return otro

    def afuera(self):
        """El mismo, para lo que la página hace **después de saltar a otro
        mapa**: sigue corriendo allá, y qué variables miran las páginas de
        allá no se sabe desde acá, así que toda escritura pide refresco. Ver
        `escritura_pide_refresco`.

        Lo demás no cambia, y no porque esté bien: un evento nombrado por id
        después del salto se traduce contra este mapa y no contra el destino.
        Ninguna página del juego que compile hoy lo hace.
        """
        otro = self.para(self.mio)
        otro.vars_observadas = None
        # Y los bloques de allá no son éstos: una sustitución después del
        # salto hablaría de tiles del mapa nuevo y la traducción es del viejo.
        otro.sustituciones = None
        return otro

    def blanco(self, quien):
        """El byte de blanco que va en OP_ROUTE, o None si no se puede mover.

        0 es el héroe; para un evento, su índice más uno. Los vehículos no
        existen en esta ROM y un id que el mapa no tiene tampoco: los dos
        devuelven None, que corta la página.
        """
        if quien == RUTA_HEROE:
            return 0
        if quien == RUTA_ESTE_EVENTO:
            quien = self.mio
        if quien in self.indices:
            return self.indices[quien] + 1
        return None


class Mensajes:
    """El bloque de textos de la ROM, y el desplazamiento de cada cuadro.

    Es de la ROM entera y no del mapa: `OP_MESSAGE` lleva un desplazamiento
    dentro de este bloque, así que todos los mapas comparten la numeración y el
    conversor lo emite una sola vez. Lo repetido se guarda una sola vez —el
    juego repite cuadros enteros, y son 418 de 2895— y sale gratis porque el
    contenido ya es la clave.

    **Los dos lados lo arman en el mismo orden.** El conversor para emitirlo y
    la referencia para saber qué texto dibujar cuando el bytecode abra un
    mensaje; si se juntaran en otro orden, el mismo desplazamiento nombraría
    otro texto y la comparación mediría dos juegos distintos. Por eso la
    referencia compila todos los mapas de la tabla al construirse, en vez de
    hacerlo cuando el héroe pisa cada uno.
    """

    def __init__(self, paso=1):
        # De a cuántos bytes cuenta el desplazamiento que va en el bytecode.
        # El bloque del juego va de a dos —ver MENSAJES_PASO— y cada cuadro
        # arranca en un byte par; los demás, como el de las tropas, de a uno.
        # Adentro todo es en bytes: el paso se aplica al entrar y al salir.
        self.paso = paso
        self.datos = bytearray()
        self.donde = {}         # las líneas ya guardadas -> su desplazamiento
        self.textos = {}        # y la vuelta, que es lo que usa la referencia

    def agregar(self, lineas):
        r"""El desplazamiento de este cuadro, guardándolo si es la primera vez.

        La cola de escapes se saca **acá** —ver `cola_de_escapes`— y no en el
        compilador, para que todo el que arme un cuadro pase por el mismo lugar:
        los `ShowMessage` del juego y los de las páginas de prueba —que es
        como se prueba esto: `autocierre` en la tanda— y las opciones de un
        `ShowChoice`.

        El recorte a lo que entra en un renglón se hace después de la cola y
        antes de deduplicar: dos textos que sólo difieran en lo que se corta son
        el mismo cuadro en pantalla, y darles dos desplazamientos distintos
        sería emitir dos veces los mismos bytes. Al revés —recortar primero— un
        renglón de 39 caracteres se comería su propio `\|\^` y el cuadro
        quedaría esperando un A que RM2k no pide.

        **La clave de la deduplicación lleva la cola**, y no es un detalle: dos
        cuadros con el mismo texto y distinta cola son dos cuadros distintos
        —uno espera al jugador y el otro no— y compartir desplazamiento los
        haría durar lo mismo en la ROM y en la referencia a la vez, o sea que la
        comparación daría cero con el error puesto.
        """
        from port import ventana as ventana_mod
        lineas, pausas, autocierre = cola_de_escapes(lineas)
        lineas = tuple(t[:ventana_mod.COLUMNAS]
                       for t in list(lineas)[:ventana_mod.LINEAS])
        clave = (lineas, pausas, autocierre)
        if clave not in self.donde:
            while len(self.datos) % self.paso:
                self.datos.append(0)
            donde = len(self.datos)
            self.datos += mensaje_bytes(lineas, pausas, autocierre)
            if donde // self.paso > 0xFFFF:
                raise SystemExit(
                    "los mensajes de esta ROM son %d bytes y el operando de "
                    "OP_MESSAGE es de 16 bits, de a %d bytes"
                    % (len(self.datos), self.paso))
            self.donde[clave] = donde
            self.textos[donde] = lineas
        return self.donde[clave] // self.paso

    def lineas(self, donde):
        """Las líneas que hay en ese desplazamiento. Es lo que dibuja la
        referencia: la ROM lee los mismos bytes del cartucho."""
        return self.textos[donde * self.paso]

    def cola(self, donde):
        """Cuántas pausas lleva ese cuadro y si se cierra solo.

        Sale de **los mismos bytes que lee la ROM** y no de un diccionario
        paralelo: `msg_empezar` decodifica ese byte de cabecera con las mismas
        máscaras. Un formato leído de dos maneras distintas es justo la forma
        de falla que este repo ya pagó dos veces.
        """
        cabecera = self.datos[donde * self.paso]
        return (cabecera >> 4, bool(cabecera & CABECERA_AUTOCIERRE))

    def marca(self):
        return len(self.datos)

    def volver(self, marca):
        """Deshace lo agregado desde `marca`.

        Hace falta porque una página se compila comando por comando y puede
        cortarse en el último: sin esto, el texto de todas las páginas que **no**
        compilan quedaría igual en el cartucho. No es una micro-optimización,
        son los 161 KB del juego entero contra los pocos que hacen falta.
        """
        del self.datos[marca:]
        self.donde = {k: v for k, v in self.donde.items() if v < marca}
        self.textos = {k: v for k, v in self.textos.items() if k < marca}

    def bytes(self):
        # Nunca vacío: el ensamblador necesita la etiqueta resuelta aunque la
        # ROM no vaya a leerla.
        return bytes(self.datos) or b"\x00"


# La cabecera de un cuadro de texto. Los escapes entran acá y no en un operando
# más de `OP_MESSAGE` porque acá salen gratis: los renglones de una ventana son
# cuatro como mucho, así que el byte que los cuenta tenía cinco bits sin usar.
# Un operando más costaría un byte por cada uno de los 2895 cuadros del juego y
# habría que emitirlo igual en los 2855 que no llevan ninguna cola.
#
#     bits 0-2   cuántos renglones trae, de 0 a 4
#     bit  3     se cierra solo: el `\^`
#     bits 4-7   cuántas pausas, de 0 a 15: los `\|`
#
# El orden no es arbitrario: los renglones van abajo porque es lo que la ROM lee
# en el lazo del compositor —`and #CABECERA_LINEAS` y listo— y las pausas
# arriba porque se leen una sola vez, al abrir, donde un `lsr` de más no se
# nota.
CABECERA_LINEAS = 0x07
CABECERA_AUTOCIERRE = 0x08

# El desplazamiento de `OP_MESSAGE` en el bloque del juego cuenta de a dos
# bytes, así que el bloque puede medir 128 KB con un operando de 16 bits.
# Hizo falta cuando los textos se rearmaron para la ventana (`port/textos.py`):
# partir cuadros suma cabeceras y largos, y el cartucho `pruebas` se pasó de
# 64 KB por once bytes. Cuesta medio byte de relleno por cuadro, en promedio.
# `msg_empezar` lo multiplica por dos: son los dos lados de la misma cuenta.
MENSAJES_PASO = 2


def mensaje_bytes(lineas, pausas=0, autocierre=False):
    """Un cuadro de texto como lo lee la ROM: la cabecera, y cada renglón con su
    largo.

    Los caracteres van como índice en la tabla de la fuente, o sea el ASCII
    menos 32. Todo el texto de este juego entra ahí: se midió, y no tiene una
    sola letra acentuada.
    """
    from port import ventana as ventana_mod
    assert 0 <= pausas <= PAUSAS_MAX
    out = bytearray([min(len(lineas), ventana_mod.LINEAS)
                     | (CABECERA_AUTOCIERRE if autocierre else 0)
                     | (pausas << 4)])
    for texto in list(lineas)[:ventana_mod.LINEAS]:
        texto = texto[:ventana_mod.COLUMNAS]
        out.append(len(texto))
        for ch in texto:
            if not 32 <= ord(ch) < 127:
                raise SystemExit("el mensaje tiene un caracter que no está en "
                                 "la fuente: %r" % ch)
            out.append(ord(ch) - 32)
    return bytes(out)


def agrupar(comandos):
    """Los comandos de a uno, salvo los cuadros de texto.

    Devuelve (comando, líneas de más), donde las de más son los
    `ShowMessage_2` que siguen a un `ShowMessage` y son parte del mismo cuadro.
    Un `ShowMessage_2` suelto se devuelve solo y no compila, que es lo correcto:
    sería una línea sin ventana donde ponerla.

    Es parte del filtro y no del emisor: contar los comandos por separado es
    lo que hizo medir mal cuánto destrababa hacer los cuadros de texto.
    """
    comandos = list(comandos)
    i = 0
    while i < len(comandos):
        j = i + 1
        if comandos[i].code == SHOW_MESSAGE:
            while j < len(comandos) and comandos[j].code == SHOW_MESSAGE_2:
                j += 1
        yield comandos[i], [c.string for c in comandos[i + 1:j]]
        i = j


def puede_dispararse(page):
    """Si la ROM sabe disparar esta página, aparte de si sus comandos compilan.

    Las dos reglas de capa salen de `Game_Player`, y son opuestas a propósito:

    * **Tecla de acción**: se mira la celda de adelante, y ahí sólo cuentan los
      eventos de la capa del héroe —`CheckEventTriggerThere` pide
      `GetLayer() == Layers_same`—. Un evento de acción en la celda **propia**
      sí existe en RM2k, pero pide la capa contraria —`CheckEventTriggerHere`
      pide `!= Layers_same`— y ésos no los hacemos.
    * **Contacto**: se dispara al pisar la celda, y ahí es al revés: la capa
      tiene que ser distinta de la del héroe, porque un evento de su misma capa
      le bloquea el paso y nunca llegaría a pisarlo. De las 983 páginas de
      contacto del juego, 978 son de la capa de abajo.

    **El giro hacia el héroe no frena la página.** Hasta el 2026-09-08 la
    frenaba, y eso costaba **1572 páginas de acción en 1224 eventos de 220
    mapas**: la mitad de los NPCs del juego no se podían usar. Desde el
    2026-09-11 el evento además gira de verdad: ver GIRO.
    """
    if page.trigger == TRIGGER_ACCION:
        # Las dos celdas valen, y cada una pide la capa contraria. La de
        # adelante es `CheckEventTriggerThere`, que pide `Layers_same`; la
        # propia es `CheckEventTriggerHere`, que pide `!= Layers_same` —tiene
        # que ser así: un evento de la capa del héroe le cierra el paso y nunca
        # llegaría a pararse encima—.
        #
        # La propia estuvo sin hacer hasta el 2026-09-07 y taro la encontró
        # jugando: la puerta que sale del pad de Talan es `TalDoorTop`, de
        # acción y **capa 2**, y se abre parándose encima. Sin esto no se
        # disparaba nunca y del pad no se podía salir.
        return True
    if page.trigger == TRIGGER_TOCA_HEROE:
        return page.layer != LAYER_MISMA
    return True


# `ConditionalBranch` y sus dos cierres. Salen de `event_codes.py`, que se
# genera de liblcf: los de las puertas se pusieron de memoria una vez y tres
# estaban mal.
COND_RAMA = 12010
COND_SINO = 22010
COND_FIN = 22011

# Las clases de condición que sabemos hacer. El número es el de RM2k tal cual
# —`parameters[0]`— y no una numeración nuestra: copiarlo evita la traducción que
# ya se equivocó una vez con los códigos de comando de las puertas.
#
# Medido sobre el juego entero, por cuántas páginas destraba cada una:
#
#     variable               332 páginas   pide variables, que no hay
#     switch                 145           hecho
#     héroe en el grupo       48           hecho, pero sólo el sub-tipo 0
#     orientación del héroe   31           destraba **cero**: esas páginas están
#                                          frenadas por otra cosa igual
#     objeto                  24           pide inventario, que no hay
#     oro                     10           hecho
#     cronómetro               1           destraba cero
#
# Vuelto a medir el 2026-09-13 sobre las 5603 páginas disparables del juego, ya
# con el inventario y las variables hechos, contando **las que pasan a compilar
# enteras** y no los comandos que se rechazan:
#
#     actor, "tiene puesto el objeto"   36 páginas lo usan,  +18 destraba
#     actor, "sabe la habilidad"        10 páginas lo usan,  +10 **encima** de
#                                       la anterior: son las mismas páginas y
#                                       necesitan las dos, así que sola da +0
#     orientación de un personaje       31 páginas lo usan,   +0, medido otra
#                                       vez y con las dos de arriba puestas
#     cronómetro                         1 página,            +0
#
# O sea que de las 433 páginas que no compilaban, las dos preguntas de actor
# valen **+28** y las otras dos clases no valen nada.
COND_SWITCH = 0
COND_ORO = 3
# El inventario **ya existe** —`OP_ITEM` y `FAR_ITEMS`, desde el 2026-09-10— así
# que el renglón de arriba está viejo: la rama por objeto es `GetItemCount(id) >
# 0`, exactamente la misma pregunta que la condición de página por ítem, que la
# ROM ya contesta leyendo `FAR_ITEMS`. El equipo no entra en la cuenta, como en
# `condiciones_ok`: `GetEquippedItemCount` pide equipo, que no hay.
COND_ITEM = 4
COND_ACTOR = 5

# Y del "héroe", tres de sus siete preguntas. Los números son los de
# `com.parameters[2]` de RM2k tal cual, y salen del `switch` de
# `Game_Interpreter::CommandConditionalBranch` caso 5 en easyrpg-player: 0 está
# en el grupo, 1 se llama así, 2 nivel >=, 3 HP >=, 4 sabe la habilidad, 5
# tiene puesto ese objeto, 6 tiene ese estado.
#
# Las que quedan afuera —el nombre, el nivel, los HP y el estado— piden
# estadísticas que este port no lleva o que no cambian nunca; medido sobre el
# juego entero, las cuatro juntas cortan **cero** páginas.
COND_ACTOR_EN_GRUPO = 0
# `actor->IsSkillLearned(p[3])`. Desde el 2026-09-21 es estado: el bit del par
# (actor, habilidad) en `FAR_HAB`, que arranca con lo que `batalla.aprendidas_de`
# dice del LDB y que `ChangeSkills` prende y apaga. El operando que viaja es la
# ranura del par y no la habilidad; ver `HABILIDAD_RANURA`.
COND_ACTOR_HABILIDAD = 4
# Los cinco `Get*Id()` de easyrpg comparados contra `p[3]`: arma, escudo,
# armadura, casco y accesorio. Esto **sí** es estado de verdad —`FAR_EQUIPO`,
# que la pantalla de equipo escribe y que viaja en la partida— y arranca del
# `initial_equipment` del LDB. Preguntar por el ítem 0 da que sí en cuanto haya
# una ranura vacía, que es lo que hace RM2k; ninguna página del juego lo hace.
COND_ACTOR_EQUIPO = 5
# La rama por variable: `[1, variable, clase del valor, valor, comparación,
# hay else]`. La clase es 0 para una constante y 1 para otra variable; la
# comparación, `==`, `>=`, `<=`, `>`, `<` y `!=`, en ese orden, que es el de
# RM2k. Compila a OP_IF_VAR, no a OP_IF: no entra en siete bytes.
COND_VARIABLE = 1

# --- las variables de RM2k ---------------------------------------------------
#
# El juego declara cinco mil y usa **81**, la mayor la 201. La ROM no lleva
# las cinco mil: el conversor mira qué variables nombran las páginas **de
# todos los mapas del juego** y les da una **ranura** cada una, de cero en
# adelante —`VARIABLE_SLOT`—, y el bytecode habla de ranuras. Así la RAM que
# cuesta es 162 bytes, viven en la RAM del banco 1 (`FAR_VARIABLES`) y viajan
# en la partida guardada. El mismo índice lo arma la referencia con
# `indexar_variables`. Hasta el 2026-09-10 a la noche el índice era de los
# mapas de cada ROM —seis variables en los mapas 1 a 10— y con eso una partida
# guardada con una ROM no valía para otra con más mapas: las ranuras se
# corrían. Con el índice del juego entero la ranura de una variable es la
# misma en cualquier ROM, y la partida pasó de 256 a 512 bytes de SRAM.
#
# Son de **dieciséis bits con signo**: RM2k las lleva a 32 y las topa en
# ±999999, pero ninguna del juego pasa de unos cientos —segundos de
# cronómetro, un azar de 0 a 100, contadores—. Lo que no entra en el word no
# compila, que es más honesto que truncar.
#
# OP_VAR: ranura (byte), operación (byte), clase (byte), a (word), b (word)
# El bit de arriba de la **ranura**, en OP_VAR y en OP_KEY: si esta escritura
# pide el refresco de páginas.
#
# Es `Game_Map::SetNeedRefreshForVarChange`, que **no** marca el refresco por
# cualquier escritura: se lo pregunta al `map_cache`, que tiene la lista de las
# variables que alguna condición de página del mapa cargado mira. Acá esa
# pregunta no hace falta correrla: quién mira qué es estático por mapa y el
# bytecode de una página se compila **para su mapa**, así que la contesta el
# conversor y en la consola queda un `bpl`.
#
# Sin esto el port corría a **30 cuadros por segundo en media Lashe City**: los
# mapas 8, 20, 23, 26, 28 y 32 tienen una página paralela que escribe cuatro
# variables por cuadro —las coordenadas del héroe contra las de un evento— y
# cada escritura pedía el refresco entero, que en el mapa 8 son 68 eventos y
# 106 páginas y **no entra en un cuadro**. Ninguna de esas cuatro variables la
# mira ninguna condición de página, ni ahí ni en ningún otro mapa del juego.
#
# La ranura cabe en siete bits: el juego usa 81 variables y `var_apuntar`
# enmascara con $7F. Si alguna vez hicieran falta más de 128, esto se muda.
VAR_REFRESCO = 0x80
VAR_RANURA_MAX = 0x7F
#
# OP_IF_VAR: ranura (byte), clase (byte), comparación (byte), valor (word),
#     destino (word): como OP_IF, el destino va último para el parcheo
# El inventario, desde el 2026-09-10 a la noche: un byte por ítem del LDB en la
# RAM lejana —`FAR_ITEMS`, pegado a las variables—, indexado por el número de
# RM2k, y `ChangeItems` compila a OP_ITEM con el ítem y cuánto se suma, con
# signo. La cuenta queda en [0, ITEM_MAX], que es `Game_Party::AddItem` con el
# tope de RM2k. El juego lo usa 509 veces, siempre con ítem y cantidad
# constantes: el ítem por variable no compila. Con esto la condición de página
# por ítem se evalúa de verdad —`GetItemCount(id) > 0`, sin equipo todavía— y
# deja de ser "nunca activa". Cambiar un ítem pide el refresco de páginas.
#
# OP_ITEM: ítem (word), delta (byte con signo)
ITEMS_N = 451       # los 450 ítems del LDB más el 0, que no se usa; lo cobra
                    # test_items.py contra RPG_RT.ldb
ITEM_MAX = 99
# `ChangeSaveAccess`, `ChangeMainMenuAccess` y `ChangeEscapeAccess`, desde que
# hay menú de pausa: **el bit** del permiso y si queda permitido. La ROM lo
# guarda en `FAR_ACCESO`. Guardar desde el save point no lo
# mira, como `OpenSaveMenu` en RM2k.
#
# El operando es el bit y no el número del permiso, y eso es de la tercera
# vuelta: la ROM lo sacaba con un `inc a` sobre el número, que da $01 y $02 para
# los dos primeros y **$03 para el tercero**, o sea prohibir las otras dos cosas
# de una. Con el bit puesto por el conversor el opcode no tiene cuenta que
# hacer y acepta los permisos que haga falta.
#
# OP_ACCESS: el bit en FAR_ACCESO (byte), permitido (byte)
# Los HP, los SP y los estados. Hasta el 2026-09-12 fuera de batalla no bajaban
# nunca —medido sobre los 328 mapas: los 11 `ChangeHP` suman, los 16
# `ChangeCondition` quitan un estado y los 54 `FullHeal` llenan— así que los
# tres comandos compilaban a nada y era exacto. **Dejó de serlo el día
# siguiente**, con la pelea: los HP y los SP pasaron a ser estado, en `FAR_HP`
# y `FAR_SP`, y un `FullHeal` que no cura deja al grupo caído. Eso trabó la
# demo hasta el 2026-09-19, porque la pelea del mapa 9 se pierde por guion y su
# manejador de derrota es justamente un `FullHeal`.
#
# Hoy `FullHeal` y el `ChangeHP` que suma son los dos OP_HEAL, y los separa la
# cantidad; el que resta sigue sin compilar. `ChangeCondition` que quita un
# estado sigue compilando a nada, y eso **no** es deuda: fuera de pelea los
# estados no existen —la pelea los arma y los tira— así que no hay nada que
# quitar. El que pone uno sigue sin compilar.
#
# OP_HEAL: actor (byte), cuánto (word). El actor en 0 es todo el grupo y la
#     cantidad en 0 es `FullHeal`, o sea los HP y los SP al máximo.
# La tienda, desde el 2026-09-11: `OpenShop` compila a OP_SHOP con el tipo
# —0 compra y vende, 1 sólo compra, 2 sólo vende—, el juego de mensajes y la
# lista de lo que vende, por número de ítem. Es de largo variable, como
# OP_CHOICE. Como guardar, la pantalla se abre adentro del intérprete y no
# cuesta ningún tick: el mapa no corre mientras se ve. Las ramas de "compró"
# y "no compró" no compilan; ninguna de las 43 tiendas del juego las usa.
#
# OP_SHOP: tipo, juego, cuántos (bytes), y de a dos bytes cada ítem
# El clima, desde el 2026-09-11: `WeatherEffects` compila a OP_WEATHER con el tipo
# y la fuerza, y la lluvia se dibuja. Es `Game_Screen::UpdateRain` con la regla
# de RM2k —cada gota vive doce cuadros, baja cuatro pixeles y corre uno a la
# izquierda por cuadro, y una apagada nace con un diez por ciento de chance en
# un lugar al azar— sobre la pantalla de 256x224, con **las gotas escaladas a
# esa superficie**: RM2k tiene 20, 60 y 100 en 320x240, y acá son 15, 45 y 75,
# la misma densidad. El azar es un xorshift propio, sembrado cada vez que el
# clima cambia, igual de los dos lados; el de RM2k no se puede reproducir.
#
# Cada gota es una raya de 4x16 con la pendiente de la de RM2k, que es de 6x24:
# dos objetos de 8x8 con prioridad 2, que la ventana de mensaje tapa con la
# misma máscara que a los eventos "above". No es semitransparente: es de tres
# grises opacos según le quede de vida, que es donde RM2k la desvanece. El tono
# de pantalla la tiñe, como a todo lo demás. Van últimas en OAM, así que
# cualquier personaje las tapa, y si la OAM se llena se cortan ahí.
#
# **La lluvia va pegada al mapa**, como en RM2k: ahí la superficie de las gotas
# es del tamaño de la pantalla, da la vuelta en los bordes, y se pega corrida
# por el paneo, que es lo que la cámara se movió. Acá es igual con una
# superficie de 256x256: las gotas viven en bytes, el paso de cada cuadro da
# la vuelta solo, y para dibujarlas se les resta el scroll del mapa —la
# sacudida incluida— en ocho bits. Hasta el 2026-09-11 iba pegada a la
# pantalla, y taro lo vio al caminar. De la superficie se ven 224 de las 256
# líneas: la densidad en pantalla es la misma de antes, con gotas que nacen
# también en la franja que no se ve.
#
# El diez por ciento de chance es `azar & 255 < 26`, 10,2%: con `% 100` la
# ROM gastaba el divisor en cada gota apagada de cada cuadro.
#
# OP_WEATHER: tipo, fuerza
CLIMA_LLUVIA = 1
LLUVIA_GOTAS = (15, 45, 75)
LLUVIA_VIDA = 12
LLUVIA_NACE = 26    # de 256
LLUVIA_SEMILLA = 0x1D2B
LLUVIA_DX, LLUVIA_DY = -1, 4
LLUVIA_COLORES = ((16, 16, 18), (11, 11, 13), (6, 6, 7))   # de 5 bits


def lluvia_pixeles(x, y):
    """Los pixeles de una gota con la esquina en (x, y): una raya de 4x16 que
    baja hacia la izquierda, un pixel cada cuatro filas."""
    return [(x + 3 - r // 4, y + r) for r in range(16)]


# Los efectos de sonido, desde el 2026-09-11: `PlaySound` compila a OP_SOUND
# con el índice de su entrada en `Temas.sonidos`, y la tabla de la ROM dice
# con qué muestra, qué altura, qué volumen de cada lado y cuántos cuadros. Las
# muestras van en la ARAM junto al banco de la música, con un presupuesto
# propio: ver `build_efectos` en snes_music.py. Suenan en la voz 7, que se le
# roba a la música mientras duran. No se ven, así que la referencia sólo los
# salta: no cuestan ningún tick, como en RM2k.
#
# OP_SOUND: índice (word)

# Las animaciones de batalla sobre el mapa, desde el 2026-09-11: sus sonidos y
# sus destellos, **sin el dibujo**. `ShowBattleAnimation` compila a
# OP_ANIMATION con la línea de tiempo entera adentro: cuántas entradas y, por
# cada una, ocho bytes —el tick en que dispara, contado desde el del comando,
# el tipo y seis de datos—. Es lo que `BattleAnimation::Update` hace con los
# `timings` de la animación: en el cuadro par `2 * (frame - 1)` suena el efecto
# y arranca el destello de la pantalla o del evento objetivo. Hay una sola a la
# vez —`Game_Screen::ShowBattleAnimation` reemplaza la anterior— y avanza una
# vez por cuadro **antes** que los destellos, que es donde `Game_Screen::Update`
# la pone. Con "esperar", la página espera lo que dura: dos cuadros por cuadro
# de la animación. Ver `animacion_tick` en rom/src/animacion_de_batalla.s.
#
# El destello no es el de RM2k exacto: allá la fuerza es
# `min((7 - (d + 1) / 2) * potencia / 6, 31)` durante diez cuadros, a
# escalones; acá es un `FlashScreen` o un `FlashSprite` que arranca en la
# primera y baja lineal en `ANIM_DESTELLO_CUADROS`. Es la misma luz y dura lo
# mismo, y los dos lados hacen esta cuenta.
#
# OP_ANIMATION: n, y n entradas de ANIM_ENTRADA bytes
ANIM_ENTRADA = 8
ANIM_SONIDO, ANIM_DESTELLO, ANIM_FLASH = 0, 1, 2
# Diez, que es lo que dura el de RM2k, y **par** a propósito: el destello de
# pantalla trabaja en dos fases según la paridad de lo que le queda —ver
# `destello_tick`—, y un `FlashScreen` del juego dura siempre décimas por seis.
# Con once la primera fase era la par, un camino que ninguna página toma y
# donde la ROM y la referencia no coinciden: `animacion` lo mostró.
ANIM_DESTELLO_CUADROS = 10
ANIMACIONES = {}
# El **dibujo**, desde el 2026-09-12. El opcode lleva dos bytes más: el número
# de animación de RM2k tal cual —180 como mucho, así que entra en uno— y sobre
# qué se dibuja. El número va crudo y no un índice nuestro a propósito: la ROM
# lo mira en `anim_batalla_de`, una tabla por número, así que ninguna de las dos
# puntas tiene que llevar un contador que la otra adivine. Ver `animacion.py`.
#
# `ANIM_SIN_DIBUJO` es "esta animación no se dibuja", y lo usan las que RM2k
# repite en tres por tres para tapar la pantalla —`global`—, que no se hacen.
ANIM_SIN_DIBUJO = 0xFF
ANIM_BLANCO_PANTALLA = 0xFF     # alcance "pantalla": va al centro, sin objetivo


def dibujo_blanco(anim, blanco):
    """Sobre qué se dibuja esta animación: el objetivo, o la pantalla.

    Con alcance "pantalla" —`Animation::Scope_screen`, que es el 1— RM2k la
    dibuja en el centro y no le pregunta nada al objetivo; con el otro, sobre
    el objetivo, que es el mismo byte que ya usan las rutas y los destellos.
    """
    if anim.get("alcance", 0) == 1:
        return ANIM_BLANCO_PANTALLA
    return blanco

# El cartel de un `ShowPicture`, desde el 2026-09-12. La ROM lleva **uno solo**
# —ver `Imagenes`— y por eso los tres opcodes no dicen cuál: dicen qué hacerle.
#
#   OP_PICTURE        r, g, b, sat (bytes, 100 neutro): lo pone con ese tono.
#   OP_PICTURE_MOVE  el tono al que va, y en cuántos cuadros. No corta el
#                    cuadro: si la página espera, el conversor le pone un
#                    OP_DELAY detrás, como al `FlashScreen` y a la sacudida.
#   OP_PICTURE_ERASE lo saca.
#
# **El fundido del cartel es el tono y no la transparencia**, que es lo que
# había que ir a mirar: los dos `MovePicture` de la página del "1 year earlier"
# dejan `top_trans` en 0 y mueven (r, g, b) entre 0 y 100 con la saturación
# quieta en 100. O sea que la imagen aparece **negra**, sube a su color y vuelve
# a negro; en la consola eso es teñir sus quince entradas de CGRAM, que es
# exactamente la cuenta que el tinte de pantalla ya hacía.
#
# OP_PICTURE: r, g, b, sat
#
# OP_PICTURE_MOVE: r, g, b, sat, cuadros (byte)
# Cuántos cuadros puede durar un `MovePicture` para que entre en el byte de
# `OP_PICTURE_MOVE`. Los dos de la página duran 210 y 120.
IMAGEN_CUADROS_MAX = 255


# --- la batalla -------------------------------------------------------------
#
# `EnemyEncounter` y sus tres manejadores. Es el hermano de `OP_CHOICE`: el
# comando abre una pantalla que bloquea, y **el resultado elige por dónde
# sigue la página**, así que el opcode lleva los tres destinos y el conversor
# los parchea al cerrar el bloque, igual que las opciones de una elección.
#
# El número de tropa va **tal cual el de RM2k** y no como índice nuestro, a
# propósito: quién entra en el cartucho lo decide el conversor mirando todas
# las páginas, y si el bytecode llevara el índice, la referencia y la ROM
# podrían numerar distinto según qué mapas lleve cada ROM. Con el número de
# RM2k adentro, el bytecode de una página es el mismo siempre; la ROM lo
# resuelve buscándolo en `tropa_id`, y una tropa que no esté ahí es una pelea
# que no se hace y que sale por la rama de victoria.
#
# Los destinos son **absolutos dentro de la página**, como los de `OP_IF`.
# Un manejador que la página no tenga apunta al final del bloque, o sea al
# `EndBattle`, que es lo que hace RM2k cuando el sub-índice no tiene rama.
#
# OP_BATTLE: tropa (word), victoria (word), huida (word), derrota (word)
# El destino que quiere decir "acá no se sigue: esto es un Game Over". Va en el
# lugar de la derrota cuando el `EnemyEncounter` trae `defeat_mode` 0, que en
# RM2k es `Scene_Gameover`. Es un destino imposible —los tres son absolutos
# adentro de la página y ninguna del juego llega a 64 KB— así que no hace falta
# un opcode nuevo ni un byte más en cada pelea. La ROM lo mira en `op_battle`.
BATALLA_PERDER = 0xFFFF

# `HaltAllMovement`: todas las rutas forzadas del mapa se abandonan de golpe.
# Es `Game_Map::RemoveAllPendingMoves`, o sea un `CancelMoveRoute` sobre el
# héroe y sobre cada evento, y lo que cancelar quiere decir está escrito una
# sola vez: es **lo mismo que pasa cuando la ruta termina sola** —quien tenía
# ruta propia de página vuelve a la suya, quien no, se queda quieto— y por eso
# la ROM llama a `retomar_pagina`.
#
# Lo que **no** toca, igual que `CancelMoveRoute`: el paso o el salto en curso
# se terminan, y hacia dónde mira cada uno queda donde la ruta lo dejó.
#
# En todo el juego hay **uno solo** —el mapa 11, el evento que reordena el
# escondite de los Lazer Teeth cuando te descubren— y por eso vale: sin él esa
# página no compila y el HQ no se puede volver a jugar después de que te
# agarren.
#
# OP_STOP_ROUTES: sin operandos

# Las dos preguntas de actor que no entran en `OP_IF`, desde el 2026-09-13:
# "¿tiene puesto este objeto?" y "¿sabe esta habilidad?". No entran porque
# llevan **dos** operandos —el actor y el ítem o la habilidad— y `OP_IF` tiene
# uno solo; el actor entra en un byte porque el LDB tiene 60 y `ACTORES_N` los
# cuenta, y el dato no, porque los ítems llegan a 450.
#
# No lleva polaridad: RM2k no le da ninguna a estas dos —la rama de abajo es el
# `else`— igual que a "está en el grupo". El destino va último, como en todos,
# porque es lo que `con_destino` parchea al cerrar la rama.
#
# OP_IF_ACTOR: sub (byte), actor (byte), dato (word), destino (word)

HALT_ALL_MOVEMENT = 11350

# `ChangePBG`, el fondo parallax. **Se acepta y se tira**, que es lo mismo que
# el port ya hace con el panorama entero: el modo 3 tiene dos capas de fondo y
# las dos están tomadas —el mapa y la capa de encima con la ventana—, así que
# no hay dónde dibujarlo. Ver workflow/tasks/wishlist/panorama-del-mapa-2.md.
#
# Se tira **al compilar**, así que la referencia tampoco lo modela y los dos
# lados quedan iguales por construcción, como las órdenes de ruta 26 y 27.
#
# Aparece **una sola vez en todo el juego**: siete comandos en una sola página,
# la del viaje en el Hover-Tram del mapa 13, donde el paisaje de la tarde corre
# por detrás y cambia de velocidad al arrancar y al frenar. Es la única página
# que traba ese mapa, así que la deuda que se declara acá es exactamente "el
# tranvía se viaja sin paisaje de fondo".
CHANGE_PBG = 11720

# `ChangeSpriteAssociation`: actor (byte) y qué gráfico de la tabla del mapa
# (byte). Es lo mismo que la orden 34 de una ruta pero sobre un **actor**, y de
# ahí salen las dos diferencias:
#
# * **Sobrevive al cambio de mapa**, porque en RM2k es del actor y no del
#   `Game_Player`. Por eso su índice sale de las ranuras reservadas de
#   `Graficos` —ver `asociaciones_de`— y no de la numeración libre del mapa.
# * **Se guarda por actor y se ve sólo si ese actor lidera.** El que no lidera
#   no se dibuja, así que el cambio queda esperando; la ROM lo resuelve en
#   `elegir_grafico_heroe`, que es el único que decide con qué se dibuja el
#   héroe.
#
# Y una cosa que **no** se hace: si el gráfico no está en el banco de sprites
# del mapa, el actor se queda con el suyo del LDB en vez de dejar de dibujarse.
# Es la diferencia con la orden 34, que ahí esconde la fila, y está elegida:
# acá el blanco es el héroe, y un héroe invisible por un mapa donde el CharSet
# no entró es peor que un héroe con el gráfico viejo. Los dos lados hacen lo
# mismo con la misma función.
# **El número se elige mirando los que ya están, no el último que uno
# recuerde.** El 2026-09-13 tres ramas de sub-agente eligieron "el siguiente
# libre" a la vez y sin verse: salieron $23 dos veces y $24 dos veces, git las
# mergeó sin un solo conflicto —cada una en su línea— y lo que se rompía era el
# recorrido del bytecode. Lo cuida `test_ningun_opcode_comparte_numero_con_otro`.
#
# OP_ACTOR_SPRITE: actor (byte), gráfico (byte)

# `KeyInputProc`: ranura de variable (byte) y qué teclas mira (byte).
#
# En RM2k es `CommandKeyInputProc` más el pedazo de `Game_Interpreter::Update`
# que lo atiende mientras espera, y el valor que guarda sale de `CheckInput`:
# 1 abajo, 2 izquierda, 3 derecha, 4 arriba, 5 la tecla de acción, 6 cancelar.
# Se miran de mayor a menor, que es lo que dice el comentario "RPG processes
# keys from highest variable value to lowest".
#
# Las dos formas son programas distintos y por eso llevan bandera:
#
#   sin espera   lee lo que está apretado **ahora** —`Input::IsPressed`— y la
#                página sigue en el mismo cuadro. Es la del volante del auto.
#   con espera   la página se para acá hasta que haya un **flanco**
#                —`IsTriggered`— de alguna de las teclas pedidas.
#
# La de espera se emite **dos veces**, la primera con `TECLA_ARRANCA`: ésa pone
# la variable en cero, se come el flanco que hubiera y devuelve el control sin
# mirar nada. Es el `Input::ResetTriggerKeys()` de RPG_RT, que existe para que
# el comando no se coma la misma tecla que acaba de cerrar un mensaje —y en
# este juego las 23 esperas vienen justo detrás de un `ShowMessage`, así que
# sin eso el cartel pasaría de largo—. Dos opcodes y no un byte de estado
# porque el intérprete no tiene dónde guardarlo: el que espera **rebobina su
# propio cursor** y se vuelve a ejecutar cuadro a cuadro, así que no puede
# distinguir la primera vuelta de las otras.
# Interruptor de **medición**, apagado por defecto: acepta el `KeyInputProc`
# sin espera, que es el volante de la persecución en auto. Existe para que el
# número de lo que falta se vuelva a sacar con un comando —ver el `raise` de
# `KEY_INPUT_PROC`, que tiene las dos mediciones— y para armar la ROM que taro
# puede jugar mientras la otra mitad del arreglo no esté.
#
# **Una ROM armada con esto no se compara contra la referencia**: es
# exactamente el camino que todavía diverge. No ponerlo en ninguna receta de la
# tanda.
PERMITIR_TECLA_SIN_ESPERA = bool(os.environ.get("TECLA_SIN_ESPERA"))
TECLA_ESPERA   = 0x01
TECLA_DIRS     = 0x02
TECLA_DECISION = 0x04
TECLA_CANCELAR = 0x08
TECLA_ARRANCA  = 0x10

KEY_INPUT_PROC = 11610

# El valor que RM2k le guarda a cada tecla, y de acá sale también el orden en
# que se las mira: de mayor a menor.
TECLA_VALOR_CANCELAR = 6
TECLA_VALOR_DECISION = 5
# Por dirección de la ROM: 0 arriba, 1 derecha, 2 abajo, 3 izquierda.
TECLA_VALOR_DIR = {0: 4, 1: 3, 3: 2, 2: 1}

# `ChangeEventLocation` con la celda **en dos variables**, que es el otro
# `LUGAR` de RM2k: mismos efectos que `OP_PLACE` —`MoveTo`, la celda cambia ya
# y el paso en curso se corta— pero los dos números se leen al correr.
#
# Va en un opcode propio y no en un bit de `OP_PLACE` porque los operandos son
# otros: dos ranuras de un byte contra dos palabras. `OPCODE_SIZE` es una
# tabla, así que un opcode que mida distinto según un bit no lo sabe recorrer
# ni el conversor ni la ROM.
#
# Lo que destraba es **una página**, medido sobre el juego entero, y son las
# 129 apariciones en 32 páginas: las otras 31 están frenadas por otra cosa
# igual. Esa página es la que importa: el motor del minijuego de las piedras
# del mapa 11, que sin esto no puede plantar la piedra donde el jugador está
# parado y por lo tanto no se puede tirar ninguna.
#
# **El número se elige mirando los que ya están**, no el último que uno
# recuerde: ver el aviso de `OP_ACTOR_SPRITE`.
#
# OP_PLACE_VAR: blanco (byte, como en OP_PLACE), ranura de la x
#     (byte), ranura de la y (byte)


def tecla_de(banderas, apretadas):
    """Qué valor le toca a la variable con estas teclas apretadas.

    `apretadas` es el conjunto de lo que el jugador tiene puesto: los enteros
    0 a 3 para las direcciones, "a" y "b" para las dos teclas. La usan los dos
    lados —acá la referencia, allá `op_key`— y el orden es el de `CheckInput`.

    **Qué conjunto se le pasa depende de la forma del comando**, y eso lo
    decide quien llama: la que espera mira los **flancos** de este cuadro
    —`Input::IsTriggered`— y la que no espera, lo que está puesto
    —`Input::IsPressed`—. Acá no se puede distinguir: las dos son "lo que
    cuenta como apretado" para esta pregunta.
    """
    if banderas & TECLA_CANCELAR and "b" in apretadas:
        return TECLA_VALOR_CANCELAR
    if banderas & TECLA_DECISION and "a" in apretadas:
        return TECLA_VALOR_DECISION
    if banderas & TECLA_DIRS:
        for direccion in (0, 1, 3, 2):          # arriba, derecha, izq, abajo
            if direccion in apretadas:
                return TECLA_VALOR_DIR[direccion]
    return 0

ENEMY_ENCOUNTER = 10710
VICTORY_HANDLER = 20710
ESCAPE_HANDLER = 20711
DEFEAT_HANDLER = 20712
END_BATTLE = 20713

# Los tres manejadores, en el orden en que sus destinos van en el opcode.
BATALLA_HANDLERS = (VICTORY_HANDLER, ESCAPE_HANDLER, DEFEAT_HANDLER)

# Los parámetros de `EnemyEncounter`, de `Game_Interpreter_Map::
# CommandEnemyEncounter`: [tropa por variable, tropa, de dónde sale el fondo,
# qué pasa al huir, qué pasa al perder, si pega primero]. Este port sólo hace
# el caso que usan las 51 peleas del juego —tropa por constante— y se planta
# en los otros, que es lo de siempre: antes emitir nada que emitir algo que la
# ROM haga distinto.
# De dónde sale el fondo, el parámetro [2] de `CommandEnemyEncounter`: 0 el
# del terreno, 1 el que nombra el comando, 2 ninguno.
BATALLA_FONDO_DEL_COMANDO = 1
# El parámetro de huida: 0 no se puede, 1 corta la pelea. Sólo se pregunta por
# el 1.
BATALLA_ESCAPE_CORTA = 1
BATALLA_DERROTA_GAME_OVER = 0


# --- el audio de la pelea ---------------------------------------------------
#
# Todo del LDB, nada inventado: el tema de batalla, el de victoria y los cinco
# efectos que `Game_System::GetSystemSE` reparte. Quién suena en qué momento
# sale de easyrpg-player y **no de memoria**, que es la regla de este repo:
#
#   battle_music      `Scene_Battle`, al construirse
#   battle_end_music  `Scene_Battle_Rpg2k`, al ganar (BGM_Victory)
#   dodge_se          `AlgorithmBase::GetFailureSe`: el golpe que erra
#   enemy_attack_se   `Normal::GetStartSe` con la fuente enemiga
#   enemy_damaged_se  el sub-estado `eMessage` del golpe, blanco enemigo
#   actor_damaged_se  ídem, blanco del grupo
#   enemy_death_se    `ProcessBattleActionDeath`
#   escape_se         `Scene_Battle_Rpg2k`, cuando el grupo escapa
#
# En el ABL `battle_se` —el de empezar la pelea— está en "(OFF)", así que no
# se registra nada por él: un nombre que no resuelve a ningún archivo entra
# igual en las tablas pero ocuparía una entrada para siempre muda.
#
# **Esto se registra de los dos lados**, y no porque la referencia suene: los
# índices de `Temas` los lleva el bytecode de cada `PlayBGM` y cada
# `PlaySound`, así que un tema que un lado numere y el otro no correría todos
# los que vengan detrás. Por eso vive acá, en la función que las dos puntas
# llaman, y no en el conversor.
AUDIO_BATALLA = {}

# El orden es el contrato con la ROM: el conversor emite `BA_SE_<n>` con el
# índice que cada uno sacó de `Temas`, en este orden.
AUDIO_BATALLA_SE = ("dodge_se", "enemy_attack_se", "enemy_damaged_se",
                    "actor_damaged_se", "enemy_death_se", "escape_se",
                    # El del 2026-09-13, cuando la pelea empezó a dejar usar
                    # ítems: `Item::GetStartSe` de easyrpg, que es el
                    # `item_se` del LDB.
                    "item_se")
AUDIO_BATALLA_BGM = ("battle_music", "battle_end_music")

# Un nombre que RM2k usa para decir "nada": ni el tema ni el efecto existen.
AUDIO_APAGADO = ("", "(OFF)")


def indexar_audio_de_batalla(game_dir):
    """El tema y los efectos de la pelea, del LDB. Lo llaman el conversor y la
    referencia, igual que `indexar_animaciones`."""
    from rpgmaker import lcf
    db = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
    AUDIO_BATALLA.clear()
    AUDIO_BATALLA["battle_music"] = db.battle_music
    AUDIO_BATALLA["battle_end_music"] = db.battle_end_music
    for nombre in AUDIO_BATALLA_SE:
        AUDIO_BATALLA[nombre] = db.system_se[nombre]


# La clave de `Temas.por_mapa` donde va el audio de la pelea. No es un mapa:
# es **un paquete de audio propio**, que la ROM carga al abrir la pelea y
# descarga al cerrarla.
#
# Va aparte y no adelante del paquete del mapa, y eso está medido: el tema de
# batalla son 18 muestras y 51.480 B de los 64.512 de ARAM, así que metiéndolo
# en el paquete del mapa 2 los 24 efectos de ese mapa —49.068 B, que hoy
# entran todos— se caían casi enteros. Con paquete propio el mapa no paga
# nada mientras no se pelee.
PAQUETE_BATALLA = "batalla"


def audio_de_batalla(temas):
    """Anota en `temas` lo que la pelea va a hacer sonar, y devuelve sus
    índices: dos temas y `AUDIO_BATALLA_SE` efectos, $FF o $FFFF el apagado.

    Se llama cada vez que una página compila un `EnemyEncounter`. Lo anotado
    cae en el paquete `PAQUETE_BATALLA` y no en el del mapa que tiene la
    pelea, así que hay que salvar y reponer `temas.mapa` alrededor.
    """
    if temas is None or not AUDIO_BATALLA:
        return None
    indices = {}
    anterior = temas.mapa
    temas.mapa = PAQUETE_BATALLA
    for nombre in AUDIO_BATALLA_BGM:
        tema = AUDIO_BATALLA[nombre]
        indices[nombre] = (0xFF if tema in AUDIO_APAGADO
                           else temas.indice(tema))
    for nombre in AUDIO_BATALLA_SE:
        efecto = AUDIO_BATALLA[nombre]
        indices[nombre] = (0xFFFF if efecto[0] in AUDIO_APAGADO
                           else temas.sonido(*efecto))
    temas.mapa = anterior
    return indices


class Imagenes:
    """El único cartel que entra en el cartucho, y qué comandos lo mueven.

    Es el hermano de `Temas` y de `Graficos`: el conversor y la referencia
    arman uno y los dos deciden lo mismo, porque la decisión está acá y no en
    ninguno de los dos.

    **Uno solo por ROM**, y ésa es la decisión que acota el alcance. Se lleva
    una paleta de sprite entera —quince colores que no se pueden fusionar con
    los de nadie, porque el fundido los tiñe a todos— y dos filas de bloques
    del banco de sprites. Un segundo cartel pediría decidir cuántos de esos hay
    para repartir, y para eso primero hay que saber cuántos `ShowPicture` del
    juego se pueden dibujar; hoy la respuesta está en el informe y no en el
    código.

    El que no entra se sigue aceptando sin hacerse, como antes: cortar la
    página le sacaría al juego las ocho que hoy compilan.
    """

    def __init__(self, game_dir):
        self.game_dir = game_dir
        self.nombre = None      # el cartel que se quedó con la ranura
        self.info = None        # lo que `imagen.convertir` sacó de él
        self.numero = None      # el número de imagen de RM2k que lo muestra
        self.donde = None       # dónde lo centró su ShowPicture

    def _leer(self, nombre):
        import os
        from PIL import Image
        ruta = os.path.join(self.game_dir, "Picture", nombre + ".png")
        if not os.path.exists(ruta):
            return None
        return Image.open(ruta)

    def elegir(self, game_maps):
        """Cuál de los `ShowPicture` de la ROM se queda con la ranura.

        Se decide **antes de compilar una sola página** y mirando todos los
        mapas del cartucho en el orden de la tabla, y no por orden de llegada.
        La diferencia importa: la referencia compila los mapas en un orden que
        depende de si la ROM lleva ventana, y con "el primero que pase" bastaba
        que dos carteles compitieran para que los dos lados eligieran distinto.
        Eso no se vería como un cartel equivocado sino como dos streams de
        bytecode distintos, que es la clase de error que la comparación reporta
        sin decir dónde.
        """
        from port import imagen as imagen_mod
        if self.nombre is not None:
            return self.info    # la ranura ya está tomada
        for game_map in game_maps:
            for event in game_map.events:
                for page in event.pages:
                    for cmd in page.commands:
                        if cmd.code != SHOW_PICTURE:
                            continue
                        if not imagen_aceptable(cmd.parameters):
                            continue
                        if cmd.parameters[7]:
                            continue    # el color transparente del PNG
                        im = self._leer(cmd.string)
                        if im is None:
                            continue
                        p = cmd.parameters
                        info = imagen_mod.convertir(im, p[2], p[3])
                        if not imagen_mod.cabe(info):
                            continue
                        self.nombre, self.info = cmd.string, info
                        self.numero, self.donde = p[0], (p[2], p[3])
                        return info
        return None

    def mostrar(self, numero, nombre, cx, cy):
        """El cartel de la ranura si este `ShowPicture` es el suyo, o None."""
        if self.nombre is None:
            return None
        return (self.info if (self.nombre, self.numero, self.donde)
                == (nombre, numero, (cx, cy)) else None)

    def suyo(self, numero, cx, cy):
        """Si el cartel de la ranura es el que este comando nombra y no se
        mueve de donde está. Lo preguntan `MovePicture` y `ErasePicture`, que
        no traen el nombre: en RM2k el número de imagen es todo lo que los liga
        a su `ShowPicture`."""
        return (self.nombre is not None and self.numero == numero
                and (cx is None or self.donde == (cx, cy)))


def indexar_animaciones(game_dir):
    """Las animaciones de batalla del LDB, por id: sus cuadros y sus
    timings, con los valores por omisión de liblcf —el decodificador omite
    los que no están—. Lo llaman el conversor y la referencia."""
    from rpgmaker import lcf
    db = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
    ANIMACIONES.clear()
    for numero, anim in db.decode().get("animations", {}).items():
        timings = []
        for _i, t in sorted((anim.get("timings") or {}).items()):
            se = t.get("se") or {}
            timings.append({
                "frame": t.get("frame", 0),
                "se": (se.get("name", ""), se.get("volume", 100),
                       se.get("tempo", 100), se.get("balance", 50)),
                "alcance": t.get("flash_scope", 0),
                "rgb": (t.get("flash_red", 31), t.get("flash_green", 31),
                        t.get("flash_blue", 31)),
                "fuerza": t.get("flash_power", 31),
            })
        # Y lo que hace falta para **dibujarla**, desde el 2026-09-12: la hoja
        # de `Battle`, las celdas de cada cuadro y dónde va la caja. Lo lee
        # `animacion.py`, que es el único que sabe qué hacer con esto; acá se
        # guarda tal cual sale del LDB para que las dos puntas lean lo mismo.
        cuadros = anim.get("frames") or {}
        ANIMACIONES[numero] = {"cuadros": [cuadros[k].get("cells") or {}
                                           for k in sorted(cuadros)],
                               "timings": timings,
                               # El nombre que la animación tiene en el editor
                               # —"Whole Magic Flame C"—: no lo mira nadie para
                               # dibujar, lo escribe su parche para que el que
                               # lea el diff sepa de cuál se habla.
                               "nombre": anim.get("name", ""),
                               "imagen": anim.get("animation_name", ""),
                               "grande": bool(anim.get("large")),
                               "alcance": anim.get("scope", 0),
                               "posicion": anim.get("position", 1)}
CHANGE_HP = 10460
CHANGE_CONDITION = 10480
FULL_HEAL = 10490
CHANGE_MENU_ACCESS = 11960
CHANGE_ESCAPE_ACCESS = 11840
ACCESO_GUARDAR, ACCESO_MENU, ACCESO_ESCAPAR = 0, 1, 2
# El bit de cada uno en `FAR_ACCESO`, y los bits van en "prohibido" para que el
# cero del reset sea "todo permitido", que es como arranca RM2k. El $80 es el
# pedido de menú —`menu_calling`— y no es un permiso.
ACCESO_BIT = (0x01, 0x02, 0x04)
# `ChangeEscapeAccess` es el permiso de huir de una batalla, y se guarda sin
# leerse: la huida la mira la batalla, que es de otro. Está igual porque es lo
# que más destraba de lo que cuesta un bit —**30 de las 39 páginas del juego
# con `EnemyEncounter` que no compilan lo tienen adelante**—, y porque un
# comando aceptado sin hacerse sería mentira: RM2k lo guarda en `Game_System`
# y viaja en la partida, y acá también.
# Las operaciones de ControlVars que compilan: poner, sumar, restar. Multiplicar,
# dividir y el resto no las usa ninguna página del juego.
VAR_PONER, VAR_SUMAR, VAR_RESTAR = 0, 1, 2
# Y de dónde sale el operando, con el número de RM2k: una constante, otra
# variable, un número al azar entre a y b, u "otro", que acá son el oro y los
# segundos que le quedan al cronómetro. El azar pide que b - a sea menor que
# 256: la ROM divide con el divisor de ocho bits del hardware.
VAR_CONSTANTE, VAR_VARIABLE, VAR_AZAR, VAR_OTRO = 0, 1, 3, 7
OTRO_ORO, OTRO_TIMER = 0, 1
# Y la clase 6: **las coordenadas de un personaje**. Los sub-operandos son los
# de `ControlVariables::Event` de easyrpg-player —el `op` de
# `game_interpreter_control_variables.cpp`—: 0 el id del mapa, 1 la x, 2 la y,
# 3 hacia dónde mira, 4 y 5 las coordenadas en pantalla y 6 el id del evento.
# No van de memoria, que es la regla de la casa.
#
# De las 829 veces que este juego la usa, **827 piden la x o la y** y las otras
# dos la x y la y de pantalla; el id del mapa, la mirada y el id del evento no
# los pide nadie. Así que la ROM hace la 1 y la 2, y el resto no compila:
#
# * la **0** en RM2k devuelve 0 para un evento —un defecto de RPG_RT que
#   easyrpg copia—, así que hacerla sería copiar un defecto que nadie usa;
# * la **3** devuelve 8, 6, 2 o 4 —el teclado numérico— y no 0..3;
# * la **4** y la **5** son pixeles de pantalla, y la nuestra mide 256x224
#   contra los 320x240 de RM2k: el número que le quedaría a la variable no es
#   el del juego original. Son dos apariciones en todo el juego, y aceptarlas
#   destrabaría **una** página más —medido, 5135 contra 5136—: no vale
#   inventar una coordenada que no es la de allá por una página.
VAR_PERSONAJE = 6
PERSONAJE_X, PERSONAJE_Y = 1, 2
CMP_IGUAL, CMP_MAYOR_IGUAL, CMP_MENOR_IGUAL, CMP_MAYOR, CMP_MENOR, \
    CMP_DISTINTO = range(6)
# El generador de azar, **el mismo de los dos lados**: un xorshift de dieciséis
# bits —x ^= x << 7; x ^= x >> 9; x ^= x << 8— sembrado en el reset. Que la
# ROM y la referencia coincidan pixel por pixel en una página con azar es
# porque las dos sacan la misma secuencia; no hay entropía de verdad, y no la
# hay en RPG_RT tampoco a los efectos de esta comparación.
AZAR_SEMILLA = 0xACE1
TIMER_PONER_VAR = 3     # la cuarta operación del cronómetro: los segundos desde
                        # una variable. Las tres de RM2k son 0, 1 y 2.

VARIABLE_SLOT = {}      # variable de RM2k -> ranura en la ROM


def mapas_del_juego(game_dir):
    """Los números de todos los mapas que hay en el juego, en orden."""
    import glob
    return sorted(int(os.path.basename(p)[3:7]) for p in
                  glob.glob(os.path.join(game_dir, "Map[0-9][0-9][0-9][0-9].lmu")))


def variables_de(game_dir, map_ids=None, extra=()):
    """Qué variables nombran las páginas de estos mapas —sin lista, las de
    todo el juego—, cada una con su ranura.

    Se miran todos los comandos y las condiciones de todas las páginas,
    compilen o no: es un superconjunto barato —dos bytes por variable— y así
    una página que compile después no cambia las ranuras de las demás. `extra`
    son las de las páginas de prueba, que no salen de ningún mapa: el
    conversor las barre con `variables_de_comandos`.

    **`KeyInputProc` también nombra una variable, y hasta el 2026-09-13 no
    estaba en esta lista.** Es el único comando del juego que le escribe a una
    variable sin ser un `ControlVars`, así que una variable que sólo él toque
    se quedaba sin ranura y la página no compilaba por un motivo que no tenía
    nada que ver con el comando. Pasan **dos**: la 5, del motor del minijuego de
    las piedras del mapa 11, y la 151, de otras dos páginas; a las tres las
    escribe este comando y no las lee nadie más.
    No era circular —no dependía de que la página compilara—: este barrido mira
    todos los comandos compilen o no, y a éste no lo miraba.
    """
    from rpgmaker import lcf
    ids = set(extra)
    for map_id in (mapas_del_juego(game_dir) if map_ids is None else map_ids):
        game_map = lcf.Map(os.path.join(game_dir, "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                if "variable" in page.condition.active:
                    ids.add(page.condition.ids["variable"])
                ids |= variables_de_comandos(page.commands)
    if map_ids is None:
        # Y las de las páginas de las tropas, que son del juego entero y no de
        # un mapa. Suman **cuarenta**, medido el 2026-09-21: los sistemas de
        # los personajes llevan cada uno sus contadores —la 81 y la 106 de
        # Talan cuentan cuántas veces absorbió cada técnica—, y ningún mapa
        # los nombra.
        db = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
        for tropa in db.troops.values():
            for pagina in tropa.pages:
                if "variable" in pagina.activos:
                    ids.add(pagina.condicion["variable_id"])
        for comandos in comandos_de_las_tropas(db):
            ids |= variables_de_comandos(comandos)
    return {variable: ranura for ranura, variable in enumerate(sorted(ids))}


def comandos_de_las_tropas(db):
    """Los comandos de cada página de tropa del LDB, con las ramas de la pelea
    traducidas a las del mapa —ver `RAMA_DE_PELEA`—, para los barridos que
    buscan variables y pares de habilidad. **No filtra**: el barrido es un
    superconjunto, como el de los mapas, compile la página o no."""
    from rpgmaker import lcf
    for tropa in db.troops.values():
        for pagina in tropa.pages:
            yield [lcf.EventCommand(RAMA_DE_PELEA.get(c.code, c.code),
                                    c.indent, c.string, c.parameters)
                   for c in pagina.commands]


def variables_de_comandos(comandos):
    """Las variables que nombran estos comandos: el barrido de `variables_de`,
    que es también el de las páginas de prueba.

    `ChangeEventLocation` con la celda en dos variables entró el 2026-09-18,
    cuando la página de prueba empezó a usarlo. En el juego son 129 y no
    agregan ninguna: medido, todas sus variables ya las nombra otro comando.
    """
    ids = set()
    for cmd in comandos:
        p = cmd.parameters
        if cmd.code == CONTROL_VARS and len(p) >= 7:
            if p[0] == 0:
                ids.add(p[1])
            elif p[0] == 1:
                ids.update(range(p[1], p[2] + 1))
            if p[4] == VAR_VARIABLE:
                ids.add(p[5])
        elif cmd.code == COND_RAMA and len(p) >= 5 \
                and p[0] == COND_VARIABLE:
            ids.add(p[1])
            if p[2] == 1:
                ids.add(p[3])
        elif cmd.code == KEY_INPUT_PROC and p:
            ids.add(p[0])
        elif cmd.code == TIMER_OPERATION and len(p) >= 3 \
                and p[0] == TIMER_PONER \
                and p[1] != TIMER_SEGUNDOS_FIJOS:
            ids.add(p[2])
        elif cmd.code == CHANGE_EVENT_LOCATION and len(p) >= 4 \
                and p[1] == LUGAR_POR_VARIABLE:
            ids.update((p[2], p[3]))
        elif cmd.code == STORE_TERRAIN_ID and len(p) >= 4:
            ids.add(p[3])
            if p[0] == 1:
                ids.update((p[1], p[2]))
    return ids


COMUNES = {}            # evento común de RM2k -> sus comandos


def indexar_comunes(game_dir):
    """Deja en `COMUNES` los comandos de cada evento común.

    Lo llaman el conversor y la referencia antes de compilar nada, igual que
    `indexar_variables`, y por lo mismo: `CallEvent` los compila en el lugar,
    así que los dos lados tienen que estar mirando la misma base.
    """
    from rpgmaker import lcf
    db = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
    COMUNES.clear()
    COMUNES.update(db.common_events)
    return COMUNES


# Lo que las dos preguntas de actor de `ConditionalBranch` necesitan saber del
# LDB: qué tiene puesto cada uno al empezar y qué habilidades sabe. Van en un
# índice de módulo, como `COMUNES` y `VARIABLE_SLOT`, y por lo mismo: el
# conversor y la referencia lo arman con la misma función antes de compilar
# nada, así que no hay dos lecturas del LDB que puedan discrepar.
ACTOR_EQUIPO = {}       # actor de RM2k -> sus cinco ranuras, en el orden de
                        # `pantallas.RANURAS_EQUIPO`
ACTOR_SABE = {}         # actor de RM2k -> las habilidades que sabe
_ACTORES_INDEXADOS = []


def indexar_actores(game_dir):
    """Deja en `ACTOR_EQUIPO` y `ACTOR_SABE` lo que el LDB dice de cada actor.

    Sin esto el intérprete contestaría que nadie tiene nada puesto y que nadie
    sabe nada, **en silencio y de un solo lado**, que es la forma de falla que
    `AGENTS.md` nombra. Por eso hay una lista que dice si se llamó y `OP_IF_ACTOR`
    la mira.
    """
    from rpgmaker import lcf
    from port import batalla
    db = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
    ACTOR_EQUIPO.clear()
    ACTOR_SABE.clear()
    ACTOR_EQUIPO.update({a: tuple(act.initial_equipment)
                         for a, act in db.actors.items()})
    ACTOR_SABE.update({a: batalla.aprendidas_de(db, a)
                       for a in db.actors})
    _ACTORES_INDEXADOS[:] = [True]
    return dict(ACTOR_EQUIPO)


# Los términos con que se arma el saludo de la posada. Son del juego y no
# nuestros —el ABL cobra en "Cr"— así que salen del LDB y no de un literal, por
# lo mismo que los de la pantalla de título. Van en un índice de módulo como
# `ACTOR_EQUIPO`: el conversor lo arma una vez antes de compilar nada.
#
# Los dos juegos de términos son el `inn_type` de `ShowInn`: 0 el A y 1 el B.
TERMINOS_POSADA = {}
_TERMINOS_DE_POSADA = ("greeting_1", "greeting_2", "greeting_3", "accept",
                       "cancel")


def indexar_terminos(game_dir):
    """Deja en `TERMINOS_POSADA` los términos de la posada y el del oro.

    Sin esto `ShowInn` no compila —y lo dice—, en vez de armar el saludo con
    palabras inventadas: el precio y la moneda son lo único que el jugador va
    a leer para decidir.
    """
    from rpgmaker import lcf
    db = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
    terminos = db.secciones["terms"]
    TERMINOS_POSADA.clear()
    TERMINOS_POSADA["gold"] = lcf.campo(terminos, "gold")
    for tipo, letra in ((0, "a"), (1, "b")):
        TERMINOS_POSADA[tipo] = tuple(
            lcf.campo(terminos, "inn_%s_%s" % (letra, nombre))
            for nombre in _TERMINOS_DE_POSADA)
    return dict(TERMINOS_POSADA)


# --- qué habilidades sabe cada actor, como estado --------------------------
#
# `ChangeSkills` le enseña y le hace olvidar habilidades a un actor, y eso es
# estado del mundo: viaja en la partida, como el equipo. Lo que la ROM guarda
# es **un bit por par (actor, habilidad)**, y no una lista por actor, porque
# el juego enseña de a muchas —al actor 14 le pone y le saca setenta en los
# eventos comunes— y una lista de largo variable en la RAM lejana pediría
# buscar, insertar ordenado y topar.
#
# Los pares son los que el juego entero puede llegar a mirar, y no más: los de
# la tabla de aprendizaje del LDB **en todos los niveles** —el día que haya
# subida de nivel, `LearnLevelSkills` prende los que le toquen—, los que algún
# `ChangeSkills` nombra y los que alguna rama "sabe la habilidad" pregunta.
# Un par que nadie nombra no puede cambiar ni ser preguntado, así que no hace
# falta su bit. Se barren todos los mapas del juego y todos los eventos comunes,
# compilen o no, por lo mismo que las variables: así una página que compile
# después no le corre la ranura a ninguna otra, y una partida guardada con una
# ROM vale para otra.
#
# El orden es por actor y después por habilidad, y no es cosmético: deja los
# pares de cada actor seguidos y ordenados por número, que es el orden en que
# `LearnSkill` los deja y en el que el menú de la pelea los muestra. Así la
# ROM arma la lista recorriendo un tramo, sin ordenar nada.
#
# OP_SKILL: ranura del par (word), aprende (byte: 1 aprende, 0 olvida)
HABILIDAD_RANURA = {}   # (actor, habilidad) -> ranura
# El techo: los bits viven en `FAR_HAB`, que tiene 256 bytes en el mapa de la
# RAM lejana. Hoy el juego usa muchos menos; si algún día no alcanzan, el
# conversor se corta en vez de pisar al vecino.
HABILIDAD_RANURAS_MAX = 256 * 8
CHANGE_SKILLS = 10440
CHANGE_EQUIPMENT = 10450
GAME_OVER = 12420


def pares_de_habilidad_de_comandos(comandos):
    """Los pares (actor, habilidad) que nombran estos comandos: el barrido de
    `pares_de_habilidad`, que es también el de las páginas de prueba.

    Sólo las formas que compilan —el actor fijo y la habilidad constante—:
    un par que viene en una variable no se puede indexar, y esos comandos no
    compilan. Ninguno del juego lo hace."""
    pares = set()
    for cmd in comandos:
        p = cmd.parameters
        if cmd.code == CHANGE_SKILLS and len(p) >= 5 \
                and p[0] == 1 and p[3] == 0:
            pares.add((p[1], p[4]))
        elif cmd.code == COND_RAMA and len(p) >= 4 and p[0] == COND_ACTOR \
                and p[2] == COND_ACTOR_HABILIDAD:
            pares.add((p[1], p[3]))
    return pares


def pares_de_habilidad(game_dir, extra=()):
    """Cada par (actor, habilidad) que el juego puede mirar, con su ranura.

    Ver `HABILIDAD_RANURA`. Los que nombran un actor o una habilidad que el
    LDB no tiene se descartan: RM2k los ignora con un aviso, y acá no
    compilan."""
    from rpgmaker import lcf
    db = lcf.Database(os.path.join(game_dir, "RPG_RT.ldb"))
    pares = set(extra)
    for numero, actor in db.actors.items():
        pares |= {(numero, s) for _nivel, s in actor.skills if s}
    for map_id in mapas_del_juego(game_dir):
        game_map = lcf.Map(os.path.join(game_dir, "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                pares |= pares_de_habilidad_de_comandos(page.commands)
    for comandos in db.common_events.values():
        pares |= pares_de_habilidad_de_comandos(comandos)
    # Y las páginas de las tropas, que desde el 2026-09-21 corren en la pelea.
    # Hoy no suman ningún par —los que enseñan los sistemas ya los nombra
    # algún mapa—, pero sin esto el primero que no lo esté no compilaría.
    for comandos in comandos_de_las_tropas(db):
        pares |= pares_de_habilidad_de_comandos(comandos)
    pares = {(a, s) for a, s in pares if a in db.actors and s in db.skills}
    return {par: ranura for ranura, par in enumerate(sorted(pares))}


def indexar_habilidades(game_dir, extra=()):
    """Deja en `HABILIDAD_RANURA` el índice del juego entero. Lo llama el
    conversor antes de compilar nada, como `indexar_variables`."""
    HABILIDAD_RANURA.clear()
    HABILIDAD_RANURA.update(pares_de_habilidad(game_dir, extra))
    if len(HABILIDAD_RANURA) > HABILIDAD_RANURAS_MAX:
        raise SystemExit("los pares de habilidad son %d y `FAR_HAB` lleva %d"
                         % (len(HABILIDAD_RANURA), HABILIDAD_RANURAS_MAX))
    return dict(HABILIDAD_RANURA)


def ranura_de_habilidad(actor, habilidad):
    if (actor, habilidad) not in HABILIDAD_RANURA:
        raise NoSePuede("el par actor %d, habilidad %d no tiene ranura"
                        % (actor, habilidad))
    return HABILIDAD_RANURA[(actor, habilidad)]


def indexar_variables(game_dir, extra=()):
    """Deja en `VARIABLE_SLOT` el índice del juego entero. Lo llaman el
    conversor y la referencia antes de compilar nada; tarda un tercio de
    segundo en leer los 328 mapas."""
    VARIABLE_SLOT.clear()
    VARIABLE_SLOT.update(variables_de(game_dir, None, extra))
    return dict(VARIABLE_SLOT)


def ranura_de_variable(numero):
    if numero not in VARIABLE_SLOT:
        raise NoSePuede("la variable %d no tiene ranura en esta ROM" % numero)
    ranura = VARIABLE_SLOT[numero]
    if ranura > VAR_RANURA_MAX:
        # El bit de arriba de la ranura es `VAR_REFRESCO`. Con más de 128
        # variables una ranura lo pisaría y todas las escrituras pedirían
        # refresco: se rompe acá, que es donde se ve.
        raise NoSePuede("la ranura %d no entra en siete bits: ver VAR_REFRESCO"
                        % ranura)
    return ranura


def escritura_pide_refresco(numero, eventos_mapa):
    """El bit `VAR_REFRESCO` para una escritura sobre la variable `numero`.

    Es `SetNeedRefreshForVarChange` resuelto al compilar: sólo piden refresco
    las variables que alguna condición de página del mapa mira. **Sin el mapa
    se pide siempre**, que es lo que hacía el port antes de esto y lo único
    honesto cuando no se sabe quién mira qué.
    """
    if eventos_mapa is None or eventos_mapa.vars_observadas is None:
        return VAR_REFRESCO     # sin el mapa, o después de irse de él
    return VAR_REFRESCO if numero in eventos_mapa.vars_observadas else 0


def azar_siguiente(x):
    """El paso del xorshift, en dieciséis bits."""
    x ^= (x << 7) & 0xFFFF
    x ^= x >> 9
    x ^= (x << 8) & 0xFFFF
    return x

# El tope del oro en RM2k: `Game_Party::GainGold` recorta a
# `MaxGoldValue()`, que por omisión es esto.
ORO_MAX = 999999

# Cuántos switches entra el bitmap de la ROM: `SWITCH_BYTES` son 128, o sea del
# 0 al 1023. Una rama sobre uno más alto escribiría fuera, así que no compila.
SWITCH_MAX = 1024


# `ShowChoice` y sus dos acompañantes, de `event_codes.py`. El `10` que cierra
# el cuerpo de cada opción es `END`, y no hace falta mirarlo: el salto al final
# de la elección se emite en la opción siguiente, que es donde se sabe que la
# anterior terminó.
SHOW_CHOICE = 10140
SHOW_CHOICE_OPTION = 20140
SHOW_CHOICE_END = 20141

# RM2k muestra cuatro opciones como mucho, y `GetChoices(4)` descarta las de
# índice mayor. La ventana de esta ROM tiene cuatro renglones, así que el tope
# es el mismo por los dos lados.
ELEGIR_MAX = 4

# El cursor, y lo que se le pone adelante a las opciones que no lo tienen para
# que el texto no se corra de renglón a renglón.
ELEGIR_CURSOR = ">"
ELEGIR_SANGRIA = " "


def opciones_de_eleccion(comandos, i):
    """Las opciones de la `ShowChoice` que está en `comandos[i]`.

    Es `Game_Interpreter::GetChoices`: se recorre hacia adelante desde el
    comando siguiente, se juntan los `ShowChoiceOption` que estén en su misma
    indentación y se corta en el `ShowChoiceEnd`. Devuelve (índice, texto).
    """
    if i + 1 >= len(comandos):
        return []
    nivel = comandos[i + 1].indent
    salida = []
    for cmd in comandos[i + 1:]:
        if cmd.indent != nivel:
            continue
        if cmd.code == SHOW_CHOICE_END:
            break
        if cmd.code == SHOW_CHOICE_OPTION and cmd.parameters \
                and cmd.parameters[0] < ELEGIR_MAX:
            salida.append((cmd.parameters[0], cmd.string or ""))
    return salida


def cuadros_de_eleccion(opciones, mensajes):
    """Un desplazamiento de `mensajes` por opción, con el cursor en su renglón.

    Los cuadros son iguales salvo por el cursor. `Mensajes` deduplica por
    contenido, así que las líneas comunes no se guardan de más: lo que se paga
    es un cuadro chico por opción.
    """
    textos = [t for _, t in opciones]
    return [mensajes.agregar(
                [(ELEGIR_CURSOR if k == n else ELEGIR_SANGRIA) + " " + t
                 for k, t in enumerate(textos)])
            for n in range(len(textos))]


def bytes_de_rama(cmd):
    """Un `ConditionalBranch` de las clases que sabemos, con el destino en blanco.

    Cinco de las doce clases: switch, variable, oro, objeto y actor; y de la de
    actor, tres de sus siete preguntas —está en el grupo, sabe la habilidad y
    tiene puesto el objeto—. Las que faltan piden estado que este port no lleva
    —el nivel, los HP y el estado de un actor, la orientación de un personaje,
    el cronómetro, el vehículo— y una rama sobre cualquiera de ésas daría
    siempre la misma respuesta, así que ni siquiera se podría probar. Las dos
    que más valdrían están medidas arriba, donde las constantes: **ninguna
    destraba una sola página**.

    La polaridad se copia tal cual de RM2k y quiere decir cosas distintas según
    la clase: en un switch, 0 es "tiene que estar prendido"; en el objeto, 0 es
    "tiene que tenerlo"; en el oro, 0 es ">=" y 1 es "<=". Es el
    `com.parameters[2]` de allá, sin traducir.
    """
    p = cmd.parameters
    if len(p) < 3:
        raise NoSePuede("una rama sin operandos")
    if p[0] == COND_SWITCH:
        numero = p[1]
        if not 0 <= numero < SWITCH_MAX:
            raise NoSePuede("switch %d fuera del bitmap" % numero)
    elif p[0] == COND_ORO:
        numero = p[1]
        if not 0 <= numero <= 0xFFFF:
            # El operando viaja en una palabra. En este juego el más grande es
            # 2000, así que no se pierde nada; si algún día aparece uno mayor,
            # esto lo dice en vez de compararlo mal.
            raise NoSePuede("comparación de oro contra %d, que no entra en una "
                            "palabra" % numero)
    elif p[0] == COND_ITEM:
        numero = p[1]
        if not 0 <= numero < ITEMS_N:
            raise NoSePuede("el ítem %d no está en el LDB" % numero)
    elif p[0] == COND_ACTOR:
        numero = p[1]
        if not 0 <= numero <= 0xFFFF:
            raise NoSePuede("actor %d fuera de rango" % numero)
        if p[2] == COND_ACTOR_EN_GRUPO:
            # "Está en el grupo" no tiene polaridad: la rama de abajo es el
            # `else`.
            return bytes([OP_IF, COND_ACTOR, numero & 0xFF, numero >> 8,
                          0, 0, 0])
        if p[2] in (COND_ACTOR_HABILIDAD, COND_ACTOR_EQUIPO):
            if len(p) < 4:
                raise NoSePuede("una rama de actor sin el objeto ni la "
                                "habilidad")
            if not 0 <= numero <= 0xFF:
                # El actor viaja en un byte: ver OP_IF_ACTOR. El LDB tiene 60.
                raise NoSePuede("actor %d, que no entra en un byte" % numero)
            if _ACTORES_INDEXADOS and numero not in ACTOR_EQUIPO:
                # Las tablas de la ROM van del 0 al último actor del LDB, así
                # que un número de más se leería fuera de la tabla. RM2k avisa
                # y se va por el `else`; acá no compila, que es lo que este
                # port hace con todo lo que no puede contestar. Ninguna página
                # del juego lo hace: se comprueba sólo cuando el índice está
                # cargado, para no cambiarle la respuesta a quien compile sin
                # llamar a `indexar_actores`.
                raise NoSePuede("el actor %d no está en el LDB" % numero)
            dato = p[3]
            if p[2] == COND_ACTOR_HABILIDAD:
                # La habilidad viaja como la ranura de su par: es el bit que
                # la ROM mira, y así no tiene que buscar. Ver
                # `HABILIDAD_RANURA`.
                dato = ranura_de_habilidad(numero, dato)
            if not 0 <= dato <= 0xFFFF:
                raise NoSePuede("una rama de actor contra %d, que no entra en "
                                "una palabra" % dato)
            return bytes([OP_IF_ACTOR, p[2], numero,
                          dato & 0xFF, dato >> 8, 0, 0])
        raise NoSePuede("del héroe sabemos si está en el grupo, si sabe una "
                        "habilidad y qué tiene puesto, y no la %d" % p[2])
    elif p[0] == COND_VARIABLE:
        if len(p) < 5:
            raise NoSePuede("una rama por variable sin operandos")
        ranura = ranura_de_variable(p[1])
        if p[2] == 0:
            clase, valor = VAR_CONSTANTE, p[3]
            if not -0x8000 <= valor <= 0x7FFF:
                raise NoSePuede("comparación contra %d, que no entra en un "
                                "word con signo" % valor)
        elif p[2] == 1:
            clase, valor = VAR_VARIABLE, ranura_de_variable(p[3])
        else:
            raise NoSePuede("rama por variable contra algo que no sabemos")
        if not 0 <= p[4] <= CMP_DISTINTO:
            raise NoSePuede("comparación %d que no existe" % p[4])
        return bytes([OP_IF_VAR, ranura, clase, p[4], valor & 0xFF,
                      (valor >> 8) & 0xFF, 0, 0])
    else:
        raise NoSePuede("rama sobre una condición que no sabemos hacer")
    return bytes([OP_IF, p[0], numero & 0xFF, numero >> 8,
                  1 if p[2] else 0, 0, 0])


class Tropas:
    """Las tropas que las peleas compiladas piden, para saber qué tablas emitir.

    Hermano de `Temas`, con una diferencia que importa: **el bytecode no
    depende de él**. `Temas` numera y el opcode lleva el número; acá el opcode
    lleva el id de RM2k y esto sólo junta la lista, así que un registro con
    otras tropas adentro no cambia un solo byte de ninguna página. Es lo que
    permite que la referencia compile sin saber qué tablas tiene el cartucho.
    """

    def __init__(self):
        self.ids = []
        # Y con qué fondo pelea cada una, que es el texto del propio
        # `EnemyEncounter` —`SJBackdropABL04` en el mapa 2— y no algo que haya
        # que buscar en el LDB. Va acá y no en un registro aparte porque es un
        # dato de la pelea, como la tropa. Ver tools/port/escena.py.
        self.fondos = {}

    def pedir(self, numero, fondo=None):
        if numero not in self.ids:
            self.ids.append(numero)
        if fondo and numero not in self.fondos:
            self.fondos[numero] = fondo
        return numero


# --- las páginas de evento de las tropas ---------------------------------------
#
# `Game_Interpreter_Battle`: cada tropa trae sus páginas, y la pelea las corre
# **con el mismo intérprete que los mapas**, `correr_codigo`, así que se
# compilan con el mismo `compilar_pagina`. Lo único que cambia es qué se
# acepta: ver `TROPA_COMANDOS`.
#
# Cuándo corre cada una lo decide la ROM y está copiado de
# `Scene_Battle_Rpg2k`; ver `ba_pag_probar` en rom/src/batalla_tropa.s.

# Los tres comandos de rama de la pelea, con su gemelo del mapa. De las seis
# preguntas de `CommandConditionalBranchBattle` el juego usa **sólo dos** —el
# switch y la variable, en 1108 ramas de 295 cuerpos distintos, medido el
# 2026-09-21— y ésas tienen los operandos en el mismo lugar que las del mapa:
# `[clase, número, polaridad o clase del valor, valor, comparación, else]`.
# Así que se traducen al código del mapa y compilan a OP_IF y OP_IF_VAR sin
# un opcode nuevo. Las otras cuatro —si un actor o un enemigo puede actuar, a
# quién apunta, qué orden dio— piden estado de la pelea y no compilan.
RAMA_DE_PELEA = {13310: COND_RAMA, 23310: COND_SINO, 23311: COND_FIN}
RAMA_DE_PELEA_CLASES = (COND_SWITCH, COND_VARIABLE)

# Lo que una página de tropa puede hacer en este port. **Es una lista de los que
# sí, no de los que no**, a propósito: casi todo lo que compila en un mapa
# supone el mapa —un teletransporte, una ruta, un tinte, una elección, que abre
# la ventana del mapa— y adentro de la pelea haría otra cosa sin avisar.
#
# Los que quedan afuera y el juego usa, por si alguien los quiere sumar:
# `ChangeHP` y `FullHeal` —en la pelea los HP viven en `BA_UNO` y `FAR_HP`
# se pisa al cerrarla—, `ChangePartyMembers`, `ChangeEquipment`, `PlaySound`,
# `Wait`, `TintScreen` y los seis que sólo existen en la pelea.
TROPA_COMANDOS = ({END, SHOW_MESSAGE, SHOW_MESSAGE_2, CONTROL_SWITCHES,
                   CONTROL_VARS, CHANGE_SKILLS, CHANGE_GOLD, CHANGE_ITEMS,
                   COND_RAMA, COND_SINO, COND_FIN} | IGNORABLES)

# Qué disparadores sabe mirar la ROM, con su bit en `tpag_flags`. Los demás
# —el turno, los HP de un actor o de un enemigo— dejan la página afuera: el
# 2026-09-21 son 173 de las 4588 páginas del juego, y ninguna de los 32
# sistemas de los personajes, que dependen sólo de `switch_a`.
TROPA_DISPARO_SWITCH_A = 0x01
TROPA_DISPARO_SWITCH_B = 0x02
TROPA_DISPARO_VARIABLE = 0x04
TROPA_DISPAROS = {"switch_a": TROPA_DISPARO_SWITCH_A,
                  "switch_b": TROPA_DISPARO_SWITCH_B,
                  "variable": TROPA_DISPARO_VARIABLE}
# Cuántas páginas de una tropa anota la pelea como "ya corrió este turno", un
# byte cada una en `BA_PAG_HECHA`. Es un tope de la RAM lejana y no del juego:
# el conversor se corta si alguna tropa pasa.
TROPA_PAGINAS_MAX = 32


def comandos_de_tropa(comandos):
    """Los comandos de una página de tropa como si fueran de un mapa, o
    `NoSePuede` si alguno no está en `TROPA_COMANDOS`.

    Devuelve copias: los de la base los comparten todas las tropas que tienen
    la misma página, y traducirlos en el lugar los dejaría traducidos para
    quien los lea después."""
    from rpgmaker import lcf
    salida = []
    for cmd in comandos:
        codigo = RAMA_DE_PELEA.get(cmd.code, cmd.code)
        if cmd.code == 13310 and (not cmd.parameters
                                  or cmd.parameters[0]
                                  not in RAMA_DE_PELEA_CLASES):
            raise NoSePuede("una rama de pelea que pregunta por la pelea")
        if codigo not in TROPA_COMANDOS:
            raise NoSePuede("el comando %d no corre en una página de tropa"
                            % cmd.code)
        salida.append(lcf.EventCommand(codigo, cmd.indent, cmd.string,
                                       cmd.parameters))
    return salida


def disparo_de_tropa(pagina):
    """`(flags, switch_a, switch_b, ranura, valor)` de la condición de una
    página de tropa, o None si mira algo que la ROM no sabe mirar.

    Una página **sin ningún disparador no corre nunca** —`AreConditionsMet`
    devuelve false de entrada— y también da None: no tiene sentido llevarla.
    La de variable es `>=`, siempre: RM2k no le da operador."""
    if not pagina.activos:
        return None
    if any(a not in TROPA_DISPAROS for a in pagina.activos):
        return None
    c = pagina.condicion
    flags = 0
    for a in pagina.activos:
        flags |= TROPA_DISPAROS[a]
    switch_a = c["switch_a_id"] if "switch_a" in pagina.activos else 0
    switch_b = c["switch_b_id"] if "switch_b" in pagina.activos else 0
    for s in (switch_a, switch_b):
        if not 0 <= s < SWITCH_MAX:
            return None
    ranura, valor = 0, 0
    if "variable" in pagina.activos:
        valor = c["variable_value"]
        if not -0x8000 <= valor <= 0x7FFF:
            return None
        try:
            ranura = ranura_de_variable(c["variable_id"])
        except NoSePuede:
            return None
    return flags, switch_a, switch_b, ranura, valor


class PaginasDeTropa:
    """Las páginas de las tropas del cartucho, compiladas y deduplicadas.

    `cuerpos` es el código de todas, uno detrás del otro y **cada cuerpo
    distinto una sola vez**: el juego copia las páginas de sus sistemas en
    cada tropa —4588 páginas y 295 cuerpos distintos—, así que la clave es el
    bytecode ya compilado, igual que `Materiales` con los bloques del mapa.

    Los mensajes van a **su propio bloque**, `mensajes_tropa`, y no al de los
    mapas: `OP_MESSAGE` lleva un desplazamiento de dieciséis bits y el bloque
    de los mapas del cartucho de pruebas ya anda por los 65 KB. La pelea los
    dibuja en su pantalla y no en la ventana del mapa, así que leerlos de otro
    lado no le cuesta nada.
    """

    def __init__(self):
        self.mensajes = Mensajes()
        self.cuerpos = bytearray()
        self.donde = {}             # bytecode -> desplazamiento en `cuerpos`
        self.por_tropa = {}         # tropa -> [(flags, a, b, ranura, valor, ofs)]
        self.paginas = 0            # cuántas se miraron
        self.afuera = 0             # y cuántas no entraron

    def compilar(self, numero, tropa):
        suyas = []
        for pagina in tropa.pages:
            self.paginas += 1
            disparo = disparo_de_tropa(pagina)
            codigo = None
            if disparo is not None:
                try:
                    comandos = comandos_de_tropa(pagina.commands)
                except NoSePuede:
                    comandos = None
                if comandos is not None:
                    codigo = compilar_pagina(_Comandos(comandos),
                                             lambda _mapa: None,
                                             self.mensajes)
            if codigo is None:
                self.afuera += 1
                continue
            codigo = bytes(codigo)
            if codigo not in self.donde:
                self.donde[codigo] = len(self.cuerpos)
                self.cuerpos += codigo
            suyas.append(disparo + (self.donde[codigo],))
        self.por_tropa[numero] = suyas
        return suyas


# --- los encuentros al azar -------------------------------------------------
#
# Todo lo de acá sale de easyrpg-player —`Game_Player::UpdateEncounterSteps`,
# `Game_Map::GetEncountersAt` y `Game_Map::PrepareEncounter`— y no de la
# intuición, que en este repo ya costó tres veces.
#
# **Dónde viven los datos**: no en el `.lmu` sino en el árbol, `RPG_RT.lmt`.
# Cada nodo —mapa o *área*— trae `encounters` (una lista de tropas),
# `encounter_steps` (25 por omisión, 0 = apagados) y `area_rect`. Un área es un
# nodo de tipo 2: no tiene `.lmu`, cuelga de un mapa y le tapa un rectángulo.
# Ver `lcf.TreeMap`.
#
# **Cómo se dispara**, paso por paso del héroe y sólo los del pad —una ruta
# forzada sale por `IsMoveRouteOverwritten` antes de `IncSteps`, así que no
# cuenta—:
#
#     acumulado += encounter_rate del terreno donde está parado
#     ratio = acumulado / encounter_steps           (entera)
#     mientras ratio >= TABLA[idx + 1][0]: idx++    (idx no baja nunca)
#     p = (1 / encounter_steps) * pmod * (rate / 100)
#     si sale, acumulado = 0 e idx = 0, y queda un encuentro pendiente
#
# El pendiente se cobra en el cuadro siguiente, con el héroe ya parado: se
# juntan las tropas del mapa más las de cada área que tape su celda y se elige
# una al azar. Si no hay ninguna —el héroe está afuera de todas las áreas— no
# pasa nada, que es lo que hace `PrepareEncounter` al volver `false`.
#
# **Dos simplificaciones, las dos medidas sobre el juego entero** y cobradas
# por `pruebas/herramientas/test_encuentros.py`, que es lo que evita que se vuelvan mentira
# el día que alguien toque los datos:
#
# * **el terreno no cambia nada**: los once tags de terreno que pisan los 53
#   mapas con encuentros tienen `encounter_rate` 100, así que el acumulado sube
#   de a 100 siempre y el factor `rate / 100` es 1;
# * **ninguna tropa filtra por terreno**: las 129 que los encuentros nombran
#   tienen el `terrain_set` vacío, y en RM2k vacío quiere decir "en todos".
#
# Con eso el modelo queda entero en enteros, que es lo que la consola puede
# hacer sin punto flotante: ver `enc_umbrales_de_paso`.

# Cada cuántos pasos, por omisión, si el nodo no trae el chunk (liblcf:
# rpg::MapInfo::encounter_steps).
ENC_PASOS_DEFECTO = 25

# El tipo de nodo del árbol que es un área. Ver `lcf.TreeMap.map_types`.
TREE_AREA = 2

# La tabla de `UpdateEncounterSteps`, en (ratio mínimo, exponente de pmod): los
# ocho `pmod` de easyrpg son potencias de dos —1/16, 1/8, 1/4, 1/2, 2, 4, 8,
# 16— así que acá van como corrimientos y la cuenta no necesita flotantes. La
# novena fila de allá es `{INT_MAX, 16.0}`, o sea un tope que no se alcanza
# nunca: el `while` no pasa de la última de éstas.
ENC_TABLA = ((0, -4), (20, -3), (40, -2), (60, -1),
             (100, 1), (140, 2), (160, 3), (180, 4))

# El `encounter_rate` con el que sube el acumulado: el del terreno, que en este
# juego es 100 en los 53 mapas con encuentros. Ver arriba.
ENC_RATE = 100

# La semilla del azar de los encuentros. Es otra que `AZAR_SEMILLA` y otra que
# `BATALLA_SEMILLA` a propósito, y por lo mismo que aquélla: caminar no le
# corre el azar al mapa —un `ControlVars` al azar tiene que dar lo mismo con
# encuentros y sin ellos— y la referencia de pixeles necesita que los dos lados
# tiren los mismos números. Lo único que se le pide es no ser cero —el xorshift
# se queda clavado— y ser el mismo de los dos lados.
ENC_SEMILLA = 0x5A17


def enc_base(pasos):
    """El `1 / encounter_steps` de la fórmula, en 1/65536.

    La chance de un paso es `pmod / pasos`, y `pmod` es una potencia de dos: si
    el cociente se precalcula acá, en la consola queda un corrimiento y una
    comparación de dieciséis bits, sin división. **El truncamiento es parte del
    contrato**: los dos lados usan este mismo número.

    Cero quiere decir apagados, que es lo que `encounter_steps` 0 significa en
    RM2k.
    """
    return 0 if pasos <= 0 else 0x10000 // pasos


def enc_umbrales_de_paso(pasos):
    """En qué paso se cruza cada fila de `ENC_TABLA`, contando desde cero.

    Allá la comparación es `ratio >= fila`, con `ratio = acumulado / pasos`
    entera y `acumulado = 100 * n`. Como la fila es entera,

        acumulado / pasos >= fila   <=>   100 * n >= fila * pasos

    o sea `n >= ceil(fila * pasos / 100)`, que es lo que se emite: siete bytes
    por mapa y ni una división en la consola. La primera fila es el 0 y no
    hace falta.
    """
    return [-(-fila * pasos // ENC_RATE) for fila, _ in ENC_TABLA[1:]]


def enc_umbral(base, idx):
    """La chance del paso, en 1/65536, o None si es "siempre".

    `pmod` corre `base` para un lado o para el otro. Con pasos chicos —los que
    pone `ChangeEncounterSteps`, o una ROM de prueba— `pmod / pasos` puede
    pasar de 1, y ahí RM2k tiene la certeza: `PercentChance` con `rate >= 1`
    da siempre que sí. En la consola eso es el acarreo del corrimiento.
    """
    corrimiento = ENC_TABLA[idx][1]
    if corrimiento < 0:
        return base >> -corrimiento
    valor = base << corrimiento
    return None if valor >= 0x10000 else valor


def zonas_de_encuentro(tree, map_id, ancho, alto):
    """Las zonas de un mapa: la suya y una por área que le cuelgue.

    Una zona es (izquierda, arriba, derecha, abajo, tropas) con el rectángulo
    **semiabierto**, que es lo que dice `Rect::IsOutOfBounds`: adentro es
    `l <= x < r` y `t <= y < b`. La del mapa tapa el mapa entero.

    El orden es el de `GetEncountersAt`, que recorre el árbol por índice: en
    este juego ningún mapa tiene tropas propias **y** áreas —medido—, así que
    poner la suya primero no puede cambiar qué tropa sale.
    """
    zonas = []
    if tree.encounters.get(map_id):
        zonas.append((0, 0, ancho, alto, list(tree.encounters[map_id])))
    for i in sorted(tree.map_types):
        if (tree.map_types[i] == TREE_AREA and tree.map_parents.get(i) == map_id
                and tree.encounters.get(i)):
            izq, arr, der, aba = tree.area_rect[i]
            zonas.append((izq, arr, der, aba, list(tree.encounters[i])))
    return zonas


class Encuentros:
    """El estado de los encuentros de una partida, igual de los dos lados.

    Lo usan las pruebas; la ROM hace lo mismo con las tablas que emite el
    conversor. Quien lo cambie tiene que cambiar `rom/src/` en el mismo
    commit: si no, el modelo y la consola dejan de ser el mismo programa.
    """

    def __init__(self, pasos, zonas, semilla=ENC_SEMILLA):
        self.zonas = list(zonas)
        self.poner_pasos(pasos)
        self.semilla = semilla
        self.reiniciar()

    def poner_pasos(self, pasos):
        """`encounter_steps` del mapa: al entrar, y `ChangeEncounterSteps`."""
        self.pasos = pasos
        self.base = enc_base(pasos) if self.zonas else 0
        self.umbrales = enc_umbrales_de_paso(pasos)

    def reiniciar(self):
        """El `SetTotalEncounterRate(0)` de `Game_Player::MoveTo`: todo
        teletransporte —y toda puerta— pone el acumulado en cero."""
        self.n = 0
        self.idx = 0
        self.pendiente = False

    def _azar(self):
        self.semilla = azar_siguiente(self.semilla)
        return self.semilla

    def paso(self):
        """Un paso del héroe con el pad. Devuelve si quedó un encuentro
        pendiente."""
        if not self.base:
            self.n = 0
            self.idx = 0
            return False
        # Se topa en 255 porque del otro lado es un byte. No cambia nada y hay
        # que decirlo: el umbral más alto del juego son 153 pasos —el mapa 258,
        # con 85—, así que para cuando `n` llegara al tope la fila ya es la
        # última y dejó de mirarse. Pero los dos lados tienen que **contar
        # igual**, y allá el contador no da la vuelta.
        self.n = min(255, self.n + 1)
        while (self.idx + 1 < len(ENC_TABLA)
               and self.n >= self.umbrales[self.idx]):
            self.idx += 1
        umbral = enc_umbral(self.base, self.idx)
        salio = umbral is None or self._azar() < umbral
        if salio:
            self.n = 0
            self.idx = 0
            self.pendiente = True
        return salio

    def candidatas(self, x, y):
        """Las tropas que se pueden pelear en esa celda: las del mapa más las
        de cada área que la tape. Es `GetEncountersAt`."""
        salida = []
        for izq, arr, der, aba, tropas in self.zonas:
            if izq <= x < der and arr <= y < aba:
                salida += tropas
        return salida

    def elegir(self, x, y):
        """El `PrepareEncounter` del cuadro siguiente: qué tropa se pelea, o
        None si en esa celda no hay ninguna."""
        self.pendiente = False
        tropas = self.candidatas(x, y)
        if not tropas:
            return None
        return tropas[self._azar() % len(tropas)]


def tropa_de_encuentro(cmd):
    """El número de tropa de un `EnemyEncounter`, o `NoSePuede`.

    Los índices salen de `Game_Interpreter_Map::CommandEnemyEncounter` de
    easyrpg-player, **no de memoria**: `[0]` dice si la tropa sale de una
    variable, `[1]` es la tropa, `[2]` de dónde sale el fondo, `[3]` qué pasa
    al huir, `[4]` qué pasa al perder y `[5]` si el grupo pega primero.

    Lo que este port hace, y por qué lo demás corta la página:

    * **la tropa por constante**: leerla de una variable pediría resolver en la
      ROM qué tropa es, y ninguna de las 51 peleas del juego lo usa;
    * **huir prohibido o con manejador**, pero no `escape_mode` 1, que en RM2k
      corta la página entera al escapar —`abort_on_escape`— y sería un camino
      sin nada que lo ejercite;
    * **perder**, con manejador o sin él: `defeat_mode` 0 es la pantalla de
      Game Over de RM2k, y desde el 2026-09-13 se emite como `BATALLA_PERDER`
      en el destino de la derrota. La ROM la resuelve volviendo al arranque
      —o sea a la pantalla de título, con la partida guardada esperando en la
      SRAM— que es lo que `Scene_Gameover` hace después de mostrar su imagen.
      **La imagen no se dibuja**, y eso es deuda declarada en
      `workflow/divergencias/game-over-sin-imagen-ni-tema.md`; lo que no se
      hace es lo de antes, que era no compilar la página: costaba 15, entre
      ellas el jefe de los Rat Tracks.

    El fondo no se mira: la pantalla de batalla va sobre un color plano, que es
    lo que taro pidió para esta vuelta. Ver workflow/tasks/done/battle.md.
    """
    p = cmd.parameters
    if len(p) < 6:
        raise NoSePuede("EnemyEncounter sin operandos")
    if p[0] != 0:
        raise NoSePuede("EnemyEncounter con la tropa en una variable")
    if not 0 < p[1] <= 0xFFFF:
        raise NoSePuede("EnemyEncounter de la tropa %d" % p[1])
    if p[3] == BATALLA_ESCAPE_CORTA:
        raise NoSePuede("EnemyEncounter que corta la página al huir")
    return p[1]


def fondo_de_encuentro(cmd):
    """El fondo de batalla que nombra el `EnemyEncounter`, o "".

    El parámetro `[2]` de `CommandEnemyEncounter` dice de dónde sale el fondo:
    1 es "el que dice este comando", que es lo que hacen las 51 peleas del
    juego, y 0 sería el del terreno. El nombre viaja en el string del comando.
    """
    p = cmd.parameters
    return cmd.string if len(p) > 2 and p[2] == BATALLA_FONDO_DEL_COMANDO else ""


def actor_de_blanco(p, que):
    """El operando de actor de OP_HEAL y de OP_EQUIPMENT, desde el `[tipo, id]`
    de RM2k.

    Es `GetActors` de easyrpg (`game_interpreter.cpp:1539`): 0 el grupo, 1 un
    actor fijo, 2 el actor que diga una variable. El operando es el actor, con
    0 por "todo el grupo": el LDB no tiene actor 0, así que no se confunde con
    nadie.

    La forma 2 no la usa ningún `FullHeal` ni ningún `ChangeHP` que sume
    —medido el 2026-09-19 sobre los 328 mapas y los eventos comunes—, ni
    ningún `ChangeEquipment` —el 2026-09-21—, así que
    no compila en vez de resolverse en la ROM sin nada que la ejercite.
    """
    if p[0] == 0:
        return 0
    if p[0] == 1 and 0 < p[1] <= 0xFF:
        return p[1]
    raise NoSePuede("%s con el actor en una variable" % que)


def con_destino(pieza, destino):
    """La misma pieza con el destino puesto en sus dos últimos bytes."""
    return pieza[:-2] + bytes([destino & 0xFF, destino >> 8])


def compilar_pagina(page, indice_de_mapa, mensajes=None, eventos_mapa=None,
                    temas=None, graficos=None, imagenes=None, tropas=None,
                    base=0, hondo=0):
    """Los comandos de una página como bytes, o None si no se puede.

    `indice_de_mapa` traduce el id de mapa de RM2k al índice en la tabla de la
    ROM, y devuelve None para los mapas que no entraron en el cartucho: un
    teletransporte hacia uno de ésos hace que la página no sea ejecutable, que
    es más honesto que saltar a cualquier lado.

    `mensajes` es el bloque de textos de la ROM. Sin él los cuadros de texto no
    compilan, y no es una opción de gusto: la ventana ocupa 8 KB de VRAM y una
    paleta, así que una ROM que no la lleve no tiene dónde dibujarlos.

    `eventos_mapa` es el `Eventos` del mapa, ya apuntado al dueño de la página.
    Sin él una ruta forzada sólo puede ser sobre el héroe: no hay con qué
    traducir el id de RM2k al índice de la tabla.

    `tropas` es el registro de las tropas que el cartucho va a tener que
    llevar. **No cambia el bytecode** —el número de tropa que se emite es el de
    RM2k— así que una ROM sin registro compila exactamente lo mismo; lo único
    que se pierde es saber qué tablas hay que emitir.

    `base` y `hondo` son para `CallEvent`, que se compila **en línea**: el
    cuerpo del evento llamado se emite en el lugar de la llamada. `base` es
    dónde arranca este pedazo adentro de la página de afuera, porque los
    destinos de las ramas son absolutos; `hondo` es el anidamiento, que se
    topa. Un pedazo en línea **no lleva `OP_DONE`**: en RM2k el `END` del
    evento llamado devuelve al que llamó, no termina la página.
    """
    marca = mensajes.marca() if mensajes is not None else None
    try:
        # Las ramas se emiten con el destino en blanco y se parchean al
        # cerrarlas, que es la única manera: hasta que no se compiló lo de
        # adentro no se sabe cuánto ocupa. La pila lleva el anidamiento, así
        # que no hace falta mirar la indentación como hace
        # `SkipToNextConditional` —él recorre la lista de comandos, acá los
        # bloques ya vienen bien anidados—.
        piezas = []
        largo = base         # ver `base`: los destinos de las ramas son
                             # absolutos adentro de la página de afuera
        pila = []            # piezas con el destino todavía en blanco
        # Las opciones de cada `ShowChoice` se juntan mirando hacia adelante,
        # que es lo que hace `GetChoices`, así que se resuelven antes del lazo:
        # acá adentro los comandos vienen de a uno y ya agrupados.
        comandos = list(page.commands)
        opciones_de = {id(c): opciones_de_eleccion(comandos, i)
                       for i, c in enumerate(comandos) if c.code == SHOW_CHOICE}
        # Qué `EnemyEncounter` vienen **sin bloque de manejadores**. RM2k no lo
        # emite cuando la pelea no tiene ninguna rama que escribir, que es
        # exactamente lo que pasa con `defeat_mode` 0: perder es la pantalla de
        # Game Over y no una rama de la página. Son las 15 páginas del juego
        # que este port no compilaba —entre ellas el jefe de los Rat Tracks—, y
        # las 15 son así: sin esto, aceptar el Game Over las dejaba caer en
        # "una batalla sin cerrar". Se mira adelante como las opciones de un
        # `ShowChoice`, porque adentro del lazo los comandos vienen de a uno.
        sin_bloque = {id(c) for i, c in enumerate(comandos)
                      if c.code == ENEMY_ENCOUNTER
                      and (i + 1 >= len(comandos)
                           or comandos[i + 1].code not in BATALLA_HANDLERS)}
        eleg = []            # las elecciones abiertas
        bat = []             # y las batallas abiertas, igual que ellas
        for cmd, extra in agrupar(comandos):
            if cmd.code == ENEMY_ENCOUNTER:
                tropa = tropa_de_encuentro(cmd)
                if tropas is not None:
                    tropas.pedir(tropa, fondo_de_encuentro(cmd))
                # El tema y los efectos que la pelea hace sonar, anotados en el
                # paquete de audio de este mapa. Va de los dos lados: ver
                # `audio_de_batalla`.
                audio_de_batalla(temas)
                perder_es_game_over = (len(cmd.parameters) > 4
                                       and cmd.parameters[4]
                                       == BATALLA_DERROTA_GAME_OVER)
                if id(cmd) in sin_bloque:
                    # Sin manejadores: la pelea se cierra acá mismo. Ganar y
                    # huir siguen por el comando de abajo —que es lo que hace
                    # RM2k cuando no hay ramas— y perder va a `BATALLA_PERDER`,
                    # o sea al Game Over.
                    #
                    # **Huir apunta a la victoria y no a otro lado**, y es una
                    # aproximación declarada: las 24 peleas de esta forma traen
                    # `escape_mode` 0 —huir prohibido—, así que allá la salida
                    # no existe; acá la pelea deja huir igual, porque el
                    # permiso no viaja en el opcode: `ChangeEscapeAccess` se
                    # acepta y no se hace.
                    sigue = largo + 9
                    perder = (BATALLA_PERDER if perder_es_game_over
                              else sigue)
                    pieza = bytes([OP_BATTLE, tropa & 0xFF, tropa >> 8,
                                   sigue & 0xFF, sigue >> 8,
                                   sigue & 0xFF, sigue >> 8,
                                   perder & 0xFF, perder >> 8])
                else:
                    bat.append({"i": len(piezas), "tropa": tropa,
                                "destinos": [None, None, None],
                                "game_over": perder_es_game_over,
                                "vistas": 0, "salidas": []})
                    pieza = bytes(9)  # el lugar, que se llena en el EndBattle
            elif cmd.code in BATALLA_HANDLERS:
                if not bat:
                    raise NoSePuede("un manejador de batalla sin su pelea")
                actual = bat[-1]
                n = BATALLA_HANDLERS.index(cmd.code)
                # El cuerpo del manejador anterior termina acá y se lo saca del
                # bloque con un salto al final, que se parchea al cerrarlo. Es
                # lo mismo que hace `ShowChoiceOption`, y por lo mismo: así no
                # hay que mirar la indentación.
                pieza = b"" if not actual["vistas"] else bytes([OP_GOTO, 0, 0])
                if pieza:
                    actual["salidas"].append(len(piezas))
                actual["vistas"] += 1
                if actual["destinos"][n] is not None:
                    raise NoSePuede("dos manejadores de batalla iguales")
                actual["destinos"][n] = largo + len(pieza)
            elif cmd.code == END_BATTLE:
                if not bat:
                    raise NoSePuede("un fin de batalla sin su pelea")
                actual = bat.pop()
                tabla = bytes([OP_BATTLE,
                               actual["tropa"] & 0xFF, actual["tropa"] >> 8])
                for n, destino in enumerate(actual["destinos"]):
                    # El manejador que la página no tiene cae en el final del
                    # bloque, que es lo que hace RM2k con un sub-índice sin
                    # rama: `SetSubcommandIndex` y a seguir. **Salvo la
                    # derrota con `defeat_mode` 0**, que allá no es una rama
                    # que falta sino el Game Over: ver `BATALLA_PERDER`.
                    if destino is None and n == 2 and actual["game_over"]:
                        d = BATALLA_PERDER
                    else:
                        d = largo if destino is None else destino
                    tabla += bytes([d & 0xFF, d >> 8])
                piezas[actual["i"]] = tabla
                for salida in actual["salidas"]:
                    piezas[salida] = con_destino(piezas[salida], largo)
                pieza = b""
            elif cmd.code == SHOW_CHOICE:
                if mensajes is None:
                    raise NoSePuede("una elección sin ventana donde ponerla")
                opciones = opciones_de[id(cmd)]
                if not opciones:
                    raise NoSePuede("una elección sin opciones")
                if [n for n, _ in opciones] != list(range(len(opciones))):
                    raise NoSePuede("opciones numeradas fuera de orden")
                cancelar = cmd.parameters[0] if cmd.parameters else 0
                if cancelar > len(opciones):
                    # `cancel_type` 5 con cuatro opciones es la "rama de
                    # cancelar", una quinta que no está en la lista. Nadie la
                    # usa en este juego y hacerla a ciegas sería inventar.
                    raise NoSePuede("elección con rama de cancelar")
                cuadros = cuadros_de_eleccion(opciones, mensajes)
                eleg.append({"i": len(piezas), "n": len(opciones),
                             "cancelar": cancelar, "cuadros": cuadros,
                             "destinos": [None] * len(opciones),
                             "vistas": 0, "salidas": []})
                # El lugar de la tabla, que se llena en el `ShowChoiceEnd`.
                pieza = bytes(3 + 4 * len(opciones))
            elif cmd.code == SHOW_CHOICE_OPTION:
                if not eleg:
                    raise NoSePuede("una opción sin su elección")
                actual = eleg[-1]
                n = cmd.parameters[0] if cmd.parameters else 0
                if not 0 <= n < actual["n"]:
                    raise NoSePuede("una opción que no está en la lista")
                # El cuerpo de la opción anterior termina acá: se lo saca de la
                # elección con un salto al final, que se parchea al cerrarla.
                # Emitirlo acá y no en el `END` del cuerpo es lo que hace que
                # esto no dependa de mirar la indentación.
                pieza = b"" if not actual["vistas"] else bytes([OP_GOTO, 0, 0])
                if pieza:
                    actual["salidas"].append(len(piezas))
                actual["vistas"] += 1
                actual["destinos"][n] = largo + len(pieza)
            elif cmd.code == SHOW_CHOICE_END:
                if not eleg:
                    raise NoSePuede("un fin de elección sin su elección")
                actual = eleg.pop()
                if any(d is None for d in actual["destinos"]):
                    raise NoSePuede("una opción sin cuerpo")
                tabla = bytes([OP_CHOICE, actual["n"], actual["cancelar"]])
                for cuadro, destino in zip(actual["cuadros"],
                                           actual["destinos"]):
                    tabla += bytes([cuadro & 0xFF, cuadro >> 8,
                                    destino & 0xFF, destino >> 8])
                piezas[actual["i"]] = tabla
                for salida in actual["salidas"]:
                    piezas[salida] = con_destino(piezas[salida], largo)
                pieza = b""
            elif cmd.code == COND_RAMA:
                pila.append(len(piezas))
                pieza = bytes_de_rama(cmd)
            elif cmd.code == COND_SINO:
                if not pila:
                    raise NoSePuede("un `else` sin su `if`")
                abierta = pila.pop()
                pieza = bytes([OP_GOTO, 0, 0])
                # El destino del `if` es **después** de este salto, que es
                # donde arranca la rama de abajo; el del salto se resuelve en
                # el `end`, con la pieza que queda abierta en su lugar.
                piezas[abierta] = con_destino(piezas[abierta], largo + 3)
                pila.append(len(piezas))
            elif cmd.code == COND_FIN:
                if not pila:
                    raise NoSePuede("un `end` sin su `if`")
                abierta = pila.pop()
                piezas[abierta] = con_destino(piezas[abierta], largo)
                pieza = b""
            elif cmd.code == SHOW_INN:
                pieza = _compilar_posada(cmd, largo, mensajes)
            elif cmd.code in (INN_STAY, INN_NO_STAY, INN_END):
                # Las tres ramas de la posada. Ninguna de las 18 páginas del
                # juego las usa —medido—, y hacerlas pide lo que `_compilar_
                # posada` justamente no tiene: un lugar donde meter el cuerpo
                # de "se quedó" adentro de una elección que ya está armada.
                raise NoSePuede("una posada con sus ramas")
            elif cmd.code == CALL_EVENT:
                pieza = _compilar_llamada(cmd, largo, hondo, indice_de_mapa,
                                          mensajes, eventos_mapa, temas,
                                          graficos, imagenes, tropas)
            else:
                pieza = _compilar(cmd, indice_de_mapa, mensajes, extra,
                                  eventos_mapa, temas, graficos, imagenes)
                # Un salto a otro mapa: la página sigue corriendo allá. Ver
                # `Eventos.afuera`.
                if cmd.code == TELEPORT and eventos_mapa is not None \
                        and cmd.parameters[0] != eventos_mapa.map_id:
                    eventos_mapa = eventos_mapa.afuera()
            piezas.append(pieza)
            largo += len(pieza)
        if pila:
            raise NoSePuede("una rama sin cerrar")
        if eleg:
            raise NoSePuede("una elección sin cerrar")
        if bat:
            raise NoSePuede("una batalla sin cerrar")
        codigo = b"".join(piezas)
        # El `OP_DONE` es de la página y no del pedazo: un cuerpo en línea que
        # lo llevara terminaría la página del que llamó en vez de devolverle el
        # control. Ver `base`.
        return codigo if hondo else codigo + bytes([OP_DONE])
    except NoSePuede:
        if mensajes is not None:
            mensajes.volver(marca)
        return None


# Hasta dónde se anida un `CallEvent`. No es una precaución abstracta: un
# evento común puede llamarse a sí mismo —el cuerpo en línea sería infinito— y
# dos pueden llamarse entre ellos. En este juego la cadena más larga que
# compila es de uno.
LLAMADA_MAX = 4


class _Comandos:
    """Un envoltorio con `.commands`, que es lo único que `compilar_pagina`
    mira de una página. Lo piden los eventos comunes, que no son páginas."""

    def __init__(self, comandos):
        self.commands = comandos


def _compilar_llamada(cmd, largo, hondo, indice_de_mapa, mensajes,
                      eventos_mapa, temas, graficos, imagenes, tropas):
    """`CallEvent`, compilado **en línea**: el cuerpo del evento llamado va en
    el lugar de la llamada.

    En RM2k esto es `Push<ExecutionType::Call>`, o sea una pila de intérpretes.
    Acá no hace falta ninguna, y ésa es la decisión: el llamado corre entero
    antes de que siga el que llamó, así que pegar su bytecode en el medio da
    exactamente lo mismo. Lo que costaría una pila de verdad —un cursor y una
    página por nivel en la RAM del banco 0, que está lleno— no lo compra
    ninguna diferencia observable: **ninguna llamada de este juego es
    recursiva**, y el único precio del pegado es el tamaño, medido abajo.

    Y sale sin tocar la ROM ni la referencia: los dos corren el mismo bytecode,
    así que no hay dos lados que puedan separarse.

    **Si el llamado no compila, la llamada se saltea**, que es lo que el port
    viene haciendo desde siempre con este comando. Es deuda declarada y no
    equivalencia, y exigir que compilara costaría 183 páginas que hoy corren:
    medido, sólo 6 de las 189 páginas que compilan y llaman tienen todos sus
    blancos compilables.
    """
    p = list(cmd.parameters)
    if len(p) < 2 or hondo >= LLAMADA_MAX:
        return b""
    if p[0] == 0:
        # Un evento común, por número. Los de este juego se cortan casi todos
        # en `ControlVars` y en los menús propios del original.
        destino, ctx = COMUNES.get(p[1]), eventos_mapa
    elif p[0] == 1 and len(p) >= 3 and eventos_mapa is not None:
        # Un evento del mapa, por id y **número de página**, que en RM2k
        # empieza en uno: es el `page->ID` de `CommandCallEvent`.
        paginas = eventos_mapa.paginas.get(p[1])
        if paginas is None or not 1 <= p[2] <= len(paginas):
            return b""
        destino = paginas[p[2] - 1].commands
        # "Este evento" adentro del llamado es **el llamado**, no el que
        # llamó: `Push` le pasa `event->GetId()`. Sin esto una ruta del
        # Hover-Tram movería al Tram Officer.
        ctx = eventos_mapa.para(p[1])
    else:
        # Por variable —el tipo 2— no se resuelve al compilar y nunca se va a
        # poder: el número sale de la partida. Se saltea, como antes.
        return b""
    if not destino:
        return b""
    return compilar_pagina(_Comandos(destino), indice_de_mapa, mensajes, ctx,
                           temas, graficos, imagenes, tropas,
                           base=largo, hondo=hondo + 1) or b""


def _compilar_posada(cmd, largo, mensajes):
    r"""`ShowInn`, expandido a comandos que la ROM ya sabe hacer.

    La posada no es un opcode nuevo: es el saludo con su elección, una rama por
    oro, el cobro y la cura, que son cinco cosas que el intérprete hace desde
    antes. Se arma acá y no en `_compilar` porque los destinos de la elección y
    de la rama son desplazamientos **absolutos dentro de la página**, y eso lo
    sabe el lazo de `compilar_pagina`, que es quien lleva `largo`.

    Lo que sale, con los desplazamientos relativos al arranque del bloque:

         0  OP_MESSAGE  el saludo, dos renglones
         3  OP_CHOICE   "Yes" y "No"; cancelar es "No"
        14  OP_IF       oro >= precio, y si no, al final
        21  OP_GOLD     se cobra
        26  OP_HEAL     el grupo entero al máximo
        30  el final, que es donde caen "No" y "no te alcanza"

    El saludo es el de `CommandShowInn` (easyrpg
    `game_interpreter_map.cpp:449-560`): `"{greeting_1} {precio}{gold}
    {greeting_2}"` en el primer renglón —de ahí los dos espacios, porque
    `greeting_2` de este juego empieza con uno— y `greeting_3` en el segundo.
    Los términos son del LDB: ver `indexar_terminos`.

    **Tres deudas declaradas**, y las tres son de lo que se ve y no de lo que
    pasa:

    * no hay ventana de oro al lado del saludo;
    * "Yes" no sale en gris cuando no alcanza, así que se puede elegir;
      elegirlo equivale a "No", que es lo que hace la rama por oro. En RM2k
      el cursor no lo deja seleccionar;
    * no hay fundido a negro ni música de posada: se cobra y se cura en el
      acto. Eso es `Scene_Map::CallInn`.

    **Una posada gratis es sólo la cura**: con el precio en cero
    `CommandShowInn` no muestra nada y va derecho a
    `ContinuationShowInnStart(indent, 0, 0)`, que se queda, cobra cero y
    descansa. Son 6 de las 18 páginas del juego, las de los mapas 39, 59, 77 y
    111 —los cuartos donde el guion deja dormir—.
    """
    p = cmd.parameters
    if len(p) < 2:
        raise NoSePuede("ShowInn sin operandos")
    tipo, precio = p[0], p[1]
    if precio == 0:
        return bytes([OP_HEAL, 0, 0, 0])
    if mensajes is None:
        raise NoSePuede("una posada sin ventana donde ponerla")
    if tipo not in TERMINOS_POSADA:
        raise NoSePuede("posada del tipo %d, que no está en los términos: "
                        "¿se llamó a indexar_terminos?" % tipo)
    if not precio <= 0xFFFF:
        # El tope es el operando de la rama de oro, que va en una palabra; el
        # más caro del juego es de 100.
        raise NoSePuede("posada de %d, que no entra en la rama de oro" % precio)
    saludo_1, saludo_2, saludo_3, si, no = TERMINOS_POSADA[tipo]
    donde = mensajes.agregar(
        ["%s %d%s %s" % (saludo_1, precio, TERMINOS_POSADA["gold"], saludo_2),
         saludo_3])
    cuadros = cuadros_de_eleccion([(0, si), (1, no)], mensajes)
    fin = largo + 30
    rama = bytes([OP_IF, COND_ORO, precio & 0xFF, precio >> 8, 0,
                  fin & 0xFF, fin >> 8])
    return (bytes([OP_MESSAGE, donde & 0xFF, donde >> 8])
            # Cancelar es la segunda opción: allá el `choice_cancel_type` por
            # omisión es 5 y `inn_stay` es `choice_result == 0`, o sea que
            # cancelar es no quedarse.
            + bytes([OP_CHOICE, 2, 2])
            + bytes([cuadros[0] & 0xFF, cuadros[0] >> 8,
                     (largo + 14) & 0xFF, (largo + 14) >> 8])
            + bytes([cuadros[1] & 0xFF, cuadros[1] >> 8,
                     fin & 0xFF, fin >> 8])
            + rama
            + bytes([OP_GOLD, 1, precio & 0xFF, (precio >> 8) & 0xFF, 0])
            + bytes([OP_HEAL, 0, 0, 0]))


def imagen_aceptable(p):
    """Si los parámetros de un `ShowPicture` o de un `MovePicture` caen dentro
    de lo que el cartel de la consola sabe hacer.

    Los índices salen de `CommandShowPicture` y `CommandMovePicture` de
    easyrpg-player, **no de memoria**: el color y la saturación van en 8..11 y
    el modo de efecto en 12, que no es lo que uno adivinaría.
    """
    return (len(p) >= 14
            and p[1] == 0               # la posición por variable
            and p[4] == 0               # pegada al mapa
            and p[5] == 100             # el zoom
            and p[6] == 0               # translúcida
            and p[11] == 100            # la saturación
            and p[12] == 0              # rotar u ondear
            and all(0 <= v <= 200 for v in p[8:12]))


def _compilar_imagen(cmd, imagenes):
    """Los tres comandos de `Picture`, o None si este cartel no entra.

    Los índices de los parámetros salen de `CommandShowPicture` y
    `CommandMovePicture` de easyrpg-player, **no de memoria**: los dos leen
    catorce y dieciséis, y el orden no es el que uno adivinaría —el color y la
    saturación van en 8..11 y el modo de efecto en 12—.
    """
    p = cmd.parameters
    if imagenes is None:
        return None
    if cmd.code == ERASE_PICTURE:
        if not p or not imagenes.suyo(p[0], None, None):
            return None
        return bytes([OP_PICTURE_ERASE])
    if not imagen_aceptable(p):
        return None
    tono = (p[8], p[9], p[10], p[11])
    if cmd.code == SHOW_PICTURE:
        # `use_transparent_color`: el índice 0 del PNG se dibuja o no. El
        # cartel del "1 year earlier" lo tiene apagado, así que es un
        # rectángulo opaco; hacerlo transparente pediría un color de la paleta
        # menos y saber cuál era el índice 0 antes de reducir.
        if p[7] or imagenes.mostrar(p[0], cmd.string, p[2], p[3]) is None:
            return None
        return bytes([OP_PICTURE]) + bytes(tono)
    # MovePicture: el mismo cartel, en el mismo lugar, con otro tono. La
    # duración viene en **décimas** —`data.time_left = duration * DEFAULT_FPS /
    # 10`—, que es lo que había que ir a leer: los 35 del primero son tres
    # segundos y medio, no medio segundo.
    if not imagenes.suyo(p[0], p[2], p[3]):
        return None
    cuadros = p[14] * CUADROS_POR_DECIMA
    if not 0 <= cuadros <= IMAGEN_CUADROS_MAX:
        return None
    salida = bytes([OP_PICTURE_MOVE]) + bytes(tono) + bytes([cuadros])
    if len(p) > 15 and p[15] and cuadros:
        # `options.wait`: la página espera lo que dura, como el `FlashScreen`.
        salida += bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])
    return salida


def _compilar(cmd, indice_de_mapa, mensajes=None, extra=(),
              eventos_mapa=None, temas=None, graficos=None, imagenes=None):
    p = cmd.parameters

    if cmd.code == END or cmd.code in IGNORABLES:
        return b""

    if cmd.code == PLAY_SOUND:
        # Sin registro de temas se acepta y no se hace, como antes. Un nombre
        # vacío es "(OFF)": no toca nada.
        if temas is None or not cmd.string or len(p) < 3:
            return b""
        # Y el trueno del mapa 1, entero: es otra muestra, con su propio
        # nombre, para que el mapa 3 —que también lo pide— siga con la de
        # siempre. Ver `SE_ENTEROS` en snes_music.py.
        nombre = cmd.string
        if nombre == "Thunder9" and temas.mapa is not None:
            try:
                if temas.mapa == indice_de_mapa(1):
                    nombre = "Thunder9@entero"
            except Exception:
                pass
        k = temas.sonido(nombre, p[0], p[1], p[2])
        return bytes([OP_SOUND, k & 0xFF, k >> 8])

    if cmd.code == WEATHER_EFFECTS:
        if len(p) < 2:
            raise NoSePuede("WeatherEffects sin operandos")
        return bytes([OP_WEATHER, p[0] & 0xFF, min(max(p[1], 0), 2)])

    if cmd.code == OPEN_SHOP:
        if len(p) < 4:
            raise NoSePuede("OpenShop sin operandos")
        if p[2]:
            raise NoSePuede("OpenShop con las ramas de compró y no compró")
        vende = [i for i in p[4:] if 0 < i < ITEMS_N]
        if len(vende) > 255 or not 0 <= p[0] <= 2 or not 0 <= p[1] <= 2:
            raise NoSePuede("OpenShop que no entra en OP_SHOP")
        return bytes([OP_SHOP, p[0], p[1], len(vende)]) + b"".join(
            bytes([i & 0xFF, i >> 8]) for i in vende)

    if cmd.code == FULL_HEAL:
        # La cantidad en 0 es lo que lo distingue de `ChangeHP`, abajo.
        if len(p) < 2:
            raise NoSePuede("FullHeal sin operandos")
        return bytes([OP_HEAL, actor_de_blanco(p, "FullHeal"), 0, 0])
    if cmd.code == CHANGE_HP:
        # [tipo, id, resta, cantidad por variable, cantidad, letal]. El que
        # suma comparte OP_HEAL con `FullHeal`, con la cantidad puesta: es
        # `Game_Battler::ChangeHp` (`game_battler.cpp:480`), que al caído no
        # lo toca y topa en el máximo —`SetHp`—. No toca los SP.
        #
        # Una cantidad en cero no hace nada en RM2k, y acá no se emite: en
        # OP_HEAL el cero quiere decir `FullHeal`.
        #
        # Las 11 que suman fuera de pelea son constantes —siete de a 1 al
        # grupo, cuatro de 300 y 999 a un actor—, así que la cantidad en una
        # variable no compila. Las que restan siguen fuera: pueden matar, y
        # `lethal` pide qué hacer con eso.
        if len(p) < 5 or p[2] != 0:
            raise NoSePuede("ChangeHP que resta")
        if p[3] != 0:
            raise NoSePuede("ChangeHP con la cantidad en una variable")
        if not 0 <= p[4] <= 0xFFFF:
            raise NoSePuede("ChangeHP de %d" % p[4])
        if p[4] == 0:
            return b""
        return bytes([OP_HEAL, actor_de_blanco(p, "ChangeHP"),
                      p[4] & 0xFF, p[4] >> 8])
    if cmd.code == CHANGE_SKILLS:
        # [tipo, id, olvida, habilidad por variable, habilidad]. Es
        # `CommandChangeSkills` de easyrpg: `LearnSkill` o `UnlearnSkill`
        # sobre cada actor del blanco, sin pedir el refresco de páginas —allá
        # tampoco lo pide— y sin mensaje: el "aprendió tal cosa" lo escribe la
        # página con un `ShowMessage`.
        #
        # Los 898 del juego son todos de actor fijo y habilidad constante, así
        # que el operando es directamente el bit: ver `HABILIDAD_RANURA`. El
        # grupo, el actor por variable y la habilidad por variable no
        # compilan.
        if len(p) < 5:
            raise NoSePuede("ChangeSkills sin operandos")
        if p[0] != 1:
            raise NoSePuede("ChangeSkills sobre el grupo o un actor por "
                            "variable")
        if p[3] != 0:
            raise NoSePuede("ChangeSkills con la habilidad en una variable")
        ranura = ranura_de_habilidad(p[1], p[4])
        return bytes([OP_SKILL, ranura & 0xFF, ranura >> 8,
                      0 if p[2] else 1])
    if cmd.code == CHANGE_EQUIPMENT:
        # [tipo, id, operación, a, b]. La operación 1 es sacarse lo de la
        # ranura `a` —0 a 4, arma a accesorio; 5 es todo— y es
        # `Game_Actor::ChangeEquipment(ranura, 0)`: la ranura queda vacía y lo
        # que tenía vuelve al inventario, topado en ITEM_MAX. Tampoco pide el
        # refresco: `CommandChangeEquipment` no lo pide.
        #
        # Los 35 que el juego corre fuera de pelea son todos de sacar una
        # ranura; los 560 que equipan son de las tropas, que este port no
        # corre. Así que equipar no compila, y sacarse todo tampoco: no lo usa
        # nadie.
        if len(p) < 4:
            raise NoSePuede("ChangeEquipment sin operandos")
        if p[2] != 1:
            raise NoSePuede("ChangeEquipment que equipa")
        from port import pantallas      # que importa este módulo
        if not 0 <= p[3] < pantallas.RANURAS_EQUIPO:
            raise NoSePuede("ChangeEquipment que saca todo el equipo")
        actor = actor_de_blanco(p, "ChangeEquipment")
        if _ACTORES_INDEXADOS and actor and actor not in ACTOR_EQUIPO:
            raise NoSePuede("el actor %d no está en el LDB" % actor)
        return bytes([OP_EQUIPMENT, actor, p[3]])
    if cmd.code == GAME_OVER:
        # `CommandGameOver`: la pantalla de Game Over y, al apretar, el título.
        # Acá es volver al arranque, igual que perder una pelea sin manejador
        # —ver `BATALLA_PERDER`—, y la imagen no se dibuja.
        return bytes([OP_GAME_OVER])
    if cmd.code == CHANGE_CONDITION:
        if len(p) < 3 or p[2] != 1:
            raise NoSePuede("ChangeCondition que pone un estado")
        return b""

    if cmd.code == KEY_INPUT_PROC:
        # [variable, esperar, las cuatro direcciones, la de acción, cancelar].
        # Las 32 apariciones del juego tienen los cinco y ninguna más: con seis
        # o más RM2k 1.50 pasa a mirar cada dirección por separado, que es otro
        # programa, así que el largo se exige en vez de suponerse.
        if len(p) != 5:
            raise NoSePuede("KeyInputProc con %d operandos" % len(p))
        banderas = ((TECLA_ESPERA if p[1] else 0)
                    | (TECLA_DIRS if p[2] else 0)
                    | (TECLA_DECISION if p[3] else 0)
                    | (TECLA_CANCELAR if p[4] else 0))
        if not banderas & (TECLA_DIRS | TECLA_DECISION | TECLA_CANCELAR):
            # Sin ninguna tecla pedida, la forma que espera no sale nunca.
            raise NoSePuede("KeyInputProc sin ninguna tecla")
        if not p[1]:
            # **La forma que no espera —leer el pad y seguir— está hecha de los
            # dos lados y no se acepta**, y el número está medido: vale +5
            # páginas del juego entero y 3 de la persecución en auto.
            #
            # Lo que la traba no es este comando sino con qué viene: las 4
            # páginas que la usan son el volante del auto —`RaceController2` de
            # los mapas 49, 51, 52 y 54— y cada una, además de leer el pad,
            # **le fuerza la ruta al héroe en todos los cuadros**. Ahí aparece
            # una divergencia que es anterior a todo esto y que ninguna página
            # compilada había ejercitado nunca: en la ROM una ruta forzada
            # manda sobre el pad —el `lda ruta_i / cmp ruta_n` de `move_hero`—
            # y en la referencia la caminata del arnés no la mira: camina por
            # celdas enteras y sólo se frena con un mensaje abierto.
            #
            # Medido: con esta forma aceptada, el caso `heroe` del mapa 52 da **55,42%
            # de pixeles distintos** caminando a la izquierda, desde el cuadro
            # 60; las otras cuatro direcciones dan cero, y es exactamente la
            # única que pelea contra el empujón hacia la derecha que la página
            # le da al héroe todos los cuadros.
            #
            # **Medido de nuevo el 2026-09-13, con la mitad del arreglo puesta.**
            # Desde ese día `hero_position` respeta la ruta forzada —mientras
            # haya ruta puesta el pad no mueve, que es lo que hace `move_hero`—
            # y con eso ese mismo caso pasa de 55,42% a **0,59%**, 248 pixeles:
            # el auto, a unos pocos pixeles de donde lo deja la ROM. Las otras
            # cuatro direcciones siguen en cero.
            #
            # Lo que falta para el cero, y por eso esto sigue sin aceptarse:
            # cuando **no** hay ruta puesta el arnés camina una celda entera de
            # un saque —cuatro cuadros— y la página paralela le puede volver a
            # poner la ruta en el medio, cosa que la ROM sí ve. O sea que hace
            # falta la otra mitad: que la caminata avance **cuadro a cuadro**.
            # Era el pedazo más delicado de la referencia.
            #
            # Y hay un segundo problema, que apareció con la medición y no es
            # de precisión: con la carrera corriendo, `heroe 52` **no
            # termina**. El volante le vuelve a poner la ruta al héroe para
            # siempre, así que "apretar hasta chocar contra la pared" deja de
            # tener final y el lazo corta en su tope de 10000 vueltas —27566
            # cuadros de emulador para una sola dirección—. Antes de aceptar
            # este comando hay que decidir qué mira ese caso, porque el mapa 52
            # es de la carrera y está en
            # `pruebas/rpgmaker/test_caminar_golden.py`.
            #
            # Para reproducir las dos mediciones sin tocar código:
            # `TECLA_SIN_ESPERA=1` sobre el caso `heroe` del mapa 52.
            if not PERMITIR_TECLA_SIN_ESPERA:
                raise NoSePuede("KeyInputProc sin espera: la ruta forzada del "
                                "héroe no manda sobre el pad en la referencia")
            return bytes([OP_KEY, ranura_de_variable(p[0]), banderas])
        # **La espera se hace con las tres cosas: la cruceta, la tecla de
        # acción y cancelar**, desde el 2026-09-13. Hasta ese día valía sólo la
        # de acción, y la razón escrita era del **arnés** y no de la ROM: la
        # tanda sostenía una dirección desde el arranque y apretaba A en
        # cuadros anotados, así que un flanco de cruceta a mitad de una escena
        # no lo podía producir ningún caso, y modelarlo igual habría sido
        # escribir de los dos lados un camino que nada ejecuta.
        #
        # Esa razón dejó de valer con `pruebas/arnes/recorrido.py`, que juega el
        # juego de verdad y puede apretar cualquier botón en cualquier cuadro,
        # y con `--tocar` de las dos mitades de la tanda, que aprieta una
        # dirección en un cuadro anotado como ya se apretaba A.
        #
        # Lo que destraba, medido: las dos páginas del `(151, 1, 1, 1, 1)` —la
        # que espera las tres— y, junto con la ranura de la variable 5, la del
        # motor del minijuego de las piedras del mapa 11, que es el `(8, 1, 1,
        # 0, 0)`: sin esto no se puede tirar ninguna piedra.
        ranura = ranura_de_variable(p[0]) | escritura_pide_refresco(
            p[0], eventos_mapa)
        return bytes([OP_KEY, ranura, banderas | TECLA_ARRANCA,
                      OP_KEY, ranura, banderas])

    if cmd.code == CHANGE_SPRITE_ASSOCIATION:
        # [actor, índice del CharSet, transparente]. Ver OP_ACTOR_SPRITE.
        if len(p) != 3:
            # Con cuatro es el bitfield de "esto sale de una variable", que
            # este juego no usa nunca.
            raise NoSePuede("ChangeSpriteAssociation con operandos que no "
                            "sabemos leer")
        if p[2]:
            raise NoSePuede("ChangeSpriteAssociation transparente: la consola "
                            "no atenúa un sprite sin color math")
        if not 0 < p[0] < 256:
            raise NoSePuede("ChangeSpriteAssociation sobre el actor %d" % p[0])
        if graficos is None:
            raise NoSePuede("ChangeSpriteAssociation sin tabla de gráficos")
        elegido = graficos.indice(cmd.string, p[1])
        if elegido > 0xFF:
            raise NoSePuede("demasiados gráficos en el mapa")
        return bytes([OP_ACTOR_SPRITE, p[0], elegido])

    if cmd.code in (CHANGE_SAVE_ACCESS, CHANGE_MENU_ACCESS,
                    CHANGE_ESCAPE_ACCESS):
        if not p:
            raise NoSePuede("%s sin operandos" % cmd.code)
        cual = {CHANGE_SAVE_ACCESS: ACCESO_GUARDAR,
                CHANGE_MENU_ACCESS: ACCESO_MENU,
                CHANGE_ESCAPE_ACCESS: ACCESO_ESCAPAR}[cmd.code]
        return bytes([OP_ACCESS, ACCESO_BIT[cual], 1 if p[0] else 0])

    if cmd.code == CHANGE_ITEMS:
        # [sumar o quitar, ítem por constante o variable, ítem, cantidad por
        # constante o variable, cantidad]. Ver OP_ITEM.
        if len(p) < 5:
            raise NoSePuede("ChangeItems sin operandos")
        if p[1] != 0 or p[3] != 0:
            raise NoSePuede("ChangeItems con el ítem o la cantidad en una "
                            "variable")
        if not 1 <= p[2] < ITEMS_N:
            raise NoSePuede("ChangeItems del ítem %d, que no está en el LDB"
                            % p[2])
        delta = -p[4] if p[0] else p[4]
        if not -128 <= delta <= 127:
            raise NoSePuede("ChangeItems de %d, que no entra en un byte" % p[4])
        return bytes([OP_ITEM, p[2] & 0xFF, p[2] >> 8, delta & 0xFF])

    if cmd.code == CHANGE_GOLD:
        # `OperateValue(operación, tipo, valor)`: la operación es 0 sumar y 1
        # restar, y el tipo 0 constante y 1 "el valor está en una variable".
        # Sin variables, lo segundo no se puede.
        if len(p) < 3:
            raise NoSePuede("ChangeGold sin operandos")
        if p[1] != 0:
            raise NoSePuede("ChangeGold con el monto en una variable")
        monto = p[2]
        if not 0 <= monto <= 0xFFFFFF:
            raise NoSePuede("ChangeGold de %d, que no entra en tres bytes" % monto)
        return bytes([OP_GOLD, 1 if p[0] else 0,
                      monto & 0xFF, (monto >> 8) & 0xFF, (monto >> 16) & 0xFF])

    if cmd.code == PLAY_BGM:
        # Sin registro de temas se acepta y no se hace, que es lo que este repo
        # hizo con PlayBGM desde el principio. Con registro se emite el índice y
        # la ROM toca el tema si le tocó llevarlo.
        if temas is None or not cmd.string:
            return b""
        return bytes([OP_BGM, temas.indice(cmd.string) & 0xFF])

    if cmd.code == PAN_SCREEN:
        # Fijar y soltar la cámara no las usa ninguna página del juego, así que
        # no compilan: modelarlas sin nada que las ejercite es inventarse una
        # diferencia. Correr y volver sí, que son las 133 que hay.
        if len(p) < 5 or p[0] not in (PAN_CORRER, PAN_VOLVER):
            raise NoSePuede()
        if p[0] == PAN_CORRER and p[1] not in PAN_SENTIDO:
            raise NoSePuede()
        if not 0 <= p[2] <= 255:
            raise NoSePuede()
        salida = bytes_de_pan(p[0], p[1], p[2], p[3], p[4])
        if salida is None:
            raise NoSePuede()
        return salida

    if cmd.code == FADE_OUT_BGM:
        if not p or p[0] < 0:
            raise NoSePuede()
        paso = paso_de_fundido(p[0])
        return bytes([OP_FADE_BGM, paso & 0xFF, paso >> 8])

    if cmd.code == OPEN_SAVE_MENU:
        return bytes([OP_SAVE])

    if cmd.code in (SHOW_PICTURE, MOVE_PICTURE, ERASE_PICTURE):
        salida = _compilar_imagen(cmd, imagenes)
        # None es "este cartel no entra en el modelo": se acepta sin hacerlo,
        # que es lo que hacían los tres hasta el 2026-09-12. Cortar la página
        # le sacaría al juego las ocho que hoy compilan por eso.
        return b"" if salida is None else salida

    if cmd.code in ACEPTADOS_SIN_HACER:
        return b""     # se acepta con la deuda declarada arriba

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
        if temas is not None:
            temas.destino(destino)
        return bytes([OP_TELEPORT, destino & 0xFF, destino >> 8,
                      p[1] & 0xFF, p[1] >> 8, p[2] & 0xFF, p[2] >> 8])

    if cmd.code == CHANGE_PARTY_MEMBERS:
        if len(p) < 3 or p[1] != GRUPO_ID_FIJO:
            raise NoSePuede()   # el id sale de una variable, y no las leemos
        if p[0] not in (GRUPO_AGREGAR, GRUPO_SACAR) or not 0 <= p[2] <= 255:
            raise NoSePuede()
        return bytes([OP_PARTY, p[0], p[2]])

    if cmd.code == PROCEED_WITH_MOVEMENT:
        return bytes([OP_WAIT_ROUTES])

    if cmd.code == HALT_ALL_MOVEMENT:
        return bytes([OP_STOP_ROUTES])

    if cmd.code == CHANGE_PBG:
        return b""      # se acepta y se tira: ver CHANGE_PBG

    if cmd.code == FLASH_SPRITE:
        if len(p) < 7:
            raise NoSePuede()
        if p[0] == RUTA_HEROE:
            blanco = 0
        elif eventos_mapa is None:
            raise NoSePuede()
        else:
            blanco = eventos_mapa.blanco(p[0])
            if blanco is None:
                raise NoSePuede()   # un vehículo, o un evento que no existe
            # **Un destello sobre un evento que comparte paleta se emite igual.**
            # Hasta el 2026-09-13 la página no compilaba: en la consola el
            # destello es un tinte de CGRAM —`pintar_flash` sube la fila
            # entera— así que dos eventos con el mismo gráfico destellan
            # juntos, y emitirlo con la referencia destellando uno solo era
            # medir dos programas distintos. El corte costaba **51 páginas**,
            # medidas, y una de ellas es el `EV0027` del mapa 20: la cinemática
            # del Bum que prende el evento de Rat Tracks B2. Sin ella el
            # jugador aparece invisible y el juego no se puede seguir.
            #
            # Lo que se hizo en vez de aflojar el corte: la referencia modela
            # lo que la consola hace y destella **la fila de paleta** —ver el
            # reparto de la referencia—, así que los dos lados volvían a ser
            # el mismo programa. Lo que queda es una divergencia declarada con
            # RM2k, que destella la imagen de un sprite solo, y está en
            # `workflow/divergencias/destello-sobre-la-paleta-de-otro.md`.
        if any(not 0 <= v <= 31 for v in p[1:5]):
            raise NoSePuede()
        cuadros = p[5] * CUADROS_POR_DECIMA
        if not 0 < cuadros <= 255:
            raise NoSePuede()
        out = bytes([OP_FLASH, blanco, p[1], p[2], p[3], p[4], cuadros])
        if p[6]:
            # Esperar es exactamente el comando Wait: `SetupWait(tenths)`, o sea
            # las mismas décimas por CUADROS_POR_DECIMA.
            out += bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == CONTROL_VARS:
        # `[cómo se elige, desde, hasta, operación, clase del operando, a, b]`.
        # De a una variable y nada más: los rangos y el indirecto no los usa
        # ninguna página del juego. Ver OP_VAR.
        if len(p) < 7:
            raise NoSePuede("un ControlVars sin operandos")
        if p[0] != 0:
            raise NoSePuede("ControlVars sobre un rango o indirecto")
        ranura = ranura_de_variable(p[1]) | escritura_pide_refresco(
            p[1], eventos_mapa)
        if p[3] not in (VAR_PONER, VAR_SUMAR, VAR_RESTAR):
            raise NoSePuede("operación %d de ControlVars" % p[3])
        clase, a, b = p[4], p[5], p[6]
        if clase == VAR_CONSTANTE:
            if not -0x8000 <= a <= 0x7FFF:
                raise NoSePuede("constante %d que no entra en un word" % a)
            b = 0
        elif clase == VAR_VARIABLE:
            a, b = ranura_de_variable(a), 0
        elif clase == VAR_AZAR:
            if not (0 <= a <= b <= 0x7FFF and b - a < 256):
                raise NoSePuede("azar entre %d y %d: la ROM divide por un "
                                "byte" % (a, b))
        elif clase == VAR_OTRO:
            if a not in (OTRO_ORO, OTRO_TIMER):
                raise NoSePuede("'otro' %d de ControlVars" % a)
            b = 0
        elif clase == VAR_PERSONAJE:
            # La celda de un personaje. `a` pasa a ser el mismo byte de blanco
            # que lleva OP_ROUTE —0 el héroe, el índice del evento más uno— y no
            # el id de RM2k: el bytecode no vuelve a ver un id, que es lo que
            # `Eventos` existe para garantizar. `b` es cuál coordenada.
            if b not in (PERSONAJE_X, PERSONAJE_Y):
                raise NoSePuede("la clase 6 de ControlVars con el "
                                "sub-operando %d" % b)
            if a == RUTA_HEROE:
                a = 0
            elif eventos_mapa is None:
                raise NoSePuede("la clase 6 sobre un evento sin el mapa")
            else:
                a = eventos_mapa.blanco(a)
                if a is None:
                    raise NoSePuede()   # un vehículo, o un evento que no existe
        else:
            raise NoSePuede("operando de clase %d en ControlVars" % clase)
        return bytes([OP_VAR, ranura, p[3], clase, a & 0xFF, (a >> 8) & 0xFF,
                      b & 0xFF, b >> 8])
    if cmd.code == TIMER_OPERATION:
        # El cronómetro. Se hace la operación entera —poner, arrancar y parar—
        # y los segundos pueden salir de una variable: es la cuarta operación,
        # `TIMER_PONER_VAR`, con la ranura en el operando.
        if len(p) < 5:
            raise NoSePuede()
        if p[0] == TIMER_PONER:
            if p[1] != TIMER_SEGUNDOS_FIJOS:
                ranura = ranura_de_variable(p[2])
                return bytes([OP_TIMER, TIMER_PONER_VAR, ranura, 0, 0])
            # La ROM cuenta los cuadros en dieciséis bits, así que el tope no
            # es el del operando sino el de la cuenta. Son dieciocho minutos, y
            # el cronómetro más largo del juego son diez.
            if not 0 <= p[2] * CUADROS_POR_SEGUNDO + TIMER_CUADROS_DE_MAS \
                    <= 0xFFFF:
                raise NoSePuede()
            return bytes([OP_TIMER, TIMER_PONER, p[2] & 0xFF, p[2] >> 8, 0])
        if p[0] in (TIMER_ARRANCAR, TIMER_PARAR):
            # El quinto parámetro es "también en batalla", y acá no hay
            # batallas: se compila igual y se ignora, como el resto de lo que
            # es de combate.
            return bytes([OP_TIMER, p[0], 0, 0, 1 if p[3] else 0])
        raise NoSePuede()

    if cmd.code == MOVE_EVENT:
        if len(p) < 4:
            raise NoSePuede()
        if p[0] == RUTA_HEROE:
            blanco = 0
        elif eventos_mapa is None:
            raise NoSePuede()   # sin el mapa no hay cómo traducir el id
        else:
            blanco = eventos_mapa.blanco(p[0])
            if blanco is None:
                raise NoSePuede()   # un vehículo, o un evento que no existe
        if not RUTA_FRECUENCIA_MIN <= p[1] <= RUTA_FRECUENCIA:
            raise NoSePuede()   # la 1 no entra en el byte de espera de la ROM
        ordenes = decodificar_ruta(list(p[4:]))
        if frecuencia_minima(p[1], [o for o, _ in ordenes],
                             bool(p[2])) < RUTA_FRECUENCIA_MIN:
            raise NoSePuede()   # las órdenes 30 y 31 la bajarían hasta la 1
        ruta = []
        # Si el cursor va entre un `begin_jump` y su `end_jump`. Adentro de un
        # salto las órdenes no se ejecutan: `BeginMoveRouteJump` sólo **suma**
        # los `move_*` y los giros, y la 9 ahí tendría que preguntar por el
        # héroe en el medio de la cuenta. Ninguna ruta del juego lo hace
        # —medido, cero—, así que se rechaza en vez de dejar que la ROM la
        # camine por un camino que ninguna prueba ejercita.
        en_salto = False
        for orden, extras in ordenes:
            if orden == RUTA_SALTO_INICIO:
                en_salto = True
            elif orden == RUTA_SALTO_FIN:
                en_salto = False
            elif orden == RUTA_HACIA_HEROE and en_salto:
                raise NoSePuede()

            if orden == RUTA_SONIDO or orden in RUTA_TRANSPARENCIA:
                # Se acepta y se tira: no se ve y no
                # cuesta cuadros —RM2k no le toca el contador de parada—. Así
                # el bytecode sigue siendo un byte por orden. La
                # transparencia, ver RUTA_TRANSPARENCIA.
                continue
            # Girar, esperar y moverse. Los `move_*` entraron el 2026-09-03,
            # cuando los dos lados empezaron a coincidir *durante* la caminata y
            # no sólo al final: lo prueba `ruta`, que compara cuatro
            # cuadros de una ruta de doce celdas con esperas en el medio. Lo
            # que entra de `rpg::MoveCommand::Code` es `RUTA_ORDENES`, y moverse
            # hacia el héroe está adentro desde el 2026-09-12 —ver
            # RUTA_HACIA_HEROE—; alejarse de él, girar en el lugar y los
            # switches siguen afuera.
            if orden not in RUTA_ORDENES:
                raise NoSePuede()
            if orden in (RUTA_ENCARAR_HEROE, RUTA_HACIA_HEROE) and blanco == 0:
                raise NoSePuede()   # el héroe encarándose o yendo hacia sí mismo
            if orden in RUTA_HEROE_AFUERA and blanco == 0:
                # Fijar y soltar la mirada sobre **el héroe**: se aceptan y se
                # tiran, como el sonido y la transparencia. Sobre eventos sí se
                # hacen. Subir y bajar la velocidad también se tiraban sobre el
                # héroe, y se hacen desde el 2026-09-10: ver RUTA_HEROE_AFUERA.
                #
                # Tirarlas y no rechazar la página entera, que fue lo primero
                # que se probó, es del 2026-09-06: **la escena de Talan tiene
                # una ruta del héroe que empieza con la 28**, así que la escena
                # que motivó los seis puntos de ese día se quedaba sin compilar
                # y el jugador no podía salir del pasillo del Emitter Room.
                continue
            if orden in RUTA_DIAGONALES and blanco == 0:
                # Y el héroe en diagonal: la ROM no lo sabe hacer y ninguna
                # de las 26 rutas del juego con diagonales es del héroe. Sin
                # este corte la ROM se iría para la izquierda —el `mover` de
                # `paso_de_ruta` cae en `try_left` por descarte—.
                raise NoSePuede()
            if orden == RUTA_CAMBIAR_GRAFICO:
                # La única orden con operando: detrás del 34 va el índice del
                # gráfico en `Graficos`, que el conversor resuelve al banco de
                # sprites del mapa. Quien recorra una ruta ya compilada tiene
                # que saltear ese byte: leído como orden, un 30 o un 31 le
                # cambian la frecuencia a la ruta sin que nadie lo pida.
                #
                # **Sobre el héroe también**, desde el 2026-09-12. Su gráfico
                # sale de la tabla de actores, pero las doce poses del actor
                # están escritas con la misma forma que una entrada de
                # `npc_poses`, así que la ROM cambia el puntero y listo: ver
                # `grafico_heroe` en rom/src/ruta_del_heroe.s. Son +29 páginas del juego, y entre
                # ellas las tres del `EV0047` del mapa 8, con el que no se
                # podía interactuar.
                if graficos is None or len(extras) < 2:
                    raise NoSePuede()
                elegido = graficos.indice(extras[0], extras[1])
                if elegido > 0xFF:
                    raise NoSePuede()
                ruta.append(orden)
                ruta.append(elegido)
                continue
            ruta.append(orden)
        if len(ruta) > 255:
            raise NoSePuede()
        if not ruta:
            # Una ruta que se quedó sin órdenes —sólo sonido o transparencia,
            # como las de las pantallas del mapa 2— no se emite: en RM2k
            # `UpdateMoveRoute` la consume entera en el mismo cuadro y la da
            # por terminada, así que ni cuesta cuadros ni deja nada que
            # esperar en `ProceedWithMovement`.
            return b""
        return bytes([OP_ROUTE, blanco, p[1], len(ruta)]) + bytes(ruta)

    if cmd.code == CHANGE_EVENT_LOCATION:
        if len(p) < 4 or p[1] not in (LUGAR_CONSTANTE, LUGAR_POR_VARIABLE):
            raise NoSePuede()
        if p[0] == RUTA_HEROE or eventos_mapa is None:
            # Al héroe no lo mueve nadie así en este juego —para eso está
            # Teleport— y sin el mapa no hay cómo traducir el id.
            raise NoSePuede()
        blanco = eventos_mapa.blanco(p[0])
        if blanco is None:
            raise NoSePuede()   # un vehículo, o un evento que no existe
        if p[1] == LUGAR_POR_VARIABLE:
            # La celda sale de dos variables, y se leen **al correr**: es el
            # `Main_Data::game_variables->Get(x)` de `CommandChangeEventLocation`.
            # Va en un opcode aparte y no en un bit de `OP_PLACE` porque los
            # operandos son otros —dos ranuras de un byte contra dos palabras—
            # y un opcode de largo variable es lo que el recorrido del
            # bytecode no sabe hacer: `OPCODE_SIZE` es una tabla.
            return bytes([OP_PLACE_VAR, blanco, ranura_de_variable(p[2]),
                          ranura_de_variable(p[3])])
        if not (0 <= p[2] <= 0xFFFF and 0 <= p[3] <= 0xFFFF):
            raise NoSePuede()
        return bytes([OP_PLACE, blanco, p[2] & 0xFF, p[2] >> 8,
                      p[3] & 0xFF, p[3] >> 8])

    if cmd.code == TILE_SUBSTITUTION:
        # `[capa alta?, tile viejo, tile nuevo]`, con los tiles numerados desde
        # el primero de su capa, que es como los numera `DoSubstitute`.
        if len(p) < 3:
            raise NoSePuede("TileSubstitution sin operandos")
        if eventos_mapa is None or eventos_mapa.sustituciones is None:
            # Sin el conversor de por medio no hay bloques contra los cuales
            # traducir. Ver `Sustituciones` en snes_convert.py.
            raise NoSePuede("TileSubstitution sin los bloques del mapa")
        pares = eventos_mapa.sustituciones.pares(bool(p[0]), p[1], p[2])
        if pares is None:
            raise NoSePuede("TileSubstitution que no se puede traducir a "
                            "bloques: ver `Sustituciones`")
        if not pares:
            # Ninguna celda del mapa dibuja el tile viejo, así que no hay nada
            # que cambiar. En RM2k la sustitución igual queda anotada, pero lo
            # que anota no lo mira nadie: no hay celda que la pueda usar.
            return b""
        out = bytearray([OP_TILE_SUB, len(pares)])
        for viejo, nuevo in pares:
            out += bytes([viejo & 0xFF, viejo >> 8, nuevo & 0xFF, nuevo >> 8])
        return bytes(out)

    if cmd.code == STORE_TERRAIN_ID:
        # `[modo, x, y, variable]`, con `ValueOrVariable`: en modo 0 la celda
        # viene escrita y en modo 1 los dos números son ids de variable. Los
        # dos se resuelven **al correr**, así que van los dos en el mismo
        # opcode con el modo puesto: leerlos acá en modo 1 sería contestar con
        # lo que las variables valían al compilar.
        if len(p) < 4 or p[0] not in (0, 1):
            raise NoSePuede("StoreTerrainID con un modo que no es 0 ni 1")
        destino = ranura_de_variable(p[3]) \
            | escritura_pide_refresco(p[3], eventos_mapa)
        if p[0]:
            x, y = ranura_de_variable(p[1]), ranura_de_variable(p[2])
        else:
            if not (0 <= p[1] <= 0xFFFF and 0 <= p[2] <= 0xFFFF):
                raise NoSePuede("StoreTerrainID fuera de los 16 bits")
            x, y = p[1], p[2]
        return bytes([OP_TERRAIN, p[0], x & 0xFF, x >> 8, y & 0xFF, y >> 8,
                      destino])

    if cmd.code == SHAKE_SCREEN:
        # `CommandShakeScreen`, en su forma de RM2k: fuerza, velocidad,
        # décimas y si espera. Las 29 del juego son de esa forma. Con cero
        # décimas es `ShakeEnd` y no espera nunca.
        if len(p) < 4 or not 0 <= p[0] <= 9 or not 0 <= p[1] <= 9:
            raise NoSePuede()
        cuadros = p[2] * CUADROS_POR_DECIMA
        if cuadros > 0xFFFF:
            raise NoSePuede()
        out = bytes([OP_SHAKE, p[0], p[1], cuadros & 0xFF, cuadros >> 8])
        if cuadros and p[3]:
            out += bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == SHOW_BATTLE_ANIMATION:
        # (animación, objetivo, esperar, global): ver OP_ANIMATION.
        if len(p) < 3:
            raise NoSePuede()
        anim = ANIMACIONES.get(p[0])
        if p[1] == RUTA_HEROE:
            blanco, quien = 0, None
        elif eventos_mapa is None:
            blanco, quien = None, None
        else:
            blanco = eventos_mapa.blanco(p[1])
            quien = (eventos_mapa.mio if p[1] == RUTA_ESTE_EVENTO else p[1])
        if anim is None or blanco is None:
            return b""      # sin animación o sin objetivo RM2k no hace nada
        # El destello del objetivo es un tinte de su paleta en la consola, y
        # dos eventos con el mismo gráfico la comparten: ver FLASH_SPRITE.
        # Acá no se corta la página por eso: ese destello no se hace. **Al
        # héroe no se lo destella nunca**: con quién comparte paleta depende
        # del grupo, que el compilador no ve —el conversor lo mira para los
        # `FlashSprite` y corta la ROM entera—, y una animación no vale eso.
        destella = (blanco != 0
                    and not eventos_mapa.comparte_grafico(quien))
        entradas = []
        for t in anim["timings"]:
            tick = (t["frame"] - 1) * 2
            if not 0 <= tick <= 255:
                continue
            nombre, volumen, tempo, balance = t["se"]
            if nombre and nombre != "(OFF)" and temas is not None:
                k = temas.sonido(nombre, volumen, tempo, balance)
                entradas.append(bytes([tick, ANIM_SONIDO, k & 0xFF, k >> 8,
                                       0, 0, 0, 0]))
            r, g, b = (min(31, max(0, v)) for v in t["rgb"])
            fuerza = min(7 * max(0, t["fuerza"]) // 6, 31)
            if t["alcance"] == 2:
                entradas.append(bytes([tick, ANIM_DESTELLO, r, g, b, fuerza,
                                       ANIM_DESTELLO_CUADROS, 0]))
            elif t["alcance"] == 1 and destella:
                entradas.append(bytes([tick, ANIM_FLASH, blanco, r, g, b,
                                       fuerza, ANIM_DESTELLO_CUADROS]))
        entradas.sort(key=lambda e: e[0])   # estable: el orden del LDB
        if len(entradas) > 255:
            raise NoSePuede()
        # Una `global` —la que RM2k repite en tres por tres para tapar la
        # pantalla— se acepta y no se dibuja: se sigue oyendo y destellando,
        # que es lo que ya hacía. Ninguna de las once de la intro la pide.
        numero = (p[0] if p[0] <= 255 and not (len(p) > 3 and p[3])
                  else ANIM_SIN_DIBUJO)
        out = (bytes([OP_ANIMATION, numero, dibujo_blanco(anim, blanco),
                      len(entradas)])
               + b"".join(entradas))
        cuadros = 2 * len(anim["cuadros"])
        if p[2] and cuadros:
            out += bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == FLASH_SCREEN:
        # `CommandFlashScreen`, en su forma de RM2k: color, fuerza, décimas y
        # si espera. Las 62 del juego son de esa forma, y ninguna dura más de
        # veinte décimas: el byte de cuadros alcanza, y la ROM divide el nivel
        # por lo que queda con el divisor de ocho bits del hardware.
        if len(p) < 6 or any(not 0 <= v <= 31 for v in p[:4]):
            raise NoSePuede()
        cuadros = p[4] * CUADROS_POR_DECIMA
        if cuadros > 0xFF:
            raise NoSePuede()
        out = bytes([OP_FLASH_SCREEN, p[0], p[1], p[2], p[3], cuadros])
        if cuadros and p[5]:
            out += bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == TRADE_EVENT_LOCATIONS:
        # `CommandTradeEventLocations`: cada uno va con `MoveTo` a la celda
        # del otro. Sobre el héroe no lo usa ninguna página del juego.
        if len(p) < 2 or eventos_mapa is None:
            raise NoSePuede()
        blancos = [eventos_mapa.blanco(q) for q in p[:2]]
        if any(b is None or b == 0 for b in blancos):
            raise NoSePuede()   # el héroe, un vehículo o un evento que no existe
        return bytes([OP_SWAP] + blancos)

    if cmd.code == WAIT:
        if len(p) < 1:
            raise NoSePuede()
        cuadros = p[0] * CUADROS_POR_DECIMA
        if cuadros > 0xFFFF:
            raise NoSePuede()
        return bytes([OP_DELAY, cuadros & 0xFF, cuadros >> 8])

    if cmd.code == TINT_SCREEN:
        if len(p) < 4:
            raise NoSePuede()
        if any(not 0 <= v <= 200 for v in p[:4]):
            raise NoSePuede()
        # La duración se descarta: el tinte se aplica de una. La pantalla que
        # se compara está siempre asentada, así que el valor final es el que
        # importa; lo que se pierde es el degradé de un segundo.
        return bytes([OP_TINT, p[0], p[1], p[2], p[3]])

    if cmd.code == SHOW_MESSAGE:
        if mensajes is None:
            raise NoSePuede()   # esta ROM no lleva ventana: no hay dónde
        lineas = [cmd.string] + list(extra)
        # La cola de escapes la saca `Mensajes.agregar`, que es por donde pasan
        # todos los cuadros; lo que no sea `\|` ni `\^` sigue cortando la
        # página desde ahí. Ver `cola_de_escapes`.
        donde = mensajes.agregar(lineas)
        return bytes([OP_MESSAGE, donde & 0xFF, donde >> 8])

    raise NoSePuede()


class Estado:
    """El grupo, para simular sus cambios al convertir: `lideres_posibles` y
    `grupo_de_la_pagina` en snes_convert.py. Es lo que quedó del estado del
    intérprete de Python, que se fue con la referencia; la ROM es la única que
    corre el bytecode."""

    def __init__(self, grupo=()):
        # El grupo, en orden. El gráfico del héroe es el del primero, así que
        # el orden decide qué poses tienen que entrar en la VRAM.
        self.grupo = list(grupo)

    def cambiar_grupo(self, operacion, actor):
        """Agrega o saca un actor, con las reglas de RM2k.

        Agregar uno que ya está no lo duplica y no lo mueve de lugar, agregar
        con el grupo lleno no hace nada, y sacar uno que no está tampoco: es lo
        que hace `Game_Party::AddActor`/`RemoveActor` en easyrpg-player, que
        además llama a `ResetGraphic` en los dos casos. Importa porque el orden
        decide quién es el líder, o sea qué sprite se dibuja.
        """
        if operacion == GRUPO_SACAR:
            if actor in self.grupo:
                self.grupo.remove(actor)
        elif actor not in self.grupo and len(self.grupo) < GRUPO_MAX:
            self.grupo.append(actor)

    def lider(self):
        return self.grupo[0] if self.grupo else None


# Cuánto ocupa cada opcode se deriva de sus argumentos declarados, así que
# `OPCODE_SIZE` y `opcode_size` vienen de `opcodes.py`, generado desde
# `tools/protocol/events.toml`. Antes se escribían a mano, y había dos copias —una
# acá y otra en el conversor—: la de acá se quedó con el OP_ROUTE viejo cuando
# el nuevo sumó la frecuencia, y fueron doce casos de la tanda en rojo.


# La sacudida de pantalla, `Shake::NextPosition` de easyrpg:
#
#     amplitud = 1 + 2 * fuerza
#     nuevo    = -amplitud * sin((resta * 4 * (velocidad + 2)) % 256 * pi / 128)
#     corte    = velocidad * amplitud / 8 + 1
#     posicion = clamp(nuevo, posicion - corte, posicion + corte)
#
# con `resta` los cuadros que le quedan, y la posición en pixeles que se le
# suman a la cámara al dibujar el mapa —`GetDisplayX`—: la ventana de mensaje
# no se mueve. RPG_RT lo hace en punto flotante y trunca; acá el seno es una
# tabla de 256 bytes a escala 127 y la división es entera, **de los dos lados
# igual**, así que la ROM y la referencia coinciden exacto y las dos pueden
# diferir de RPG_RT en un pixel en algún cuadro. La tabla la emite el
# conversor al mapdata.inc desde esta misma lista.
SENO_SACUDIDA = [round(math.sin(t * math.pi / 128) * 127) for t in range(256)]


def recorrer_codigo(codigo):
    """(desplazamiento, código) de cada opcode de una página ya compilada."""
    i = 0
    while i < len(codigo):
        yield i, codigo
        i += opcode_size(codigo, i)


def blancos_de_ruta(paginas):
    """Los eventos a los que estas páginas ya compiladas les mandan una ruta.

    Recorre el bytecode y no los comandos de RM2k, que es lo que hace que sea la
    verdad y no una conjetura: lo que cuenta es lo que quedó emitido, después de
    que el filtro decidiera qué páginas entran.
    """
    blancos = set()
    for pagina in paginas:
        codigo = pagina.get("codigo")
        for i, c in recorrer_codigo(codigo or b""):
            if c[i] == OP_ROUTE and c[i + 1]:
                blancos.add(c[i + 1] - 1)
    return blancos


# El switch con el que la página de prueba se apaga a sí misma: el último del
# bitmap de la ROM —`SWITCH_BYTES` son 128, o sea del 0 al 1023— y el juego
# llega hasta el 1003. Uno más alto se escribiría **fuera** del bitmap, que es
# lo que pasó la primera vez que esto se escribió con el 2000.
#
# Existe desde que las automáticas se repiten mientras siguen activas, que es
# lo que hacen en RM2k: una página inventada sin condición se repetiría para
# siempre y reiniciaría su propia ruta cada vez. Las páginas de verdad no
# tienen ese problema porque terminan prendiendo el switch que las desactiva
# —es el idioma de RM2k— así que la de prueba hace lo mismo, y de paso ejercita
# ese idioma.
SWITCH_DE_PRUEBA = 1023

# La variable que elige cuál de las páginas de prueba corre, cuando un cartucho
# lleva varias: ver `--caso` en snes_convert.py. La página k pide que valga
# **al menos** k, que es la única comparación que RM2k 2000 ofrece en la
# condición de una página, y como gana la de número más alto que se cumple,
# con la variable en k corre la k y ninguna otra. Con una sola variable
# alcanza para cualquier cantidad de casos; con un switch por caso no: libres
# quedan del 1004 al 1020 y el 1022.
#
# El número no importa, porque la ROM habla de ranuras, y ninguna página del
# juego nombra al 1000. Va más arriba que todas las del juego, así que su
# ranura es la última y no corre la de ninguna otra.
VARIABLE_DE_CASO = 1000
COMPARAR_AL_MENOS = 1   # el `>=` de las condiciones de página de RM2k
# El switch que no se prende nunca: es lo que lleva como `switch_a` una página
# con una condición que el port no puede cumplir —un ítem, ver
# `rm2k.CONDICIONES_IMPOSIBLES`— para que ni la ROM ni la referencia la elijan
# jamás, y las otras páginas del evento sí. Los dos lados leen la misma tabla,
# así que no hay dos maneras de equivocarse. El juego consulta switches hasta el
# 1003 y el 1023 es el de la página de prueba.
SWITCH_IMPOSIBLE = 1021


# Los pesos de luminancia de RM2k, que son los de Y' del Y'CbCr: la cuenta de
# `saturation_tone` en easyrpg es `(7471*b + 38470*g + 19595*r) >> 16`. Suman
# exactamente 65536, así que aplicados a canales de cinco bits dan una
# luminancia de cinco bits sin tener que reescalar nada.
LUZ_R, LUZ_G, LUZ_B = 19595, 38470, 7471
LUZ_TOTAL = 65536


def luminancia(r, g, b):
    """La luminancia de un color de 15 bits, en cinco bits."""
    return (LUZ_R * r + LUZ_G * g + LUZ_B * b) // LUZ_TOTAL


def saturar(canal, luz, s):
    """Un canal acercado o alejado del gris, con `s` en las unidades de RM2k.

    Es `saturation_tone` de easyrpg puesto en cinco bits y en las unidades de
    RM2k en vez de las suyas. Allá el factor es
    `sat = gray > 128 ? 1024 + (gray - 128) * 16 : gray * 8` sobre 1024, con
    `gray = s * 128 / 100`; hecha la cuenta, eso es `s / 100` para `s <= 100` y
    `(2s - 100) / 100` para `s > 100`. O sea que 0 lleva todo al gris, 100 no
    hace nada, y 200 triplica la distancia al gris.

    El caso de más de 100 va con el signo separado y truncando, en vez de con
    el desplazamiento aritmético de easyrpg, que redondea hacia abajo también
    con números negativos. La diferencia es de un valor de 31 y sólo cuando
    sobresatura; hacerlo con signo en el 65816 costaría bastante más que eso.
    """
    if s <= TINTE_NEUTRO:
        # Una interpolación entre el gris y el color, con los dos términos
        # positivos: es la forma que el 65816 puede hacer sin signo.
        return (luz * (TINTE_NEUTRO - s) + canal * s) // TINTE_NEUTRO
    m = s - TINTE_NEUTRO
    if canal >= luz:
        return min(31, canal + (canal - luz) * m // TINTE_NEUTRO)
    return max(0, canal - (luz - canal) * m // TINTE_NEUTRO)


def tenir_canal(canal, valor):
    """Un canal de cinco bits pasado por el tinte de RM2k, que es un hard light.

    RM2k no escala el canal: lo compone con un *hard light* —`hard_light.table`
    en easyrpg, que es `2ab` para la mitad de abajo y el screen `1-2(1-a)(1-b)`
    para la de arriba—. En las unidades de RM2k, con 100 neutro, eso es:

        valor <= 100:  canal * valor / 100
        valor  > 100:  31 - (200 - valor) * (31 - canal) / 100

    La primera mitad es exactamente lo que este repo venía haciendo, y por eso
    los tintes que oscurecen no cambian: la ROM y la referencia dan lo mismo que
    antes. La segunda no lo era. `canal * valor / 100` con valor hasta 200
    multiplica por dos y topa, y eso **no es** lo que hace RM2k: la diferencia
    llega a 31 de 31 con valor 200, o sea la pantalla entera. No lo cobró nadie
    porque ninguna página que compilara usaba un tinte que aclare; las dos que
    lo destraba la saturación —los mapas 229 y 230— sí, con (0, 120, 120).

    Medido contra la cuenta de easyrpg sobre ocho bits, esta versión difiere en
    **un valor de 31 como mucho**, para todos los tintes que el juego usa. Es la
    misma tolerancia que ya tenía la mitad de abajo, y viene de que RM2k hace la
    cuenta con ocho bits y la consola tiene cinco.
    """
    if valor <= TINTE_NEUTRO:
        return min(31, canal * valor // TINTE_NEUTRO)
    return min(31, 31 - (2 * TINTE_NEUTRO - valor) * (31 - canal) // TINTE_NEUTRO)


def tenir(palabra, tinte):
    """Un color de 15 bits pasado por el tinte de pantalla.

    Primero la saturación y después el color, que es el orden de `ToneBlit`:
    allá `saturation_tone` corre antes que `color_tone`. Hacerlo al revés da
    otra cosa —el gris se calcularía sobre el color ya teñido— y es de las que
    la comparación no vería, porque los dos lados harían lo mismo mal.

    La cuenta va con enteros y sobre los 15 bits, no sobre los 24 del PNG: la
    consola tiene cinco bits por canal y redondearía distinto.
    """
    canales = [palabra & 0x1F, (palabra >> 5) & 0x1F, (palabra >> 10) & 0x1F]
    if len(tinte) > 3 and tinte[3] != TINTE_NEUTRO:
        # Sólo cuando hace falta, igual que el `apply_sat` de easyrpg: la
        # saturación no se puede hacer canal por canal —necesita el gris del
        # color entero— y es lo caro de esto en la consola.
        luz = luminancia(*canales)
        canales = [saturar(c, luz, tinte[3]) for c in canales]
    salida = 0
    for numero, (canal, valor) in enumerate(zip(canales, tinte)):
        salida |= tenir_canal(canal, valor) << (numero * 5)
    return salida


def deudas_de_la_pagina(page, imagenes=None):
    """Qué comandos de esta página se aceptan sin hacerlos.

    Para que el conversor pueda avisar en vez de que la deuda quede muda.

    Los tres de `Picture` sólo son deuda **si esta página no es la del cartel
    que la ROM sí dibuja**: avisar igual sería el aviso que nadie lee, que es
    como una deuda de verdad se pierde entre las que ya no lo son.
    """
    salida = set()
    for cmd in page.commands:
        if cmd.code not in ACEPTADOS_SIN_HACER:
            continue
        if (cmd.code in (SHOW_PICTURE, MOVE_PICTURE, ERASE_PICTURE)
                and _compilar_imagen(cmd, imagenes) is not None):
            continue
        salida.add(cmd.code)
    return sorted(salida)


def paginas_del_mapa(game_map, indice_de_mapa, mensajes=None, temas=None,
                     graficos=None, imagenes=None, tropas=None):
    """Las páginas que la ROM necesita para resolver los eventos del mapa.

    Se emiten *todas* las páginas de un evento que tenga alguna disparable, no
    sólo ésas: cuál queda activa depende de las condiciones de todas ellas, y
    una página posterior que no dispare nada igual gana y le impide correr a la
    de más abajo.
    """
    salida = []
    del_mapa = Eventos(game_map)
    chipset = getattr(game_map, "chipset_nombre", None)
    for numero_evento, event in enumerate(game_map.events):
        # Van **todos** los eventos, tengan o no una página que dispare algo:
        # desde el 2026-09-05 la tabla dice además en qué capa está la página
        # activa, que es lo que decide si el evento le cierra el paso al héroe
        # —o a otro evento—, y eso lo hace cualquier evento, hasta uno que no
        # corre nada. Antes se guardaban sólo los que tenían código, y un
        # droide sin página compilable —el de la batalla— no habría frenado a
        # nadie.
        #
        # Si alguna página del evento pide una condición que la ROM no sabe
        # evaluar —una variable, un cronómetro— entonces no se sabe cuál
        # página está activa, y correr la equivocada es peor que no correr
        # ninguna. El evento entero queda afuera, y tampoco frena: su capa es
        # tan desconocida como su código. La condición de **ítem** es otra
        # cosa: se sabe que no se cumple nunca, y la página se emite como tal.
        if not rm2k.condiciones_soportadas(event):
            continue

        grupo = []
        for numero_pagina, page in enumerate(event.pages):
            cond = page.condition
            codigo = None
            if rm2k.pagina_imposible(page):
                # Nunca activa: sin código, sin gráfico, y con el switch que
                # no se prende. Las páginas de abajo siguen ganando cuando les
                # toca, que es lo que hace RM2k mientras el ítem no está.
                grupo.append({
                    "evento": numero_evento, "pagina": numero_pagina,
                    "trigger": page.trigger,
                    "switch_a": SWITCH_IMPOSIBLE, "switch_b": 0, "actor": 0,
                    "variable": None, "item": 0,
                    "capa": page.layer, "frecuencia": page.move_frequency,
                    "velocidad": page.move_speed, "codigo": None,
                    "ruta_propia": None, "grafico": None, "tile_pasa": None,
                    "gira": False,
                })
                continue
            grafico = rm2k.grafico_de_pagina(page, chipset)
            # **Una página automática o paralela sin un solo comando no arranca
            # nada.** Es `Game_Interpreter::Push`, que vuelve en seguida con una
            # lista vacía: el intérprete no queda corriendo y el jugador camina.
            # Acá, en cambio, la página vacía se volvía la activa, se ejecutaba
            # en un tick, terminaba, y como una automática se repite mientras
            # siga siendo la activa, volvía a arrancar: el mapa quedaba
            # congelado para siempre y el héroe no daba un paso.
            #
            # Es el idioma con el que RM2k desactiva un evento —una página de
            # abajo prende el switch que activa una de arriba, y ésa está
            # vacía—, así que no es un caso raro: en Rat Tracks B1 son dos, y el
            # mapa era injugable. Lo delató `heroe 21` al tardar catorce
            # minutos, porque la referencia se comía sus 100.000 ticks de
            # páginas automáticas antes de empezar a caminar.
            #
            # Se apaga poniéndole el código en None, que es lo que los dos lados
            # ya miran para decidir si una página automática cuenta
            # (`eventos_auto` acá, el bit 7 de la página en el conversor).
            vacia = not page.commands and page.trigger in (TRIGGER_AUTOMATICO,
                                                           TRIGGER_PARALELO)
            if page.trigger in TRIGGERS and puede_dispararse(page) and not vacia:
                codigo = compilar_pagina(page, indice_de_mapa, mensajes,
                                         del_mapa.para(event.id), temas,
                                         graficos, imagenes, tropas)
            grupo.append({
                "evento": numero_evento,
                "pagina": numero_pagina,
                "trigger": page.trigger,
                "switch_a": cond.ids["switch_a"] if "switch_a" in cond.active else 0,
                "switch_b": cond.ids["switch_b"] if "switch_b" in cond.active else 0,
                "actor": cond.ids["actor"] if "actor" in cond.active else 0,
                "variable": ((ranura_de_variable(cond.ids["variable"]),
                              cond.operator, cond.variable_value)
                             if "variable" in cond.active else None),
                "item": cond.ids["item"] if "item" in cond.active else 0,
                "capa": page.layer,
                "frecuencia": page.move_frequency,
                "velocidad": page.move_speed,
                "codigo": codigo,
                "ruta_propia": ruta_propia(page),
                # Lo que dibuja la página y lo que su tile le impone a la
                # celda: ver `rm2k.collect_npcs`, y `pasa_con_evento` en
                # rom/src/heroe.s, que es quien los aplica.
                "grafico": grafico,
                "tile_pasa": (rm2k.pasabilidad_del_tile(game_map, grafico[0],
                                                        page.layer)
                              if grafico is not None else None),
                # Si el evento se da vuelta hacia el héroe con esta página: un
                # CharSet —un tile del chipset no tiene hacia dónde mirar— y
                # un tipo de animación que no fije la dirección. Ver GIRO.
                "gira": bool(page.character_name)
                        and page.animation_type not in ANIM_FIJAS,
            })
        salida += grupo
    return salida


# Los tipos de animación de la página, `rpg::EventPage::AnimType`.
ANIM_NO_CONTINUA, ANIM_CONTINUA_TIPO, ANIM_FIJA_NO_CONTINUA = 0, 1, 2
ANIM_FIJA_CONTINUA, ANIM_GRAFICO_FIJO, ANIM_GIRO = 3, 4, 5


def ruta_propia(page):
    """La ruta propia de la página —`move_type` 6, la ruta que camina sola—,
    o None si no tiene o no se puede.

    Van las mismas órdenes que en un MoveEvent, con el sonido y la
    transparencia tirados. Las diagonales entran: una ruta propia es siempre
    de un evento, que es sobre quien la ROM las camina. Lo que queda afuera:
    moverse hacia o desde el héroe, cambiar el gráfico —ninguna la usa— y los
    switches; y el giro en el lugar
    (`AnimType_spin`), que ninguna de las dos páginas del juego que lo usan
    está en los primeros mapas. Los otros tipos de movimiento —al azar,
    vertical, horizontal, hacia el héroe— tampoco: son otra máquina.

    **Moverse hacia el héroe queda afuera también acá**, aunque desde el
    2026-09-12 la ROM la camine en una ruta forzada: son dos páginas del mapa
    105 —medido, las únicas de las 37 rutas propias del juego que la usan— y
    ninguna prueba llega ahí, así que aceptarla sería estrenar el camino sin
    nada que lo ejercite. La 21 está afuera por lo mismo desde antes: cero
    rutas propias la usan.
    """
    if page.move_type != 6 or not page.move_route.commands:
        return None
    if not RUTA_FRECUENCIA_MIN <= page.move_frequency <= RUTA_FRECUENCIA:
        return None
    if not 1 <= page.move_speed <= 6 or page.animation_type == ANIM_GIRO:
        return None
    ordenes = []
    for orden in page.move_route.commands:
        if orden == RUTA_SONIDO or orden in RUTA_TRANSPARENCIA:
            continue
        if orden not in RUTA_ORDENES or orden in (RUTA_ENCARAR_HEROE,
                                                  RUTA_HACIA_HEROE):
            return None
        if orden == RUTA_CAMBIAR_GRAFICO:
            # Acá no hay dónde poner el operando —una ruta de página es una
            # lista pelada de códigos, no un MoveEvent con su texto— y no hace
            # falta: **ninguna de las 3509 rutas propias del juego cambia de
            # gráfico**, medido. El día que aparezca una, esto la rechaza en
            # vez de compilar un 34 sin a qué cambiar.
            return None
        ordenes.append(orden)
    if frecuencia_minima(page.move_frequency, ordenes,
                         page.move_route.repeat) < RUTA_FRECUENCIA_MIN:
        return None             # las órdenes 30 y 31 la bajarían hasta la 1
    if not ordenes or len(ordenes) > 255:
        return None
    return {
        "ordenes": ordenes,
        "frecuencia": page.move_frequency,
        "velocidad": page.move_speed,
        "repite": page.move_route.repeat,
        "saltable": page.move_route.skippable,
        "dir_fija": page.animation_type in (ANIM_FIJA_NO_CONTINUA,
                                           ANIM_FIJA_CONTINUA,
                                           ANIM_GRAFICO_FIJO),
        "anim_continua": page.animation_type in (ANIM_CONTINUA_TIPO,
                                                ANIM_FIJA_CONTINUA),
    }
