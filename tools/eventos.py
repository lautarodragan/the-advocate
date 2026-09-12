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

import math
import os
import sys

import rm2k

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- los comandos de RM2k que sabemos ejecutar ------------------------------
END = 10
CONTROL_SWITCHES = 10210
TELEPORT = 10810
TINT_SCREEN = 11030
WAIT = 11410
CHANGE_SAVE_ACCESS = 11930
# Abrir el menú de guardar: la pantalla de ranuras, que congela el juego
# mientras se ve y no cuesta ningún tick. Ver `OP_GUARDAR`.
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


def con_signo(palabra):
    """Los dieciséis bits de un word leídos como entero con signo."""
    return palabra - 0x10000 if palabra & 0x8000 else palabra


def paso_de_pan(velocidad):
    """Cuánto corre la cámara por cuadro, en 1/16 de pixel.

    Es `data()->pan_speed = 2 << speed` de `Game_Player::StartPan`, con la
    velocidad topada entre 1 y 6 como hace `CommandPanScreen`. El juego usa de
    la 2 a la 6: de medio pixel por cuadro a ocho.
    """
    return 2 << min(PAN_VEL_MAX, max(PAN_VEL_MIN, velocidad))


def cuadros_de_pan(falta, paso):
    """Cuántos cuadros espera la página que pidió el pan con `esperar`.

    Es `Game_Player::GetPanWait`: la distancia que falta dividida por el paso,
    redondeando para arriba. Se mide **al pedirlo** y sobre lo que falta, no
    sobre lo que este comando pidió: con un pan todavía corriendo RM2k espera
    por los dos, y de ahí el comentario de `CommandPanScreen` sobre el máximo.
    """
    return -(-falta // paso)
LUGAR_CONSTANTE = 0         # p[1]: 0 es la celda escrita, 1 la lee de variables

# Un cuadro de texto. RM2k emite un `ShowMessage` con la primera línea y un
# `ShowMessage_2` por cada una de las que siguen del mismo cuadro: son un solo
# comando —una ventana, una espera del jugador— y quien los cuente por separado
# mide cualquier cosa. Ya pasó: contándolos aparte, los cuadros de texto
# parecían destrabar tres páginas en vez de cincuenta y cinco.
SHOW_MESSAGE = 10110
SHOW_MESSAGE_2 = 20110

# Los códigos de escape que el texto de este juego usa: `\|` es una pausa de un
# segundo y `\^` cierra el cuadro sin esperar a que el jugador apriete nada.
# Los dos son tiempo, no texto, y no los hacemos.
#
# Una página que los use no compila, y eso es a propósito. Dibujarlos como dos
# letras se vería —son 35 líneas del juego—, y borrarlos calladito sería peor:
# con `\^` el cuadro se cierra solo, así que la ROM quedaría esperando un A que
# RM2k nunca pidió y la página entera pasaría a durar lo que tarde el jugador.
# Son 17 páginas de las 279 con texto; cuando el compositor sepa pausar y
# autocerrar, esto se cae solo.
ESCAPE = "\\"

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
RUTA_VEHICULOS = (10002, 10003, 10004)      # barco, nave, avión: no existen acá
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
    mismo que una ruta compilada, donde la 34 arrastra un byte —para ésa está
    `recorrer_ruta`—.

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
# Y el salto, `jump_speed[move_speed - 1]`.
SALTO_VELOCIDADES = (8, 12, 16, 24, 32, 64)
# Cada cuántos cuadros cambia el frame de la caminata, por velocidad:
# `GetStationaryAnimFrames` mientras se camina y `GetContinuousAnimFrames`
# quieto con la animación continua. Es `Game_Character::UpdateAnimation`.
ANIM_PARADO = (12, 10, 8, 6, 5, 4)
ANIM_CONTINUA = (16, 12, 10, 8, 7, 6)


def columna_animada(tick, velocidad):
    """La columna del ciclo de un evento **quieto** con animación continua.

    Los que caminan llevan su propio contador adentro de la ranura de ruta y
    esto no los toca; los quietos no tienen ranura ni dónde guardar un contador
    —ver `animar_quietos` en main.s— así que la columna sale del reloj del
    juego: cada `ANIM_CONTINUA` ticks avanza un paso del ciclo de cuatro.

    **La fase no es la de RM2k**, que arranca el contador de cada personaje
    cuando el mapa lo crea. Acá es global, así que un evento que aparece a mitad
    de la partida entra con el ciclo empezado. Es una elección, está declarada
    en `assets/LIMITACIONES.md`, y lo que la hace válida es que los dos lados la
    calculan con la misma fórmula y el mismo reloj.
    """
    paso = (tick & rm2k.TICK_MASCARA) // ANIM_CONTINUA[velocidad - 1]
    return rm2k.CICLO_TRES[paso % len(rm2k.CICLO_TRES)]

# El sonido va adentro de la ruta y se acepta sin hacerlo —PlaySound sí suena
# desde el 2026-09-11, pero la ruta no tiene cómo pedirlo—: no se ve. Se tira al compilar, así que el bytecode sigue siendo un byte por
# orden y no cuesta ni un cuadro, que es lo que hace RM2k —no toca el contador
# de parada—.
RUTA_SONIDO_SE_TIRA = True

# Un salto dura lo que tarda `remaining_step` en bajar de 256 a 0 a
# `jump_speed[move_speed - 1]` por cuadro. Con la velocidad 4 —la de este
# juego— son 24 por cuadro, o sea once cuadros, y **no depende de la
# distancia**: saltar cinco celdas cuesta lo mismo que saltar en el lugar.
SALTO_PASO = 256
SALTO_VELOCIDAD = 24

# Qué celda es "la de al lado" en cada dirección. Vive acá y no en quien camina
# porque ahora camina más de uno: el héroe y los eventos con ruta forzada.
RUTA_PASOS = {0: (0, -1), 1: (1, 0), 2: (0, 1), 3: (-1, 0),
              4: (1, -1), 5: (1, 1), 6: (-1, 1), 7: (-1, -1)}

# Las cuatro diagonales de ruta, cada una con sus dos componentes: primero la
# vertical y después la horizontal. Son `move_upright`, `move_downright`,
# `move_downleft` y `move_upleft`.
#
# Las caminan **sólo los eventos**. De las 26 rutas del juego que las usan
# ninguna es del héroe, así que la ROM no las tiene sobre él: caminar en
# diagonal con el pad no existe y darle un paso diagonal al héroe pediría
# duplicar `try_up` y sus tres hermanas para nada. El conversor rechaza la
# página que lo intente —ver MOVE_EVENT en `traducir`—, que es lo que impide
# que los dos lados se separen en silencio.
RUTA_DIAGONALES = {4: (0, 1), 5: (2, 1), 6: (2, 3), 7: (0, 3)}


def encarar_en_diagonal(mirando, orden):
    """Hacia dónde queda mirando quien da un paso en diagonal.

    Es `Game_Character::UpdateFacing`, y la respuesta no es "hacia la
    diagonal": el charset tiene cuatro poses y ninguna apunta a un rincón. RM2k
    se queda con la que el personaje ya tenía si es una de las dos componentes
    del paso, y si no la da vuelta 180°. O sea que caminar arriba-derecha
    mirando abajo deja mirando arriba, y mirando arriba no cambia nada.
    """
    vertical, horizontal = RUTA_DIAGONALES[orden]
    if mirando in (vertical, horizontal):
        return mirando
    return (mirando + 2) % 4


def puede_en_diagonal(orden, puede):
    """Si el paso diagonal sale, con la regla de `Game_Character::Move`.

    RM2k **no mira la celda diagonal**: prueba las dos eles. Primero la
    vertical y después la horizontal, y si esa no sale, la horizontal y después
    la vertical; alcanza con que una de las dos esté libre entera, codo
    incluido. Por eso no se cruza el vértice de dos paredes en diagonal, pero
    sí se pasa si hay por dónde rodear.

    `puede(direccion, desde)` es el mismo del paso derecho con la celda de
    partida corrida: la segunda pata de cada ele arranca en el codo, no donde
    está parado el personaje.
    """
    vertical, horizontal = RUTA_DIAGONALES[orden]
    codo_v, codo_h = RUTA_PASOS[vertical], RUTA_PASOS[horizontal]
    return ((puede(vertical) and puede(horizontal, codo_v))
            or (puede(horizontal) and puede(vertical, codo_h)))

# Las órdenes de ruta que sabemos caminar, en un solo lugar. `destraba.py` mide
# con esta misma lista, así que el día que aprenda una más el número sube solo.
RUTA_ORDENES = (set(RUTA_MIRAR) | set(RUTA_MOVER)
                | {RUTA_ESPERAR, RUTA_SALTO_INICIO, RUTA_SALTO_FIN,
                   RUTA_ATRAVESAR_ON, RUTA_ATRAVESAR_OFF,
                   RUTA_ANIM_PARAR, RUTA_ANIM_SEGUIR, RUTA_ENCARAR_HEROE,
                   RUTA_FIJAR_DIR, RUTA_SOLTAR_DIR, RUTA_VEL_MAS, RUTA_VEL_MENOS,
                   RUTA_FREC_MAS, RUTA_FREC_MENOS, RUTA_CAMBIAR_GRAFICO})


def recorrer_ruta(ruta):
    """Las órdenes de una ruta **ya compilada**, con su operando si lo lleva.

    El bytecode es un byte por orden salvo la 34, que arrastra detrás a qué
    gráfico cambia. Recorrerlo plano sería la trampa de `decodificar_ruta` otra
    vez: el operando se leería como una orden, y con un 30 o un 31 de operando
    cambiaría la frecuencia de la ruta sin que nadie lo pidiera.
    """
    i = 0
    while i < len(ruta):
        orden = ruta[i]
        i += 1
        if orden == RUTA_CAMBIAR_GRAFICO:
            if i >= len(ruta):
                raise NoSePuede()
            yield orden, ruta[i]
            i += 1
        else:
            yield orden, None


def direccion_hacia(desde, hasta):
    """Hacia dónde mira quien está en `desde` para encarar a `hasta`, en celdas.

    Es `Game_Character::GetDirectionToCharacter`, con sus dos vueltas: gana el
    eje con **más** distancia y en empate el vertical, y sobre la misma celda
    o con el otro más abajo se mira abajo.
    """
    sx = desde[0] - hasta[0]
    sy = desde[1] - hasta[1]
    if abs(sx) > abs(sy):
        return 3 if sx > 0 else 1        # izquierda si el otro está a la izquierda
    return 0 if sy > 0 else 2            # arriba si el otro está más arriba

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
# tiempo sale gratis: es un OP_ESPERAR detrás.
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
# venía sonando. La pantalla no lo nota, pero `snes-check` compararía el audio
# contra el MIDI del mapa y no contra el tema que la página pidió, así que ahí
# la prueba mediría lo que no es. Ver "Lo que falta" en README.md.
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
# Se acepta porque **es lo único que traba la cinemática de apertura**, que es
# la puerta a los primeros diez minutos del juego. Sin esto la ROM no arranca la
# historia; con esto arranca, sin lluvia.
#
# **Desde el 2026-09-11 la lluvia se dibuja**: ver OP_CLIMA. La nieve, la
# niebla y la tormenta de arena siguen sin dibujarse, y apagan la lluvia.
WEATHER_EFFECTS = 11070

# PlaySound toca un efecto: una puerta, un golpe, el Insta-Shave de Talan.
# Suena desde el 2026-09-11 (ver OP_SONIDO); hasta ahí se aceptaba sin
# tocarlo, y era la deuda más barata de todas las que hay acá: **no se
# ve**. La pantalla que se compara es exactamente la misma con y sin sonido, y
# el audio que sí se compara —`snes-check`, contra el MIDI del mapa— tampoco
# cambia, porque el tema de fondo sigue sonando igual.
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
# **Desde el 2026-09-11 suenan**: ver OP_SONIDO.
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
# cualquier otro que entre en el mismo molde. Ver `Imagenes`, OP_IMAGEN y "El
# cartel de 'One year previously'" en el README. Los que no entran —los 27 de
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
# contestaran; desde el 11 abre la tienda de verdad: ver OP_TIENDA.
OPEN_SHOP = 10720

ACEPTADOS_SIN_HACER = {
    # CallEvent llama a la página de otro evento en el lugar. En los mapas 1 a
    # 10 lo usa una sola página, el Tram Officer del mapa 9, para subir al
    # Hover-Tram; taro pidió el 2026-09-10 dejarlo para otra vuelta. Lo que se
    # pierde: la escena del tram no corre y el jugador se queda parado con el
    # "It's here!" dicho. Es deuda declarada, no equivalencia.
    CALL_EVENT,
    SHOW_PICTURE,
    MOVE_PICTURE,
    ERASE_PICTURE,
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
        # audio de cada mapa: ver `paquete_cargar` en main.s.
        self.mapa = None
        self.por_mapa = {}

    def _anotar(self, que, valor):
        if self.mapa is None:
            return
        lista = self.por_mapa.setdefault(
            self.mapa, {"temas": [], "sonidos": []})[que]
        if valor not in lista:
            lista.append(valor)

    def indice(self, nombre):
        if nombre not in self.nombres:
            self.nombres.append(nombre)
        self._anotar("temas", self.nombres.index(nombre))
        return self.nombres.index(nombre)

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
    """

    def __init__(self):
        self.pares = []

    def indice(self, charset, index):
        par = (charset, index)
        if par not in self.pares:
            self.pares.append(par)
        return self.pares.index(par)


# --- los opcodes que emitimos -----------------------------------------------
# Uno por comando, con los operandos ya resueltos: la ROM no vuelve a mirar el
# LCF ni conoce sus números.
OP_FIN      = 0x00
OP_SWITCH   = 0x01      # id (word), valor (byte)
OP_TELEPORT = 0x02      # mapa (byte), x (word), y (word)
OP_ESPERAR  = 0x03      # cuadros (word): la cinemática espera seis
                        # segundos, o sea 360, y no entran en un byte
OP_TINTE    = 0x04      # r, g, b, sat (byte cada uno)
OP_GRUPO    = 0x05      # operación (byte), actor (byte)
OP_RUTA     = 0x06      # blanco (byte), frecuencia (byte), cuántos comandos (byte), y los
                        # comandos. El blanco es 0 para el héroe, y si no el
                        # índice del evento en la tabla del mapa más uno.
                        #
                        # **El índice no es el id de RM2k.** 39 mapas de este
                        # juego tienen huecos en la numeración de eventos, así
                        # que una ruta apuntada al id 8 movería al que esté
                        # octavo en la lista, que puede ser cualquier otro. Lo
                        # traduce el conversor, que es el único que ve el mapa.
OP_MENSAJE  = 0x07      # desplazamiento (word) dentro del bloque `mensajes`:
                        # abre esa ventana y bloquea la página hasta que el
                        # jugador apriete A
OP_RUTAS    = 0x08      # sin operandos: la página no sigue hasta que no quede
                        # ninguna ruta forzada corriendo
OP_FLASH    = 0x09      # blanco (byte), r, g, b, potencia (byte cada uno, de 0
                        # a 31) y cuántos cuadros dura (byte)
OP_LUGAR    = 0x0C      # blanco (byte, como en OP_RUTA: el índice del evento
                        # más uno), x (word), y (word). Planta al evento en la
                        # celda y le corta el paso en curso; no toca su ruta ni
                        # hacia dónde mira, que es lo que hace `MoveTo`.
OP_TRUEQUE  = 0x0D      # dos blancos (byte cada uno, como en OP_LUGAR): los
                        # dos eventos se cambian de celda entre sí, cada uno
                        # con `MoveTo`, que es `CommandTradeEventLocations`.
OP_SACUDIR  = 0x0E      # fuerza (byte), velocidad (byte), cuadros (word):
                        # `ShakeOnce`. Con cero cuadros es `ShakeEnd`: la
                        # pantalla vuelve a su lugar. Ver `sacudida_siguiente`.
OP_DESTELLO = 0x0F      # r, g, b, fuerza (byte cada uno, 0..31) y cuadros
                        # (byte): `FlashOnce`, el destello de la pantalla
                        # entera. Ver `Estado.cuadro_de_destello`.
OP_SI       = 0x12      # tipo (byte), operando (word), polaridad (byte),
                        # destino (word):
                        # `ConditionalBranch` con condición de switch. Si no se
                        # cumple, el cursor salta al destino, que es el `else`
                        # o el `end` de esa misma rama. La polaridad es la de
                        # RM2k al revés y a propósito: allá `parameters[2] == 0`
                        # quiere decir "tiene que estar prendido", así que acá
                        # 0 es "prendido" y 1 es "apagado", igual que el dato.
                        #
                        # El destino es **absoluto** dentro de la página, no
                        # relativo: el cursor de la ROM es un índice de 16 bits
                        # en el mismo array, así que asignarlo es todo el salto.
OP_IR       = 0x13      # destino (word): el salto sin condición que se emite
                        # donde estaba el `else`, para que la rama de arriba se
                        # saltee la de abajo.
OP_GUARDAR  = 0x16      # sin operandos: la partida a la SRAM del cartucho.
                        # Es `OpenSaveMenu`, pero sin menú: hay una sola ranura
                        # y el evento la pisa. Lo que se guarda lo dice
                        # `partida_tabla` en main.s, que es el único lugar donde
                        # está escrito. No cuesta un cuadro: en RM2k el menú
                        # bloquea, y acá no hay nada que mirar.
OP_ORO      = 0x15      # signo (byte: 0 suma, 1 resta) y monto de 24 bits. Es
                        # `ChangeGold`, y va en tres bytes porque el tope de
                        # RM2k son 999999 y el juego usa el valor entero: hay un
                        # comando que da exactamente eso.
                        #
                        # La ROM recorta a [0, ORO_MAX] como
                        # `Game_Party::GainGold`. Todavía no hay dónde mostrarlo
                        # —el menú no existe— pero sí quién lo pregunta: la rama
                        # de oro de `ConditionalBranch`.
OP_ELEGIR   = 0x14      # cuántas opciones (byte), qué hace cancelar (byte), y
                        # después una entrada por opción: el cuadro de texto
                        # (word) y el destino (word). Es `ShowChoice`.
                        #
                        # **Un cuadro de texto por opción, no uno solo.** Los
                        # cuadros llevan las mismas líneas y se diferencian en
                        # dónde está el cursor, así que mover el cursor es
                        # recomponer la ventana con otro desplazamiento y no
                        # dibujar nada nuevo. Cuesta unas decenas de bytes por
                        # elección y ahorra un tile de sprite, una paleta y todo
                        # el código de dibujarlo: en la consola no hay dónde
                        # poner un cursor que no sea un sprite, y los sprites de
                        # este mapa ya están repartidos entre los personajes.
                        #
                        # El destino es absoluto dentro de la página, como el de
                        # OP_SI, y el cuerpo de cada opción termina en un OP_IR
                        # al final de la elección.
OP_PAN      = 0x11      # operación (byte: PAN_CORRER o PAN_VOLVER), cuánto se
                        # corre el destino en x y en y (word con signo cada
                        # uno, en 1/16 de pixel), el paso por cuadro (byte) y
                        # si la página espera (byte).
                        #
                        # La dirección y la distancia vienen resueltas a un
                        # desplazamiento con signo, y la velocidad a su paso:
                        # son cuentas fijas y el conversor las hace una vez.
                        # Lo que **no** se puede resolver acá son los cuadros
                        # que la página espera: salen de lo que le falta al pan
                        # cuando el comando corre, y con uno todavía en curso
                        # eso no es lo que este comando pidió. Ver `GetPanWait`
                        # y el comentario de `CommandPanScreen` sobre el
                        # máximo.
OP_FUNDIR_BGM = 0x10    # paso (word): cuánto baja por cuadro el volumen del
                        # tema, en 1/65536 de lo que estuviera sonando.
                        #
                        # Va el paso y no los milisegundos que trae RM2k
                        # porque el 65816 no divide sin hardware y la cuenta
                        # es siempre la misma: `ceil(65536 / cuadros)`. Es la
                        # misma clase de número que el índice de mapa de un
                        # teletransporte —resuelto por el conversor para que
                        # la ROM no lo vuelva a mirar—, y lo hace
                        # `paso_de_fundido`.
OP_BGM      = 0x0B      # el índice del tema en `Temas` (byte). La ROM toca
                        # los que llevó —los primeros `TEMA_TOTAL`— y con
                        # cualquier otro no hace nada. Ver `Temas`.
OP_TIMER    = 0x0A      # operación (byte), segundos (word), visible (byte).
                        # Los cinco bytes son fijos aunque cada operación use
                        # dos: así el intérprete lo saltea sin mirar cuál es,
                        # que es lo que hace `recorrer_codigo` del conversor.

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


def brillo_de_fundido(t):
    """El brillo maestro en el cuadro `t` de un fundido, contado desde que el
    teletransporte se pidió. Fuera del fundido es `BRILLO_MAX`."""
    if t < 0 or t >= FUNDIDO_TOTAL:
        return BRILLO_MAX
    rampa = rampa_de_fundido()
    if t < FUNDIDO_RAMPA:
        return rampa[FUNDIDO_RAMPA - 1 - t]     # se va apagando
    if t < FUNDIDO_CUADROS + FUNDIDO_NEGRO:
        return 0                                # el negro donde carga el mapa
    return rampa[t - FUNDIDO_CUADROS - FUNDIDO_NEGRO]


def oscurecer(palabra, brillo):
    """Los 15 bits de un color con el brillo maestro aplicado.

    Es lo que hace el PPU con INIDISP, y la cuenta sale de la tabla que arma
    `PPU::PPU()` en bsnes: `round(canal * brillo / 15)` sobre los cinco bits de
    cada canal. Los tres cores dan lo mismo, comprobado.
    """
    if brillo >= BRILLO_MAX:
        return palabra
    salida = 0
    for i in range(3):
        canal = (palabra >> (5 * i)) & 0x1F
        salida |= ((2 * canal * brillo + BRILLO_MAX)
                   // (2 * BRILLO_MAX)) << (5 * i)
    return salida


# Qué dispara una página. Los de `rpg::EventPage::Trigger` de liblcf.
TRIGGER_ACCION = 0          # el jugador aprieta la tecla de acción enfrente
TRIGGER_TOCA_HEROE = 1      # el héroe camina encima
TRIGGER_TOCA_EVENTO = 2
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
        return otro

    def blanco(self, quien):
        """El byte de blanco que va en OP_RUTA, o None si no se puede mover.

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

    Es de la ROM entera y no del mapa: `OP_MENSAJE` lleva un desplazamiento
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

    def __init__(self):
        self.datos = bytearray()
        self.donde = {}         # las líneas ya guardadas -> su desplazamiento
        self.textos = {}        # y la vuelta, que es lo que usa la referencia

    def agregar(self, lineas):
        """El desplazamiento de este cuadro, guardándolo si es la primera vez.

        El recorte a lo que entra en un renglón se hace **acá**, antes de
        deduplicar: dos textos que sólo difieran en lo que se corta son el
        mismo cuadro en pantalla, y darles dos desplazamientos distintos sería
        emitir dos veces los mismos bytes.
        """
        import ventana as ventana_mod
        lineas = tuple(t[:ventana_mod.COLUMNAS]
                       for t in list(lineas)[:ventana_mod.LINEAS])
        if lineas not in self.donde:
            donde = len(self.datos)
            self.datos += mensaje_bytes(lineas)
            if len(self.datos) > 0x10000:
                raise SystemExit(
                    "los mensajes de esta ROM son %d bytes y el operando de "
                    "OP_MENSAJE es de 16 bits" % len(self.datos))
            self.donde[lineas] = donde
            self.textos[donde] = lineas
        return self.donde[lineas]

    def lineas(self, donde):
        """Las líneas que hay en ese desplazamiento. Es lo que dibuja la
        referencia: la ROM lee los mismos bytes del cartucho."""
        return self.textos[donde]

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


def mensaje_bytes(lineas):
    """Un cuadro de texto como lo lee la ROM: cuántas líneas, y cada una con su
    largo.

    Los caracteres van como índice en la tabla de la fuente, o sea el ASCII
    menos 32. Todo el texto de este juego entra ahí: se midió, y no tiene una
    sola letra acentuada.
    """
    import ventana as ventana_mod
    out = bytearray([min(len(lineas), ventana_mod.LINEAS)])
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

    Lo usan los dos que filtran páginas —`compilar_pagina` y `destraba.py`—
    porque el agrupado es parte del filtro, no del emisor: contar los comandos
    por separado es lo que hizo medir mal cuánto destrababa hacer los cuadros
    de texto.
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
COND_SWITCH = 0
COND_ORO = 3
COND_ACTOR = 5

# Y del "héroe" sólo la primera de sus siete preguntas. Las otras —nivel, HP,
# habilidad, equipo, estado— piden estadísticas de actor que este port no lleva.
# De los 155 comandos del juego que preguntan por un héroe, 57 son de ésta; 78
# preguntan por el equipo y 20 por una habilidad.
COND_ACTOR_EN_GRUPO = 0
# La rama por variable: `[1, variable, clase del valor, valor, comparación,
# hay else]`. La clase es 0 para una constante y 1 para otra variable; la
# comparación, `==`, `>=`, `<=`, `>`, `<` y `!=`, en ese orden, que es el de
# RM2k. Compila a OP_SI_VAR, no a OP_SI: no entra en siete bytes.
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
OP_VAR = 0x17       # ranura (byte), operación (byte), clase (byte), a (word), b (word)
OP_SI_VAR = 0x18    # ranura (byte), clase (byte), comparación (byte), valor (word),
                    # destino (word): como OP_SI, el destino va último para el parcheo
# El inventario, desde el 2026-09-10 a la noche: un byte por ítem del LDB en la
# RAM lejana —`FAR_ITEMS`, pegado a las variables—, indexado por el número de
# RM2k, y `ChangeItems` compila a OP_ITEM con el ítem y cuánto se suma, con
# signo. La cuenta queda en [0, ITEM_MAX], que es `Game_Party::AddItem` con el
# tope de RM2k. El juego lo usa 509 veces, siempre con ítem y cantidad
# constantes: el ítem por variable no compila. Con esto la condición de página
# por ítem se evalúa de verdad —`GetItemCount(id) > 0`, sin equipo todavía— y
# deja de ser "nunca activa". Cambiar un ítem pide el refresco de páginas.
OP_ITEM = 0x19      # ítem (word), delta (byte con signo)
ITEMS_N = 451       # los 450 ítems del LDB más el 0, que no se usa; lo cobra
                    # test_items.py contra RPG_RT.ldb
ITEM_MAX = 99
# `ChangeSaveAccess` y `ChangeMainMenuAccess`, desde que hay menú de pausa: cuál
# —0 guardar, 1 el menú— y si queda permitido. La ROM lo guarda en
# `FAR_ACCESO`; acá en `Estado`. Guardar desde el save point no lo mira, como
# `OpenSaveMenu` en RM2k.
OP_ACCESO = 0x1A    # cuál (byte), permitido (byte)
# Los HP y los estados, que fuera de batalla **no bajan nunca** en este juego:
# medido sobre los 328 mapas, los 11 `ChangeHP` suman —siete de a 1 al grupo,
# cuatro de 300 y 999 a un actor—, los 16 `ChangeCondition` quitan un estado y
# los 54 `FullHeal` llenan. O sea que fuera de batalla todos tienen siempre los
# HP y los SP al máximo y ningún estado, y estos tres comandos no cambian nada:
# compilan a nada, y es exacto, no una aproximación. El que baje HP o ponga un
# estado no compila, porque ahí sí habría algo que llevar.
# La tienda, desde el 2026-09-11: `OpenShop` compila a OP_TIENDA con el tipo
# —0 compra y vende, 1 sólo compra, 2 sólo vende—, el juego de mensajes y la
# lista de lo que vende, por número de ítem. Es de largo variable, como
# OP_ELEGIR. Como guardar, la pantalla se abre adentro del intérprete y no
# cuesta ningún tick: el mapa no corre mientras se ve. Las ramas de "compró"
# y "no compró" no compilan; ninguna de las 43 tiendas del juego las usa.
OP_TIENDA = 0x1B    # tipo, juego, cuántos (bytes), y de a dos bytes cada ítem
# El clima, desde el 2026-09-11: `WeatherEffects` compila a OP_CLIMA con el tipo
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
OP_CLIMA = 0x1C     # tipo, fuerza
CLIMA_LLUVIA = 1
LLUVIA_GOTAS = (15, 45, 75)
LLUVIA_VIDA = 12
LLUVIA_NACE = 26    # de 256
LLUVIA_SEMILLA = 0x1D2B
LLUVIA_LADO = 256   # la superficie, en los dos sentidos
LLUVIA_DX, LLUVIA_DY = -1, 4
LLUVIA_COLORES = ((16, 16, 18), (11, 11, 13), (6, 6, 7))   # de 5 bits


def lluvia_tono(t):
    """Cuál de los tres grises: más claro recién nacida."""
    return 0 if t >= 9 else 1 if t >= 5 else 2


def lluvia_pixeles(x, y):
    """Los pixeles de una gota con la esquina en (x, y): una raya de 4x16 que
    baja hacia la izquierda, un pixel cada cuatro filas."""
    return [(x + 3 - r // 4, y + r) for r in range(16)]


# Los efectos de sonido, desde el 2026-09-11: `PlaySound` compila a OP_SONIDO
# con el índice de su entrada en `Temas.sonidos`, y la tabla de la ROM dice
# con qué muestra, qué altura, qué volumen de cada lado y cuántos cuadros. Las
# muestras van en la ARAM junto al banco de la música, con un presupuesto
# propio: ver `build_efectos` en snes_music.py. Suenan en la voz 7, que se le
# roba a la música mientras duran. No se ven, así que la referencia sólo los
# salta: no cuestan ningún tick, como en RM2k.
OP_SONIDO = 0x1D    # índice (word)

# Las animaciones de batalla sobre el mapa, desde el 2026-09-11: sus sonidos y
# sus destellos, **sin el dibujo**. `ShowBattleAnimation` compila a
# OP_ANIMACION con la línea de tiempo entera adentro: cuántas entradas y, por
# cada una, ocho bytes —el tick en que dispara, contado desde el del comando,
# el tipo y seis de datos—. Es lo que `BattleAnimation::Update` hace con los
# `timings` de la animación: en el cuadro par `2 * (frame - 1)` suena el efecto
# y arranca el destello de la pantalla o del evento objetivo. Hay una sola a la
# vez —`Game_Screen::ShowBattleAnimation` reemplaza la anterior— y avanza una
# vez por cuadro **antes** que los destellos, que es donde `Game_Screen::Update`
# la pone. Con "esperar", la página espera lo que dura: dos cuadros por cuadro
# de la animación. Ver `cuadro_de_animacion`, y `animacion_tick` en main.s.
#
# El destello no es el de RM2k exacto: allá la fuerza es
# `min((7 - (d + 1) / 2) * potencia / 6, 31)` durante diez cuadros, a
# escalones; acá es un `FlashScreen` o un `FlashSprite` que arranca en la
# primera y baja lineal en `ANIM_DESTELLO_CUADROS`. Es la misma luz y dura lo
# mismo, y los dos lados hacen esta cuenta.
OP_ANIMACION = 0x1E     # n, y n entradas de ANIM_ENTRADA bytes
ANIM_ENTRADA = 8
ANIM_SONIDO, ANIM_DESTELLO, ANIM_FLASH = 0, 1, 2
# Diez, que es lo que dura el de RM2k, y **par** a propósito: el destello de
# pantalla trabaja en dos fases según la paridad de lo que le queda —ver
# `destello_tick`—, y un `FlashScreen` del juego dura siempre décimas por seis.
# Con once la primera fase era la par, un camino que ninguna página toma y
# donde la ROM y la referencia no coinciden: `snes-animacion` lo mostró.
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
#   OP_IMAGEN        r, g, b, sat (bytes, 100 neutro): lo pone con ese tono.
#   OP_IMAGEN_MOVER  el tono al que va, y en cuántos cuadros. No corta el
#                    cuadro: si la página espera, el conversor le pone un
#                    OP_ESPERAR detrás, como al `FlashScreen` y a la sacudida.
#   OP_IMAGEN_BORRAR lo saca.
#
# **El fundido del cartel es el tono y no la transparencia**, que es lo que
# había que ir a mirar: los dos `MovePicture` de la página del "1 year earlier"
# dejan `top_trans` en 0 y mueven (r, g, b) entre 0 y 100 con la saturación
# quieta en 100. O sea que la imagen aparece **negra**, sube a su color y vuelve
# a negro; en la consola eso es teñir sus quince entradas de CGRAM, que es
# exactamente la cuenta que el tinte de pantalla ya hacía.
OP_IMAGEN = 0x1F        # r, g, b, sat
OP_IMAGEN_MOVER = 0x20  # r, g, b, sat, cuadros (byte)
OP_IMAGEN_BORRAR = 0x21
# Cuántos cuadros puede durar un `MovePicture` para que entre en el byte de
# `OP_IMAGEN_MOVER`. Los dos de la página duran 210 y 120.
IMAGEN_CUADROS_MAX = 255


def imagen_tono(desde, hasta, paso, pasos):
    """El tono del cartel en el cuadro `paso` de `pasos`, componente por
    componente.

    `Game_Pictures::Picture::Update` interpola con `(finish - current) / dt`
    sobre `double`, con `dt` los cuadros que quedan más uno, que es un
    "acercarse a la parte que falta" cuyo resultado exacto es lineal:
    `desde + (hasta - desde) * paso / pasos`. La consola no tiene `double`, así
    que la cuenta va con enteros; el signo se saca antes de dividir porque el
    divisor del hardware no lo tiene, y `//` de Python redondearía para el otro
    lado con negativos. Ver `imagen_tick` en main.s.
    """
    if paso >= pasos:
        return tuple(hasta)
    salida = []
    for a, b in zip(desde, hasta):
        if b >= a:
            salida.append(a + (b - a) * paso // pasos)
        else:
            salida.append(a - (a - b) * paso // pasos)
    return tuple(salida)


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
        import imagen as imagen_mod
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
    import lcf
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
                               "imagen": anim.get("animation_name", ""),
                               "grande": bool(anim.get("large")),
                               "alcance": anim.get("scope", 0),
                               "posicion": anim.get("position", 1)}
CHANGE_HP = 10460
CHANGE_CONDITION = 10480
FULL_HEAL = 10490
CHANGE_MENU_ACCESS = 11960
ACCESO_GUARDAR, ACCESO_MENU = 0, 1
# Las operaciones de ControlVars que compilan: poner, sumar, restar. Multiplicar,
# dividir y el resto no las usa ninguna página del juego.
VAR_PONER, VAR_SUMAR, VAR_RESTAR = 0, 1, 2
# Y de dónde sale el operando, con el número de RM2k: una constante, otra
# variable, un número al azar entre a y b, u "otro", que acá son el oro y los
# segundos que le quedan al cronómetro. El azar pide que b - a sea menor que
# 256: la ROM divide con el divisor de ocho bits del hardware.
VAR_CONSTANTE, VAR_VARIABLE, VAR_AZAR, VAR_OTRO = 0, 1, 3, 7
OTRO_ORO, OTRO_TIMER = 0, 1
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
VARIABLES_PRUEBA_AL_TIMER = 9   # la "operación" de --vars-de-prueba que pone el
                                # cronómetro desde la variable; ver pagina_de_prueba


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
    son las de la página de prueba, que no salen de ningún mapa.
    """
    import lcf
    ids = set(extra)
    for map_id in (mapas_del_juego(game_dir) if map_ids is None else map_ids):
        game_map = lcf.Map(os.path.join(game_dir, "Map%04d.lmu" % map_id))
        for evento in game_map.events:
            for page in evento.pages:
                if "variable" in page.condition.active:
                    ids.add(page.condition.ids["variable"])
                for cmd in page.commands:
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
                    elif cmd.code == TIMER_OPERATION and len(p) >= 3 \
                            and p[0] == TIMER_PONER \
                            and p[1] != TIMER_SEGUNDOS_FIJOS:
                        ids.add(p[2])
    return {variable: ranura for ranura, variable in enumerate(sorted(ids))}


def indexar_variables(game_dir, extra=()):
    """Deja en `VARIABLE_SLOT` el índice del juego entero. Lo llaman el
    conversor y la referencia antes de compilar nada; tarda un tercio de
    segundo en leer los 328 mapas."""
    VARIABLE_SLOT.clear()
    VARIABLE_SLOT.update(variables_de(game_dir, None, extra))
    return dict(VARIABLE_SLOT)


def con_signo_byte(valor):
    return valor - 256 if valor & 0x80 else valor


def cumple_comparacion(valor, comparacion, contra):
    """`CheckOperator` de RM2k: ==, >=, <=, >, <, != en ese orden. Lo usan la
    rama por variable y la condición de página; en la ROM es `comparar_var`
    para las dos."""
    return (valor == contra, valor >= contra, valor <= contra, valor > contra,
            valor < contra, valor != contra)[comparacion]


def ranura_de_variable(numero):
    if numero not in VARIABLE_SLOT:
        raise NoSePuede("la variable %d no tiene ranura en esta ROM" % numero)
    return VARIABLE_SLOT[numero]


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

    Tres de las doce: switch, oro y "el actor está en el grupo". Las otras piden
    estado que este port no lleva —variables, inventario, estadísticas de
    actor— y una rama sobre cualquiera de ésas daría siempre la misma respuesta,
    así que ni siquiera se podría probar.

    La polaridad se copia tal cual de RM2k y quiere decir cosas distintas según
    la clase: en un switch, 0 es "tiene que estar prendido"; en el oro, 0 es
    ">=" y 1 es "<=". Es el `com.parameters[2]` de allá, sin traducir.
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
    elif p[0] == COND_ACTOR:
        if p[2] != COND_ACTOR_EN_GRUPO:
            raise NoSePuede("del héroe sólo sabemos si está en el grupo")
        numero = p[1]
        if not 0 <= numero <= 0xFFFF:
            raise NoSePuede("actor %d fuera de rango" % numero)
        # "Está en el grupo" no tiene polaridad: la rama de abajo es el `else`.
        return bytes([OP_SI, COND_ACTOR, numero & 0xFF, numero >> 8, 0, 0, 0])
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
        return bytes([OP_SI_VAR, ranura, clase, p[4], valor & 0xFF,
                      (valor >> 8) & 0xFF, 0, 0])
    else:
        raise NoSePuede("rama sobre una condición que no sabemos hacer")
    return bytes([OP_SI, p[0], numero & 0xFF, numero >> 8,
                  1 if p[2] else 0, 0, 0])


def con_destino(pieza, destino):
    """La misma pieza con el destino puesto en sus dos últimos bytes."""
    return pieza[:-2] + bytes([destino & 0xFF, destino >> 8])


def compilar_pagina(page, indice_de_mapa, mensajes=None, eventos_mapa=None,
                    temas=None, graficos=None, imagenes=None):
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
        largo = 0
        pila = []            # piezas con el destino todavía en blanco
        # Las opciones de cada `ShowChoice` se juntan mirando hacia adelante,
        # que es lo que hace `GetChoices`, así que se resuelven antes del lazo:
        # acá adentro los comandos vienen de a uno y ya agrupados.
        comandos = list(page.commands)
        opciones_de = {id(c): opciones_de_eleccion(comandos, i)
                       for i, c in enumerate(comandos) if c.code == SHOW_CHOICE}
        eleg = []            # las elecciones abiertas
        for cmd, extra in agrupar(comandos):
            if cmd.code == SHOW_CHOICE:
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
                pieza = b"" if not actual["vistas"] else bytes([OP_IR, 0, 0])
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
                tabla = bytes([OP_ELEGIR, actual["n"], actual["cancelar"]])
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
                pieza = bytes([OP_IR, 0, 0])
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
            else:
                pieza = _compilar(cmd, indice_de_mapa, mensajes, extra,
                                  eventos_mapa, temas, graficos, imagenes)
            piezas.append(pieza)
            largo += len(pieza)
        if pila:
            raise NoSePuede("una rama sin cerrar")
        if eleg:
            raise NoSePuede("una elección sin cerrar")
        codigo = b"".join(piezas) + bytes([OP_FIN])
        return codigo
    except NoSePuede:
        if mensajes is not None:
            mensajes.volver(marca)
        return None


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
        return bytes([OP_IMAGEN_BORRAR])
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
        return bytes([OP_IMAGEN]) + bytes(tono)
    # MovePicture: el mismo cartel, en el mismo lugar, con otro tono. La
    # duración viene en **décimas** —`data.time_left = duration * DEFAULT_FPS /
    # 10`—, que es lo que había que ir a leer: los 35 del primero son tres
    # segundos y medio, no medio segundo.
    if not imagenes.suyo(p[0], p[2], p[3]):
        return None
    cuadros = p[14] * CUADROS_POR_DECIMA
    if not 0 <= cuadros <= IMAGEN_CUADROS_MAX:
        return None
    salida = bytes([OP_IMAGEN_MOVER]) + bytes(tono) + bytes([cuadros])
    if len(p) > 15 and p[15] and cuadros:
        # `options.wait`: la página espera lo que dura, como el `FlashScreen`.
        salida += bytes([OP_ESPERAR, cuadros & 0xFF, cuadros >> 8])
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
        k = temas.sonido(cmd.string, p[0], p[1], p[2])
        return bytes([OP_SONIDO, k & 0xFF, k >> 8])

    if cmd.code == WEATHER_EFFECTS:
        if len(p) < 2:
            raise NoSePuede("WeatherEffects sin operandos")
        return bytes([OP_CLIMA, p[0] & 0xFF, min(max(p[1], 0), 2)])

    if cmd.code == OPEN_SHOP:
        if len(p) < 4:
            raise NoSePuede("OpenShop sin operandos")
        if p[2]:
            raise NoSePuede("OpenShop con las ramas de compró y no compró")
        vende = [i for i in p[4:] if 0 < i < ITEMS_N]
        if len(vende) > 255 or not 0 <= p[0] <= 2 or not 0 <= p[1] <= 2:
            raise NoSePuede("OpenShop que no entra en OP_TIENDA")
        return bytes([OP_TIENDA, p[0], p[1], len(vende)]) + b"".join(
            bytes([i & 0xFF, i >> 8]) for i in vende)

    if cmd.code == FULL_HEAL:
        return b""
    if cmd.code == CHANGE_HP:
        if len(p) < 3 or p[2] != 0:
            raise NoSePuede("ChangeHP que resta: los HP dejarían de estar "
                            "siempre llenos")
        return b""
    if cmd.code == CHANGE_CONDITION:
        if len(p) < 3 or p[2] != 1:
            raise NoSePuede("ChangeCondition que pone un estado")
        return b""

    if cmd.code in (CHANGE_SAVE_ACCESS, CHANGE_MENU_ACCESS):
        if not p:
            raise NoSePuede("%s sin operandos" % cmd.code)
        cual = (ACCESO_GUARDAR if cmd.code == CHANGE_SAVE_ACCESS
                else ACCESO_MENU)
        return bytes([OP_ACCESO, cual, 1 if p[0] else 0])

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
        return bytes([OP_ORO, 1 if p[0] else 0,
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
        return bytes([OP_FUNDIR_BGM, paso & 0xFF, paso >> 8])

    if cmd.code == OPEN_SAVE_MENU:
        return bytes([OP_GUARDAR])

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
        return bytes([OP_TELEPORT, destino,
                      p[1] & 0xFF, p[1] >> 8, p[2] & 0xFF, p[2] >> 8])

    if cmd.code == CHANGE_PARTY_MEMBERS:
        if len(p) < 3 or p[1] != GRUPO_ID_FIJO:
            raise NoSePuede()   # el id sale de una variable, y no las leemos
        if p[0] not in (GRUPO_AGREGAR, GRUPO_SACAR) or not 0 <= p[2] <= 255:
            raise NoSePuede()
        return bytes([OP_GRUPO, p[0], p[2]])

    if cmd.code == PROCEED_WITH_MOVEMENT:
        return bytes([OP_RUTAS])

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
            quien = (eventos_mapa.mio if p[0] == RUTA_ESTE_EVENTO else p[0])
            if eventos_mapa.comparte_grafico(quien):
                # En la consola el destello se hace sobre la paleta del
                # personaje, y dos eventos con el mismo gráfico comparten una
                # sola: destellarían juntos. Antes que emitir eso y que la
                # referencia lo copie —que es cómo un error se vuelve
                # invisible—, la página no compila. Hoy no cuesta ninguna: son
                # tres destellos y sus páginas se cortan igual por otra cosa.
                raise NoSePuede()
        if any(not 0 <= v <= 31 for v in p[1:5]):
            raise NoSePuede()
        cuadros = p[5] * CUADROS_POR_DECIMA
        if not 0 < cuadros <= 255:
            raise NoSePuede()
        out = bytes([OP_FLASH, blanco, p[1], p[2], p[3], p[4], cuadros])
        if p[6]:
            # Esperar es exactamente el comando Wait: `SetupWait(tenths)`, o sea
            # las mismas décimas por CUADROS_POR_DECIMA.
            out += bytes([OP_ESPERAR, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == CONTROL_VARS:
        # `[cómo se elige, desde, hasta, operación, clase del operando, a, b]`.
        # De a una variable y nada más: los rangos y el indirecto no los usa
        # ninguna página del juego. Ver OP_VAR.
        if len(p) < 7:
            raise NoSePuede("un ControlVars sin operandos")
        if p[0] != 0:
            raise NoSePuede("ControlVars sobre un rango o indirecto")
        ranura = ranura_de_variable(p[1])
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
        for orden, extras in ordenes:

            if orden == RUTA_SONIDO or orden in RUTA_TRANSPARENCIA:
                # Se acepta y se tira: no se ve y no
                # cuesta cuadros —RM2k no le toca el contador de parada—. Así
                # el bytecode sigue siendo un byte por orden. La
                # transparencia, ver RUTA_TRANSPARENCIA.
                continue
            # Girar, esperar y moverse. Los `move_*` entraron el 2026-09-03,
            # cuando los dos lados empezaron a coincidir *durante* la caminata y
            # no sólo al final: lo prueba `snes-ruta`, que compara cuatro
            # cuadros de una ruta de doce celdas con esperas en el medio. Todo
            # lo demás de `rpg::MoveCommand::Code` —moverse hacia el héroe o
            # desde él, girar en el lugar, los switches— sigue afuera.
            if orden not in RUTA_ORDENES:
                raise NoSePuede()
            if orden == RUTA_ENCARAR_HEROE and blanco == 0:
                raise NoSePuede()   # el héroe encarándose a sí mismo
            if orden in RUTA_HEROE_AFUERA and blanco == 0:
                # Fijar y soltar la mirada y subir y bajar la velocidad, sobre
                # **el héroe**: se aceptan y se tiran, como el sonido y la
                # transparencia. La ROM las ignora —su paso es fijo,
                # `WALK_SPEED`, ocho cuadros por celda— y tirarlas al compilar
                # es lo que hace que la referencia tampoco las camine. Sobre
                # eventos sí se hacen.
                #
                # Rechazar la página entera, que fue lo primero que se probó,
                # arreglaba la paridad y costaba demasiado: **la escena de
                # Talan tiene una ruta del héroe que empieza con la 28**, así
                # que la escena que motivó los seis puntos del 2026-09-06 se
                # quedaba sin compilar y el jugador no podía salir del pasillo
                # del Emitter Room. Son 4 páginas automáticas más esa.
                #
                # Lo que se pierde es el cambio de ritmo: donde RM2k acelera al
                # héroe, acá camina a la suya. Es visible y está aceptado; lo
                # que lo arregla de verdad es que su paso deje de ser fijo, y
                # eso está en ESTADO.md.
                continue
            if orden in RUTA_DIAGONALES and blanco == 0:
                # Y el héroe en diagonal: la ROM no lo sabe hacer y ninguna
                # de las 26 rutas del juego con diagonales es del héroe. Sin
                # este corte la referencia caminaría la diagonal y la ROM se
                # iría para la izquierda —el `mover` de `paso_de_ruta` cae en
                # `try_left` por descarte—, o peor, los dos lados harían lo
                # mismo mal el día que alguien "arregle" uno solo.
                raise NoSePuede()
            if orden == RUTA_CAMBIAR_GRAFICO:
                # La única orden con operando: detrás del 34 va el índice del
                # gráfico en `Graficos`, que el conversor resuelve al banco de
                # sprites del mapa. Ver `recorrer_ruta`, que es por dónde tiene
                # que pasar todo el que recorra una ruta ya compilada.
                #
                # Sobre el héroe no se compila. Su gráfico sale de la tabla de
                # actores —`place_hero` lo busca por el id del líder— y una
                # ruta que se lo cambie tendría que pisar ese mecanismo. Son
                # 89 rutas de páginas automáticas y diez páginas más, medido;
                # queda anotado en "Lo que falta".
                if blanco == 0 or graficos is None or len(extras) < 2:
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
        return bytes([OP_RUTA, blanco, p[1], len(ruta)]) + bytes(ruta)

    if cmd.code == CHANGE_EVENT_LOCATION:
        if len(p) < 4 or p[1] != LUGAR_CONSTANTE:
            raise NoSePuede()   # la celda sale de variables, y no las leemos
        if p[0] == RUTA_HEROE or eventos_mapa is None:
            # Al héroe no lo mueve nadie así en este juego —para eso está
            # Teleport— y sin el mapa no hay cómo traducir el id.
            raise NoSePuede()
        blanco = eventos_mapa.blanco(p[0])
        if blanco is None:
            raise NoSePuede()   # un vehículo, o un evento que no existe
        if not (0 <= p[2] <= 0xFFFF and 0 <= p[3] <= 0xFFFF):
            raise NoSePuede()
        return bytes([OP_LUGAR, blanco, p[2] & 0xFF, p[2] >> 8,
                      p[3] & 0xFF, p[3] >> 8])

    if cmd.code == SHAKE_SCREEN:
        # `CommandShakeScreen`, en su forma de RM2k: fuerza, velocidad,
        # décimas y si espera. Las 29 del juego son de esa forma. Con cero
        # décimas es `ShakeEnd` y no espera nunca.
        if len(p) < 4 or not 0 <= p[0] <= 9 or not 0 <= p[1] <= 9:
            raise NoSePuede()
        cuadros = p[2] * CUADROS_POR_DECIMA
        if cuadros > 0xFFFF:
            raise NoSePuede()
        out = bytes([OP_SACUDIR, p[0], p[1], cuadros & 0xFF, cuadros >> 8])
        if cuadros and p[3]:
            out += bytes([OP_ESPERAR, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == SHOW_BATTLE_ANIMATION:
        # (animación, objetivo, esperar, global): ver OP_ANIMACION.
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
        out = (bytes([OP_ANIMACION, numero, dibujo_blanco(anim, blanco),
                      len(entradas)])
               + b"".join(entradas))
        cuadros = 2 * len(anim["cuadros"])
        if p[2] and cuadros:
            out += bytes([OP_ESPERAR, cuadros & 0xFF, cuadros >> 8])
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
        out = bytes([OP_DESTELLO, p[0], p[1], p[2], p[3], cuadros])
        if cuadros and p[5]:
            out += bytes([OP_ESPERAR, cuadros & 0xFF, cuadros >> 8])
        return out

    if cmd.code == TRADE_EVENT_LOCATIONS:
        # `CommandTradeEventLocations`: cada uno va con `MoveTo` a la celda
        # del otro. Sobre el héroe no lo usa ninguna página del juego.
        if len(p) < 2 or eventos_mapa is None:
            raise NoSePuede()
        blancos = [eventos_mapa.blanco(q) for q in p[:2]]
        if any(b is None or b == 0 for b in blancos):
            raise NoSePuede()   # el héroe, un vehículo o un evento que no existe
        return bytes([OP_TRUEQUE] + blancos)

    if cmd.code == WAIT:
        if len(p) < 1:
            raise NoSePuede()
        cuadros = p[0] * CUADROS_POR_DECIMA
        if cuadros > 0xFFFF:
            raise NoSePuede()
        return bytes([OP_ESPERAR, cuadros & 0xFF, cuadros >> 8])

    if cmd.code == TINT_SCREEN:
        if len(p) < 4:
            raise NoSePuede()
        if any(not 0 <= v <= 200 for v in p[:4]):
            raise NoSePuede()
        # La duración se descarta: el tinte se aplica de una. La pantalla que
        # se compara está siempre asentada, así que el valor final es el que
        # importa; lo que se pierde es el degradé de un segundo.
        return bytes([OP_TINTE, p[0], p[1], p[2], p[3]])

    if cmd.code == SHOW_MESSAGE:
        if mensajes is None:
            raise NoSePuede()   # esta ROM no lleva ventana: no hay dónde
        lineas = [cmd.string] + list(extra)
        if any(ESCAPE in t for t in lineas):
            raise NoSePuede()   # ver ESCAPE, arriba
        donde = mensajes.agregar(lineas)
        return bytes([OP_MENSAJE, donde & 0xFF, donde >> 8])

    raise NoSePuede()


# --- ejecutar lo compilado --------------------------------------------------
#
# La ROM y la referencia corren el mismo bytecode. Tener el intérprete una sola
# vez del lado de Python no evita que haya dos implementaciones —la otra está en
# main.s— pero sí evita que haya dos *lenguajes*: lo que se ejecuta es el mismo
# programa, y las reglas de selección de página están escritas una vez acá y una
# vez allá, no una vez por llamador.


class Ruta:
    """Una ruta forzada corriendo sobre alguien: el héroe o un evento.

    La misma clase para los dos, y no por ahorrar líneas. Cómo una ruta consume
    el tiempo —girar es gratis y se sigue en el mismo cuadro, esperar cuesta un
    cuadro, moverse arranca un paso de una celda que dura CUADROS_POR_CELDA, y
    un movimiento bloqueado se saltea— es una decisión de modelo que la ROM y la
    referencia comparten. Escrita dos veces es como se separan.

    La posición vive afuera, en quien la use: la del héroe está en pixeles y
    manda la cámara, la de un evento está en celdas y la lleva `Estado`.
    """

    def __init__(self):
        self.ordenes = []
        self.paso_dir = None
        self.paso_cuadros = 0
        # Los cuadros que faltan de un `wait`. Ver CUADROS_DE_ESPERA_DE_RUTA.
        self.espera = 0
        # El salto en curso: lo que le queda de los 256 y de dónde salió, en
        # celdas. La celda de destino ya es la del personaje —se mueve al
        # empezar, igual que un paso— y lo que se interpola es el dibujo.
        self.salto_resta = 0
        self.salto_dx = 0
        self.salto_dy = 0
        # Y el salto que arrancó **en este cuadro**, para que quien lleva la
        # posición mueva la celda. Se limpia en cada vuelta.
        self.arranco_salto = None
        # A qué gráfico la cambió una orden 34, o None si ninguna. Es el
        # índice en `Graficos` del mapa, y sobrevive a la ruta: RM2k no lo
        # devuelve al terminar —`SetSpriteGraphic` escribe el dato del
        # personaje, no un estado de la ruta—, así que el evento se queda con
        # el gráfico nuevo hasta que otra cosa se lo cambie.
        self.grafico = None
        # Atravesar paredes, y la animación de caminata parada. Las dos son
        # estado de la ruta y sobreviven a las órdenes que las prendieron.
        self.atraviesa = False
        self.anim_parada = False
        # Cuántos cuadros seguidos lleva moviéndose, para la pose de caminata.
        # `animate_hero` lo reinicia en cuanto se queda quieto. Y el ciclo de
        # caminata del héroe, que va aparte del de `_animar`: ver
        # `_contar_movimiento`.
        self.cuadros_moviendose = 0
        self.anim_heroe_cuenta = 0
        self.anim_heroe_cuadro = 1
        # Hacia dónde mira si una ruta se lo dijo. None es "lo decide la
        # caminata", que es lo de siempre.
        self.mirando = None
        # Y hacia dónde mira su página, que es lo que RM2k tiene ahí mientras
        # `mirando` sea None: el dibujo ya lo usaba de reemplazo y un paso en
        # diagonal lo necesita **como dato**, porque de la pose de antes sale
        # la de después. Lo pone `Estado.ruta_de_evento` desde la fila del NPC,
        # igual que la velocidad; 2 —abajo— es para un evento sin gráfico, al
        # que no se le ve la pose.
        self.mirando_pagina = 2
        # La frecuencia de la ruta puesta: cuánto se queda quieto entre orden y
        # orden. Ver `espera_tras_paso`.
        self.frecuencia = RUTA_FRECUENCIA
        # La velocidad, de 1 a 6: ver PASO_POR_VELOCIDAD. Lo que falta del
        # paso en curso va en `paso_resta`, de 256 por celda, y `paso_cuadros`
        # es lo mismo en cuadros a la velocidad de ahora, que es lo que miran
        # quienes deciden si el paso terminó.
        self.velocidad = 4
        self.paso_resta = 0
        # Hacia dónde mira no cambia al caminar: `lock_facing`, y los tipos de
        # animación de dirección fija de la página. Los `face_*` sí lo cambian,
        # que es el `SetFacing` directo de `UpdateMoveRoute`.
        self.dir_fija = False
        # La ruta propia de la página, si la tiene: `ordenes_pagina` es de
        # dónde se recarga si se repite, y `de_pagina` dice que es la que está
        # corriendo —una forzada la pisa y al terminar vuelve ésta—. `pagina`
        # es con cuál se cargó, para el refresco al cambiar un switch.
        self.ordenes_pagina = ()
        self.repite = False
        self.saltable = True
        self.de_pagina = False
        self.pagina = None
        self.recargada = False
        # La animación como la lleva RM2k: el frame del ciclo, 0 a 3 con el 3
        # dibujando la columna 1, y cuántos cuadros lleva en él. Con la
        # animación continua el ciclo sigue aunque esté quieto.
        self.anim_continua = False
        self.anim_cuadro = 1
        self.anim_cuenta = 0

    def reemplazar(self, ordenes, frecuencia):
        """Una ruta forzada nueva sobre quien ya tenía una, o no.

        Es `ForceMoveRoute`, y lo que importa es lo que **no** toca: el paso o
        el salto en curso se terminan, hacia dónde mira queda, y atravesar
        paredes y la animación parada siguen como estaban. Lo que sí: las
        órdenes son las nuevas, la espera se corta —`SetStopCount(0xFFFF)`: la
        primera orden corre ya— y la frecuencia es la de esta ruta. La ROM hace
        lo mismo al reusar la ranura; antes reseteaba la ranura entera, y el
        evento volvía a mirar adonde decía su página hasta que la ruta nueva
        lo girara.
        """
        self.ordenes = list(ordenes)
        self.espera = 0
        self.frecuencia = frecuencia
        self.de_pagina = False
        self.saltable = True

    def cortar_paso(self):
        """Deja al personaje sobre su celda: sin paso ni salto en curso.

        Es lo que hace `MoveTo` con `SetRemainingStep(0)`. Las órdenes, la
        espera y hacia dónde mira quedan como estaban.
        """
        self.paso_dir = None
        self.paso_cuadros = 0
        self.paso_resta = 0
        self.salto_resta = 0
        self.arranco_salto = None

    @property
    def pendiente(self):
        """Si todavía le queda ruta por caminar.

        Es el `IsMoveRouteOverwritten() && !IsMoveRouteFinished()` de
        `Game_Map::IsAnyMovePending`, que es a lo que espera
        `ProceedWithMovement`.
        """
        if self.de_pagina:
            return False            # la ruta propia de la página no se espera
        return (bool(self.ordenes) or self.paso_cuadros > 0
                or self.espera > 0 or self.salto_resta > 0)

    def cargar_pagina(self, propia, pagina):
        """La ruta propia de la página, desde el principio.

        Es `Game_Event::SetupFromPage` con `MoveType_custom`: las órdenes, la
        frecuencia y la velocidad de la página, y `SetMaxStopCountForTurn`
        antes de la primera orden. El paso en curso no se corta.
        """
        self.ordenes_pagina = tuple(propia["ordenes"])
        self.ordenes = list(self.ordenes_pagina)
        self.frecuencia = propia["frecuencia"]
        self.velocidad = propia["velocidad"]
        self.repite = propia["repite"]
        self.saltable = propia["saltable"]
        self.dir_fija = propia["dir_fija"]
        self.anim_continua = propia["anim_continua"]
        self.de_pagina = True
        self.pagina = pagina
        self.espera = espera_tras_giro(self.frecuencia)

    def sin_pagina(self):
        """La página nueva no tiene ruta propia: se le saca."""
        self.ordenes_pagina = ()
        self.pagina = None
        if self.de_pagina:
            self.ordenes = []
            self.espera = 0
            self.de_pagina = False

    def columna(self):
        """La columna del CharSet que se dibuja: el frame del ciclo, con el 3
        dibujando la misma que el 1."""
        return 1 if self.anim_cuadro == 3 else self.anim_cuadro

    def _contar_movimiento(self, moviendo):
        """Los cuadros que el **héroe** lleva moviéndose, y su ciclo.

        Es lo que `animate_hero` hace en la ROM, que no es `_animar` entero:
        parado vuelve al frame del medio en el acto y la cuenta a cero;
        moviéndose la cuenta sube y el frame cambia al llegar al tope de la
        velocidad **de ese cuadro**, `ANIM_PARADO`, que una orden 28 o 29 de
        la misma ruta puede haber cambiado a mitad del frame. Antes esto era
        `cuadros_moviendose // ANIM_FRAMES` en snes_expect.py, que sólo sirve
        con la velocidad quieta.
        """
        if not moviendo:
            self.cuadros_moviendose = 0
            self.anim_heroe_cuenta = 0
            self.anim_heroe_cuadro = 1
            return
        self.cuadros_moviendose += 1
        self.anim_heroe_cuenta += 1
        if self.anim_heroe_cuenta >= ANIM_PARADO[self.velocidad - 1]:
            self.anim_heroe_cuenta = 0
            self.anim_heroe_cuadro = (self.anim_heroe_cuadro + 1) % 4

    def columna_del_heroe(self):
        """La columna del CharSet del héroe caminando por esta ruta."""
        return 1 if self.anim_heroe_cuadro == 3 else self.anim_heroe_cuadro

    def _animar(self, moviendo, saltando=False):
        """`Game_Character::UpdateAnimation`, sin el giro en el lugar.

        Con la animación parada o saltando el frame es el del medio. Si no,
        la cuenta sube mientras se camina, siempre con la animación continua,
        y quieto sólo hasta llegar al frame del medio; el frame cambia cada
        `ANIM_PARADO` cuadros caminando y cada `ANIM_CONTINUA` quieto.
        """
        if self.anim_parada or saltando:
            self.anim_cuadro = 1
            self.anim_cuenta = 0
            return
        parado = ANIM_PARADO[self.velocidad - 1]
        continua = ANIM_CONTINUA[self.velocidad - 1]
        if (self.anim_continua or moviendo or self.anim_cuadro in (0, 2)
                or self.anim_cuenta < parado - 1):
            self.anim_cuenta += 1
        if self.anim_cuenta >= continua or (moviendo
                                            and self.anim_cuenta >= parado):
            self.anim_cuadro = (self.anim_cuadro + 1) % 4
            self.anim_cuenta = 0

    def cuadro(self, puede, saltar=None, hacia_heroe=None, congelada=False,
               existe=None):
        """Un cuadro de la ruta.

        `puede(direccion, desde)` dice si se puede dar el paso, con `desde`
        el corrimiento en celdas de dónde arranca —(0, 0) salvo la segunda
        pata de una diagonal, que sale del codo: ver `puede_en_diagonal`—;
        `saltar(dx, dy)` si se puede caer en esa celda —es `MakeWay` con el personaje saltando, que
        saltea la cara que se deja y pide que la de destino sea pasable por los
        cuatro lados— y `hacia_heroe()` hacia dónde hay que mirar para encarar
        al héroe; sin él, `face_hero` no hace nada, que es lo que hace la ROM
        con una orden que no espera.

        `congelada` es que el intérprete tiene una página corriendo: la ruta
        propia de la página no lee órdenes nuevas mientras tanto —es el
        `Game_Map::GetInterpreter().IsRunning()` de `UpdateNextMovementAction`—
        pero el paso en curso se termina y las esperas siguen contando. Una
        forzada no se congela.

        Devuelve la dirección del paso que se está dando, o None. Un salto que
        arranca en este cuadro queda en `arranco_salto` para que quien lleve la
        posición mueva la celda, igual que hace con un paso.
        """
        self.arranco_salto = None
        self.recargada = False
        if self.paso_resta:
            paso = PASO_POR_VELOCIDAD[self.velocidad - 1]
            self.paso_resta -= min(paso, self.paso_resta)
            self.paso_cuadros = -(-self.paso_resta // paso)
            # Con la animación parada el ciclo de caminata no avanza: RM2k
            # llama a `ResetAnimation` en cada cuadro mientras `IsAnimPaused()`,
            # que deja la pose del medio y el contador en cero. Camina igual;
            # lo único que no pasa es el ciclo.
            self._contar_movimiento(not self.anim_parada)
            direccion = self.paso_dir
            if not self.paso_resta:
                self.paso_dir = None
                # El paso terminó: con órdenes por delante, la frecuencia dice
                # cuántos cuadros quieto antes de leer la siguiente. Sin
                # órdenes no se espera nada: la ruta se cancela en el último
                # paso —ver `paso_de_ruta` en snes_expect.py— y
                # `ProceedWithMovement` no la tiene que esperar.
                if self.ordenes or (self.de_pagina and self.repite):
                    self.espera = espera_tras_paso(self.frecuencia)
            self._animar(True)
            return direccion
        if self.salto_resta:
            # Un salto en curso. No hay pose de caminata: RM2k llama a
            # `ResetAnimation` mientras se salta, o sea la del medio.
            self.salto_resta = max(
                0, self.salto_resta - SALTO_VELOCIDADES[self.velocidad - 1])
            self._contar_movimiento(False)
            # En el cuadro en que el salto termina ya no se está saltando:
            # `UpdateAnimation` corre después de `UpdateMovement`, que bajó
            # la bandera, y la cuenta sube. La ROM lo hace igual sin
            # proponérselo; acá se contaba uno de menos.
            self._animar(False, saltando=self.salto_resta > 0)
            return None
        if self.espera:
            self.espera -= 1
            self._contar_movimiento(False)
            self._animar(False)
            return None
        if congelada and self.de_pagina:
            self._contar_movimiento(False)
            self._animar(False)
            return None
        while True:
            if not self.ordenes:
                if self.de_pagina and self.repite and self.ordenes_pagina \
                        and not self.recargada:
                    # `repeat`: vuelve al principio en el mismo cuadro, y una
                    # sola vez por cuadro, que es el `current_index ==
                    # start_index -> return` de `UpdateMoveRoute`.
                    self.ordenes = list(self.ordenes_pagina)
                    self.recargada = True
                    continue
                if not self.de_pagina and self.ordenes_pagina:
                    # La forzada terminó: vuelve la de la página. RM2k la
                    # retoma donde la había dejado; acá arranca de nuevo.
                    self.cargar_pagina(self._propia(), self.pagina)
                break
            orden = self.ordenes.pop(0)
            if orden in RUTA_MIRAR or orden == RUTA_ENCARAR_HEROE:
                if orden in RUTA_MIRAR:
                    self.mirando = RUTA_MIRAR[orden]
                elif hacia_heroe is not None:
                    self.mirando = hacia_heroe()
                # Girar es gratis con la frecuencia 8 y cuesta
                # `espera_tras_giro` cuadros con las otras: éste y los que
                # siguen, como el `wait`.
                giro = espera_tras_giro(self.frecuencia)
                if not giro:
                    continue
                self.espera = giro - 1
                break
            if orden == RUTA_CAMBIAR_GRAFICO:
                # La única con operando, y no cuesta un cuadro: en
                # `UpdateMoveRoute` cae en la rama que no toca el contador de
                # parada, así que la orden que sigue corre en este mismo
                # cuadro.
                self.grafico = self.ordenes.pop(0) if self.ordenes else None
                continue
            if orden == RUTA_ATRAVESAR_ON:
                self.atraviesa = True
                continue
            if orden == RUTA_ATRAVESAR_OFF:
                self.atraviesa = False
                continue
            if orden == RUTA_ANIM_PARAR:
                self.anim_parada = True
                continue
            if orden == RUTA_ANIM_SEGUIR:
                self.anim_parada = False
                continue
            if orden == RUTA_FIJAR_DIR:
                self.dir_fija = True
                continue
            if orden == RUTA_SOLTAR_DIR:
                self.dir_fija = False
                continue
            if orden == RUTA_VEL_MAS:
                self.velocidad = min(6, self.velocidad + 1)
                continue
            if orden == RUTA_VEL_MENOS:
                self.velocidad = max(1, self.velocidad - 1)
                continue
            if orden == RUTA_FREC_MAS:
                self.frecuencia = min(RUTA_FRECUENCIA, self.frecuencia + 1)
                continue
            if orden == RUTA_FREC_MENOS:
                # Topa en 1 como RM2k y no en RUTA_FRECUENCIA_MIN, aunque con
                # la 1 la ROM no sepa esperar: lo que garantiza que no se
                # llegue es `frecuencia_minima`, que rechaza la ruta al
                # compilarla. Topando distinto acá, los dos lados se
                # equivocarían igual el día que el guard fallara.
                self.frecuencia = max(1, self.frecuencia - 1)
                continue
            if orden == RUTA_SALTO_FIN:
                continue            # el par ya lo consumió `RUTA_SALTO_INICIO`
            if orden == RUTA_SALTO_INICIO:
                armado = self._armar_salto(saltar)
                if armado is None or armado:
                    # El salto arrancó y se lleva el cuadro; o no se pudo y la
                    # ruta no es salteable, y se reintenta el cuadro que viene.
                    break
                continue            # no se pudo, o no había `end_jump`
            if orden == RUTA_ESPERAR:
                # Veinte cuadros, no uno: éste y los diecinueve que siguen. Y
                # con una frecuencia baja, los del giro encima:
                # `GetMaxStopCountForWait` es 20 más `ForTurn`.
                self.espera = (CUADROS_DE_ESPERA_DE_RUTA - 1
                               + espera_tras_giro(self.frecuencia))
                break
            direccion = RUTA_MOVER[orden]
            diagonal = orden in RUTA_DIAGONALES
            if not self.dir_fija:
                # En diagonal no se gira hacia el rincón: se conserva la pose
                # o se da vuelta. Ver `encarar_en_diagonal`.
                self.mirando = (
                    encarar_en_diagonal(
                        self.mirando if self.mirando is not None
                        else self.mirando_pagina, orden)
                    if diagonal else direccion)
            libre = (puede_en_diagonal(orden, puede) if diagonal
                     else puede(direccion))
            if self.atraviesa:
                # **Atravesar paredes no es salirse del mapa.** En
                # `Game_Map::CheckOrMakeWayEx` el `IsValid` va **antes** que el
                # `if (self.GetThrough()) return true;`, y la ROM lo modela así
                # desde siempre —ver `puede_celda`—. Acá no, y se veía: el
                # `Car3` de Lashe City, que camina a la derecha atravesando
                # paredes, llega a la última columna del mapa y la consola lo
                # deja clavado ahí unos cuadros hasta que otro evento lo
                # reubica; la referencia lo sacaba del mapa.
                libre = existe is None or existe(direccion)
            if not libre:
                if self.saltable:
                    continue        # bloqueado: se saltea
                # Sin `skippable` la orden se reintenta el cuadro que viene,
                # y así hasta que el paso salga: es lo que deja plantarse
                # delante de un droide del mapa 2 y que se quede empujando.
                self.ordenes.insert(0, orden)
                break
            paso = PASO_POR_VELOCIDAD[self.velocidad - 1]
            self.paso_dir = direccion
            self.paso_resta = SALTO_PASO - paso
            self.paso_cuadros = self.paso_resta // paso
            self._contar_movimiento(not self.anim_parada)
            self._animar(True)
            return direccion
        # Ningún paso en este cuadro: el contador vuelve a cero, que es lo que
        # hace `animate_hero` cuando `moving` está apagado —la pose parada, y el
        # ciclo empezando de nuevo en el paso siguiente—. La espera cae acá por
        # `break` y no por `return`: en la ROM una espera de ruta deja al héroe
        # quieto, igual que el final de la ruta, y antes acá seguía contando.
        self._contar_movimiento(False)
        self._animar(False)
        return None

    def _propia(self):
        """Lo que `cargar_pagina` necesita, sacado de lo que ya tiene."""
        return {"ordenes": self.ordenes_pagina, "frecuencia": self.frecuencia,
                "velocidad": self.velocidad, "repite": self.repite,
                "saltable": self.saltable, "dir_fija": self.dir_fija,
                "anim_continua": self.anim_continua}

    def _armar_salto(self, saltar):
        """Consume las órdenes hasta `end_jump` y arranca el salto.

        Es `BeginMoveRouteJump`: lo que hay en el medio no se camina, se **suma**
        —cada `move_*` aporta su desplazamiento y cada giro cambia hacia dónde
        apunta el siguiente— y el personaje aparece del otro lado en once
        cuadros, los mismos salte una celda o cinco.

        Sin `end_jump` el salto se saltea y las órdenes que quedaban se pierden,
        que es lo que hace RM2k al llegar al final de la ruta.

        Devuelve True si el salto arrancó, False si se saltea, y None si no se
        pudo caer y la ruta **no es salteable**: ahí RM2k vuelve el cursor al
        `begin_jump` —`current_index = saved_index`— y corta el cuadro, así que
        el salto se reintenta cuadro a cuadro hasta que la celda se libere. Es
        lo que hace el droide del mapa 2 cuando el jugador se le planta en la
        celda a la que vuelve: se queda animando contra la pared, y salta apenas
        el jugador se corre.
        """
        dx = dy = 0
        guardadas = [RUTA_SALTO_INICIO] + list(self.ordenes)
        direccion = self.mirando
        hubo_fin = False
        while self.ordenes:
            orden = self.ordenes.pop(0)
            if orden == RUTA_CAMBIAR_GRAFICO:
                # Adentro de un salto **no se ejecuta**: el lazo de
                # `BeginMoveRouteJump` sólo mira los `move_*`, los que giran y
                # el `end_jump`, y todo lo demás lo consume sin hacer nada. Lo
                # que sí hay que hacer es tragarse el operando, o se leería
                # como una orden. Ninguna ruta del juego tiene una acá adentro
                # —medido, cero—, así que esto es por corrección y no porque
                # pase.
                if self.ordenes:
                    self.ordenes.pop(0)
                continue
            if orden == RUTA_SALTO_FIN:
                hubo_fin = True
                break
            if orden in RUTA_MOVER:
                direccion = RUTA_MOVER[orden]
                paso = RUTA_PASOS[direccion]
                dx += paso[0]
                dy += paso[1]
            elif orden in RUTA_MIRAR:
                direccion = RUTA_MIRAR[orden]
        if not hubo_fin:
            self.ordenes = []
            return False
        # `CheckOrMakeWayEx` corta con `if (self.GetThrough()) return true;`
        # justo después de mirar los límites del mapa, así que **el que
        # atraviesa paredes cae donde sea**. Sin esto, la piedra del recuerdo de
        # Core es una celda cerrada y el salto se saltea: taro lo vio como que
        # Core se mueve arriba de su islita y no salta nunca. La ruta que lo
        # mueve arranca justamente con un `atravesar_on`.
        if saltar is not None and not self.atraviesa and not saltar(dx, dy):
            if self.saltable:
                return False        # no se puede caer ahí: el salto se saltea
            self.ordenes = guardadas
            return None             # se reintenta el cuadro que viene
        # Hacia dónde queda mirando: gana el eje de mayor recorrido, y con
        # empate el vertical. En el lugar no cambia nada.
        if dx or dy:
            self.mirando = (2 if dy >= 0 else 0) if abs(dy) >= abs(dx) \
                else (1 if dx >= 0 else 3)
        self.salto_dx, self.salto_dy = dx, dy
        self.salto_resta = SALTO_PASO - SALTO_VELOCIDADES[self.velocidad - 1]
        self.arranco_salto = (dx, dy)
        self._contar_movimiento(False)
        return True


class Estado:
    """Lo que el intérprete recuerda entre páginas y entre mapas."""

    def __init__(self, grupo=()):
        self.switches = set()
        self.tinte = (TINTE_NEUTRO,) * 4      # r, g, b y saturación
        self.salto = None       # (mapa, x, y) si una página pidió mudarse
        # El fundido del teletransporte: en qué cuadro va, o None si no hay
        # ninguno corriendo. Mientras haya, el juego está congelado y lo único
        # que cambia es el brillo de la pantalla. Ver `brillo_de_fundido`.
        self.fundido = None
        self.fundidos = 0       # cuántos hubo, para el plan de la caminata
        # Cuántos ticks vivió la referencia. Lo cuenta `cuadro_de_eventos`, que
        # es por donde pasa un cuadro entero del mundo, y es lo que el plan le
        # dice al emulador: no "cuánto dura la caminata" sino **cuántos ticks
        # correr**, que es lo único que hace que los dos lados miren el mismo
        # momento cuando el mapa tiene algo que se mueve solo.
        self.ticks = 0
        # El grupo, en orden. El gráfico del héroe es el del primero, así que
        # esto no es contabilidad: se ve en la pantalla que se compara.
        self.grupo = list(grupo)
        # La ruta forzada del héroe. Las de los eventos van en `rutas_ev`,
        # indexadas por el índice del evento en la tabla del mapa; los cinco
        # atributos de siempre —`ruta`, `mirando`, `paso_dir`, `paso_cuadros`,
        # `cuadros_moviendose`— siguen valiendo y son ésta.
        self.ruta_heroe = Ruta()
        self.rutas_ev = {}
        # La animación de batalla en curso: ver OP_ANIMACION.
        self.animacion = None
        # Y su dibujo, que va por su cuenta y dura más: la línea de tiempo se
        # termina con la última entrada y el dibujo, dos cuadros por cada
        # cuadro de RM2k. Es (número de RM2k, blanco, tick, cuántos cuadros)
        # o None. Ver `empezar_dibujo` y `animacion.py`.
        self.anim_dibujo = None
        # Y qué cuadro le toca dibujar a este cuadro de consola, que es el
        # tick de antes de avanzarlo: ver `cuadro_de_animacion`.
        self.anim_cuadro = None
        # El cartel puesto, o None: (tono de ahora, desde, hasta, paso, pasos).
        # Ver OP_IMAGEN y `cuadro_de_imagen`.
        self.imagen = None
        # El evento que mira al héroe porque él lo disparó: ver `girar`.
        self.giro = None
        # Qué página tiene activa cada evento, como la dejó el último refresco.
        # Ver `pagina_activa`.
        self.paginas_activas = {}
        # Los destellos corriendo, por blanco: (r, g, b, potencia, cuadros, k).
        # `k` es cuántos cuadros pasaron desde que empezó.
        self.flashes = {}
        # Dónde está cada evento del mapa, en celdas. La lleva el estado y no el
        # mapa porque una ruta la cambia y la siguiente arranca de ahí: hay una
        # página de este juego que manda a caminar nueve veces al mismo evento.
        # Se rearma al entrar a cada mapa, igual que `load_npcs` en la ROM.
        self.pos_ev = {}
        # Los intérpretes paralelos del mapa cargado. Los arma
        # `entrar_a_un_mapa`; antes de entrar a ninguno no hay ninguno.
        self.paralelos = []
        # El desplazamiento del cuadro de texto que está en pantalla, o None
        # si no hay ninguno. Mientras esté abierto la página no avanza —es lo
        # que hace `Game_Message`— pero todo lo demás sí: la ruta forzada del
        # héroe sigue caminando y la cámara lo sigue.
        #
        # Es None y no False porque el desplazamiento 0 es un mensaje válido, y
        # de hecho es el que más se usa: `--mensaje-de-prueba` va primero en el
        # bloque justamente para no depender de en qué orden se compilen los
        # mapas. Todo lo que pregunte por esto tiene que preguntar `is not
        # None`.
        self.mensaje = None
        # El oro del grupo. No se muestra en ningún lado —el menú no existe—
        # pero la rama de oro de `ConditionalBranch` lo pregunta.
        self.oro = 0
        # Y el inventario: cuántos hay de cada ítem, por número de RM2k. Lo
        # que no está es cero. Ver OP_ITEM.
        self.items = {}
        # Si se puede guardar desde el menú y si se puede abrir el menú. Ver
        # OP_ACCESO.
        self.permitido = [True, True]
        # La elección abierta, si hay una. Mientras esté puesta, `mensaje`
        # apunta al cuadro de la opción marcada y la página está bloqueada.
        self.eleccion = None
        # El cronómetro: cuántos cuadros le quedan, si corre y si se dibuja.
        # Son tres cosas y no una porque RM2k las separa: un cronómetro puede
        # estar corriendo sin verse —`StartTimer(visible=false)`—, que es como
        # el juego mide cuánto tardó el jugador sin decírselo.
        # Qué eventos ya dieron su paso en este cuadro, movidos pegados a su
        # intérprete paralelo. Lo vacía la pasada de todos, al final.
        self.rutas_ev_movidas = set()
        self.timer_cuadros = 0
        self.timer_activo = False
        self.timer_dibujado = 0
        # La sacudida de pantalla: dónde está, cuánto le queda y con qué.
        self.sacudida_pos = 0
        # El clima: el tipo y la fuerza que puso el último WeatherEffects, las
        # gotas —[x, y, vida]— y su azar. Ver OP_CLIMA.
        self.clima = (0, 0)
        self.gotas = []
        self.lluvia_azar = LLUVIA_SEMILLA
        # La cámara corrida sin el héroe: dónde está y adónde va, las dos en
        # 1/16 de pixel, y cuánto corre por cuadro. Ver `cuadro_de_pan`.
        self.pan_x = self.pan_y = 0
        self.pan_dest_x = self.pan_dest_y = 0
        self.pan_paso = 0
        self.sacudida_resta = 0
        self.sacudida_fuerza = 0
        self.sacudida_vel = 0
        # El destello de pantalla: hacia qué color, cuánto nivel le queda —a
        # escala 256, para que la resta de cada cuadro no se coma el resto— y
        # cuántos cuadros. Ver `cuadro_de_destello`.
        self.destello = (0, 0, 0)
        self.destello_nivel = 0
        self.destello_resta = 0
        # Lo que se ve, que va un paso atrás del nivel: ver `cuadro_de_destello`.
        self.destello_pendiente = 0
        self.destello_mostrado = 0
        self.tinte_cambio = False
        self.timer_visible = False
        # Las variables, por ranura, y el estado del azar. Las variables viajan
        # en la partida guardada; el azar no, que RM2k tampoco lo guarda.
        self.variables = {}
        self.azar_estado = AZAR_SEMILLA

    def variable(self, ranura):
        return self.variables.get(ranura, 0)

    def item(self, numero):
        return self.items.get(numero, 0)

    def poner_variable(self, ranura, valor):
        """Dieciséis bits con signo, dando la vuelta como la ROM."""
        self.variables[ranura] = con_signo(valor & 0xFFFF)

    def azar(self, a, b):
        """Un número entre a y b, del xorshift compartido con la ROM."""
        self.azar_estado = azar_siguiente(self.azar_estado)
        return a + self.azar_estado % (b - a + 1)

    # El héroe visto como estaba antes. Su ruta es una `Ruta` como la de
    # cualquier evento, pero el resto del código la lee por estos nombres y no
    # hay razón para hacerlo cambiar.
    @property
    def ruta(self):
        return self.ruta_heroe.ordenes

    @ruta.setter
    def ruta(self, valor):
        self.ruta_heroe.ordenes = list(valor)

    @property
    def mirando(self):
        return self.ruta_heroe.mirando

    @mirando.setter
    def mirando(self, valor):
        self.ruta_heroe.mirando = valor

    @property
    def paso_dir(self):
        return self.ruta_heroe.paso_dir

    @property
    def paso_cuadros(self):
        return self.ruta_heroe.paso_cuadros

    @property
    def cuadros_moviendose(self):
        return self.ruta_heroe.cuadros_moviendose

    def cuadro_de_ruta(self, puede, saltar=None, existe=None):
        """Un cuadro de la ruta forzada del héroe."""
        return self.ruta_heroe.cuadro(puede, saltar, existe=existe)

    def entrar_a_un_mapa(self, posiciones, paginas=(), velocidades=None,
                         miradas=None):
        """Las posiciones de los eventos del mapa nuevo, en celdas.

        Las rutas que estuvieran corriendo se tiran: en RM2k son de los eventos
        del mapa que se deja, y allá no queda nadie caminando. Es el equivalente
        de que `cargar_mapa` vuelva a copiar la tabla desde la ROM.
        """
        self.rutas_ev = {}
        self.flashes = {}
        self.giro = None            # las filas del mapa nuevo son otras
        self.animacion = None       # y la animación de batalla no sigue
        self.anim_dibujo = None     # ni su dibujo: sus tiles son de un mapa
        self.anim_cuadro = None
        # Y el cartel se borra al cambiar de mapa: es el
        # `flags.erase_on_map_change` de `Game_Pictures`, que viene prendido de
        # fábrica y que este juego no apaga en ninguna de sus imágenes.
        self.imagen = None
        # Y la cámara corrida vuelve a cero, de golpe: es lo que hace
        # `PerformTeleport` con `map_changed`, devolviéndole a `pan_current` y a
        # `pan_finish` el valor por omisión. Un salto al mismo mapa no pasa por
        # acá y no la toca, igual que en RM2k.
        self.pan_x = self.pan_y = 0
        self.pan_dest_x = self.pan_dest_y = 0
        self.pos_ev = dict(posiciones)
        # Los intérpretes paralelos, uno por evento con página paralela que
        # compiló. **Son del mapa y no del `Interprete` de turno**: en la ROM
        # viven en `FAR_PAR_ESTADO`, que `cargar_mapa` pone a cero y nadie más
        # toca. Armarlos en `Interprete.__init__` los reiniciaba cada vez que
        # alguien hacía uno —la tecla de acción, un contacto, la caminata— y
        # entonces un auto que va por la mitad de su página volvía a empezar.
        # Ver `paralelos_del_mapa`.
        self.paralelos = paralelos_del_mapa(paginas)
        # Y las rutas propias de las páginas activas, que arrancan solas al
        # entrar, como `Game_Event::SetupFromPage`. Se vuelven a mirar cuando
        # cambia un switch o el grupo: `refrescar`.
        self.paginas_rutas = paginas
        self.velocidades = velocidades or {}
        # Y hacia dónde mira la página de cada uno. Sale de `collect_npcs`,
        # como la velocidad, así que se queda con la del mapa recién cargado.
        # La ROM la lee viva de la fila del NPC, que el refresco reescribe
        # cuando un evento cambia de página; que las dos coincidan igual no es
        # suerte: **los 21 eventos del juego que caminan una diagonal miran
        # para el mismo lado en todas sus páginas**, así que no hay refresco
        # que las separe. El día que eso deje de ser cierto, esto tiene que
        # pasar a leerse de la página activa.
        self.miradas = miradas or {}
        self.refresco = False
        self.aplicar = False
        self.rutas_de_pagina()

    def girar(self, indice, pagina, celda, heroe):
        """El giro hacia el héroe de un evento que él disparó: ver GIRO.

        Gira si su página gira y no tiene una ruta andando —ésa decide adónde
        mira—. Una que ya terminó no cuenta: la ranura no se suelta hasta el
        mapa que viene, y con "tiene ruta" el `GangMember1` de Lashe City, al
        que una escena había movido, no giraba nunca más.
        `celda` es la del evento y `heroe` la del héroe. Queda anotado el
        gráfico de la página, para que un refresco sepa si el giro sigue. La
        ROM es `giro_disparar`.
        """
        ruta = self.rutas_ev.get(indice)
        if not pagina.get("gira") or (ruta is not None
                                      and (ruta.de_pagina or ruta.pendiente)):
            return
        self.giro = {"evento": indice, "dir": direccion_hacia(celda, heroe),
                     "grafico": tuple(pagina["grafico"])}

    def giro_por_ruta(self, indice):
        """Una ruta que agarra al evento termina su giro: desde ahí mira
        adonde diga ella. La ROM es `giro_por_ruta`."""
        if self.giro is not None and self.giro["evento"] == indice:
            self.giro = None

    def revisar_giro(self):
        """Al aplicar las páginas: el giro se termina si el evento se quedó
        sin página, o con una que no gira o que dibuja otra cosa. Es el
        `SetFacing(page->character_direction)` de `Game_Event::RefreshPage`,
        que sólo corre si la página es otra; con la misma, el evento sigue
        mirando al héroe. La ROM es `giro_revisar`.

        Una diferencia declarada: si la página nueva trae otro CharSet con la
        misma dirección y la misma columna, RM2k lo deja girado con el dibujo
        nuevo y acá se termina el giro.
        """
        if self.giro is None:
            return
        pagina = self.paginas_activas.get(self.giro["evento"])
        if (pagina is None or not pagina.get("gira")
                or tuple(pagina["grafico"]) != self.giro["grafico"]):
            self.giro = None

    def pose_girada(self, indice, pose):
        """La pose con que se dibuja el evento: la de siempre, o la que mira
        al héroe si es el que gira —la misma columna, la fila del giro—."""
        if self.giro is not None and self.giro["evento"] == indice:
            return self.giro["dir"] * 3 + pose % 3
        return pose

    def rutas_de_pagina(self):
        """`Game_Map::Refresh` entero: elegir las páginas y aplicarlas."""
        self.elegir_paginas()
        self.aplicar_paginas()

    def elegir_paginas(self):
        """La instantánea de qué página tiene cada evento.

        Se rehace acá y en ningún otro lado: es `Game_Event::page`, que sólo
        escribe `Refresh`. Va separada de `aplicar_paginas` porque el refresco
        a mitad de comando corre sólo esta mitad; ver `ejecutar`.
        """
        self.paginas_activas = {
            indice: pagina_activa_viva(self.paginas_rutas, indice, self)
            for indice in self.pos_ev}

    def aplicar_paginas(self):
        """Cada evento con la ruta propia de su página activa.

        Un evento cuya página activa cambió carga la ruta de la nueva desde el
        principio, y uno cuya página nueva no tiene ruta se queda quieto. Un
        evento con la misma página de antes no se toca, y su ruta sigue por
        donde iba.
        """
        self.revisar_giro()
        for indice in self.pos_ev:
            pagina = self.paginas_activas[indice]
            propia = pagina.get("ruta_propia") if pagina is not None else None
            ruta = self.rutas_ev.get(indice)
            if propia:
                if ruta is not None and ruta.pagina is pagina:
                    continue
                if ruta is None:
                    ruta = self.ruta_de_evento(indice)
                self.giro_por_ruta(indice)
                ruta.cargar_pagina(propia, pagina)
            elif ruta is not None and ruta.ordenes_pagina:
                ruta.sin_pagina()

    def paginas_caminando(self):
        """Si alguna ruta propia de página tiene algo por hacer. No entra en
        `algo_corriendo` a propósito: `OP_RUTAS` no las espera, y una que se
        repite no termina nunca. Lo mira sólo el lazo con presupuesto de
        cuadros, para no cortar antes de tiempo un mapa donde alguien camina
        solo."""
        return any(r.de_pagina and (r.ordenes or r.paso_resta or r.espera
                                    or r.salto_resta)
                   for r in self.rutas_ev.values())

    def refrescar(self):
        """El refresco pendiente, si un switch o el grupo cambió desde el
        último. Se hace al empezar el cuadro, antes del intérprete, que es
        cuando `Game_Map::Update` mira `GetNeedRefresh`.

        La otra mitad —`aplicar`— puede venir de un refresco a mitad de
        comando, que sólo eligió las páginas. Ver `refrescar_eligiendo`."""
        if self.refresco:
            self.refresco = False
            self.aplicar = False
            self.rutas_de_pagina()
        elif self.aplicar:
            self.aplicar = False
            self.aplicar_paginas()

    def refrescar_eligiendo(self):
        """El refresco de adentro del lazo de comandos, que sólo elige.

        `Game_Interpreter::Update` refresca antes de cada comando, y de eso
        depende que una página que apaga su propia condición deje de ser la
        activa en el acto. Lo que el comando siguiente puede llegar a mirar es
        **cuál es la página activa**; recargar las rutas y los gráficos de los
        NPCs no cambia nada hasta que se dibuje el cuadro, así que eso queda
        para el principio del cuadro que viene.

        No es un atajo de la referencia: es lo que hace la ROM, y por la misma
        razón. Su segunda pasada recorre los eventos del mapa recargando filas
        de OAM y ranuras de ruta, y hacerla en medio de un cuadro le costaba el
        cuadro entero en el mapa 2.
        """
        if self.refresco:
            self.refresco = False
            self.aplicar = True
            self.elegir_paginas()

    def evento_en(self, celda):
        """Qué evento está parado en esa celda, o None.

        Los eventos que no se pueden disparar están en la tabla igual: lo que
        decide es la página activa, y eso lo mira quien llama.
        """
        for indice, donde in self.pos_ev.items():
            if donde == celda:
                return indice
        return None

    def ruta_de_evento(self, indice):
        if indice not in self.rutas_ev:
            # Con ruta, adónde mira lo decide ella: el giro se termina. En la
            # ROM es `giro_por_ruta`, donde el evento se queda con su ranura.
            if self.giro is not None and self.giro["evento"] == indice:
                self.giro = None
            self.rutas_ev[indice] = Ruta()
            # A la velocidad de la página con que se dibuja, que es la que
            # RM2k le deja a una ruta forzada: `SetupFromPage` la pone y
            # `ForceMoveRoute` no la toca. Sale de `collect_npcs`, como en la
            # fila del NPC de la ROM; por defecto es 3, dieciséis cuadros por
            # celda, y no la 4 del héroe.
            self.rutas_ev[indice].velocidad = self.velocidades.get(indice, 3)
            # Y mirando adonde mira su página: ver `Ruta.mirando_pagina`.
            self.rutas_ev[indice].mirando_pagina = self.miradas.get(indice, 2)
        return self.rutas_ev[indice]

    def mover_evento(self, indice, x, y):
        """Planta al evento en la celda, como `Game_Character::MoveTo`.

        La celda es la nueva desde este cuadro y el paso o el salto en curso
        se cortan —`SetRemainingStep(0)`—: el evento se dibuja exactamente
        sobre la celda. Lo que **no** se toca es la ruta, que sigue con la
        orden siguiente desde acá, ni hacia dónde mira. Un evento que nunca
        recibió una ruta tampoco la recibe por esto: en la ROM no se lleva
        una ranura, y se dibuja con la pose de su página, sólo que en otra
        celda.
        """
        self.pos_ev[indice] = (x, y)
        if indice in self.rutas_ev:
            self.rutas_ev[indice].cortar_paso()

    def cuadro_de_paralelos(self, paginas, mover_evento=None):
        """Un cuadro de cada evento con página paralela, **y su paso detrás**.

        `Game_Event::Update` corre el intérprete paralelo del evento y a
        continuación llama a `Game_Character::Update()`, o sea que lo mueve
        —easyrpg, `game_event.cpp:580`—, y `UpdateMapEvents` hace eso evento por
        evento. No es lo mismo que correr todos los intérpretes y después mover
        a todos, y la diferencia se ve cuando una página paralela le fuerza una
        ruta a **otro** evento: en Lashe City el `Car4` le pisa la suya al
        `Car2` en cada cuadro, y con los pasos todos al final el pisotón gana y
        el `Car2` no camina nunca. En EasyRPG y en el RPG Maker original los
        cuatro autos andan.

        `mover_evento` es quien sabe dar ese paso: lo pone el que arma el
        cuadro, que es el único que tiene la pasabilidad del mapa. **Sin él el
        evento no camina**, y ése era el último rojo de la tanda: el camino
        colapsado —la entrada y la caminata de `hero_position`— llamaba acá sin
        pasarlo, o directamente no llamaba, así que el `Car3` del mapa 8 se
        quedaba clavado en su celda de arranque mientras el de la ROM se iba de
        cámara.

        Vive en el estado y no en `Interprete` porque es del **mapa**: en la
        ROM son `FAR_PAR_ESTADO`, que sólo pone a cero `cargar_mapa`.
        """
        for paralelo in self.paralelos:
            paralelo.cuadro(pagina_activa(paginas, paralelo.evento, self),
                            self)
            if mover_evento is not None:
                mover_evento(paralelo.evento)

    def rutas_pendientes(self):
        """Si queda alguna ruta forzada sin terminar, la del héroe incluida.

        Es `Game_Map::IsAnyMovePending`, y es global a propósito:
        `ProceedWithMovement` no espera al evento que se acaba de mandar a
        caminar sino a que no quede ninguno.
        """
        return (self.ruta_heroe.pendiente
                or any(r.pendiente for r in self.rutas_ev.values()))

    def asentado(self, paginas):
        """Si el mapa terminó de asentarse, o sea `algo_corriendo` al revés y
        **sin contar lo que mueven los intérpretes paralelos**.

        Lo mira el único lazo que corre "hasta que todo se aquiete", que es la
        entrada sin presupuesto de cuadros. Un evento con página paralela no se
        aquieta nunca —para eso existe: los cuatro autos de Lashe City dan
        vueltas mientras el mapa esté cargado— así que mirarlo con
        `algo_corriendo` a secas se comía las diez mil vueltas del tope. Es el
        mismo motivo por el que el cronómetro tampoco entra en `algo_corriendo`.

        `rutas_pendientes` no se toca: eso es `Game_Map::IsAnyMovePending` y es
        global a propósito, porque una página que espera a las rutas espera
        también a las de los autos, allá y en la consola.
        """
        paralelos = {p.evento for p in self.paralelos}
        return not (self.sacudida_resta > 0 or self.destello_nivel > 0
                    or bool(self.flashes) or self.pan_falta() > 0
                    or self.ruta_heroe.pendiente
                    or any(ruta.pendiente
                           for indice, ruta in self.rutas_ev.items()
                           if indice not in paralelos))

    def cuadro_de_rutas_ev(self, puede_pasar, puede_caer=None, heroe=None,
                           congelada=False, solo=None, existe=None):
        """Un cuadro de todas las rutas de eventos. `puede_pasar(indice, x, y,
        direccion)` dice si ese evento puede dar ese paso, `puede_caer(x, y,
        indice)` si ese evento puede aterrizar en esa celda, y `heroe` es la
        celda del héroe, que es a quien encara `face_hero`.

        La celda se mueve al **empezar** el paso, igual que el héroe: es lo que
        hace `begin_step` en la ROM, y modelarlo distinto acá dejaría a los dos
        lados contando los cuadros de otra manera. Un salto la mueve igual, sólo
        que de una y no de a una celda.
        """
        # `solo` es la vuelta de un evento suelto, la que corre pegada a su
        # intérprete paralelo; los que se movieron así quedan anotados para que
        # la pasada de todos no los mueva dos veces. Ver `cuadro_de_paralelos`.
        for indice, ruta in list(self.rutas_ev.items()):
            if solo is not None:
                if indice not in solo:
                    continue
                self.rutas_ev_movidas.add(indice)
            elif indice in self.rutas_ev_movidas:
                continue
            x, y = self.pos_ev.get(indice, (0, 0))
            empezaba = ruta.paso_cuadros == 0
            direccion = ruta.cuadro(
                lambda d, desde=(0, 0), i=indice, px=x, py=y: puede_pasar(
                    i, px + desde[0], py + desde[1], d),
                saltar=(lambda dx, dy, px=x, py=y, i=indice:
                        puede_caer is None or puede_caer(px + dx, py + dy, i)),
                hacia_heroe=(None if heroe is None else
                             lambda px=x, py=y: direccion_hacia((px, py),
                                                                heroe)),
                congelada=congelada,
                existe=(None if existe is None else
                        lambda d, px=x, py=y: existe(px, py, d)))
            if ruta.arranco_salto is not None:
                dx, dy = ruta.arranco_salto
                self.pos_ev[indice] = (x + dx, y + dy)
            elif direccion is not None and empezaba:
                dx, dy = RUTA_PASOS[direccion]
                self.pos_ev[indice] = (x + dx, y + dy)
        if solo is None:
            self.rutas_ev_movidas.clear()

    def algo_corriendo(self):
        """Si queda algo andando solo: una ruta forzada, un destello, la
        sacudida de pantalla o la cámara corriéndose.

        Lo mira quien decide cuándo dejar de contar cuadros. Sin los destellos
        acá, una página que sólo destella termina en el primer cuadro y el
        destello no avanza nunca: se queda encendido para siempre.
        """
        return (self.sacudida_resta > 0 or self.destello_nivel > 0
                or bool(self.flashes) or self.rutas_pendientes()
                or self.pan_falta() > 0 or self.animacion is not None)

    def cuadro_de_destello(self):
        """Un cuadro del destello de pantalla: `Flash::Update` sin el continuo,
        que este juego no usa.

        RM2k baja el nivel en `nivel / cuadros_que_quedan` por cuadro, con
        `double`: de 31 en treinta cuadros, 29.97, 28.93... La consola no tiene
        `double`, así que el nivel va a escala 256 y la resta es entera. Lo que
        se dibuja es la parte entera del nivel, de 0 a 31; contra la cuenta con
        `double` difiere en uno como mucho, que es lo mismo que el tinte.

        En el último cuadro el nivel cae a cero de golpe, como allá: con un
        cuadro restante la resta es el nivel entero.

        Lo que se **ve** cambia cuadro por medio, y un cuadro después de la
        cuenta. Es lo que hace la ROM: el destello es una transformación de
        CGRAM, como el tinte, y rehacer las doscientas y pico entradas de las
        tres paletas del mapa no entra en un cuadro junto con todo lo demás
        —medido con `cuadros_perdidos`: perdía uno por cuadro—. Así que la ROM
        lo reparte: en el cuadro en que a la resta le queda un número impar
        arma las tablas del nivel de ese cuadro y pasa las paletas del fondo,
        y en el siguiente pasa las de los sprites y sube todo junto. Un
        destello de treinta cuadros se ve en quince escalones, y nadie lo
        distingue de treinta. La excepción es un tinte que cambie en el cuadro
        impar: ahí la ROM hace todo de una, para que el tinte nuevo no se vea
        un cuadro sin destello, y lo que se ve es el nivel de ese cuadro.
        """
        if self.destello_nivel > 0:
            if self.destello_resta > 0:
                self.destello_nivel -= self.destello_nivel // self.destello_resta
                self.destello_resta -= 1
            if self.destello_resta <= 0:
                self.destello_nivel = 0
                self.destello_mostrado = 0
            elif self.destello_resta & 1:
                self.destello_pendiente = self.destello_nivel >> 8
                if self.tinte_cambio:
                    self.destello_mostrado = self.destello_pendiente
            else:
                self.destello_mostrado = self.destello_pendiente
        self.tinte_cambio = False

    def poner_clima(self, tipo, fuerza):
        """`SetWeatherEffect`: si no cambia nada no toca nada; si cambia, las
        gotas arrancan apagadas y el azar vuelve a su semilla."""
        if (tipo, fuerza) == self.clima:
            return
        self.clima = (tipo, fuerza)
        self.gotas = ([[0, 0, 0] for _ in range(LLUVIA_GOTAS[fuerza])]
                      if tipo == CLIMA_LLUVIA else [])
        self.lluvia_azar = LLUVIA_SEMILLA

    def _lluvia_azar(self):
        self.lluvia_azar = azar_siguiente(self.lluvia_azar)
        return self.lluvia_azar

    def poner_imagen(self, tono):
        """`Game_Pictures::Show`: el cartel aparece ya con su tono."""
        self.imagen = (tuple(tono), tuple(tono), tuple(tono), 0, 0)

    def mover_imagen(self, hasta, cuadros):
        """`Game_Pictures::Move`: el tono se va hacia `hasta` en `cuadros`.

        Sin cartel puesto no hace nada, como allá: `Move` sobre una imagen que
        no se mostró le escribe el destino a una que no se dibuja.
        """
        if self.imagen is None:
            return
        ahora = self.imagen[0]
        if not cuadros:
            self.imagen = (tuple(hasta), tuple(hasta), tuple(hasta), 0, 0)
        else:
            self.imagen = (ahora, ahora, tuple(hasta), 0, cuadros)

    def cuadro_de_imagen(self):
        """Un cuadro del fundido del cartel: `Game_Pictures::Picture::Update`.

        El paso avanza primero y el tono sale de `imagen_tono`, que es la misma
        cuenta que hace `imagen_tick` en main.s.
        """
        if self.imagen is None:
            return
        _ahora, desde, hasta, paso, pasos = self.imagen
        if paso >= pasos:
            return
        paso += 1
        self.imagen = (imagen_tono(desde, hasta, paso, pasos),
                       desde, hasta, paso, pasos)

    def cuadro_de_lluvia(self):
        """`Game_Screen::UpdateRain`, un cuadro. La ROM es `lluvia_tick`."""
        for gota in self.gotas:
            if gota[2] > 0:
                gota[2] -= 1
                gota[0] = (gota[0] + LLUVIA_DX) % LLUVIA_LADO
                gota[1] = (gota[1] + LLUVIA_DY) % LLUVIA_LADO
            elif self._lluvia_azar() & 0xFF < LLUVIA_NACE:
                gota[2] = LLUVIA_VIDA
                gota[0] = self._lluvia_azar() & 0xFF
                gota[1] = self._lluvia_azar() & 0xFF

    def cuadro_de_sacudida(self):
        """Un cuadro de la sacudida: `Shake::Update` sin la continua, que
        este juego no usa. En el último cuadro la pantalla vuelve a cero."""
        if self.sacudida_resta > 0:
            self.sacudida_resta -= 1
            if self.sacudida_resta > 0:
                self.sacudida_pos = sacudida_siguiente(
                    self.sacudida_fuerza, self.sacudida_vel,
                    self.sacudida_resta, self.sacudida_pos)
            else:
                self.sacudida_pos = 0

    def cuadro_de_pan(self):
        """Un cuadro de la cámara corrida: `Game_Player::UpdatePan`.

        Se acerca al destino de a `pan_paso` por eje, sin pasarse. Las dos
        cuentas son de dieciseisavos de pixel, que es donde RM2k lleva la
        cámara; quien dibuja las baja a pixeles enteros con `pan_en_pixeles`.
        """
        if not self.pan_paso:
            return
        for eje in ("x", "y"):
            actual = getattr(self, "pan_" + eje)
            destino = getattr(self, "pan_dest_" + eje)
            if actual == destino:
                continue
            paso = min(self.pan_paso, abs(destino - actual))
            setattr(self, "pan_" + eje,
                    actual + (paso if destino > actual else -paso))

    def pan_falta(self):
        """Lo que le falta al pan, que es de lo que sale la espera. Es el
        `max` de los dos ejes de `GetPanWait`."""
        return max(abs(self.pan_x - self.pan_dest_x),
                   abs(self.pan_y - self.pan_dest_y))

    def cuadro_de_timer(self):
        """Un cuadro del cronómetro.

        Es `Game_Party::UpdateTimers`, y lo que importa de él es el final: al
        llegar a cero segundos el cronómetro no se queda mostrando `00:00`,
        sino que `StopTimer` lo apaga **y lo esconde**. O sea que el último
        cuadro en que se ve dice `00:01`, y el siguiente ya no hay nada
        dibujado. Modelarlo como "se para" nada más dejaría a la referencia
        dibujando cinco glifos que RM2k no dibuja.
        """
        # Lo que se dibuja es la cuenta de **antes** de este cuadro. La
        # consola muestra en cada cuadro la OAM que armó la vuelta anterior
        # —es el mismo cuadro de retraso de la caminata, que `paso_de_ruta`
        # compensa con la fase del paso—, y con los dígitos y los dos puntos
        # no había con qué compensarlo: el parpadeo cambiaba un cuadro antes
        # acá que en la ROM, con el mismo estado de los dos lados. Lo vio el
        # arranque fijo, que alinea los cuadros exacto.
        self.timer_dibujado = self.timer_cuadros
        if self.timer_activo and self.timer_cuadros > 0:
            self.timer_cuadros -= 1
            if self.timer_cuadros // CUADROS_POR_SEGUNDO == 0:
                self.timer_activo = self.timer_visible = False

    def timer_texto(self):
        """Los cinco caracteres que se dibujan: MM:SS, con los dos puntos que
        parpadean.

        Es `Sprite_Timer::Draw`: los minutos y los segundos salen de
        `cuadros / 60`, y los dos puntos se saltean cuando `cuadros % 60 < 30`.
        El espacio en el medio es "no dibujar nada".
        """
        segundos = self.timer_dibujado // CUADROS_POR_SEGUNDO
        return "%02d%s%02d" % (
            segundos // 60,
            ":" if (self.timer_dibujado % CUADROS_POR_SEGUNDO
                    >= CUADROS_POR_SEGUNDO // 2) else " ",
            segundos % 60)

    def cuadro_de_animacion(self):
        """Un cuadro de la animación de batalla: las entradas de este tick
        disparan su destello —el sonido no se ve— y el reloj avanza. Va antes
        que los destellos, como en `Game_Screen::Update`. La ROM es
        `animacion_tick`."""
        anim = self.animacion
        if anim is None:
            return
        while anim["entradas"] and anim["entradas"][0][0] == anim["t"]:
            e = anim["entradas"].pop(0)
            if e[1] == ANIM_DESTELLO:
                self.destello = (e[2], e[3], e[4])
                self.destello_nivel = e[5] << 8
                self.destello_resta = e[6]
            elif e[1] == ANIM_FLASH:
                self.flashes[e[2]] = (e[3], e[4], e[5], e[6], e[7], 0)
        anim["t"] += 1
        if not anim["entradas"]:
            self.animacion = None

    def cuadro_de_dibujo(self):
        """Qué cuadro de la animación se dibuja en este cuadro de consola.

        Dos cuadros de consola por cada cuadro de RM2k, que es lo que dura
        `BattleAnimation`: `num_frames = GetRealFrames() * 2`. El que se dibuja
        sale del tick **antes** de avanzarlo, así que en el tick 0 se dibuja el
        cuadro 0, que es el mismo en que dispara el `timing` del cuadro 1 de
        RM2k. Es `animacion_dibujo_tick` en main.s.
        """
        self.anim_cuadro = None
        if self.anim_dibujo is None:
            return
        _numero, _blanco, t, cuantos = self.anim_dibujo
        if t // 2 >= cuantos:
            self.anim_dibujo = None
            return
        self.anim_cuadro = t // 2
        self.anim_dibujo[2] = t + 1

    def empezar_dibujo(self, numero, blanco):
        """Arranca el dibujo de la animación `numero` sobre `blanco`.

        La nueva reemplaza a la que hubiera, como la línea de tiempo. Una
        animación sin cuadros o marcada `ANIM_SIN_DIBUJO` no dibuja nada, y la
        ROM llega al mismo lugar por su tabla: el $FF de `anim_batalla_de`.
        """
        anim = ANIMACIONES.get(numero) if numero != ANIM_SIN_DIBUJO else None
        cuantos = len(anim["cuadros"]) if anim else 0
        self.anim_dibujo = ([numero, blanco, 0, cuantos] if cuantos else None)
        self.anim_cuadro = None

    def cuadro_de_flashes(self):
        """Un cuadro de todos los destellos: los que se acabaron se apagan."""
        for blanco in list(self.flashes):
            r, g, b, potencia, cuadros, k = self.flashes[blanco]
            if k >= cuadros:
                del self.flashes[blanco]
            else:
                self.flashes[blanco] = (r, g, b, potencia, cuadros, k + 1)

    def nivel_de_flash(self, blanco):
        """Con cuánta fuerza destella este blanco ahora mismo, de 0 a 31.

        La curva es la forma cerrada de la que easyrpg calcula a mano:
        `level -= level / time_left` cuadro a cuadro da exactamente
        `potencia * (cuadros - k) / cuadros`. Acá va con enteros porque los dos
        lados tienen que dar el mismo número, y allá va con `double`.
        """
        if blanco not in self.flashes:
            return 0
        _r, _g, _b, potencia, cuadros, k = self.flashes[blanco]
        return potencia * (cuadros - k) // cuadros

    def color_de_flash(self, blanco):
        """(r, g, b) del destello de este blanco, en cinco bits."""
        return self.flashes[blanco][:3]

    def encendido(self, numero):
        return numero in self.switches

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
        self.refresco = True     # las páginas que piden un actor pueden cambiar

    def lider(self):
        return self.grupo[0] if self.grupo else None


# Cuánto ocupa cada opcode, para recorrer una página compilada sin ejecutarla.
# Es **la** tabla: el conversor y `blancos_de_ruta` recorren con esto, y
# `ejecutar` avanza con las mismas cuentas. Había dos copias —una acá y otra
# en el conversor— y la de acá se quedó con el OP_RUTA viejo cuando el nuevo
# sumó la frecuencia, y sin OP_LUGAR: doce casos de la tanda en rojo, y
# hasta ahí un recorrido que podía dar mal **sin decirlo** a quién le tocan
# las doce poses. OP_RUTA no está: lleva las órdenes detrás y lo mide
# `largo_de_opcode`.
LARGO_DE_OPCODE = {
    OP_FIN: 1, OP_SWITCH: 4, OP_TELEPORT: 6, OP_ESPERAR: 3, OP_TINTE: 5,
    OP_GRUPO: 3, OP_MENSAJE: 3, OP_RUTAS: 1, OP_FLASH: 7, OP_TIMER: 5,
    OP_BGM: 2, OP_LUGAR: 6, OP_TRUEQUE: 3, OP_SACUDIR: 5, OP_DESTELLO: 6,
    OP_FUNDIR_BGM: 3, OP_PAN: 8, OP_SI: 7, OP_IR: 3, OP_ORO: 5,
    OP_GUARDAR: 1, OP_VAR: 8, OP_SI_VAR: 8, OP_ITEM: 4, OP_ACCESO: 3,
    OP_CLIMA: 3, OP_SONIDO: 3,
    OP_IMAGEN: 5, OP_IMAGEN_MOVER: 6, OP_IMAGEN_BORRAR: 1,
}


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


def sacudida_siguiente(fuerza, velocidad, resta, posicion):
    amplitud = 1 + 2 * fuerza
    seno = SENO_SACUDIDA[(resta * 4 * (velocidad + 2)) % 256]
    cociente = (amplitud * abs(seno)) // 127
    nuevo = -cociente if seno > 0 else cociente
    corte = (velocidad * amplitud) // 8 + 1
    return max(posicion - corte, min(posicion + corte, nuevo))


def largo_de_opcode(codigo, i):
    """Cuántos bytes ocupa el opcode que empieza en `codigo[i]`."""
    op = codigo[i]
    if op == OP_RUTA:
        return 4 + codigo[i + 3]
    if op == OP_ELEGIR:
        return 3 + 4 * codigo[i + 1]
    if op == OP_TIENDA:
        return 4 + 2 * codigo[i + 3]
    if op == OP_ANIMACION:
        return 4 + ANIM_ENTRADA * codigo[i + 3]
    largo = LARGO_DE_OPCODE.get(op)
    if largo is None:
        raise ValueError("opcode %d que no sé medir" % op)
    return largo


def recorrer_codigo(codigo):
    """(desplazamiento, código) de cada opcode de una página ya compilada."""
    i = 0
    while i < len(codigo):
        yield i, codigo
        i += largo_de_opcode(codigo, i)


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
            if c[i] == OP_RUTA and c[i + 1]:
                blancos.add(c[i + 1] - 1)
    return blancos


def pixeles_del_paso(x, y, ruta):
    """Dónde está en pixeles quien está a mitad de un paso, desde su celda.

    La celda se mueve al **empezar** el paso y los pixeles van detrás: a la
    celda de destino se le descuentan los que falten, a WALK_SPEED por cuadro,
    que es como los come `advance_step` en la ROM. Sin esto, quien camina
    aparece en la celda nueva un paso antes de tiempo; en el cuadro final da
    igual, y por eso no se notó hasta comparar *durante* la caminata.

    Lo usan el héroe y los eventos, que es la razón de que viva acá.
    """
    px, py = x * CELDA_PX, y * CELDA_PX
    if ruta.paso_resta and ruta.paso_dir is not None:
        dx, dy = RUTA_PASOS[ruta.paso_dir]
        # De 256 por celda a pixeles: los dieciseisavos se tiran, que es lo que
        # hace la ROM con `resta >> 4`. A velocidad 4 es lo mismo que los
        # cuadros por dos.
        faltan = ruta.paso_resta >> 4
        px -= dx * faltan
        py -= dy * faltan
    elif ruta.salto_resta:
        # En un salto la interpolación es la de RM2k y la división va **al
        # final**: `GetSpriteX` hace `x * 256 - dx * restante` y recién ahí
        # divide por 16. Dividir el descuento por separado da uno de más o de
        # menos cada vez que no es múltiplo de 16, que con 24 por cuadro es la
        # mitad de los cuadros del salto.
        por_celda = SALTO_PASO // CELDA_PX
        px = (x * SALTO_PASO - ruta.salto_dx * ruta.salto_resta) // por_celda
        py = (y * SALTO_PASO - ruta.salto_dy * ruta.salto_resta) // por_celda
    return px, py


def altura_del_salto(ruta):
    """Cuántos pixeles hay que subir el dibujo por el arco del salto.

    Es `GetJumpHeight`: sube y baja con lo que queda del salto, y la curva no es
    lineal sino la tabla de RM2k. Lo que se dibuja es la posición interpolada
    menos esto; **lo que se ordena contra los demás no**, porque `GetScreenZ`
    llama a `GetScreenY(false)`, o sea sin el salto. Un personaje saltando no
    pasa por delante de los que están más abajo.
    """
    if not ruta.salto_resta:
        return 0
    resta = ruta.salto_resta
    bruta = (SALTO_PASO - resta if resta > SALTO_PASO // 2 else resta) // 8
    if bruta < 5:
        return bruta * 2
    if bruta < 13:
        return bruta + 4
    return 16


def pagina_activa(paginas, evento, estado):
    """La página activa del evento **como la dejó el último refresco**.

    En RM2k la página activa no se recalcula cada vez que alguien pregunta: es
    `Game_Event::page`, y sólo la reescribe `Game_Map::Refresh()`, que corre al
    principio de `Game_Map::Update`. Todo lo que pasa después en ese cuadro —el
    intérprete, el héroe, los eventos— ve la página **vieja**. La ROM hace lo
    mismo, guardándola en la fila del NPC.

    Acá se calculaba viva, y la diferencia no era teórica: un switch prendido
    por una página le abría el paso al héroe en ese mismo cuadro, y en la ROM
    no. Y como una orden de ruta bloqueada se saltea y no se reintenta, eso no
    se veía como un cuadro de atraso sino como que el héroe **nunca** cruzaba
    la puerta del Emitter Room.

    Sin instantánea —antes del primer refresco— se calcula viva, que es lo que
    hace `Refresh` la primera vez.
    """
    if evento in estado.paginas_activas:
        return estado.paginas_activas[evento]
    return pagina_activa_viva(paginas, evento, estado)


def pagina_activa_viva(paginas, evento, estado):
    """La página de número más alto del evento cuyas condiciones se cumplen.

    Es la regla de RM2k, y es la misma pasada que hace la ROM. La usa el
    refresco; todo lo demás pregunta por `pagina_activa`, que devuelve lo que
    el refresco dejó.
    """
    elegida = None
    for pagina in paginas:
        if pagina["evento"] != evento:
            continue
        if pagina["switch_a"] and not estado.encendido(pagina["switch_a"]):
            continue
        if pagina["switch_b"] and not estado.encendido(pagina["switch_b"]):
            continue
        if pagina["actor"] and pagina["actor"] not in estado.grupo:
            continue
        # Y la de ítem, desde la misma noche: que haya al menos uno. Es
        # `GetItemCount(id) + GetEquippedItemCount(id)`, sin equipo. Antes
        # estas páginas se emitían como "nunca activas".
        if pagina.get("item") and not estado.item(pagina["item"]):
            continue
        # Y la condición por variable, desde el 2026-09-10 a la noche: la
        # ranura, la comparación y el valor, como `AreConditionsMet` con
        # `CheckOperator`. Catorce páginas del juego la usan, todas con >=.
        if pagina.get("variable") is not None:
            ranura, comparacion, contra = pagina["variable"]
            if not cumple_comparacion(estado.variable(ranura), comparacion,
                                      contra):
                continue
        elegida = pagina
    return elegida


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
# El switch que no se prende nunca: es lo que lleva como `switch_a` una página
# con una condición que el port no puede cumplir —un ítem, ver
# `rm2k.CONDICIONES_IMPOSIBLES`— para que ni la ROM ni la referencia la elijan
# jamás, y las otras páginas del evento sí. Los dos lados leen la misma tabla,
# así que no hay dos maneras de equivocarse. El juego consulta switches hasta el
# 1003 y el 1023 es el de la página de prueba.
SWITCH_IMPOSIBLE = 1021

def evento_de_prueba(game_map):
    """Qué número de evento le toca a la página inventada: el primero libre.

    Tiene que **entrar en la tabla** —la ROM lleva un byte de estado por
    evento, indexado por este número— y no chocar con ninguno del mapa. Y tiene
    que ser **bajo**: los barridos de la ROM van de cero a `ev_total`, así que
    un número alto los obliga a recorrer eventos que no existen. Con el 119
    fijo, un mapa de cuatro eventos barría ciento veinte, y eso alcanzaba para
    perder el cuadro.

    Antes de eso fue 9999, que entraba en el bytecode pero se caía de la tabla:
    la ROM lo descartaba en silencio y la página de prueba no arrancaba nunca.
    """
    return len(game_map.events)


def pagina_de_prueba(espera=0, tinte=(), ruta=(), mensaje=None, ruta_ev=(),
                    flash=(), switches=(), timer=(), lugar=(),
                    frecuencia=RUTA_FRECUENCIA, sacudida=(), fundir_bgm=0,
                    pan=(), rama=(), destello=(), guardar=False,
                    variables=(), rama_var=(), items=(), acceso=(),
                    lluvia=None, animacion=(), eventos_mapa=None):
    """Una página automática inventada: una ruta forzada, una espera, un tinte.

    No sale de ningún dato del juego, y ésa es la idea. El intérprete corre
    cuadro a cuadro desde que dejó de colapsar el tiempo, pero **ninguna página
    del juego que compile tiene una espera**, así que ese camino —el corazón del
    cambio— no lo ejercitaba nada. Es el mismo caso que `snes-encima`, que
    existe porque ningún evento del juego llega a la prioridad 2.

    Lo sintético es la entrada, no la comparación: los dos lados corren este
    bytecode y se comparan como siempre, la ROM contra la referencia. Y es una
    prueba filosa por construcción: antes del cuadro N la pantalla está sin
    teñir y después está teñida, así que si la ROM y la referencia no cuentan
    los mismos cuadros, se ve.

    La escribe el conversor con `--pagina-de-prueba` y la corre la referencia
    con la misma función, que es lo que garantiza que sea el mismo programa.

    `mensaje` es el desplazamiento del cuadro de texto en el bloque de la ROM,
    o None si esta página no abre ninguno.

    `frecuencia` es la de las dos rutas —la del héroe y la del evento—, que
    con la 8 caminan seguidas y con otra se paran entre orden y orden.

    `lugar` es (blanco, x, y, espera) para plantar a un evento en una celda
    —OP_LUGAR— después de esperar esos cuadros. Va **entre** la ruta del
    evento y su OP_RUTAS a propósito: con la espera a mitad de un paso, el
    corte del paso que hace `MoveTo` es lo que se ve, y la ruta sigue desde la
    celda nueva.

    `ruta_ev` es (blanco, órdenes) para mandar a caminar a un evento, y detrás
    va un OP_RUTAS. Existe por lo mismo que el resto: **ninguna página del juego
    que compile manda a caminar a un evento sin depender de un switch**, así que
    ese camino no lo ejercitaría nada. Y es filoso por construcción: hasta que
    la ruta no termine, el tinte de más abajo no se aplica, así que el cuadro en
    que la pantalla cambia de color es el cuadro en que la ruta terminó.
    """
    # Lo primero de todo: el switch que la desactiva. Sin esto la página se
    # repetiría mientras siga siendo la activa, que es lo que hace una
    # automática en RM2k; ver `SWITCH_DE_PRUEBA`.
    #
    # Va al principio y no al final por una razón de tiempo, no de gusto: el
    # refresco que dispara le apaga el `FLAG_AUTO` antes de que la página
    # termine, así que cuando termina no queda nada por hacer. Al final, en
    # cambio, el evento seguía marcado en ese mismo cuadro y la ROM volvía a
    # resolver su página activa —una recorrida entera de las páginas del mapa—
    # justo ahí, y perdía el cuadro. La página que corre no se entera del
    # cambio: su código está en la ROM y el cursor es suyo, igual que en RM2k.
    codigo = bytes([OP_SWITCH, SWITCH_DE_PRUEBA & 0xFF,
                    SWITCH_DE_PRUEBA >> 8, 1])
    if lluvia is not None:
        # La fuerza de un WeatherEffects de lluvia, de 0 a 2. La única que
        # llueve en el juego es la apertura, y ahí la cámara no se mueve: sin
        # esto nada miraría que las gotas van pegadas al mapa.
        codigo += bytes([OP_CLIMA, CLIMA_LLUVIA, lluvia])
    if timer:
        # (segundos, visible). El cronómetro del juego lo prende una página que
        # no compila —la del despertador del pad—, así que sin esto no habría
        # con qué comparar: es el mismo motivo por el que existe el resto de
        # esta página.
        segundos, visible = timer
        codigo += bytes([OP_TIMER, TIMER_PONER,
                         segundos & 0xFF, segundos >> 8, 0])
        codigo += bytes([OP_TIMER, TIMER_ARRANCAR, 0, 0, 1 if visible else 0])
    for numero in switches:
        # Prender switches a mano pone al mundo en un estado al que el juego
        # llega más tarde. Hace falta para probar lo que depende de ellos sin
        # jugar hasta ahí: todas las páginas del pad de Talan piden el 24, que
        # prende la cinemática de apertura.
        codigo += bytes([OP_SWITCH, numero & 0xFF, numero >> 8, 1])
    if rama:
        # (switch, adentro, después): una rama de verdad, con la condición
        # decidida por un switch que esta misma página prendió arriba. Existe
        # por lo mismo que el resto: ninguna página del juego que use
        # `ConditionalBranch` prende antes el switch que la decide, así que no
        # hay ninguna donde se pueda elegir qué rama se toma. Sin eso, la rama
        # que **corre** no la ejercita nada; sólo la que se saltea.
        #
        # Compila a lo mismo que compilaría el juego —`OP_SI` y `OP_IR`, con el
        # destino puesto por el mismo parcheo— porque sale del mismo camino:
        # se arma la lista de comandos y la compila `compilar_pagina`.
        cual, adentro, despues = rama
        # El destino es el mismo que pondría `compilar_pagina` al cerrar la
        # rama: después del `OP_SI` —siete bytes desde que lleva la clase de
        # condición adelante— y del `OP_SWITCH` de adentro —cuatro—. Acá se
        # calcula a mano porque esta página no sale de comandos de RM2k, así que
        # no pasa por el parcheo; el bytecode que resulta es el mismo byte por
        # byte, que es lo que hace que pruebe algo.
        destino = len(codigo) + LARGO_DE_OPCODE[OP_SI] + 4
        codigo += bytes([OP_SI, COND_SWITCH, cual & 0xFF, cual >> 8, 0,
                         destino & 0xFF, destino >> 8])
        codigo += bytes([OP_SWITCH, adentro & 0xFF, adentro >> 8, 1])
        codigo += bytes([OP_SWITCH, despues & 0xFF, despues >> 8, 1])
    if fundir_bgm:
        # Los milisegundos de un `FadeOutBGM`. Va primero de todo para que el
        # fundido arranque en el cuadro cero y se lo pueda medir contra el
        # reloj; y existe por lo mismo que el resto de esta página: **ninguna
        # página del juego que hoy compile apaga la música**, así que el camino
        # no lo ejercitaría nada. La que va a ejercitarlo —la puerta del mapa
        # 3— es de tecla y no automática, y encima su mapa no tiene tema
        # propio, así que no hay con qué oírla.
        paso = paso_de_fundido(fundir_bgm)
        codigo += bytes([OP_FUNDIR_BGM, paso & 0xFF, paso >> 8])
    if ruta:
        if any(o in RUTA_HEROE_AFUERA for o in ruta):
            # Acá **sí** se corta en vez de tirarlas. Una ruta escrita a mano
            # con `--ruta-de-prueba` es una prueba: si se tiraran en silencio,
            # el caso mediría otra cosa que la que dice su línea.
            raise NoSePuede("el héroe no fija la mirada ni cambia de velocidad")
        if any(o in RUTA_DIAGONALES for o in ruta):
            # El mismo corte que hace `traducir` con un MoveEvent del juego: la
            # ROM camina las diagonales sobre eventos y no sobre el héroe.
            raise NoSePuede("el héroe no camina en diagonal")
        codigo += bytes([OP_RUTA, 0, frecuencia, len(ruta)]) + bytes(ruta)
    if flash:
        # (blanco, r, g, b, potencia, cuadros). Existe por lo mismo que todo lo
        # demás de esta página: ninguna del juego que compile destella sin
        # depender de un switch.
        codigo += bytes([OP_FLASH]) + bytes(flash)
    if destello:
        # (r, g, b, potencia, cuadros): `FlashScreen`, que es **otra cosa** que
        # el de arriba. Aquél tiñe la paleta de un personaje; éste pasa las tres
        # paletas del mapa por las tablas del destello. Ninguna página del juego
        # que compile lo usa sin depender de un switch, y hasta que apareció el
        # relámpago de la apertura —una paralela— este camino no lo corría nadie:
        # así sobrevivió el `lda #0` de `destellar_fondo`.
        codigo += bytes([OP_DESTELLO]) + bytes(destello)
    if animacion:
        # (animación, objetivo, esperar): un `ShowBattleAnimation` compilado
        # por el mismo camino que el juego. Existe por lo mismo que el resto:
        # la escena del Emitter Room, que es la que las usa, no se puede
        # disparar desde una prueba —ver ESTADO—.
        #
        # El objetivo puede ser el héroe o **un evento del mapa**, y eso desde
        # el 2026-09-12, con el dibujo: la animación sobre un evento sale por
        # otro camino de la ROM —`npc_de_evento`, la fila del NPC— que sobre el
        # héroe no se toca. Por eso `eventos_mapa`: sin él un objetivo que no
        # sea el héroe no compila y la prueba no probaría nada.
        import lcf
        codigo += _compilar(lcf.EventCommand(
            SHOW_BATTLE_ANIMATION, 0, "", list(animacion) + [0]), None,
            eventos_mapa=eventos_mapa)
    if ruta_ev:
        blanco, ordenes = ruta_ev
        codigo += (bytes([OP_RUTA, blanco, frecuencia, len(ordenes)])
                   + bytes(ordenes))
    if lugar:
        blanco, x, y, cuadros = lugar
        if cuadros:
            codigo += bytes([OP_ESPERAR, cuadros & 0xFF, cuadros >> 8])
        codigo += bytes([OP_LUGAR, blanco, x & 0xFF, x >> 8, y & 0xFF, y >> 8])
    if ruta_ev:
        codigo += bytes([OP_RUTAS])
    if pan:
        # Uno o más (operación, dirección, distancia, velocidad, esperar): lo
        # mismo que compila un PanScreen del juego. Existe por lo mismo que el
        # resto de esta página: ninguna de las que hoy compilan corre la
        # cámara, y la que va a hacerlo —la escena de Talan— tiene otros tres
        # comandos que todavía la cortan. Van varios para poder correr la
        # cámara y **devolverla**, que es la otra operación que el juego usa.
        for k in range(0, len(pan), 5):
            codigo += bytes_de_pan(*pan[k:k + 5])
    if sacudida:
        # (fuerza, velocidad, décimas, esperar): lo mismo que compila un
        # ShakeScreen del juego. Con esperar, el tinte de más abajo recién se
        # aplica cuando la sacudida termina, que es lo que la hace filosa.
        fuerza, velocidad, decimas, esperar = sacudida
        cuadros = decimas * CUADROS_POR_DECIMA
        codigo += bytes([OP_SACUDIR, fuerza, velocidad,
                         cuadros & 0xFF, cuadros >> 8])
        if cuadros and esperar:
            codigo += bytes([OP_ESPERAR, cuadros & 0xFF, cuadros >> 8])
    if mensaje is not None:
        # El mensaje va antes de la espera y del tinte a propósito: bloquea, así
        # que lo que venga después es lo que prueba que la página **siguió**
        # cuando se apretó A. Con el tinte detrás, antes de apretar la pantalla
        # está sin teñir y después está teñida, igual que en `snes-espera`.
        codigo += bytes([OP_MENSAJE, mensaje & 0xFF, mensaje >> 8])
    if espera:
        codigo += bytes([OP_ESPERAR, espera & 0xFF, espera >> 8])
    if variables:
        # ControlVars, de a cinco números —variable, operación, clase, a, b—
        # con los mismos números de RM2k, y compilados por el mismo camino que
        # el juego: el mismo `_compilar` con un comando armado a mano.
        import lcf
        for k in range(0, len(variables), 5):
            v, operacion, clase, a, b = variables[k:k + 5]
            if operacion == VARIABLES_PRUEBA_AL_TIMER:
                # La operación inventada de la página de prueba: los segundos
                # del cronómetro desde la variable, que en RM2k es un
                # TimerOperation y no un ControlVars. Va en la misma lista
                # para no abrir otro flag por una sola cosa.
                codigo += _compilar(lcf.EventCommand(
                    TIMER_OPERATION, 0, "", [TIMER_PONER, 1, v, 0, 0]), None)
                continue
            codigo += _compilar(lcf.EventCommand(
                CONTROL_VARS, 0, "", [0, v, v, operacion, clase, a, b]), None)
    if items:
        # ChangeItems, de a dos números —ítem y cuánto, con signo— por el
        # mismo `_compilar` que el juego.
        import lcf
        for k in range(0, len(items), 2):
            numero, cuanto = items[k:k + 2]
            codigo += _compilar(lcf.EventCommand(
                CHANGE_ITEMS, 0, "", [1 if cuanto < 0 else 0, 0, numero, 0,
                                      abs(cuanto)]), None)
    if acceso:
        # ChangeSaveAccess y ChangeMainMenuAccess, de a dos números —cuál, 0
        # guardar y 1 el menú, y si queda permitido—, por el mismo camino.
        import lcf
        for k in range(0, len(acceso), 2):
            cual, permitido = acceso[k:k + 2]
            codigo += _compilar(lcf.EventCommand(
                CHANGE_SAVE_ACCESS if cual == ACCESO_GUARDAR
                else CHANGE_MENU_ACCESS, 0, "", [permitido]), None)
    if rama_var:
        # (variable, comparación, valor, adentro, después): la rama por
        # variable, como `rama` pero con OP_SI_VAR. Existe porque en los mapas
        # 1 a 10 la única página que compara una variable es el Tram Officer, y
        # ahí el valor sale de un azar.
        import lcf
        v, comparacion, valor, adentro, despues = rama_var
        destino = len(codigo) + LARGO_DE_OPCODE[OP_SI_VAR] + 4
        codigo += con_destino(bytes_de_rama(lcf.EventCommand(
            COND_RAMA, 0, "", [COND_VARIABLE, v, 0, valor, comparacion, 0])),
            destino)
        codigo += bytes([OP_SWITCH, adentro & 0xFF, adentro >> 8, 1])
        codigo += bytes([OP_SWITCH, despues & 0xFF, despues >> 8, 1])
    if guardar:
        # Guardar la partida. El save point del mapa 8 es el único evento del
        # juego que lo pide, y está en un mapa que las pruebas no llevan; sin
        # esto `OP_GUARDAR` sería un camino que no ejercita nada, que es
        # exactamente cómo sobrevivieron los tres errores del intérprete.
        #
        # Va **después de la espera** a propósito: así la prueba puede mover la
        # partida —irse a otro mapa, caminar— mientras la página espera, y lo
        # que se guarda no es el estado del arranque. Guardando el del arranque,
        # cargar y no cargar dan lo mismo y la prueba no prueba nada.
        codigo += bytes([OP_GUARDAR])
    if tinte:
        # (r, g, b) y, si viene, la saturación; si no, la neutra.
        codigo += bytes([OP_TINTE]) + bytes(tinte[:3])
        codigo += bytes([tinte[3] if len(tinte) > 3 else TINTE_NEUTRO])
    return codigo + bytes([OP_FIN])


# Cuántas páginas se pueden arrancar encadenadas en un mismo cuadro. En RM2k el
# tope no es de páginas sino de comandos —`loop_limit = 10000` en
# `game_interpreter.h`— repartido entre todas las que arranquen en el cuadro.
# Acá se cuenta por página, que es más grueso: sólo se nota con una página que
# termine sin hacer nada y vuelva a activarse, o sea la que en RM2k cuelga el
# juego. El número tiene que ser el mismo que `ARRANQUES_MAX` en la ROM.
ARRANQUES_MAX = 8


class Interprete:
    """El intérprete corriendo, con su cursor y su espera, cuadro a cuadro.

    Antes esto era una sola pasada: la página entera se ejecutaba de golpe, con
    la pantalla apagada mientras se cargaba el mapa, y las esperas se salteaban.
    Eso colapsaba el tiempo. Todo lo que en RM2k pasa *durante* una página —una
    espera de seis segundos, un NPC caminando su ruta, un fundido— no existía:
    quedaba nada más el estado final. Y como el 46% de las páginas automáticas
    del juego terminan en un teletransporte, lo que ocurría antes del salto era
    además imposible de verificar, porque el cuadro que se compara ya está en el
    mapa de destino.

    Ahora avanza un cuadro por vuelta, igual que `eventos_tick` en la ROM:
    ejecuta opcodes hasta toparse con una espera o con un teletransporte, y ahí
    devuelve el control.
    """

    def __init__(self, paginas, estado):
        self.estado = estado
        # Qué eventos tienen una página esperando turno. Es el
        # `waiting_execution` de EasyRPG y el `ev_flags` de la ROM: un evento,
        # no un puntero, y por eso no puede entrar dos veces.
        #
        # Antes esto era una cola armada **una sola vez acá**, con las páginas
        # automáticas activas al cargar el mapa. Una que se volvía activa
        # después —porque una página prendió su switch— no arrancaba nunca, y
        # como la ROM hacía lo mismo la comparación daba cero. Con eso quedaba
        # muerta la segunda mitad del recuerdo de CORE y MANTA, que prende su
        # switch recién después de aterrizar en el mapa.
        self.esperando_ev = set()
        self.paginas = paginas
        self.eventos = sorted({p["evento"] for p in paginas})
        # Los eventos que tienen **alguna** página automática que compiló. Son
        # los únicos a los que un refresco les puede sacar o poner la marca, y
        # es el bit 7 que el conversor le pone a sus páginas para que la ROM
        # sepa a quiénes mirar sin leerlas todas.
        self.eventos_auto = {p["evento"] for p in paginas
                             if p["trigger"] == TRIGGER_AUTOMATICO
                             and p["codigo"]}
        # Los paralelos **no** se arman acá: son del mapa y viven en el estado,
        # que sobrevive a los intérpretes. Ver `Estado.entrar_a_un_mapa`.
        self.codigo = None
        self.cursor = 0
        self.esperando = 0

    def pendiente(self):
        """La página que está corriendo, para que sobreviva a un teletransporte.

        En RM2k el salto no reinicia nada: `CommandTeleport` hace `index++` y
        devuelve false, así que la misma página retoma en el comando siguiente
        una vez cambiado el mapa. El código vive en el cartucho, que no se mueve.
        """
        if self.codigo is None:
            return None
        return (self.codigo, self.cursor, self.esperando)

    def retomar(self, pendiente):
        """Vuelve a poner la página que venía corriendo antes del salto."""
        self.codigo, self.cursor, self.esperando = pendiente

    def ocupado(self):
        """Si hay una página corriendo o esperando su turno."""
        return self.codigo is not None or bool(self.esperando_ev)

    def probar_accion(self, x, y, mirando, estado):
        """La tecla de acción: la celda propia y la de adelante.

        Las dos están en `Game_Player::CheckActionEvent`, y **cada una pide la
        capa contraria**: la propia es `CheckEventTriggerHere`, que pide
        `GetLayer() != Layers_same`, y la de adelante es
        `CheckEventTriggerThere`, que pide `== Layers_same`. Tiene sentido: un
        evento de la capa del héroe le cierra el paso, así que nunca llegaría a
        pararse encima.

        El orden es el de allá —primero la propia— y se prueban las dos, que es
        lo que hace el `result |=`.

        Lo de "hasta tres mostradores" no está: son las celdas de tipo counter,
        que dejan hablar del otro lado de un mostrador.
        """
        propia = self.probar_celda(x, y, TRIGGER_ACCION, estado,
                                   capa_propia=True, heroe=(x, y))
        dx, dy = RUTA_PASOS[mirando]
        adelante = self.probar_celda(x + dx, y + dy, TRIGGER_ACCION, estado,
                                     capa_propia=False, heroe=(x, y))
        return propia or adelante

    def probar_contacto(self, x, y, estado):
        """El contacto: el evento de la celda que el héroe acaba de pisar.

        Es `CheckEventTriggerHere` desde `Game_Player::UpdateMovement`, que
        corre cuando el paso termina.
        """
        return self.probar_celda(x, y, TRIGGER_TOCA_HEROE, estado,
                                 heroe=(x, y))

    def probar_celda(self, x, y, trigger, estado, capa_propia=None,
                     heroe=None):
        """Encola la página activa del evento de esa celda si la dispara eso.

        `capa_propia` dice cuál de las dos reglas de capa se aplica: `True` es
        la celda del héroe, que pide una capa **distinta** de la suya, y `False`
        la de adelante, que pide la **suya**. `None` no mira la capa, que es lo
        que hace el contacto.
        """
        indice = estado.evento_en((x, y))
        if indice is None:
            return False
        pagina = pagina_activa(self.paginas, indice, estado)
        if pagina is not None and capa_propia is not None:
            if (pagina["capa"] == LAYER_MISMA) == capa_propia:
                return False
        if (pagina is not None and pagina["trigger"] == trigger
                and pagina["codigo"]):
            self.esperando_ev.add(indice)
            if heroe is not None:
                estado.girar(indice, pagina, (x, y), heroe)
            return True
        return False

    def refrescar_y_remarcar(self, eligiendo):
        """Un refresco, y las marcas que deja.

        Es `Game_Event::RefreshPage`: al rehacer la página activa, el evento
        que se queda sin una automática pierde la marca —incluido el que se
        queda sin página del todo, que es el
        `ClearWaitingForegroundExecution` del `if (!new_page)`— y el que la
        conserva la mantiene. Sin lo primero, una página que acaba de terminar
        volvía a arrancar en el mismo cuadro: en la cinemática de apertura eso
        reiniciaba la escena entera.
        """
        antes = self.estado.refresco
        if eligiendo:
            self.estado.refrescar_eligiendo()
        else:
            self.estado.refrescar()
        if antes:
            self.esperando_ev -= self.eventos_auto
            self.esperando_ev |= set(self.automaticos())

    def automaticos(self):
        """Los eventos cuya página activa es una automática que compiló.

        Es `Game_Event::CheckEventAutostart`, que RM2k pregunta **cada cuadro**
        y para todos los eventos. La respuesta sólo cambia cuando cambia la
        página activa —o sea en un refresco— así que la ROM la guarda en el bit
        `FLAG_AUTO` de `ev_flags` y la rehace ahí; acá se recalcula, que sale
        igual porque `pagina_activa` lee la instantánea.
        """
        salida = []
        for evento in self.eventos:
            pagina = pagina_activa(self.paginas, evento, self.estado)
            if (pagina is not None
                    and pagina["trigger"] == TRIGGER_AUTOMATICO
                    and pagina["codigo"]):
                salida.append(evento)
        return salida

    def cuadro_de_paralelos(self, mover_evento=None):
        """Un cuadro de cada evento con página paralela, **y su paso detrás**.

        `Game_Event::Update` corre el intérprete paralelo del evento y a
        continuación llama a `Game_Character::Update()`, o sea que lo mueve
        —easyrpg, `game_event.cpp:580`—, y `UpdateMapEvents` hace eso evento por
        evento. No es lo mismo que correr todos los intérpretes y después mover
        a todos, y la diferencia se ve cuando una página paralela le fuerza una
        ruta a **otro** evento: en Lashe City el `Car4` le pisa la suya al
        `Car2` en cada cuadro, y con los pasos todos al final el pisotón gana y
        el `Car2` no camina nunca. En EasyRPG y en el RPG Maker original los
        cuatro autos andan.

        `mover_evento` es quien sabe dar ese paso: lo pone el que arma el cuadro,
        que es el único que tiene la pasabilidad del mapa. Sin él —los lazos que
        no dibujan— se corre como antes y los pasos van todos al final.
        """
        self.estado.cuadro_de_paralelos(self.paginas, mover_evento)

    def _arrancar(self):
        """La página del primer evento que espere. False si no hay ninguna.

        El orden es por número de evento, que es el mismo en que
        `Game_Map::Update` recorre `events`. La página se resuelve **acá** y no
        cuando se marcó el evento: entre una cosa y la otra pudo haber un
        refresco y ser otra la activa.
        """
        while self.esperando_ev:
            evento = min(self.esperando_ev)
            # Se desmarca sepa o no correrse, igual que el
            # `ClearWaitingForegroundExecution` de `Game_Map::Update`. Si es
            # automática, el barrido del cuadro que viene la vuelve a marcar.
            self.esperando_ev.discard(evento)
            pagina = pagina_activa(self.paginas, evento, self.estado)
            if pagina is not None and pagina["codigo"]:
                self.codigo, self.cursor = pagina["codigo"], 0
                self.evento_corriendo = evento
                return True
        return False

    @property
    def terminado(self):
        # También las automáticas que el barrido del cuadro que viene va a
        # marcar: sin eso esto decía "terminado" en el cuadro en que una página
        # prende el switch que activa a otra, y los lazos que lo miran cortaban
        # justo antes de que arrancara.
        # Y tampoco con un refresco pendiente: la página que acaba de terminar
        # pudo prender el switch que activa a otra, y `automaticos` lee la
        # instantánea, que recién se rehace en el refresco del cuadro que viene.
        return (self.codigo is None and not self.esperando_ev
                and not self.estado.refresco and not self.automaticos())

    def cuadro(self, apreto_a=False, mover_evento=None):
        """Avanza un cuadro. Devuelve True si en éste se pidió un salto.

        `apreto_a` es que el jugador **acaba de** apretar A en este cuadro, no
        que lo tenga apretado: RM2k cierra el mensaje con `IsTriggered`, o sea
        con el flanco. En la ROM eso es `pad_a` contra `pad_a_ant`.

        **El refresco pendiente se hace acá**, arriba de todo, que es donde lo
        hace `Game_Map::Update`: `if (GetNeedRefresh()) Refresh();` y recién
        después los intérpretes y el héroe. Estaba en los lazos que llaman acá,
        y uno de ellos no lo llamaba nunca después de prender un switch: la
        página activa quedaba sin rehacer y nadie se enteraba porque se
        calculaba viva. Un solo lugar es lo que hace que no vuelva a pasar.
        """
        self.refrescar_y_remarcar(eligiendo=False)
        # `Game_Event::CheckEventAutostart`, cada cuadro y para todos. Que
        # corra **también mientras la página de ese evento está corriendo** es
        # lo que hace que una automática se repita al terminar, mientras siga
        # siendo la activa; la que apaga su propia condición no se repite,
        # porque el refresco la saca de la lista.
        #
        # Va **antes** del intérprete, que es el orden de `Game_Map::Update`:
        # una página que se vuelve activa en medio de otra arranca recién en el
        # cuadro siguiente. La ROM se saltea el lazo cuando no hay ninguna
        # automática activa —lleva la cuenta en `auto_n`—; acá el lazo no
        # cuesta nada y se deja el que se lee igual que la fuente.
        self.esperando_ev.update(self.automaticos())
        # Los paralelos, **antes** del héroe y antes del mensaje: en
        # `Game_Map::Update` el orden es refresco, `UpdateMapEvents`,
        # `game_player->Update()`, `UpdateMessage` y recién ahí
        # `UpdateForegroundEvents`. O sea que un evento paralelo sigue
        # corriendo con un cuadro de texto abierto y con otra página en curso,
        # que es justo para lo que existe.
        self.cuadro_de_paralelos(mover_evento)
        if self.estado.mensaje is not None:
            if not apreto_a:
                return False
            # Se cierra y la página sigue **en el mismo cuadro**, que es lo que
            # hace la ROM: `eventos_tick` limpia `msg_abierto` y cae en el
            # `jsr correr_codigo` de siempre. Cerrar acá y seguir el cuadro
            # siguiente sería un cuadro de diferencia entre los dos lados.
            self.estado.mensaje = None
            if self.estado.eleccion is not None:
                # Si lo que estaba abierto era una elección, A no retoma la
                # página donde quedó: la manda al cuerpo de la opción marcada.
                #
                # **Acá el cursor siempre está en la primera opción**, y no es
                # una simplificación escondida: la tanda de pixeles sólo sabe
                # apretar A, así que mover el cursor es un camino que no puede
                # ejercitar. Modelarlo igual sería escribir de este lado código
                # que ninguna prueba corre, que es la manera en que este repo ya
                # se equivocó tres veces. Moverlo lo hace la ROM y lo cubre una
                # prueba de estado, que sí puede apretar abajo; ver
                # `pruebas/test_elegir.py` y "Lo que la tanda no cubre".
                eleccion = self.estado.eleccion
                self.estado.eleccion = None
                self.cursor = eleccion["destinos"][eleccion["sel"]]
        if self.esperando == ESPERAR_RUTAS:
            if self.estado.rutas_pendientes():
                return False
            self.esperando = 0
        elif self.esperando:
            self.esperando -= 1
            return False
        # El `while (!interp.IsRunning())` de
        # `Game_Map::UpdateForegroundEvents`: una página que termina deja
        # arrancar a la que siga esperando **en este mismo cuadro**.
        arranques = ARRANQUES_MAX
        while True:
            if self.codigo is None and not self._arrancar():
                return False
            corte = ejecutar(self.codigo, self.estado, self.cursor)
            # El refresco pendiente, al salir del intérprete: es el
            # `if (Game_Map::GetNeedRefresh()) Game_Map::Refresh();` del final
            # de `Game_Interpreter::Update`. De él depende que el idioma de
            # RM2k funcione: la página que prende el switch que la desactiva
            # deja de ser la activa antes de que se decida qué corre después.
            # Sin esto, al terminar seguía pareciendo automática y volvía a
            # arrancar en el mismo cuadro.
            self.refrescar_y_remarcar(eligiendo=True)
            if corte is None:               # la página terminó
                self.codigo = None
                # Y el evento que giraba vuelve a su pose, si era el suyo: el
                # `UpdateFacing` de `OnFinishForegroundEvent`.
                giro = self.estado.giro
                if (giro is not None
                        and giro["evento"] == getattr(self, "evento_corriendo",
                                                      None)):
                    self.estado.giro = None
                arranques -= 1
                if not arranques:
                    return False
                continue
            self.cursor, self.esperando, salto = corte
            return salto


def paralelos_del_mapa(paginas):
    """Un intérprete paralelo por evento con página paralela que compiló.

    Van por el **mismo** bit 7 que las automáticas: en la ROM ese bit quiere
    decir "mirale las páginas a este evento en el refresco", y quién es
    automática y quién paralela lo dice el trigger de la página que gane. Ver
    `tabla_de_paginas` en snes_convert.py.
    """
    return [Paralelo(evento) for evento in
            sorted({p["evento"] for p in paginas
                    if p["trigger"] == TRIGGER_PARALELO and p["codigo"]})]


class Paralelo:
    """El intérprete de un evento con página paralela.

    Es `Game_Event::Update`: corre **todos los cuadros**, aparte del de primer
    plano y sin que le importe si hay un mensaje abierto o una página corriendo.
    Y cuando su página termina, la vuelve a empezar: RPG_RT hace el `Push` justo
    antes de cada `Update` si el intérprete no está corriendo, así que una
    página que se agota en un cuadro se reinicia al siguiente para siempre.

    Su estado —dónde va y cuánto le falta esperar— es del **evento**, no de una
    ranura: si la página activa cambia, RM2k rehace el intérprete, así que acá
    se compara contra la que estaba y se arranca de cero.
    """

    def __init__(self, evento):
        self.evento = evento
        self.pagina = None          # la que estaba, para notar el cambio
        self.cursor = 0
        self.esperando = 0
        self.corriendo = False

    def cuadro(self, pagina, estado):
        """Un cuadro de este evento. `pagina` es su página activa, o None."""
        if pagina is None or not pagina["codigo"]:
            self.pagina = pagina
            self.corriendo = False
            self.cursor = self.esperando = 0
            return
        if pagina is not self.pagina:
            # `Game_Event::Setup`: otra página, otro intérprete.
            self.pagina = pagina
            self.corriendo = False
            self.cursor = self.esperando = 0
        if self.esperando == ESPERAR_RUTAS:
            if estado.rutas_pendientes():
                return
            self.esperando = 0
        elif self.esperando:
            self.esperando -= 1
            return
        if not self.corriendo:
            self.cursor = 0
            self.corriendo = True
        corte = ejecutar(pagina["codigo"], estado, self.cursor)
        if corte is None:
            # Terminó. No se reinicia en este mismo cuadro: el `Push` de RPG_RT
            # corre una vez por `Update`, así que le toca al que viene.
            self.corriendo = False
            self.cursor = self.esperando = 0
            return
        self.cursor, self.esperando, _salto = corte


def correr_automaticos(paginas, estado, cuadros=100000, avanzar=None,
                       mover_evento=None):
    """Corre las páginas automáticas del mapa hasta que pidan un salto.

    Atajo para quien no necesita mirar el tiempo: adelanta cuadros hasta que el
    intérprete pida mudarse o se quede sin páginas. Lo que sí mira el tiempo
    —la referencia de la pantalla— usa `Interprete` directamente.

    El salto pendiente se borra al entrar, que es el `stz salto_hay` de la ROM:
    sin eso, el primer mapa que teletransporta dejaría el salto puesto y el
    mapa de destino saldría saltando de nuevo al mismo lado sin haber corrido
    ningún evento.
    """
    estado.salto = None
    interprete = Interprete(paginas, estado)
    for _ in range(cuadros):
        # `mover_evento` va sí o sí cuando el mapa tiene eventos que caminan
        # desde una página paralela: sin él sus intérpretes corren pero nadie
        # les da el paso. Ver `Estado.cuadro_de_paralelos`.
        if interprete.cuadro(mover_evento=mover_evento):
            return estado.salto
        # Las rutas de los eventos avanzan acá porque este lazo es el dueño del
        # tiempo. Sin esto, una página que espere a que terminen —OP_RUTAS— no
        # terminaría nunca: nadie las estaría caminando.
        if avanzar is not None:
            avanzar()
        if interprete.terminado or estado.mensaje is not None:
            # Con un mensaje abierto no hay a quién esperar: acá no hay
            # jugador. Se corta con la ventana en pantalla, que es exactamente
            # lo que hace la consola si nadie aprieta nada. Quien quiera
            # comparar el cierre pasa cuadros y dice en cuál se aprieta A.
            break
    return None


# Lo que `ejecutar` devuelve como "cuántos cuadros esperar" cuando la espera no
# es una cuenta sino una condición: que no quede ninguna ruta forzada corriendo.
# Es un valor aparte y no un número grande para que nadie lo sume por error.
ESPERAR_RUTAS = "rutas"


def ejecutar(codigo, estado, desde=0):
    """Corre la página desde `desde` hasta toparse con una espera o el final.

    Devuelve None si la página terminó, o (cursor, cuadros_a_esperar, salto) si
    hay que devolver el control. Igual que `correr_codigo` en la ROM, que ahora
    también vuelve con el cursor guardado en vez de correr la página entera.
    """
    i = desde
    while i < len(codigo):
        op = codigo[i]
        if op == OP_FIN:
            return None
        if op == OP_SWITCH:
            numero = codigo[i + 1] | (codigo[i + 2] << 8)
            if codigo[i + 3]:
                estado.switches.add(numero)
                estado.refresco = True
            else:
                estado.switches.discard(numero)
                estado.refresco = True
            i += 4
        elif op == OP_SI:
            # `CommandConditionalBranch`: si no se cumple, el cursor se va al
            # `else` o al `end`. El destino es absoluto dentro de la página, así
            # que el salto es la asignación.
            #
            # El tipo es el de RM2k tal cual, y la polaridad quiere decir cosas
            # distintas según cuál sea: en un switch 0 es "prendido" y en el oro
            # 0 es ">=".
            tipo = codigo[i + 1]
            operando = codigo[i + 2] | (codigo[i + 3] << 8)
            polaridad = codigo[i + 4]
            if tipo == COND_SWITCH:
                vale = (operando in estado.switches) == (not polaridad)
            elif tipo == COND_ORO:
                vale = (estado.oro >= operando if not polaridad
                        else estado.oro <= operando)
            elif tipo == COND_ACTOR:
                vale = operando in estado.grupo
            else:
                raise ValueError("condición %d que no conozco" % tipo)
            if vale:
                i += 7
            else:
                i = codigo[i + 5] | (codigo[i + 6] << 8)
        elif op == OP_ACCESO:
            estado.permitido[codigo[i + 1]] = bool(codigo[i + 2])
            i += 3
        elif op == OP_ITEM:
            # `Game_Party::AddItem`: suma y recorta a [0, ITEM_MAX], y pide el
            # refresco, como `CommandChangeItems`. La ROM hace lo mismo en
            # `op_item`.
            numero = codigo[i + 1] | (codigo[i + 2] << 8)
            delta = con_signo_byte(codigo[i + 3])
            estado.items[numero] = max(0, min(ITEM_MAX,
                                              estado.item(numero) + delta))
            estado.refresco = True
            i += 4
        elif op == OP_ORO:
            # `Game_Party::GainGold`: suma y recorta a [0, ORO_MAX].
            monto = (codigo[i + 2] | (codigo[i + 3] << 8)
                     | (codigo[i + 4] << 16))
            estado.oro = max(0, min(ORO_MAX, estado.oro
                                    + (-monto if codigo[i + 1] else monto)))
            i += 5
        elif op == OP_IR:
            i = codigo[i + 1] | (codigo[i + 2] << 8)
        elif op == OP_TELEPORT:
            # El resto de la página sí corre. En
            # `Game_Interpreter_Map::CommandTeleport` el motor reserva el
            # teletransporte, hace `index++` y devuelve false: corta el cuadro,
            # pero retoma en el comando siguiente una vez cambiado el mapa. Acá
            # la página corre entera de una, así que seguir es lo mismo que
            # retomar, y con dos teletransportes gana el último —que es también
            # dónde RM2k deja al héroe—.
            #
            # Lo que este modelo no hace es correr los eventos automáticos del
            # mapa intermedio, que RM2k sí correría entre un teletransporte y el
            # siguiente. En la cinemática de apertura los dos van al mismo mapa,
            # así que no cambia nada; si alguna vez aparece una página que salte
            # entre mapas distintos, esto hay que mirarlo de nuevo.
            estado.salto = (codigo[i + 1],
                            codigo[i + 2] | (codigo[i + 3] << 8),
                            codigo[i + 4] | (codigo[i + 5] << 8))
            # Cuántos fundidos lleva la corrida. No lo usa el intérprete: lo
            # usa el plan de la caminata, que le dice al emulador cuántos
            # cuadros correr y tiene que contar los 70 de cada teletransporte.
            # Se cuenta acá, que es el único lugar por donde pasan todos.
            estado.fundidos += 1
            return (i + 6, 0, True)     # corta el cuadro, como `return false`
        elif op == OP_ESPERAR:
            # Y acá se devuelve el control. Antes se salteaba: "no tenemos
            # cuadros que dejar pasar", decía el comentario, y era cierto
            # mientras la página corriera entera con la pantalla apagada.
            cuadros = codigo[i + 1] | (codigo[i + 2] << 8)
            return (i + 3, cuadros, False)
        elif op == OP_RUTA:
            # La ruta se encola y la camina quien la recibió, no el intérprete:
            # en RM2k `ForceMoveRoute` es asincrónico y la página sigue. Quien
            # la hace avanzar es `cuadro_de_ruta` / `cuadro_de_rutas_ev`, una
            # vez por cuadro. Y encolar pisa lo que hubiera: RM2k sobrescribe la
            # ruta forzada anterior, no la encadena.
            blanco = codigo[i + 1]
            frecuencia = codigo[i + 2]
            cuantos = codigo[i + 3]
            ordenes = list(codigo[i + 4:i + 4 + cuantos])
            ruta = (estado.ruta_heroe if blanco == 0
                    else estado.ruta_de_evento(blanco - 1))
            if blanco:
                estado.giro_por_ruta(blanco - 1)
            ruta.reemplazar(ordenes, frecuencia)
            i += 4 + cuantos
        elif op == OP_FLASH:
            # Empieza un destello. No corta el cuadro: si la página espera, el
            # conversor le pone un OP_ESPERAR detrás, que es lo que hace
            # `CommandFlashSprite` con `SetupWait(tenths)`.
            estado.flashes[codigo[i + 1]] = (codigo[i + 2], codigo[i + 3],
                                             codigo[i + 4], codigo[i + 5],
                                             codigo[i + 6], 0)
            i += 7
        elif op == OP_BGM:
            # La referencia no modela el audio: la comparación es de pixeles. El
            # opcode existe igual porque **ocupa dos bytes** en el bytecode, y
            # los dos lados tienen que recorrer el mismo stream.
            i += 2
        elif op == OP_PAN:
            # `CommandPanScreen`. Mueve el destino y devuelve el control en el
            # mismo cuadro; con `esperar`, la página se queda los cuadros que
            # dice `GetPanWait` sobre lo que falta **después** de moverlo.
            if codigo[i + 1] == PAN_VOLVER:
                estado.pan_dest_x = estado.pan_dest_y = 0
            else:
                estado.pan_dest_x += con_signo(codigo[i + 2]
                                               | (codigo[i + 3] << 8))
                estado.pan_dest_y += con_signo(codigo[i + 4]
                                               | (codigo[i + 5] << 8))
            estado.pan_paso = codigo[i + 6]
            espera = (cuadros_de_pan(estado.pan_falta(), estado.pan_paso)
                      if codigo[i + 7] else 0)
            if espera:
                return (i + 8, espera, False)
            i += 8
        elif op == OP_VAR:
            ranura, operacion, clase = codigo[i + 1], codigo[i + 2], codigo[i + 3]
            a = con_signo(codigo[i + 4] | (codigo[i + 5] << 8))
            b = con_signo(codigo[i + 6] | (codigo[i + 7] << 8))
            if clase == VAR_CONSTANTE:
                valor = a
            elif clase == VAR_VARIABLE:
                valor = estado.variable(a)
            elif clase == VAR_AZAR:
                valor = estado.azar(a, b)
            elif a == OTRO_ORO:
                valor = min(estado.oro, 0x7FFF)
            else:
                valor = estado.timer_cuadros // CUADROS_POR_SEGUNDO
            actual = estado.variable(ranura)
            estado.poner_variable(ranura, valor if operacion == VAR_PONER
                                  else actual + valor if operacion == VAR_SUMAR
                                  else actual - valor)
            # Las páginas con condición por variable pueden cambiar:
            # `SetNeedRefreshForVarChange`, que RM2k hace tras cada
            # ControlVars. La ROM marca `refresco` en `var_pone`.
            estado.refresco = True
            i += 8
        elif op == OP_SI_VAR:
            ranura, clase, comparacion = codigo[i + 1], codigo[i + 2], codigo[i + 3]
            contra = con_signo(codigo[i + 4] | (codigo[i + 5] << 8))
            if clase == VAR_VARIABLE:
                contra = estado.variable(contra)
            if cumple_comparacion(estado.variable(ranura), comparacion,
                                  contra):
                i += 8
            else:
                i = codigo[i + 6] | (codigo[i + 7] << 8)
        elif op == OP_IMAGEN:
            # El cartel se pone con su tono y en el mismo cuadro, como
            # `Game_Pictures::Show`: `time_left` queda en cero.
            estado.poner_imagen(tuple(codigo[i + 1:i + 5]))
            i += 5
        elif op == OP_IMAGEN_MOVER:
            # Y `Move`: el tono al que va y en cuántos cuadros. No cuesta
            # ningún tick; si la página espera, atrás viene un OP_ESPERAR.
            estado.mover_imagen(tuple(codigo[i + 1:i + 5]), codigo[i + 5])
            i += 6
        elif op == OP_IMAGEN_BORRAR:
            estado.imagen = None
            i += 1
        elif op == OP_SONIDO:
            i += 3                  # no se ve y no cuesta ningún tick
        elif op == OP_CLIMA:
            # Como `CommandWeatherEffects`: no cuesta ningún tick.
            estado.poner_clima(codigo[i + 1], codigo[i + 2])
            i += 3
        elif op == OP_TIENDA:
            # La tienda, como guardar: no cuesta ningún tick y de este lado no
            # hay nada que dibujar. Lo que muestra lo cobran `snes-tienda` y
            # `pruebas/test_tienda.py`.
            i += 4 + 2 * codigo[i + 3]
        elif op == OP_GUARDAR:
            # La pantalla de ranuras, y guardar en la que se elija. De este
            # lado no hay nada que guardar —la referencia es un modelo, no una
            # partida— ni nada que dibujar: lo que importa es que el opcode
            # ocupe el mismo byte y **no cueste ningún tick**, que es lo que
            # hace RM2k: `OpenSaveMenu` apila una escena y el reloj del mapa
            # no corre hasta que se cierra. En la ROM la pantalla bloquea
            # adentro del intérprete y `vueltas` no avanza mientras se ve, así
            # que en ticks los dos lados siguen leyendo el mismo stream en el
            # mismo cuadro, tarde lo que tarde el jugador en elegir. Lo que la
            # pantalla muestra lo cobra `just snes-guardar` contra
            # `titulo.py --ranuras`, y lo que la ROM escribe,
            # `pruebas/test_guardar.py`.
            i += 1
        elif op == OP_FUNDIR_BGM:
            # Lo mismo que OP_BGM: no se modela el audio, pero el opcode ocupa
            # tres bytes y el stream tiene que ser el mismo de los dos lados.
            # Y tampoco cuesta un cuadro: `CommandFadeOutBGM` devuelve true en
            # el mismo, así que la página sigue de largo.
            i += 3
        elif op == OP_LUGAR:
            # `MoveTo`: la celda cambia ya y el paso en curso se corta. La ruta
            # sigue desde la celda nueva, y hacia dónde mira no cambia.
            estado.mover_evento(codigo[i + 1] - 1,
                                codigo[i + 2] | (codigo[i + 3] << 8),
                                codigo[i + 4] | (codigo[i + 5] << 8))
            i += 6
        elif op == OP_SACUDIR:
            # `ShakeOnce`, que no reinicia la posición —"so that multiple
            # shakes which interrupt each other flow smoothly"—, o `ShakeEnd`
            # con cero cuadros. No corta el cuadro: si la página espera, el
            # conversor le pone un OP_ESPERAR detrás.
            cuadros = codigo[i + 3] | (codigo[i + 4] << 8)
            if cuadros:
                estado.sacudida_fuerza = codigo[i + 1]
                estado.sacudida_vel = codigo[i + 2]
                estado.sacudida_resta = cuadros
            else:
                estado.sacudida_pos = estado.sacudida_resta = 0
            i += 5
        elif op == OP_ANIMACION:
            # La animación nueva reemplaza a la que hubiera; sus entradas las
            # dispara `cuadro_de_animacion`. No cuesta ningún tick.
            n = codigo[i + 3]
            estado.animacion = {
                "entradas": [codigo[i + 4 + ANIM_ENTRADA * j:
                                    i + 4 + ANIM_ENTRADA * (j + 1)]
                             for j in range(n)],
                "t": 0}
            # Y su dibujo, que va por su cuenta: la línea de tiempo se termina
            # con la última entrada y el dibujo dura los dos cuadros por cuadro
            # de RM2k. Cuántos son no está en el bytecode —la ROM los saca de
            # su tabla— así que acá salen de la misma tabla, `ANIMACIONES`.
            estado.empezar_dibujo(codigo[i + 1], codigo[i + 2])
            i += 4 + ANIM_ENTRADA * n
        elif op == OP_DESTELLO:
            # `FlashOnce`: el nivel arranca en la fuerza y baja cuadro a
            # cuadro. No corta el cuadro: si la página espera, el conversor le
            # pone un OP_ESPERAR detrás. Con cero cuadros el primer
            # `cuadro_de_destello` lo apaga sin que se vea.
            estado.destello = (codigo[i + 1], codigo[i + 2], codigo[i + 3])
            estado.destello_nivel = codigo[i + 4] << 8
            estado.destello_resta = codigo[i + 5]
            i += 6
        elif op == OP_TRUEQUE:
            # `CommandTradeEventLocations`: los dos `MoveTo`, con las celdas
            # leídas antes de mover a ninguno.
            a, b = codigo[i + 1] - 1, codigo[i + 2] - 1
            donde_a, donde_b = estado.pos_ev[a], estado.pos_ev[b]
            estado.mover_evento(a, *donde_b)
            estado.mover_evento(b, *donde_a)
            i += 3
        elif op == OP_TIMER:
            # `CommandTimerOperation`. No corta el cuadro: las tres operaciones
            # son asignaciones, y quien hace correr el cronómetro es
            # `cuadro_de_timer`, una vez por cuadro.
            operacion = codigo[i + 1]
            if operacion == TIMER_PONER:
                estado.timer_cuadros = ((codigo[i + 2] | (codigo[i + 3] << 8))
                                        * CUADROS_POR_SEGUNDO
                                        + TIMER_CUADROS_DE_MAS)
            elif operacion == TIMER_PONER_VAR:
                # Una variable negativa pone cero: `Game_Party::SetTimer` topa
                # abajo en cero.
                segundos = max(0, estado.variable(codigo[i + 2]))
                estado.timer_cuadros = (segundos * CUADROS_POR_SEGUNDO
                                        + TIMER_CUADROS_DE_MAS)
            elif operacion == TIMER_ARRANCAR:
                estado.timer_activo = True
                estado.timer_visible = bool(codigo[i + 4])
            else:
                # `StopTimer` apaga las dos cosas, no sólo la cuenta.
                estado.timer_activo = estado.timer_visible = False
            i += 5
        elif op == OP_RUTAS:
            # "Esperá a que terminen las rutas". Se devuelve el control con una
            # marca en vez de una cuenta de cuadros: no se sabe cuántos van a
            # ser, y quien decide es `Interprete.cuadro` mirando si queda alguna
            # pendiente. Si no queda ninguna no cuesta ni un cuadro, que es lo
            # que hace el `while` de `Game_Interpreter::Update`.
            if not estado.rutas_pendientes():
                i += 1
                continue
            return (i + 1, ESPERAR_RUTAS, False)
        elif op == OP_ELEGIR:
            # Abre la ventana con las opciones y corta el cuadro, igual que un
            # mensaje. La diferencia es que la página no retoma donde quedó: el
            # cursor se lo pone `Interprete.cuadro` cuando el jugador elige, y
            # sale del destino de la opción que haya quedado.
            #
            # El cursor arranca en cero, que es `Window_Selectable` con su
            # índice en cero, y la tabla se guarda entera porque de ahí salen
            # los dos: el cuadro que se dibuja y el destino al que se salta.
            n = codigo[i + 1]
            estado.eleccion = {
                "n": n,
                "cancelar": codigo[i + 2],
                "sel": 0,
                "cuadros": [codigo[i + 3 + 4 * k] | (codigo[i + 4 + 4 * k] << 8)
                            for k in range(n)],
                "destinos": [codigo[i + 5 + 4 * k] | (codigo[i + 6 + 4 * k] << 8)
                             for k in range(n)],
            }
            estado.mensaje = estado.eleccion["cuadros"][0]
            return (i, 0, False)
        elif op == OP_MENSAJE:
            # Abre la ventana y corta el cuadro. El cursor queda en el comando
            # siguiente, pero `Interprete.cuadro` no vuelve a llegar acá hasta
            # que alguien apriete A: la página queda bloqueada, que es lo que
            # hace `Game_Message` en RM2k.
            estado.mensaje = codigo[i + 1] | (codigo[i + 2] << 8)
            return (i + 3, 0, False)
        elif op == OP_GRUPO:
            estado.cambiar_grupo(codigo[i + 1], codigo[i + 2])
            i += 3
        elif op == OP_TINTE:
            estado.tinte = (codigo[i + 1], codigo[i + 2], codigo[i + 3],
                            codigo[i + 4])
            estado.tinte_cambio = True      # lo mira `cuadro_de_destello`
            i += 5
        else:
            raise ValueError("opcode %d que no conozco" % op)
    return None


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


def destellar_canal_pantalla(canal, hacia, nivel):
    """Un canal de cinco bits, con el destello de pantalla encima.

    RM2k dibuja el destello como un rectángulo del color pedido con alfa
    `nivel * 8` sobre la pantalla ya compuesta —`Screen::Draw`—, o sea que
    cada canal se acerca al del color en `nivel / 31` del camino. Acá va con
    enteros y sobre cinco bits, y la resta se hace del lado positivo para que
    la división truncada dé lo mismo en la consola, que no tiene signo en el
    divisor.
    """
    if hacia >= canal:
        return canal + (hacia - canal) * nivel // 31
    return canal - (canal - hacia) * nivel // 31


def destellar_pantalla(palabra, color, nivel):
    """Un color de 15 bits con el destello de pantalla encima. `nivel` es la
    parte entera del de `Estado`, de 0 a 31.

    No es `destellar`, que es el destello de **un personaje** —`FlashSprite`—
    y tiene otra cuenta: la primera versión de esto se llamaba igual y la
    tapaba, y la comparación lo cobró con un color de diferencia.
    """
    salida = 0
    for numero, hacia in enumerate(color):
        canal = (palabra >> (numero * 5)) & 0x1F
        salida |= destellar_canal_pantalla(canal, hacia, nivel) << (numero * 5)
    return salida


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


def destellar(palabra, color, nivel):
    """Un color de 15 bits mezclado hacia el del destello.

    Es la cuenta de easyrpg puesta en cinco bits: allá el destello es un color
    con alfa `nivel * 8` compuesto sobre el sprite —`Flash::MakeColor` y el
    `PIXMAN_OP_OVER` de `BlendBlit`— o sea `destino * a + origen * (255 - a)`
    sobre 255. La diferencia es el espacio: RM2k mezcla los ocho bits del PNG y
    nosotros los cinco que entran en CGRAM, así que **el resultado no es el de
    RM2k**, es el que da la misma cuenta con menos bits.

    Está declarado porque es la clase de cosa que la comparación no ve: los dos
    lados hacen lo mismo y dan cero. Lo mismo pasa con el tinte de pantalla, y
    por la misma razón. Quien quiera medirlo necesita una captura de EasyRPG
    tomada durante un destello.
    """
    if nivel <= 0:
        return palabra
    alfa = nivel * 8
    salida = 0
    for numero in range(3):
        canal = (palabra >> (numero * 5)) & 0x1F
        mezcla = (color[numero] * alfa + canal * (255 - alfa)) // 255
        salida |= min(31, mezcla) << (numero * 5)
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
                     graficos=None, imagenes=None):
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
            # mapa era injugable. Lo delató `snes-heroe 21` al tardar catorce
            # minutos, porque la referencia se comía sus 100.000 ticks de
            # `correr_automaticos` antes de empezar a caminar.
            #
            # Se apaga poniéndole el código en None, que es lo que los dos lados
            # ya miran para decidir si una página automática cuenta
            # (`eventos_auto` acá, el bit 7 de la página en el conversor).
            vacia = not page.commands and page.trigger in (TRIGGER_AUTOMATICO,
                                                           TRIGGER_PARALELO)
            if page.trigger in TRIGGERS and puede_dispararse(page) and not vacia:
                codigo = compilar_pagina(page, indice_de_mapa, mensajes,
                                         del_mapa.para(event.id), temas,
                                         graficos, imagenes)
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
                # celda: ver `rm2k.collect_npcs` y `pasabilidad_de_evento`.
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
        if orden not in RUTA_ORDENES or orden == RUTA_ENCARAR_HEROE:
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


def bloqueada(paginas, estado, celda, capa, ignorar=None, heroe=None):
    """Si quien se mueve en la capa `capa` no puede entrar a `celda` porque hay
    alguien parado ahí.

    Es `WouldCollide` de `game_map.cpp`, con lo que este repo modela: dos
    personajes chocan si están en la misma capa, y no chocan si alguno de los
    dos atraviesa paredes. Lo que no se modela es `overlap_forbidden` —17
    páginas del juego— y el conflicto de un evento con gráfico de tile contra
    su propio bloque.

    La celda de cada evento es la de `pos_ev`, que se mueve al **empezar** el
    paso: es `IsInPosition` sobre `GetX()`/`GetY()`, o sea la de destino
    mientras camina. Un evento sin página activa no está —`IsActive()`— y no
    choca con nadie. `ignorar` es el índice del que se mueve, que no choca
    consigo mismo, y `heroe` es la celda del héroe cuando quien se mueve es un
    evento: el héroe está en la capa del medio y frena a los de su capa.
    """
    for indice, donde in estado.pos_ev.items():
        if donde != celda or indice == ignorar:
            continue
        ruta = estado.rutas_ev.get(indice)
        if ruta is not None and ruta.atraviesa:
            continue
        pagina = pagina_activa(paginas, indice, estado)
        if pagina is not None and pagina["capa"] == capa:
            return True
    if heroe is not None and heroe == celda and capa == LAYER_MISMA \
            and not estado.ruta_heroe.atraviesa:
        return True
    return False


def pasabilidad_de_evento(paginas, estado, celda):
    """Los bits de paso que un evento le impone a la celda, o None.

    Es la parte de `Game_Map::IsPassableTile` que mira los eventos: de los
    que están parados en la celda, con página activa, sin atravesar y con
    gráfico de tile en la capa de abajo, gana el de id más alto —el último
    de la tabla—, y si su tile no es de los que van por encima, sus bits
    reemplazan a los del terreno. Lo que no se modela es el "conflicto
    consigo mismo" de un evento de tile que camina: ninguno camina.
    """
    valor = None
    for indice, donde in estado.pos_ev.items():
        if donde != celda:
            continue
        ruta = estado.rutas_ev.get(indice)
        if ruta is not None and ruta.atraviesa:
            continue
        pagina = pagina_activa(paginas, indice, estado)
        if pagina is not None and pagina.get("tile_pasa") is not None:
            valor = pagina["tile_pasa"]
    return valor


def capa_activa(paginas, estado, indice):
    """La capa de la página activa del evento, o None si no tiene ninguna."""
    pagina = pagina_activa(paginas, indice, estado)
    return None if pagina is None else pagina["capa"]
