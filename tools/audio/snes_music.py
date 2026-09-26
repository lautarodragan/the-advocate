"""Convierte el MIDI de un mapa a muestras BRR y un stream para el S-DSP.

Lo que no depende del chip —leer el MIDI y pasar los tiempos a cuadros— está
en midi.py y musica.py; lo del S-DSP, en sdsp.py. Las voces se reparten nota a
nota, las ocho para todos los canales: ver `assign`.

Salen dos cosas: el bloque que se sube a la memoria del SPC700 (el directorio
de muestras más las muestras en BRR) y el stream de cada tema, por nota, que el
65816 expande a escrituras al DSP cuadro a cuadro: ver "el formato por nota". Quien lo llama es el conversor, con
todos los temas del cartucho a la vez: ver `build_varios`.
"""

import collections
import math
import os

from rpgmaker import lcf
from audio import musica
from audio import midi
from audio import muestras_brr
from audio import sdsp
from audio import snes_samples
from audio import spc700
from render.render_map import GAME_DIR, find_resource

TICKS_PER_SECOND = musica.TICKS_PER_SECOND

# Dónde vive cada cosa en los 64 KB del SPC700. Los primeros $200 bytes se los
# queda la ROM de arranque para sus variables, así que se empieza más arriba.
DRIVER_ADDR = 0x0200
SAMPLES_ADDR = 0x0400

BLOQUE = muestras_brr.BLOQUE_MUESTRAS   # 16 muestras por bloque de BRR

# Las muestras van de $0400 hasta el final de los 64 KB —`ARAM_FIN`, más
# abajo—, sin reserva: el eco está apagado —FLG con el bit de "no escribir el
# buffer"— y la pila del SPC700 vive en $0100, o sea debajo. Ahí entra un
# paquete por vez, y es contra eso que se reparte: ver `Banco`.
#
# Y lo que se le deja libre a cada paquete al repartir. El largo de cada
# muestra se redondea a bloques de BRR y el reparto pide por presupuesto, así
# que es holgura para eso; `Banco` comprueba lo que ocupan de verdad contra
# la ARAM sin margen. Con 1 KB es con lo que se midió el paso 6.
ARAM_MARGEN = 1024

# Los opcodes del stream **no se declaran acá**: salen de
# `tools/protocol/music.toml`, que es del que escribe el stream y del que lo lee, y
# de ninguno. Hasta el 2026-09-15 estaban escritos a mano de los dos lados, en
# este archivo y en main.s, sin nada que los atara.
from audio.music_opcodes import *   # noqa: E402,F401,F403


# Los temas que además tienen pista de MSU-1, y con qué número. El MSU-1 no es
# hardware de la consola sino una extensión que soportan el FX Pak Pro y los
# emuladores: la música sale de un archivo PCM al lado de la ROM
# —`<rom>-<pista>.pcm`, habilitado por un `<rom>.msu`— en vez de sintetizarse
# en el SPC700. Cuando el tema tiene pista, la ROM calla el SPC700 y la toca;
# los efectos siguen sonando en el SPC700, así que la ARAM les queda entera.
#
# Es el experimento que pidió taro el 2026-09-11, porque la música
# sintetizada suena fea. Las pistas las arma `tools/audio/msu.py` desde los mismos
# MIDI, con el soundfont con que sonaba el juego original en la PC.
#
# **Son los 21 temas que suenan hasta salir de Lashe City**, que es el alcance
# que pidió taro el 2026-09-14: *"tal vez no sea factible usar PCM para todo,
# pero sí o sí quiero todos los temas que suenan hasta salir de Lashe City"*.
# Los del juego entero son 43 —91 minutos, 923 MB— y ésos entran el día que
# haya una ROM que los toque.
#
# **Los números del 1 al 8 no se tocan nunca**: son los que ya están en la
# tarjeta de taro, y cambiarlos obligaría a renombrar archivos. Por eso los
# catorce que se agregaron el 2026-09-14 van del 9 en adelante y en un orden
# que no dice nada: el orden acá no significa nada para la ROM, que lee
# `tema_msu` por índice de tema.
#
# El del **título** (8) y el de **batalla** (9) no son de ningún mapa: salen de
# `title_music` y `battle_music` del LDB. El de batalla suena en todas las
# peleas y es el más caro del cartucho —226 s y 156.520 B de stream, el doble
# que el siguiente—; que tenga pista es lo que más se oye por tema emitido.
#
# **Lo que NO arregla darle pista al de batalla**, medido el 2026-09-14 porque
# parecía que sí: sacarlo del banco compartido libera 4 muestras y 565 B, sube
# la tasa mediana de 11521 a 12496 Hz y **no devuelve ni un tema** de los nueve
# recortados. Su peso es de stream, que vive en el cartucho, no de ARAM.
#
# Y el tamaño: 16 bits estéreo a 44,1 kHz son 10,6 MB por minuto, así que los
# 21 son unos 423 MB por ROM. Recortarlos por loop tampoco da: de los 21, el
# **único** que repite exacto a la mitad es `C3classi` —medido comparando las
# notas de las dos mitades— y son 8,6 MB de 423.
PISTAS_MSU = {
    "escape_newyork": 1,
    "hzstream": 2,
    "TF3_1_awe": 3,
    "evilrhys": 4,
    "lufsorr": 5,
    "cd4": 6,
    "C3classi": 7,
    "Fantasia_Of_The_Wind": 8,
    "T_VGFighterMAX_Masako": 9,
    "rshinld": 10,
    "cd2": 11,
    "hzbreach": 12,
    "wb3mlair": 13,
    "Astpgmarch": 14,
    "Gaden": 15,
    "3D-Galax": 16,
    "wb3shop": 17,
    "KSSMKEND": 18,
    "vswar": 19,
    "Lunar_Pyramid": 20,
    "dcbest": 21,
    "golden_axe-turtlevillage2": 22,
}


# --- el driver del SPC700 ---------------------------------------------------
# Se queda esperando que el 65816 cambie el testigo del puerto 3 —lo
# incrementa en cada escritura, y el driver se lo devuelve como acuse— y mira
# el puerto 2, que dice qué hacer:
#
#   0  un par (registro, valor) del DSP en los puertos 0 y 1: la música
#   1  un byte del puerto 0 a la ARAM, donde apunta el puntero, que avanza
#   2  el puntero de la ARAM, de los puertos 0 y 1
#   3  un bloque: el puerto 0 dice cuántas ternas vienen —hasta 85, para
#      que el índice Y no pase de un byte—, y después llega una por testigo,
#      en los puertos 0, 1 y 2, detrás del puntero. El puntero no avanza: el
#      65816 lo vuelve a poner antes de cada bloque. Son unos 56 ciclos del
#      SPC700 por terna, unos 55 KB por segundo
#   4  volver a la ROM del IPL: ver abajo. No contesta el acuse, porque para
#      cuando el 65816 lo leería el driver ya no existe
#
# El comando 4 está para **volver a arrancar la ROM**. El 65816 no puede
# resetear al SPC700 —el botón de reset de la consola sí, porque la línea les
# llega a los dos, pero un `jml reset` de adentro del juego no—, así que
# después del Game Over el SPC700 sigue corriendo este driver y el IPL ya no
# está para saludar con $AA/$BB. `spc_upload` se quedaba esperando ese saludo
# **para siempre**, con la pantalla ya encendida y el mapa dibujado: es el
# cuelgue del cofre trampa de los Rat Tracks. Prendiendo el bit 7 de $F1 la
# ROM del IPL vuelve a aparecer en $FFC0 y saltar ahí la arranca de cero, que
# es exactamente lo que ve el 65816 cuando la consola se enciende.
#
# Los tres de la ARAM existen por el paquete de audio de cada mapa: las
# muestras se suben mientras la música suena, así que el driver tiene que
# poder recibirlas sin dejar de atender al DSP. Ver `paquete_cargar` en
# rom/src/paquete_de_audio.s. El puntero y la cuenta viven en $00-$03 de la página cero, que la
# ROM de arranque usa y deja libre.
#
# La música sigue mandando comandos 0 sin tocar el puerto 2: quien sube a la
# ARAM lo deja en cero antes de soltar el bus, que es lo que hace que nada del
# stream haya tenido que cambiar.

DRIVER = """
    mov x, $F7          ; arrancar con el testigo que ya esté, sin disparar
espera:
    cmp x, $F7
    beq espera
    mov x, $F7
    mov a, $F6          ; el comando
    bne no_dsp
    mov a, $F4          ; registro del DSP
    mov $F2, a
    mov a, $F5          ; el valor que va en ese registro
    mov $F3, a
    mov $F7, x          ; acusar recibo devolviendo el testigo
    bra espera
no_dsp:
    cmp a, #$01
    bne no_byte
    mov a, $F4
    mov y, #$00
    mov [$00]+y, a
    incw $00
    mov $F7, x
    bra espera
no_byte:
    cmp a, #$02
    bne no_puntero
    mov a, $F4
    mov $00, a
    mov a, $F5
    mov $01, a
    mov $F7, x
    bra espera
no_puntero:
    cmp a, #$04
    bne bloque
    mov a, #$80         ; la ROM del IPL, de vuelta en $FFC0
    mov $F1, a
    jmp !$FFC0
bloque:
    mov a, $F4
    mov $02, a
    mov $F7, x
    mov y, #$00
terna:
    cmp x, $F7
    beq terna
    mov x, $F7
    mov a, $F4
    mov [$00]+y, a
    inc y
    mov a, $F5
    mov [$00]+y, a
    inc y
    mov a, $F6
    mov [$00]+y, a
    inc y
    mov $F7, x
    dec $02
    bne terna
    bra espera
"""


# --- muestras ---------------------------------------------------------------

# --- los efectos de sonido -------------------------------------------------
#
# Los WAV de `PlaySound` —del juego o del RTP—, en la misma ARAM que el banco
# de la música, con **lo que la música deja libre** y hasta `SE_ARAM`: la
# música va primero. El primer intento les reservaba 16 KB y se los sacaba a
# la percusión, que es la que se queda con lo que sobra, y el banco de la
# demo bajó de 44 muestras a 22. La demo pide 38 efectos que suman más de 40
# segundos, y eso no entra a ninguna calidad razonable, así que se eligen:
# primero los que piden los primeros mapas de la ROM, a `SE_TASA`, recortados a
# `SE_MAX_SEGUNDOS`; uno más largo repite sus últimos `SE_LOOP_SEGUNDOS`
# hasta durar lo que dura en RM2k —la lluvia de la apertura son cinco
# segundos de ruido, y así se la oye entera—. Los que no entran no suenan, y
# el conversor lo dice.
SE_ARAM = 16 * 1024
SE_TASA = 6000
SE_MAX_SEGUNDOS = 0.75           # desde el paquete por mapa: ver `paquete_cargar`
SE_LOOP_SEGUNDOS = 0.4
SE_VOZ = 7                      # la que se le roba a la música
# Y la segunda, para que dos efectos suenen a la vez —la lluvia y el trueno de
# la apertura—, como en RM2k. Las dos son las que el reparto de la música
# llena primero con la percusión: ver `VOCES_DE_EFECTOS`.
SE_VOZ2 = 6
# Los que van enteros, sin tope ni bucle, a la tasa que dice cada uno:
# terminan cuando termina la muestra, que es lo que hacen en RM2k. Con el
# tope, el trueno repetía sus 0,35–0,75 s hasta cumplir los cuadros y taro lo
# oyó tartamudear: `decisiones/el-trueno-va-entero-a-22-khz.md`.
#
# **Lo que un efecto entero ocupa de más no le cuesta nada a la música**: el
# banco se reparte contando cada efecto como si no estuviera acá, y lo de más
# tiene que entrar en lo que la música deja libre en cada paquete donde está
# —si no, el conversor se corta; ver `_enteros_entran`—. Es de taro: *"No me
# parece aceptable que instrumentos pierdan calidad por un solo mapa, pero
# tampoco quiero perder calidad en los efectos de sonido."* Un efecto que
# está en un paquete que limita muestras —cuál limita a cada una lo imprime
# el conversor— no puede estar acá sin que algún instrumento lo pague, y eso
# lo decide taro escuchando: ver la tarea `efectos-de-sonido-sin-recortes.md`.
#
# La tasa de cada uno se eligió el 2026-09-26: los que más se oyen primero, a
# la más alta que entra —22.050 Hz es la de los WAV, así que no se
# remuestrean—, y sin que los efectos de un paquete que hoy entran al lado de
# un tema que puede venir sonando dejen de entrar (ver
# `decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md`).
#
# El trueno de la apertura es un alias: lo que va después de la `@` es un
# nombre aparte para la misma WAV, que `_compilar` pone sólo en el mapa 1,
# porque el 3 también pide el trueno y ahí entero no entra sin bajarle la
# tasa a su tema.
#
# Y es el único que **sí** lo paga la música, si hace falta: taro lo eligió
# entero a 22 kHz escuchándolo, antes de esta regla. En `release` su paquete
# no limita a ninguna muestra, así que no le cuesta nada a nadie; en
# `test-special`, que lleva otros temas, sí, y ahí el trueno gana.
SE_ENTEROS = {
    "Thunder9@entero": 22050,
    "Sword3": 22050, "Monster2": 22050, "Recovery4": 22050, "Flame5": 22050,
    "Explosion5": 22050, "Dark5": 22050, "Cold2": 22050, "Thunder6": 22050,
    "Thunder4": 22050, "Decision2": 22050, "Earth8": 22050, "Fall2": 22050,
    "Buzzer1": 22050, "Blow7": 22050, "Failure1": 22050,
    "Holy6": 16000, "Kill3": 16000,
    "Sword2": 11025, "Dark1": 11025, "Sword1": 11025,
    "Numbness3": 6000, "Refer Book": 6000, "Earth1": 6000, "Thunder5": 6000,
}
SE_ENTEROS_PAGADOS = {"Thunder9@entero"}

# **Los que sí paga la música**, del 2026-09-26: taro, escuchando los que no
# entraban en lo libre, *"tengo cero dudas de que tienen que tener su
# longitud completa (todos)"*, y la tasa, de la baja a la media como mínimo.
# Van enteros aunque le bajen la tasa a los instrumentos de su paquete: cuánto
# y a cuáles está en `tasks/*/efectos-de-sonido-sin-recortes.md`.
#
# La media es 11.025 Hz, o 16.000 donde así se grabó para que taro eligiera
# (los golpes de la pelea). **Donde la media no entra, 6.000**, que sigue
# siendo entero:
#
# * la lluvia de la apertura: entera a 11 kHz son 31 KB, al lado de los 24 del
#   trueno, y la música del mapa 1 no entra ni con cada muestra en `PISO`;
# * los del mapa 3, que suman 43 KB de efectos: los cinco enteros a 11 kHz
#   pasan de la ARAM sin música. Ahí van con un alias (`SE_DEL_MAPA`), así
#   que en los demás paquetes siguen a la media. Cada alias es una entrada
#   del directorio, que está lleno: le cuesta la última copia a `copias`.
#
# Bow2 y Holy5 están además en el 26 y el 261, llenos con los de
# `SE_ENTEROS`: para que les entren a la media, ahí bajan Monster2, Thunder4 y
# Buzzer1 de 22 a 16 kHz, que ya no tienen que ver con la música.
SE_ENTEROS.update({
    "Monster2": 16000, "Thunder4": 16000, "Buzzer1": 16000,
    "Rain1": 6000,
    "Attack2": 16000, "Damage1": 16000, "Evasion1": 16000, "Escape": 16000,
    "Bite": 11025, "Item2": 11025, "Monster1": 11025,
    "Thunder9": 11025, "Darkness": 11025, "Explosion4": 11025,
    "Glass": 11025, "Switch1": 11025,
    "Bow2": 11025, "Holy5": 11025, "Blow2": 11025,
    "Thunder9@3": 6000, "Darkness@3": 6000, "Explosion4@3": 6000,
    "Glass@3": 6000,
})
SE_ENTEROS_PAGADOS |= {
    "Rain1", "Attack2", "Damage1", "Evasion1", "Escape", "Bite", "Item2",
    "Monster1", "Thunder9", "Darkness", "Explosion4", "Glass", "Switch1",
    "Bow2", "Holy5", "Blow2",
    "Thunder9@3", "Darkness@3", "Explosion4@3", "Glass@3",
}

# Los alias por mapa: (nombre en RM2k, id del mapa) -> la muestra que suena
# ahí. Los pone `_compilar`, en tools/port/eventos.py.
SE_DEL_MAPA = {
    ("Thunder9", 1): "Thunder9@entero",
    ("Thunder9", 3): "Thunder9@3",
    ("Darkness", 3): "Darkness@3",
    ("Explosion4", 3): "Explosion4@3",
    ("Glass", 3): "Glass@3",
}


class Efecto:
    """Un efecto listo para el SPC700: `data` en BRR, a `rate`, que vuelve al
    bloque `loop_block` si repite, y dura `segundos` en RM2k."""

    def __init__(self, name, data, rate, loop_block, segundos):
        self.name = name
        self.data = data
        self.rate = rate
        self.loop_block = loop_block or 0
        self.repite = loop_block is not None
        self.segundos = segundos


def leer_wav(nombre, game_dir=GAME_DIR):
    """Las muestras de un WAV mono como enteros de 16 bits con signo, y su
    tasa. None si no está o no es un WAV que se entienda."""
    import wave
    from render.render_map import RTP_DIR
    ruta = find_resource([game_dir, RTP_DIR], "Sound", nombre,
                         (".wav", ".WAV"))
    if not ruta:
        return None
    try:
        w = wave.open(ruta)
    except Exception:
        return None
    ancho, canales, tasa = w.getsampwidth(), w.getnchannels(), w.getframerate()
    datos = w.readframes(w.getnframes())
    if ancho == 1:
        crudo = [(b - 128) << 8 for b in datos]
    elif ancho == 2:
        crudo = [int.from_bytes(datos[i:i + 2], "little", signed=True)
                 for i in range(0, len(datos), 2)]
    else:
        return None
    if canales > 1:
        crudo = [sum(crudo[i:i + canales]) // canales
                 for i in range(0, len(crudo), canales)]
    return crudo, tasa


def build_efecto(nombre, game_dir=GAME_DIR, tasa=SE_TASA, enteros=None):
    """`enteros` es `SE_ENTEROS` si no viene; con {} sale el de siempre, que
    es lo que la música le presupuesta: ver `SE_ENTEROS`."""
    enteros = SE_ENTEROS if enteros is None else enteros
    leido = leer_wav(nombre.split("@")[0], game_dir)
    if not leido or not leido[0]:
        return None
    crudo, fuente = leido
    segundos = len(crudo) / float(fuente)
    guardar = min(len(crudo), int(SE_MAX_SEGUNDOS * fuente))
    if nombre in enteros:
        tasa, guardar = enteros[nombre], len(crudo)
    salen = max(BLOQUE,
                int(round(guardar * tasa / float(fuente)))
                // BLOQUE * BLOQUE)
    audio = snes_samples.normalize(snes_samples.resample(crudo[:guardar],
                                                         salen))
    loop = None
    if guardar < len(crudo):
        largo_loop = int(SE_LOOP_SEGUNDOS * tasa) // BLOQUE
        loop = max(0, salen // BLOQUE - max(1, largo_loop))
    return Efecto(nombre, muestras_brr.codificar(audio, loop_block=loop),
                  tasa, loop,
                  segundos)


def build_efectos(pedidos, game_dir=GAME_DIR, budget=SE_ARAM):
    """Los efectos que entran en `budget`, por prioridad: `pedidos` es una
    lista de nombres ya ordenada de más a menos pedido. Devuelve {nombre:
    Efecto} con los que entraron."""
    hechos, usado = {}, 0
    for nombre in pedidos:
        if nombre in hechos:
            continue
        efecto = build_efecto(nombre, game_dir)
        if efecto is None:
            continue
        costo = len(efecto.data) + 4          # la muestra y su entrada
        if usado + costo > budget:
            continue
        hechos[nombre] = efecto
        usado += costo
    return hechos


def altura_de_efecto(efecto, tempo):
    """El registro de altura del DSP: 4096 es la tasa de 32 kHz, y el tempo
    de RM2k —de 50 a 150— la estira."""
    return min(0x3FFF, int(round(efecto.rate * 4096 / 32000.0 * tempo / 100.0)))


def cuadros_de_efecto(efecto, tempo):
    """Cuánto dura, en cuadros de 60 Hz, con el tempo aplicado."""
    return max(1, int(round(efecto.segundos * 60 * 100.0 / max(1, tempo))))


def volumen_de_efecto(volumen, balance):
    """Izquierda y derecha del DSP, de 0 a 127, desde el volumen y el paneo
    de RM2k: el paneo en 50 es el centro, y a cada lado baja el otro."""
    tope = sdsp.MASTER if hasattr(sdsp, "MASTER") else 0x7F
    # Los $60 se eligieron con el volumen general en $60, que también se les
    # aplica a los efectos —con MSU-1 o sin él—. Con el aire de `sdsp` el
    # general subió, y el techo del efecto baja lo mismo para que suene igual.
    v = max(0, min(100, volumen)) * int(round(0x60 * 0x60 / sdsp.MASTER)) // 100
    izquierda = v * min(50, 100 - balance) // 50
    derecha = v * min(50, balance) // 50
    return max(0, min(0x7F, izquierda)), max(0, min(0x7F, derecha))


# --- reparto de voces -------------------------------------------------------

def assign(notes):
    """Qué voces del DSP puede tomar cada canal del MIDI: las ocho, todos.

    Hasta el 2026-09-26 cada canal melódico tenía sus voces fijas —repartidas
    por cuánto tiempo-nota agregaba cada una— y la batería dos al final. En
    `escape_newyork` eso dejaba una voz para los acordes de tres notas de las
    cuerdas, una para los de seis del polysynth, y ninguna para el clavinet y
    la onda cuadrada: se perdía el 55% del tiempo-nota contra el 23% que se
    pierde sin remedio con ocho voces. Ahora el reparto es nota a nota, en
    `build_events`: una nota toma una voz libre, y si no hay, le roba a otra
    por prioridad —ver `_victima`—. Es el paso 5 de
    `workflow/tasks/todo/la-calidad-de-la-musica.md`.

    Sigue devolviendo un grupo por canal porque `build_events` los acepta
    distintos, y las pruebas lo usan para armar casos chicos.
    """
    return {channel: list(range(sdsp.VOICES))
            for channel in sorted({n.channel for n in notes})}


# Las voces que los efectos de sonido le sacan a la música: `SE_VOZ` y
# `SE_VOZ2`. Mientras un efecto suena, lo que la música le escribe a su voz va
# a la sombra y no al DSP —ver `dsp_musica`—, así que la nota que estuviera
# ahí se calla. Por eso ahí van primero los golpes de percusión, que duran
# medio segundo, y las notas melódicas sólo si no queda otra libre: es lo que
# pasaba cuando la batería tenía esas dos voces fijas.
VOCES_DE_EFECTOS = (SE_VOZ2, SE_VOZ)


# El GAIN con que se baja una voz que suena un cuadro antes de dársela a otra
# nota: lineal, 64 pasos de 6 muestras, así que llega a cero en 12 ms, antes
# del cuadro siguiente. Lo que evita es el clic del KON, que pone la
# envolvente en cero de golpe: el prototipo del paso 5 de
# `workflow/tasks/todo/la-calidad-de-la-musica.md` lo grabó (la variante 07).
# Es un `OP_RELEASE_GAIN` más del stream: el driver no cambia.
RAMPA = sdsp.GAIN_LINEAR_DECREASE | 26
assert 64 * sdsp.PERIODO[RAMPA & 0x1F] <= sdsp.SAMPLE_RATE // TICKS_PER_SECOND


class _Voz:
    """Lo que el reparto sabe de una voz: la nota que la tiene, hasta cuándo
    la sostiene —`fin`— y hasta cuándo se oye —`cola`, con el release o lo que
    dura el golpe—, y con qué volumen arrancó, izquierda más derecha."""

    __slots__ = ("nota", "fin", "cola", "nivel")

    def __init__(self, nota, fin, cola, nivel):
        self.nota, self.fin, self.cola, self.nivel = nota, fin, cola, nivel


def _cuadros_del_release(gain):
    """Cuántos cuadros tarda en callarse una voz soltada con ese GAIN, desde
    arriba: el lineal baja 1/64 por paso, y el exponencial llega a cero en
    `PASOS_HASTA_CERO` —ver `sdsp`—."""
    periodo = sdsp.PERIODO[gain & 0x1F] or 0
    pasos = (64 if gain & 0xE0 == sdsp.GAIN_LINEAR_DECREASE
             else sdsp.PASOS_HASTA_CERO)
    return int(pasos * periodo * TICKS_PER_SECOND / sdsp.SAMPLE_RATE) + 1


def _libre(voz, t, voces, nota, drums):
    """El orden entre las voces libres —las que nadie sostiene en `t`—: la
    menor gana."""
    s = voces.get(voz)
    # Primero las calladas: reusar una que todavía suena en su cola la corta.
    # Entre las que suenan, la que se apaga antes.
    suena = s is not None and s.cola > t
    return (suena, s.cola if suena else 0,
            # Los golpes, a las voces de los efectos; lo melódico, a las otras.
            (voz in VOCES_DE_EFECTOS) != drums,
            # Y la que tuvo una nota del mismo canal: mismo instrumento y
            # mismo volumen, así que la nota nueva sale en dos bytes.
            s is None or s.nota.channel != nota.channel,
            voz)


def _victima(nota, t, grupo, voces, nivel):
    """A qué voz le roba `nota` cuando todas las de su grupo están
    sostenidas, o None si no le roba a ninguna y no suena.

    Es la regla del prototipo —lo que taro escuchó en la variante 09 y dijo
    que "es muy aceptable"—. Medida en los 32 temas del `release`: robarle
    siempre a la más vieja sin ceder nunca pierde el mismo tiempo-nota pero
    corta 2,5 veces más notas mientras suenan, y robarle siempre a la más
    débil pierde más; protegerle además la nota más grave y la más aguda, o
    robar primero dentro del propio canal, empatan con ella en promedio y
    ganan en unos temas lo que pierden en otros, así que no entraron. Los
    números, en el paso 5 de `workflow/tasks/todo/la-calidad-de-la-musica.md`.

    * La misma tecla del mismo canal que vuelve a sonar le roba a sí misma:
      es un sintetizador que redispara la nota.
    * Nunca a una nota que arrancó en este mismo cuadro, que no llegaría a
      sonar; ni a la última voz de un canal, que lo dejaría mudo.
    * Entre las demás, a la más débil —el volumen con que arrancó— y, a la
      par, a la más vieja.
    * Y la nota nueva cede en vez de robar si su canal ya suena y la víctima
      es la última de otro, o es más fuerte que ella y su canal no tiene más
      voces que el de la nueva.
    """
    por_canal = collections.Counter(voces[v].nota.channel for v in grupo)
    for v in grupo:
        s = voces[v].nota
        if s.channel == nota.channel and s.pitch == nota.pitch:
            return v

    def ultima(s):
        # La última voz de otro canal: robársela lo deja mudo. La del mismo
        # no, que sigue sonando con la nota nueva.
        return s.nota.channel != nota.channel and por_canal[s.nota.channel] <= 1

    def costo(v):
        s = voces[v]
        return (s.nota.start == t, ultima(s), s.nivel, s.nota.start, v)

    v = min(grupo, key=costo)
    s = voces[v]
    if s.nota.start == t:
        return None
    if por_canal[nota.channel] >= 1 and s.nota.channel != nota.channel and (
            ultima(s) or (s.nivel > nivel and por_canal[s.nota.channel]
                          <= por_canal[nota.channel])):
        return None
    return v


# Los golpes de General MIDI que son el mismo instrumento tocado de otra
# manera: dos bombos, dos cajas, el charles cerrado, con pedal y abierto, dos
# platos de choque, dos rides. Un MIDI que los pide juntos está engordando el
# golpe, no tocando dos —el de batalla pega 35 y 36 en cada tiempo, y 38 y 40
# en cada caja—. Los toms no: son tambores distintos y un redoble los junta.
FAMILIAS_DE_GOLPES = {35: "bombo", 36: "bombo", 38: "caja", 40: "caja",
                      42: "charles", 44: "charles", 46: "charles",
                      49: "platillo", 57: "platillo", 51: "ride", 59: "ride"}


def _orden_del_cuadro(notas, nivel):
    """En qué orden eligen voz las notas que arrancan en un mismo cuadro:
    cuando no hay para todas, las últimas son las que se quedan afuera,
    porque `_victima` no le roba a una nota que arrancó en el cuadro.

    * **Primero los golpes, uno por familia** (`FAMILIAS_DE_GOLPES`), del más
      fuerte al más suave: duran poco, y son el ritmo.
    * **Después lo melódico, por su nivel dividido por su lugar en su
      canal**: la nota más fuerte de cada canal va con su nivel, la segunda
      con la mitad, la tercera con un tercio. Así la voz de arriba de un
      acorde va antes que un canal más suave, pero la segunda nota de ese
      acorde va después, salvo que ese canal sea poco más que un susurro.
    * **Al final, el golpe repetido de una familia**, que sólo suena si
      sobra una voz.

    `nivel` es el de cada nota con los controladores del cuadro, izquierda
    más derecha: el de `_victima`, que es con el que la nota va a sonar.

    Hasta el 2026-09-26 el orden era el de la velocidad, y entre iguales el
    más grave primero. En el de batalla todo va con velocidad 127, así que
    los cinco o seis golpes de cada tiempo —dos bombos, dos cajas, charles—,
    los dos bajos y los metales tomaban las ocho voces antes de que llegara
    la melodía, que es lo más agudo; y no se le puede robar a una nota del
    mismo cuadro. De las 536 notas de la voz de arriba de su órgano —el
    canal 0, el más fuerte de la mezcla por su CC7— 214 no sonaban, y la
    frase principal (de los 15 a los 22 s) se cortaba una nota sí y otra no.
    Con el reparto fijo de antes del paso 5 no pasaba: el órgano tenía su
    voz. Medido con los 32 temas del `release`, con un script descartable:

    * la melodía de la batalla pasa de perder 48% de su tiempo a 0%;
    * en promedio, el tiempo-nota perdido baja de 7,38% a 7,05%, y los robos
      de 2.883 a 2.528; la nota más aguda de cada instante se pierde 6,9% del
      tiempo en vez de 10,7%, la más grave 3,7% en vez de 3,3%; los golpes
      que no suenan —contando una familia por cuadro— bajan de 0,39% a 0,12%;
    * el stream baja 3,6 KB, porque hay menos robos y con ellos menos rampas.

    Lo que se probó y no alcanzó, en la tarea
    (`workflow/tasks/todo/la-calidad-de-la-musica.md`, paso 5b): ordenar por
    nivel sin más, sin repartir por canal (la melodía pierde 22%); una ronda
    estricta —cada canal su primera nota antes que cualquiera su segunda—,
    que salva la melodía igual pero le da voz a las cuerdas de velocidad 29
    de `escape_newyork` a costa del polysynth; y lo que se hace en
    `_victima` —no robar una nota recién empezada, un tope de voces para la
    batería, que los golpes no roben—, que no cambia nada: la melodía no se
    perdía por robos sino por llegar última a su cuadro.
    """
    niveles = {id(n): nivel(n) for n in notas}
    lugar = {}
    por_canal = collections.defaultdict(list)
    for n in notas:
        por_canal[n.channel].append(n)
    for canal, ns in por_canal.items():
        if canal == midi.DRUM_CHANNEL:
            vistas = set()
            for n in sorted(ns, key=lambda n: (-niveles[id(n)], n.pitch)):
                familia = FAMILIAS_DE_GOLPES.get(n.pitch, n.pitch)
                lugar[id(n)] = (2 if familia in vistas else 0, -niveles[id(n)])
                vistas.add(familia)
        else:
            por_nivel = sorted(ns, key=lambda n: (-niveles[id(n)], -n.pitch))
            for i, n in enumerate(por_nivel):
                lugar[id(n)] = (1, -niveles[id(n)] / (1.0 + i))
    return sorted(notas, key=lambda n: lugar[id(n)] + (n.pitch,))


# --- el banco compartido ----------------------------------------------------

# Las muestras se piden por clave: ("p", programa, tecla) una melódica,
# ("g", tecla) un golpe de percusión. Es una por programa de General MIDI y
# una por golpe en todo el cartucho, así que dos temas que tocan piano usan
# la misma. La tecla de la melódica elige la zona del SoundFont: ver
# `zonas_mas_usadas`.
def claves_del_tema(leido, teclas=None):
    """Las muestras que pide un tema leído por `leer_tema`, o ninguna.
    `teclas` son las de `zonas_mas_usadas`; sin ella, el do central."""
    if not leido:
        return set()
    teclas = teclas or {}
    return ({("p", p, teclas.get(p, snes_samples.REFERENCE_KEY))
             for p in leido["melodicos"]}
            | {("g", g) for g in leido["golpes"]})


def zonas_mas_usadas(leidos):
    """{programa: tecla}: con qué tecla se pide la muestra de cada programa,
    que es la que elige la zona del SoundFont.

    **La zona donde el cartucho entero toca más tiempo-nota de ese
    programa**, y no la del do central. Una muestra suena bien cerca de su
    raíz: lejos, el DSP la estira o la aprieta y se oye —una octava abajo
    los agudos que faltan, una arriba el loop que se acorta—. Medido el
    2026-09-26 con los 32 temas del `release`: el 34% del tiempo-nota
    melódico sonaba a doce semitonos o más de la raíz de la muestra del do
    central, en teclas para las que el SoundFont tiene otra; el bajo
    sintético 33, en doce temas, toca la zona de `MMBAS40` y no la del 62.
    Es una por programa igual que antes, así que no cuesta ARAM; lo que
    pierde es que un programa que dos temas tocan en registros distintos
    queda bien para uno solo. Es el paso 6 de
    `workflow/tasks/todo/la-calidad-de-la-musica.md`.

    La tecla es la raíz de esa zona si la zona la cubre —así dos temas que
    tocan la misma zona piden la misma muestra—, y si no, la tecla que más
    suena adentro de la zona.
    """
    tiempo = collections.defaultdict(collections.Counter)
    adentro = collections.defaultdict(collections.Counter)
    for leido in leidos:
        if not leido:
            continue
        for nota in leido["notas"]:
            if (nota.channel == midi.DRUM_CHANNEL
                    or nota.channel not in leido["voces"]):
                continue
            programa = leido["programas"].get(nota.channel, 0)
            zona = muestras_brr.zona("program:%d@%d" % (programa, nota.pitch),
                                     snes_samples.SOUNDFONT)
            if zona is None:
                continue
            tiempo[programa][zona] += nota.end - nota.start
            adentro[programa, zona][nota.pitch] += nota.end - nota.start
    teclas = {}
    for programa, por_zona in tiempo.items():
        zona = max(por_zona, key=lambda z: (por_zona[z], z))
        raiz = zona[1]
        if muestras_brr.zona("program:%d@%d" % (programa, raiz),
                             snes_samples.SOUNDFONT) == zona:
            teclas[programa] = raiz
        else:
            cuanto = adentro[programa, zona]
            teclas[programa] = max(cuanto, key=lambda k: (cuanto[k], -k))
    return teclas


def _muestra(clave, presupuesto):
    """La voz de una clave con ese presupuesto en bytes de BRR, o None si el
    SoundFont no la tiene."""
    if clave[0] == "p":
        return snes_samples.build_voice(snes_samples.SOUNDFONT, clave[1],
                                        presupuesto, key=clave[2])
    return snes_samples.build_drum(snes_samples.SOUNDFONT, clave[1],
                                   presupuesto)


# Un presupuesto que nadie alcanza: con él, cada muestra sale a la tasa del
# SoundFont —topada en `MAX_RATE`—, que es lo que pesaría sin recortar.
NATIVA = 1 << 24
# Lo mínimo que se le da a una muestra aunque su paquete esté lleno.
PISO = 256


class Restriccion(collections.namedtuple("Restriccion",
                                         "nombre claves libre")):
    """Un grupo de muestras que tiene que entrar junto en `libre` bytes: las
    de los temas de un paquete, con lo que ocupan sus efectos ya restado, o
    las de un paquete más las del tema que puede venir sonando."""
    __slots__ = ()


class Grupo(collections.namedtuple("Grupo", "nombre temas ocupan")):
    """Temas —índices— que tienen que entrar juntos en la ARAM, con `ocupan`
    bytes de efectos al lado: los de un paquete, un tema de salida solo, o
    un paquete con el tema que puede venir sonando. Es de lo que salen las
    `Restriccion`: con qué muestra toca cada tema lo dice `copias`."""
    __slots__ = ()


def libre_para(muestras, efectos):
    """Lo libre para muestras con `muestras` de música y `efectos` en el
    directorio: la ARAM desde detrás del directorio y del silencio hasta
    `ARAM_FIN`. Cada entrada del directorio son cuatro bytes."""
    return ARAM_FIN - (SAMPLES_ADDR + 4 * (muestras + efectos) + len(SILENCIO))


def restricciones_de(asignacion, grupos, libre):
    """Las `Restriccion` de `repartir` para esos grupos, con las muestras que
    le tocan a cada tema según `asignacion` —ver `copias`—."""
    salida = []
    for g in grupos:
        claves = set().union(*[set(asignacion[t].values()) for t in g.temas])
        if claves:
            salida.append(Restriccion(g.nombre, claves, libre - g.ocupan))
    return salida


# El SRCN es de un byte y las listas de muestras de la ROM se cierran con $FF,
# así que el directorio llega a 255 entradas: la música y los efectos juntos.
DIRECTORIO_MAX = 255
# Una copia no se hace por una muestra que ya suena casi a su tasa: una
# entrada del directorio vale más que eso.
COPIA_HASTA = 0.9


def copias(claves_de, grupos, efectos, tope=DIRECTORIO_MAX,
           hasta=COPIA_HASTA):
    """[{clave: muestra}], uno por tema: con qué muestra toca cada tema cada
    una de sus claves. Casi siempre la clave misma —una muestra por programa
    y por golpe en todo el cartucho—, salvo **las copias**.

    Una muestra tiene que entrar en todos los grupos donde está, así que su
    tasa la fija el peor, y lo paga también el tema que nunca suena ahí:
    hasta el 2026-09-26, los 43 KB de efectos del mapa 3 dejaban la batería
    de **todos** los temas a 10 kHz y el oboe a 7. Una copia es la misma
    clave como otra muestra, sólo para los temas del grupo que la limita:
    ellos quedan igual, y los de afuera dejan de pagar un paquete donde no
    están. Es la opción B del paso 6 de
    `workflow/tasks/testing/la-calidad-de-la-musica.md`, acotada: B entera
    —una copia por tema— serían unas 370 entradas del directorio contra 255.

    Se hacen de a una, **la peor primero**: la muestra de fracción más baja
    de su tamaño nativo que tenga algún tema fuera del grupo que la limita.
    Después se vuelve a repartir, porque la copia cambia lo que ocupa cada
    grupo, y se sigue hasta llenar el directorio o hasta que no quede una
    por debajo de `hasta`. `efectos` es cuántas entradas del directorio
    ocupan los efectos.
    """
    asignacion = [{k: k for k in ks} for ks in claves_de]
    nativas = {}

    def nativa(clave):
        if clave not in nativas:
            nativas[clave] = len(_muestra(clave, NATIVA).data)
        return nativas[clave]

    while True:
        claves = {k for a in asignacion for k in a.values()}
        if len(claves) + efectos >= tope:
            break
        rs = restricciones_de(asignacion, grupos,
                              libre_para(len(claves), efectos))
        presupuesto, limita = repartir(claves, rs)
        temas_de = {g.nombre: set(g.temas) for g in grupos}
        peor = None
        for clave, nombre in sorted(limita.items()):
            fraccion = presupuesto[clave] / float(nativa(clave))
            if fraccion >= hasta:
                continue
            usan = [t for t, a in enumerate(asignacion)
                    if clave in a.values()]
            adentro = [t for t in usan if t in temas_de[nombre]]
            afuera = len(usan) - len(adentro)
            if not adentro or not afuera:
                continue
            candidato = (round(fraccion, 3), -afuera, clave, nombre, adentro)
            if peor is None or candidato < peor:
                peor = candidato
        if peor is None:
            break
        _f, _a, clave, nombre, adentro = peor
        copia = clave + ("@" + nombre,)
        for t in adentro:
            for base, suya in asignacion[t].items():
                if suya == clave:
                    asignacion[t][base] = copia
    return asignacion


def repartir(claves, restricciones, margen=None):
    """({clave: presupuesto}, {clave: restricción que la limitó}): cuánto le
    toca a cada muestra para que cada restricción entre en lo suyo menos
    `margen`.

    Es un llenado progresivo sobre la fracción del tamaño nativo de cada
    muestra: se sube la fracción de todas juntas hasta que alguna restricción
    se llena, las de ésa quedan fijas, y se sigue con las demás. Así una
    muestra queda limitada por su **peor** paquete y no por el banco entero,
    y el que tiene lugar de sobra no paga por el que no. Lo que no está en
    ninguna restricción que se llene va entera.
    """
    margen = ARAM_MARGEN if margen is None else margen
    nativas = {k: len(_muestra(k, NATIVA).data) for k in claves}
    fraccion, limita = {}, {}
    libres = set(claves)
    activas = [r for r in restricciones if r.claves & libres]
    while libres and activas:
        peor, cual = None, None
        for r in activas:
            suyas = [k for k in r.claves if k in libres]
            if not suyas:
                continue
            fijo = sum(fraccion[k] * nativas[k] for k in r.claves
                       if k in fraccion)
            f = (r.libre - margen - fijo) / sum(nativas[k] for k in suyas)
            if peor is None or f < peor:
                peor, cual = f, r
        if peor is None or peor >= 1:
            break
        for k in cual.claves & libres:
            fraccion[k] = max(0.0, peor)
            limita[k] = cual.nombre
        libres -= cual.claves
        activas.remove(cual)
    return ({k: max(PISO, int(fraccion.get(k, 1.0) * nativas[k]))
             for k in claves}, limita)


class Banco:
    """Las muestras que comparten **todos** los temas de la ROM, una por
    programa y una por golpe, cada una con el presupuesto de su peor paquete.

    Es uno solo —salvo las copias de `copias`—, y no por ahorrar cartucho
    —de ése sobra— sino por la numeración: el SRCN que el stream escribe es el índice de la muestra en
    el cartucho, así que dos temas que tocan piano apuntan a la misma. Pero
    **no se sube entero**: a la ARAM van de a paquetes, uno por mapa —ver
    `paquete_cargar` en rom/src/paquete_de_audio.s—, así que lo que tiene que
    entrar en los 64 KB no es el banco sino cada paquete, con sus efectos.

    Por eso el presupuesto es por paquete: el paso 6 de
    `workflow/tasks/todo/la-calidad-de-la-musica.md`, la opción A, elegida
    por taro el 2026-09-26. Hasta ese día el banco entero tenía que entrar
    en la ARAM —40 KB para lo melódico y la percusión con lo que sobrara—, y
    los temas que no cabían dejaban de aportar programas: diecinueve de los
    treinta y dos del `release` sonaban con lo que otros habían puesto, o
    mudos.

    `restricciones` son las de `repartir`; `limita` dice cuál fijó cada
    muestra, para el informe del conversor.
    """

    def __init__(self, claves, restricciones=(), margen=None):
        claves = {k for k in claves if _muestra(k, NATIVA) is not None}
        presupuesto, self.limita = repartir(claves, restricciones, margen)
        voz = {k: _muestra(k, presupuesto[k]) for k in claves}
        # El presupuesto es una guía: el largo real se redondea a bloques de
        # BRR, así que se comprueba lo que ocupa de verdad y, si una
        # restricción se pasa de lo suyo —sin el margen: el margen es para
        # esto—, se les pide menos a sus muestras y se vuelve a armar.
        for _ in range(20):
            pasadas = [r for r in restricciones
                       if self._suma(voz, r.claves) > r.libre]
            if not pasadas:
                break
            for r in pasadas:
                usa = self._suma(voz, r.claves)
                for k in r.claves & set(voz):
                    presupuesto[k] = max(PISO, int(presupuesto[k] * r.libre
                                                   / usa * 0.98))
                    voz[k] = _muestra(k, presupuesto[k])
        else:
            raise SystemExit(
                "las muestras de %s no entran en la ARAM ni con el mínimo"
                % ", ".join("%s (%d de %d B)" % (r.nombre,
                                                 self._suma(voz, r.claves),
                                                 r.libre) for r in pasadas))
        self.restricciones = list(restricciones)
        self.claves = ([k for k in sorted(claves) if k[0] == "p"]
                       + [k for k in sorted(claves) if k[0] == "g"])
        self.voces = [voz[k] for k in self.claves]
        # De programa de MIDI a índice en el banco, que es lo que va en
        # `V_SRCN`; los golpes van después de los melódicos, así que el DSP no
        # distingue percusión de nada más. Son los de las muestras sin copia:
        # un tema con copias pide los suyos con `del_tema`.
        self.melodicas = {k[1]: i for i, k in enumerate(self.claves)
                          if k[0] == "p" and len(k) == 3}
        self.golpes = {k[1]: i for i, k in enumerate(self.claves)
                       if k[0] == "g" and len(k) == 2}
        self._envolventes = {}

    def del_tema(self, asignacion):
        """El banco como lo ve un tema: sus programas y sus golpes apuntan a
        las muestras que le tocaron —ver `copias`—, y lo demás es lo de
        todos. `asignacion` es {clave: muestra}."""
        vista = _Vista(self)
        indice = {k: i for i, k in enumerate(self.claves)}
        vista.melodicas = {base[1]: indice[k] for base, k in asignacion.items()
                           if base[0] == "p" and k in indice}
        vista.golpes = {base[1]: indice[k] for base, k in asignacion.items()
                        if base[0] == "g" and k in indice}
        return vista

    @staticmethod
    def _suma(voz, claves):
        return sum(len(voz[k].data) for k in claves if k in voz)

    def ocupa(self, claves):
        """Cuánto ocupan en la ARAM las muestras de esas claves."""
        return sum(len(v.data) for k, v in zip(self.claves, self.voces)
                   if k in claves)

    def envolvente(self, program, key):
        """(ADSR1, ADSR2, GAIN del release) de una nota melódica: la
        envolvente de la zona del SoundFont que cubre la tecla, traducida por
        `sdsp.envelope`.

        La zona puede no ser la de la muestra —cada programa lleva una sola,
        la de `zonas_mas_usadas`—, y es a propósito: es la envolvente que el
        SoundFont le daría a esa tecla, y en el piano el decaimiento cambia
        tecla por tecla. Si ninguna zona cubre la tecla, la del do central.
        """
        clave = (program, key)
        if clave not in self._envolventes:
            sf2 = (muestras_brr.envolvente("program:%d@%d" % (program, key),
                                           snes_samples.SOUNDFONT)
                   or muestras_brr.envolvente(
                       "program:%d@%d" % (program, snes_samples.REFERENCE_KEY),
                       snes_samples.SOUNDFONT))
            self._envolventes[clave] = sdsp.envelope(sf2, key)
        return self._envolventes[clave]

    @property
    def bytes(self):
        """Cuánto ocupa en ARAM: el directorio más las muestras."""
        return 4 * len(self.voces) + sum(len(v.data) for v in self.voces)


class _Vista:
    """Lo que devuelve `Banco.del_tema`: el mismo banco con los índices de un
    tema. Lo que no pisa lo lee del banco."""

    def __init__(self, banco):
        self._banco = banco

    def __getattr__(self, nombre):
        return getattr(self._banco, nombre)


# --- eventos ----------------------------------------------------------------

class Frame:
    """Todo lo que pasa en un cuadro, separado por cuándo hay que escribirlo.

    El orden importa: primero se prepara cada voz —volumen, altura, timbre— y
    recién al final se tocan KON y KOF, que son los que disparan. Si se hiciera
    al revés, la nota arrancaría con los valores de la anterior.
    """

    __slots__ = ("release", "setup", "kon", "kof", "control")

    def __init__(self):
        # Las notas que se sueltan en este cuadro: (voz, GAIN del release), y
        # las voces que se bajan con `RAMPA` porque otra nota las toma en el
        # cuadro siguiente.
        self.release = []
        # Las que arrancan: una `Preparacion` por nota, en orden.
        self.setup = []
        self.kon = 0
        self.kof = 0
        # Lo que los controladores le cambian a una voz que ya sonaba:
        # registro -> valor, y gana el último del cuadro. Un dict y no una
        # lista porque un fundido trae varios CC7 por cuadro, y escribir los
        # del medio son bytes que el DSP no llega a usar.
        self.control = {}


# Lo que una nota le escribe a su voz antes del KON, y el GAIN con que se va
# a soltar —None en la batería, que no se suelta—. Las siete escrituras salen
# de `Preparacion.escrituras`, en el orden en que van al DSP.
class Preparacion(collections.namedtuple(
        "Preparacion", "voz izquierda derecha altura muestra adsr1 adsr2 gain")):
    __slots__ = ()

    def escrituras(self):
        base = self.voz * 0x10
        return [(base + sdsp.V_VOL_L, self.izquierda),
                (base + sdsp.V_VOL_R, self.derecha),
                (base + sdsp.V_PITCH_L, self.altura & 0xFF),
                (base + sdsp.V_PITCH_H, self.altura >> 8),
                (base + sdsp.V_SRCN, self.muestra),
                (base + sdsp.V_ADSR1, self.adsr1),
                (base + sdsp.V_ADSR2, self.adsr2)]


def build_events(notes, voices, programs, banco, controls=(), reparto=None,
                 aire=sdsp.AIRE):
    """Las escrituras al DSP, cuadro por cuadro.

    Cada canal tiene su grupo de voces —desde el paso 5, las ocho para todos:
    ver `assign`—; una nota que arranca toma una libre, la que menos corte
    según `_libre`, y si están todas sostenidas le roba a la que diga
    `_victima`, o no suena. Es lo que hace un sintetizador cuando se le acaba
    la polifonía.

    El banco viene de afuera y no se arma acá: lo comparten todos los temas de
    la ROM, así que los índices de `V_SRCN` que este stream escribe son los de
    ese banco y no los de uno propio. Ver `Banco`.

    `controls` son los `midi.Control` del tema, ya en cuadros: el volumen, la
    expresión y el paneo entran en el volumen de cada lado de la nota, y el
    bend en su altura. Los de un cuadro se aplican antes que sus notas, así
    que la nota arranca con el estado con que termina el cuadro; y a una voz
    que ya sonaba —o que está en su cola— se le reescriben sus registros.

    `reparto`, si viene una lista, se llena con lo que le tocó a cada nota que
    tiene muestra: (nota, voz o None si no sonó, cuadro en que le robaron la
    voz o None, hasta cuándo la sostiene —el fin de la nota, o el de la
    muestra si es un golpe más corto que ella—). Es de dónde sale cuánto
    tiempo-nota se pierde.

    `aire` es el techo de las voces de este tema, el de `sdsp.AIRE` o uno
    más bajo: ver `leer_techos`.
    """
    frames = collections.defaultdict(Frame)
    techo = aire / sdsp.AIRE
    bank, index_of, drum_index = banco.voces, banco.melodicas, banco.golpes

    estado = collections.defaultdict(lambda: dict(midi.DEFAULTS))
    pendientes = sorted(controls, key=lambda c: c.start)
    siguiente = 0

    def lados(note, drums):
        c = estado[note.channel]
        return sdsp.volume(note.velocity,
                           techo * (sdsp.CEILING_DRUM if drums
                                    else sdsp.CEILING),
                           c[midi.VOLUME], c[midi.EXPRESSION], c[midi.PAN])

    def altura(note, drums):
        if drums:
            # En General MIDI la nota elige el instrumento, no la altura, así
            # que cada golpe tiene su propia muestra y se toca a su tasa
            # original: transponerla convertiría un bombo en otra cosa. Por
            # eso el bend tampoco la mueve.
            drum = bank[drum_index[note.pitch]]
            return sdsp.pitch_for(drum.root, drum.root, drum.rate)
        instrument = bank[index_of[programs.get(note.channel, 0)]]
        return sdsp.pitch_for(note.pitch + estado[note.channel][midi.BEND],
                              instrument.root, instrument.rate)

    def controlar(hasta):
        """Aplica los controladores hasta el cuadro `hasta`, y a las voces
        cuya nota es de ese canal les reescribe lo que cambió."""
        nonlocal siguiente
        while (siguiente < len(pendientes)
               and pendientes[siguiente].start <= hasta):
            c = pendientes[siguiente]
            siguiente += 1
            if estado[c.channel][c.number] == c.value:
                continue
            estado[c.channel][c.number] = c.value
            # `owner` sigue teniendo a la nota después de su fin, así que
            # esto también le cambia el volumen a una cola que se apaga, como
            # fluidsynth. Cortarlo en el fin de la nota ahorraba 1.195 B en
            # los 32 temas del `release` (2026-09-26): no vale un caso aparte.
            for voice, note in owner.items():
                if note.channel != c.channel:
                    continue
                base = voice * 0x10
                drums = note.channel == midi.DRUM_CHANNEL
                frame = frames[c.start].control
                if c.number == midi.BEND:
                    if drums:
                        continue
                    step = altura(note, drums)
                    frame[base + sdsp.V_PITCH_L] = step & 0xFF
                    frame[base + sdsp.V_PITCH_H] = step >> 8
                else:
                    izquierda, derecha = lados(note, drums)
                    frame[base + sdsp.V_VOL_L] = izquierda
                    frame[base + sdsp.V_VOL_R] = derecha

    def en_orden():
        """Las notas cuadro por cuadro, cada cuadro en el orden de
        `_orden_del_cuadro`. Los controladores del cuadro se aplican antes de
        ordenarlo, porque el orden va por el nivel con que arranca cada nota;
        y como es un generador, eso pasa recién cuando el cuadro anterior ya
        repartió sus voces, que es cuando lo hacía cada nota."""
        por_cuadro = collections.defaultdict(list)
        for note in notes:
            por_cuadro[note.start].append(note)
        for cuadro in sorted(por_cuadro):
            controlar(cuadro)
            yield from _orden_del_cuadro(por_cuadro[cuadro], lambda n: sum(
                lados(n, n.channel == midi.DRUM_CHANNEL)))

    # De quién es cada voz ahora: la última nota que la tomó, con hasta
    # cuándo la sostiene y hasta cuándo se oye. El release de una nota se
    # agenda recién al final, y sólo si llegó a su fin siendo la dueña: si
    # otra le robó la voz antes, soltarla soltaría a la ladrona. Hasta el
    # 2026-09-25 se agendaba al tomar la voz y eran 329 notas de
    # `escape_newyork` cortadas antes de tiempo, casi todas del bajo.
    voces, owner, robbed, sounded, rampas = {}, {}, {}, [], []
    de_la_voz = {}                  # la entrada de `reparto` de su dueña
    for note in en_orden():
        group = voices.get(note.channel)
        if not group:
            continue
        program = programs.get(note.channel, 0)
        drums = note.channel == midi.DRUM_CHANNEL
        # Antes de elegir voz: una nota sin muestra no suena, y si ocupara la
        # voz le quitaría el lugar a una que sí.
        source = (drum_index.get(note.pitch) if drums
                  else index_of.get(program))
        if source is None:
            continue                    # el banco no trae ese golpe o programa

        step = altura(note, drums)
        izquierda, derecha = lados(note, drums)
        if drums:
            # Ataque instantáneo y sin decaimiento: el golpe ya trae su propia
            # forma, la envolvente sólo lo apaga al final para que no siga
            # leyendo memoria. No tiene release, así que tampoco GAIN: se oye
            # hasta que la muestra se acaba. Pero la voz la sostiene sólo
            # hasta el fin de la nota en el MIDI, y lo que sigue es como la
            # cola de un release: se la puede tomar otra nota. Sostenerla
            # hasta el final de la muestra le hacía perder a lo melódico, en
            # los 32 temas, 8,3% del tiempo-nota en promedio en vez de 7,9%
            # —Lunar_Pyramid 33% en vez de 23%— para salvar colas de golpes
            # que en fluidsynth también se sueltan con el fin de la nota.
            adsr1, adsr2, gain = 0x8F, 0xE0, None
            muestra = bank[source]
            cola = note.start + int(math.ceil(
                muestra.frames * TICKS_PER_SECOND / float(muestra.rate)))
            fin = min(cola, note.end)
        else:
            adsr1, adsr2, gain = banco.envolvente(program, note.pitch)
            fin, cola = note.end, note.end + _cuadros_del_release(gain)

        t = note.start
        libres = [v for v in group if v not in voces or voces[v].fin <= t]
        if libres:
            voice = min(libres, key=lambda v: _libre(v, t, voces, note, drums))
        else:
            voice = _victima(note, t, group, voces, izquierda + derecha)
        if voice is None:
            if reparto is not None:
                reparto.append([note, None, None, fin])
            continue
        if voice in owner:
            robbed.setdefault(id(owner[voice]), t)
            if voice in de_la_voz:
                de_la_voz[voice][2] = t
            # Si la voz todavía suena, se la baja a cero en el cuadro de antes:
            # el KON pone la envolvente en cero de golpe, y eso es un clic. No
            # a una nota que arrancó en ese mismo cuadro, que se prepara detrás
            # del release y lo deshace.
            anterior = voces[voice]
            if anterior.cola > t - 1 and anterior.nota.start < t - 1:
                rampas.append((t - 1, voice))
        voces[voice] = _Voz(note, fin, cola, izquierda + derecha)
        owner[voice] = note
        if reparto is not None:
            reparto.append([note, voice, None, fin])
            de_la_voz[voice] = reparto[-1]

        start = frames[note.start]
        base = voice * 0x10
        # Lo que los controladores le reescribían a la dueña anterior en este
        # cuadro ya no va: esta nota escribe los suyos, con el mismo estado.
        for registro in (sdsp.V_VOL_L, sdsp.V_VOL_R, sdsp.V_PITCH_L,
                         sdsp.V_PITCH_H):
            start.control.pop(base + registro, None)
        start.setup.append(Preparacion(voice, izquierda, derecha, step, source,
                                       adsr1, adsr2, gain))

        start.kon |= 1 << voice
        if not drums:
            sounded.append((note, voice, gain))

    # Los que quedan después de la última nota: el fundido del final de
    # `escape_newyork` es CC7 sobre las notas que ya sonaban.
    controlar(float("inf"))

    for note, voice, gain in sounded:
        # Robada en el mismo cuadro en que termina tampoco se suelta: la
        # ladrona escribe su ADSR1 detrás del release y lo deshace, así que
        # serían seis bytes que no hacen nada.
        if robbed.get(id(note), note.end + 1) <= note.end:
            continue
        frames[note.end].release.append((voice, gain))
    # Las rampas van después de los releases de su cuadro, para ganarles.
    for cuadro, voice in rampas:
        frames[cuadro].release.append((voice, RAMPA))

    return frames


def init_writes():
    """El estado del DSP antes de la primera nota.

    No depende del banco ni de qué voces son percusión: todo lo que hay acá es
    global del DSP. Llevaba los dos como parámetros y no los miraba.
    """
    writes = [
        (sdsp.FLG, sdsp.FLG_BASE),          # sin eco, sin mute
        (sdsp.MVOL_L, sdsp.MASTER), (sdsp.MVOL_R, sdsp.MASTER),
        (sdsp.EVOL_L, 0x00), (sdsp.EVOL_R, 0x00),
        (sdsp.EON, 0x00),                   # ninguna voz manda al eco
        (sdsp.PMON, 0x00),                  # sin modulación entre voces
        (sdsp.NON, 0x00),                   # ya no se usa el ruido: la
                                            # percusión tiene muestras propias
        (sdsp.DIR, SAMPLES_ADDR >> 8),      # dónde está el directorio
        (sdsp.KON, 0x00), (sdsp.KOF, 0x00),
    ]
    return writes


def escrituras(frames, length, init):
    """Lo que el tema le escribe al DSP: (cuadro, registro, valor), en orden.

    Es **la especificación del stream**, y lo que hasta el 2026-09-26 era el
    stream mismo —un `OP_DSP registro valor` de tres bytes por escritura—. El
    formato por nota de `pack` tiene que expandirse a exactamente esto, cuadro
    por cuadro: lo verifica `build_varios` con cada tema que arma, y en la ROM
    `pruebas/rpgmaker/test_musica_escrituras.py`.

    Los registros del DSP son simples cerrojos: vuelto a escribir el mismo valor
    no pasa nada. Así que se lleva la cuenta de qué tiene cada uno y se saltean
    las escrituras que no cambian nada, que son muchas: el timbre y la muestra
    de una voz casi nunca cambian entre dos notas seguidas.

    Eso es seguro aun con el tema en loop. Una escritura se saltea sólo porque
    otra anterior del mismo stream dejó ese valor, y esa anterior también se
    ejecuta en la segunda vuelta; por inducción, el estado del DSP en cada punto
    de la segunda vuelta es el mismo que en la primera.

    KON es la excepción y nunca se cachea: no es un cerrojo sino un disparador.
    El DSP lo mira cada dos milisegundos y arranca las voces cuyo bit esté
    puesto, así que hay que bajarlo a mano o la nota se repite sola.
    """
    salen = []
    state = {}
    cuadro = 0

    def write(register, value):
        value &= 0xFF
        if state.get(register) == value:
            return
        state[register] = value
        salen.append((cuadro, register & 0xFF, value))

    for register, value in init:
        write(register, value)

    sounding = 0
    for at in sorted(frames):
        if at > length:
            break
        frame = frames[at]
        if not (frame.release or frame.setup or frame.kon or frame.kof
                or frame.control):
            continue
        cuadro = at

        if sounding:                       # bajar el disparo del cuadro anterior
            salen.append((cuadro, sdsp.KON, 0x00))
            sounding = 0
        write(sdsp.KOF, 0x00)
        for voice, gain in frame.release:
            write(voice * 0x10 + sdsp.V_ADSR1, 0x00)    # apagar ADSR: manda GAIN
            write(voice * 0x10 + sdsp.V_GAIN, gain)
        for preparacion in frame.setup:
            for register, value in preparacion.escrituras():
                write(register, value)
        for register, value in sorted(frame.control.items()):
            write(register, value)
        if frame.kof:
            write(sdsp.KOF, frame.kof)
        if frame.kon:
            salen.append((cuadro, sdsp.KON, frame.kon))
            sounding = frame.kon

    # Al final se apaga todo, si no la última nota queda sonando en el loop.
    cuadro = max(cuadro, length)
    salen.append((cuadro, sdsp.KON, 0x00))
    salen.append((cuadro, sdsp.KOF, 0xFF))
    return salen


# --- el formato por nota ---------------------------------------------------
#
# Hasta el 2026-09-26 el stream eran las escrituras mismas —`OP_DSP registro
# valor`, tres bytes cada una— y pesaba más de la quinta parte del cartucho.
# Ahora son eventos, y el 65816 los expande (`music_frame`) a **las mismas
# escrituras, cuadro por cuadro**: el formato no puede cambiar cómo suena. Lo
# verifica `build_varios` con cada tema que arma, y en la ROM
# `pruebas/rpgmaker/test_musica_escrituras.py`.
#
# Un tema es su stream y su tabla de *sonidos*: todo lo que una nota le
# escribe a su voz salvo el volumen —altura, muestra, ADSR— más el GAIN con que
# se va a soltar. La altura va adentro, y no aparte, porque con eso el
# instrumento y la tecla son un solo byte: la batería cambia de golpe en casi
# cada nota, y el piano de ADSR2 con la tecla.
#
# Lo que el formato **no** asume, a propósito, es de qué canal es cada voz: el
# evento dice la voz y el conversor la eligió. Así el reparto por prioridad del
# paso 5 de `la-calidad-de-la-musica.md` —cualquier voz para cualquier canal—
# entra sin tocarlo: que una voz cambie de instrumento nota a nota cuesta lo
# mismo que no cambiarlo, un sonido por nota. Y la rampa antes de reusar una
# voz que suena es un `OP_RELEASE_GAIN` con el GAIN de la rampa, un cuadro
# antes de la nota.
#
# El caché de registros de `escrituras` lo lleva el 65816 y no el stream: cada
# evento dice valores y el decodificador saltea el que el registro ya tiene.
# Tiene una sola trampa, que es que no sabe decir "no sé" —ver `decodificar`—.
# El KON tampoco va en el stream: lo juntan las notas y lo dispara la espera
# que cierra el cuadro, que es exactamente la regla de `escrituras`.

VOCES = sdsp.VOICES
# Los registros de voz que el decodificador lleva en su caché: de VOL_L a GAIN.
REGISTROS_DE_VOZ = 8


# Las familias de ocho opcodes, una por voz: la voz va en los tres bits bajos
# y la familia en los de arriba, que es como las encuentra el decodificador.
# Ver el encabezado de `tools/protocol/music.toml`, que no las puede declarar.
FAMILIAS = ["NOTE", "NOTE_VOL", "NOTE_PAN", "RELEASE", "RELEASE_GAIN",
            "SET_VOL", "SET_PAN", "SET_PITCH"]
for _k, _familia in enumerate(FAMILIAS):
    for _v in range(VOCES):
        assert globals()["OP_%s_V%d" % (_familia, _v)] == 8 * _k + _v, (
            "music.toml: OP_%s_V%d no está donde la familia lo espera"
            % (_familia, _v))
# Las esperas cortas, de OP_WAIT_1 a OP_WAIT_32: un byte cierra el cuadro y
# espera. Entran casi todas; las demás van con OP_WAIT, de dieciséis bits.
ESPERA_CORTA = 32
for _n in range(1, ESPERA_CORTA + 1):
    assert globals()["OP_WAIT_%d" % _n] == OP_WAIT_1 + _n - 1, _n
assert OP_WAIT_1 == 8 * len(FAMILIAS)


def _es_de_voz(registro):
    return registro < 0x80 and registro & 0x0F < REGISTROS_DE_VOZ


def escrituras_del_arranque():
    """Lo que escribe `OP_INIT`: la tabla `dsp_init_*` que `emit` le deja a la
    ROM —el arranque sin KON ni KOF— y detrás KON y KOF en cero."""
    return ([(r, v) for r, v in init_writes() if r not in (sdsp.KON, sdsp.KOF)]
            + [(sdsp.KON, 0x00), (sdsp.KOF, 0x00)])


class _Codificador:
    """Arma el stream por nota de un tema. Lleva el mismo estado que el
    decodificador del 65816 —el caché de los registros de voz, el sonido de
    cada voz, el KON juntado del cuadro— y el mismo caché que `escrituras`,
    así que decide cada evento sabiendo exactamente qué escrituras va a
    producir."""

    def __init__(self):
        self.stream = bytearray()
        self.sonidos, self._sonido = [], {}
        self.state = {}             # el caché de `escrituras`
        self.sonido_de = {}         # el sonido de la última nota de cada voz

    def sonido(self, p):
        # En el orden en que se escriben —PITCH_L, PITCH_H, SRCN, ADSR1,
        # ADSR2—, que es lo que deja al 65816 recorrerlo con un solo índice.
        clave = (p.altura & 0xFF, p.altura >> 8, p.muestra, p.adsr1, p.adsr2,
                 0 if p.gain is None else p.gain)
        if clave not in self._sonido:
            self._sonido[clave] = len(self.sonidos)
            self.sonidos.append(clave)
        return self._sonido[clave]

    def cambia(self, registro, valor):
        return self.state.get(registro) != valor & 0xFF

    def escribir(self, registro, valor):
        self.state[registro] = valor & 0xFF

    def op(self, codigo, *datos):
        self.stream.extend((codigo,) + datos)

    def global_(self, registro, valor):
        """Una escritura cacheada fuera de las voces: va cruda si cambia."""
        assert not _es_de_voz(registro), registro
        if self.cambia(registro, valor):
            self.escribir(registro, valor)
            self.op(OP_DSP, registro, valor & 0xFF)

    def nota(self, p):
        v, base = p.voz, p.voz * 0x10
        s = self.sonido(p)
        if (not self.cambia(base + sdsp.V_VOL_L, p.izquierda)
                and not self.cambia(base + sdsp.V_VOL_R, p.derecha)):
            self.op(OP_NOTE_V0 + v, s)
        elif p.izquierda == p.derecha:
            self.op(OP_NOTE_VOL_V0 + v, p.izquierda, s)
        else:
            self.op(OP_NOTE_PAN_V0 + v, p.izquierda, p.derecha, s)
        self.sonido_de[v] = s
        for registro, valor in p.escrituras():
            self.escribir(registro, valor)

    def release(self, v, gain):
        base = v * 0x10
        if (not self.cambia(base + sdsp.V_ADSR1, 0)
                and not self.cambia(base + sdsp.V_GAIN, gain)):
            return                      # no escribiría nada
        if self.sonidos[self.sonido_de[v]][5] == gain:
            self.op(OP_RELEASE_V0 + v)
        else:
            self.op(OP_RELEASE_GAIN_V0 + v, gain)
        self.escribir(base + sdsp.V_ADSR1, 0)
        self.escribir(base + sdsp.V_GAIN, gain)

    def controles(self, control):
        por_voz = collections.defaultdict(dict)
        for registro, valor in control.items():
            assert _es_de_voz(registro), (
                "un controlador escribe $%02X, que no es de una voz" % registro)
            por_voz[registro >> 4][registro & 0x0F] = valor
        for v in sorted(por_voz):
            regs, base = por_voz[v], v * 0x10
            assert set(regs) in ({0, 1}, {2, 3}, {0, 1, 2, 3}), (
                "un controlador le escribe a la voz %d los registros %s: el "
                "formato sólo sabe del par de volumen y el de altura"
                % (v, sorted(regs)))
            if 0 in regs and (self.cambia(base, regs[0])
                              or self.cambia(base + 1, regs[1])):
                if regs[0] == regs[1]:
                    self.op(OP_SET_VOL_V0 + v, regs[0])
                else:
                    self.op(OP_SET_PAN_V0 + v, regs[0], regs[1])
                self.escribir(base, regs[0])
                self.escribir(base + 1, regs[1])
            if 2 in regs and (self.cambia(base + 2, regs[2])
                              or self.cambia(base + 3, regs[3])):
                self.op(OP_SET_PITCH_V0 + v, regs[2], regs[3])
                self.escribir(base + 2, regs[2])
                self.escribir(base + 3, regs[3])

    def esperar(self, cuadros):
        if 1 <= cuadros <= ESPERA_CORTA:
            self.op(OP_WAIT_1 + cuadros - 1)
        else:
            self.op(OP_WAIT, cuadros & 0xFF, cuadros >> 8)


def pack(frames, length, init):
    """El tema en el formato por nota: (stream, sonidos).

    `sonidos` son los que el tema toca, en el orden de sus índices: cada uno
    es (PITCH_L, PITCH_H, SRCN, ADSR1, ADSR2, GAIN del release), y el stream
    los nombra por índice. Lo que el stream produce en el DSP es
    **exactamente** `escrituras(frames, length, init)`, escritura por
    escritura y cuadro por cuadro; lo verifica `build_varios` con
    `decodificar`, que es el modelo del decodificador del 65816.
    """
    c = _Codificador()
    init = list(init)
    if [(r, v & 0xFF) for r, v in init] == escrituras_del_arranque():
        c.op(OP_INIT)
        for r, v in init:
            c.escribir(r, v)
    else:
        for r, v in init:
            c.global_(r, v)

    previo, sonando = 0, 0
    for at in sorted(frames):
        if at > length:
            break
        frame = frames[at]
        if not (frame.release or frame.setup or frame.kon or frame.kof
                or frame.control):
            continue
        if at > previo:
            c.esperar(at - previo)
            sonando = 0                 # el decodificador baja el KON al abrir
        previo = at
        c.global_(sdsp.KOF, 0x00)
        for voz, gain in frame.release:
            c.release(voz, gain)
        kon = 0
        for p in frame.setup:
            c.nota(p)
            kon |= 1 << p.voz
        c.controles(frame.control)
        if frame.kof:
            c.global_(sdsp.KOF, frame.kof)
        assert kon == frame.kon, "el KON del cuadro no es el de sus notas"
        sonando = kon

    # El final: `escrituras` baja KON y apaga todo en el cuadro `length`.
    if length > previo:
        c.esperar(length - previo)
        if not sonando:
            c.op(OP_DSP, sdsp.KON, 0x00)
    else:
        c.op(OP_WAIT, 0, 0)             # suelta el KON sin esperar
        c.op(OP_DSP, sdsp.KON, 0x00)
    c.op(OP_DSP, sdsp.KOF, 0xFF)
    c.op(OP_END)
    if len(c.sonidos) > 256:
        raise SystemExit("el tema usa %d sonidos y el índice es de un byte"
                         % len(c.sonidos))
    return bytes(c.stream), c.sonidos


def decodificar(stream, sonidos):
    """El modelo del decodificador del 65816 —`music_frame`, en
    rom/src/musica.s—, paso por paso: lo que el stream escribe, (cuadro,
    registro, valor), hasta su `OP_END`. Tiene que dar lo mismo que
    `escrituras`.

    Imita también lo que el 65816 **no** sabe. Su caché no tiene "vacío":
    al arrancar el tema tiene lo que haya quedado, y lo que lo reemplaza es
    que la primera nota de cada voz escribe todo sin mirarlo, y el primer
    release escribe su GAIN igual. Si el stream llegara a comparar contra un
    registro que nadie escribió todavía, en la consola estaría comparando
    contra basura: acá eso corta.
    """
    salen, cache, vistas, con_gain = [], {}, set(), set()
    gain_de = {}
    cuadro, kon, sonando, i = 0, 0, 0, 0

    def w(registro, valor):
        salen.append((cuadro, registro, valor))

    def escribir(registro, valor, forzar=False):
        if not forzar:
            assert registro in cache, (
                "el stream compara el registro $%02X contra el caché antes "
                "de escribirlo: en la ROM sería basura" % registro)
            if cache[registro] == valor:
                return
        cache[registro] = valor
        w(registro, valor)

    def leer():
        nonlocal i
        i += 1
        return stream[i - 1]

    while True:
        op = leer()
        if op == OP_END:
            return salen
        if op == OP_INIT:
            for r, v in escrituras_del_arranque():
                w(r, v)
            continue
        if op == OP_DSP:
            r, v = leer(), leer()
            assert not _es_de_voz(r)
            w(r, v)
            continue
        if op == OP_WAIT or OP_WAIT_1 <= op < OP_WAIT_1 + ESPERA_CORTA:
            if op == OP_WAIT:
                n = leer()
                n |= leer() << 8
            else:
                n = op - OP_WAIT_1 + 1
            if kon:
                w(sdsp.KON, kon)
                sonando, kon = kon, 0
            if n:
                cuadro += n
                if sonando:
                    w(sdsp.KON, 0)
                    sonando = 0
            continue
        assert op < OP_WAIT_1, "opcode $%02X" % op
        familia, v = FAMILIAS[op >> 3], op & 7
        base = v * 0x10
        if familia.startswith("NOTE"):
            # La primera nota de la voz escribe todo: ver arriba.
            forzar = v not in vistas
            vistas.add(v)
            if familia == "NOTE_VOL":
                vol = leer()
                escribir(base + sdsp.V_VOL_L, vol, forzar)
                escribir(base + sdsp.V_VOL_R, vol, forzar)
            elif familia == "NOTE_PAN":
                izq, der = leer(), leer()
                escribir(base + sdsp.V_VOL_L, izq, forzar)
                escribir(base + sdsp.V_VOL_R, der, forzar)
            sonido = sonidos[leer()]
            for k in range(5):          # de PITCH_L a ADSR2, en ese orden
                escribir(base + sdsp.V_PITCH_L + k, sonido[k], forzar)
            gain_de[v] = sonido[5]
            kon |= 1 << v
        elif familia.startswith("RELEASE"):
            gain = leer() if familia == "RELEASE_GAIN" else gain_de[v]
            escribir(base + sdsp.V_ADSR1, 0)
            escribir(base + sdsp.V_GAIN, gain, v not in con_gain)
            con_gain.add(v)
        elif familia == "SET_VOL":
            vol = leer()
            escribir(base + sdsp.V_VOL_L, vol)
            escribir(base + sdsp.V_VOL_R, vol)
        elif familia == "SET_PAN":
            izq, der = leer(), leer()
            escribir(base + sdsp.V_VOL_L, izq)
            escribir(base + sdsp.V_VOL_R, der)
        elif familia == "SET_PITCH":
            lo, hi = leer(), leer()
            escribir(base + sdsp.V_PITCH_L, lo)
            escribir(base + sdsp.V_PITCH_H, hi)
        else:
            raise AssertionError("opcode $%02X" % op)


def verificar_formato(nombre, stream, sonidos, referencia):
    """Que el stream de un tema, decodificado, escriba lo mismo que
    `escrituras`: cada registro, cada valor, en el mismo orden y el mismo
    cuadro. Se corta el conversor en la primera diferencia."""
    salen = decodificar(stream, sonidos)
    if salen == referencia:
        return
    for n, (a, b) in enumerate(zip(salen, referencia)):
        if a != b:
            break
    else:
        n = min(len(salen), len(referencia))
    raise SystemExit(
        "el stream de %s no escribe lo que tiene que escribir: la escritura "
        "%d es %s y tenía que ser %s (cuadro, registro, valor)"
        % (nombre, n, salen[n] if n < len(salen) else "ninguna",
           referencia[n] if n < len(referencia) else "ninguna"))


def tema_del_mapa(map_id, game_dir=GAME_DIR):
    """El nombre del tema que le toca a un mapa por el árbol, o "" si no tiene."""
    return temas_de_los_mapas([map_id], game_dir)[0]


def temas_de_los_mapas(map_ids, game_dir=GAME_DIR):
    """`tema_del_mapa` de cada uno, leyendo el árbol una sola vez.

    "" quiere decir que entrar al mapa **no cambia** lo que suena: o el mapa
    no trae tema —la raíz del árbol—, o es el `music_type` 1, "lo decide un
    evento". Es el `return` temprano de `Game_Map::PlayBgm` en easyrpg. Un
    "(OFF)" sí es un tema: calla, igual que un `PlayBGM` de "(OFF)".
    """
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    nombres = []
    for map_id in map_ids:
        music = tree.map_music(map_id)
        nombres.append(music["name"] if music else "")
    return nombres


def leer_tema(name, game_dir=GAME_DIR):
    """Lo que hay que saber de un tema **antes** de tener el banco.

    Devuelve None si el nombre no está o no es un MIDI, que es como un mapa sin
    música: el tema entra igual en la numeración —el bytecode ya lleva su
    índice— pero su stream es un `OP_END` solo y la ROM sale muda cuando lo
    prenden.
    """
    path = (find_resource([game_dir], "Music", name, (".mid", ".wav"))
            if name else None)
    if not path or not path.lower().endswith(".mid"):
        return None
    notes, tempos, division, programs, controls = midi.read(path)
    voices = assign(notes)
    largo = musica.timeline(notes, tempos, division)
    musica.timeline(controls, tempos, division)
    return {
        "nombre": name,
        "notas": notes,
        "controles": controls,
        "largo": largo,
        "voces": voices,
        "programas": programs,
        # Lo que aporta al banco compartido: los programas de sus canales
        # melódicos y las teclas de percusión que toca.
        "melodicos": {programs.get(c, 0) for c in voices
                      if c != midi.DRUM_CHANNEL},
        "golpes": {n.pitch for n in notes if n.channel == midi.DRUM_CHANNEL},
    }


# --- el techo de cada tema --------------------------------------------------

# El aire de cada tema que recortaría con el de `sdsp.AIRE`: la opción B del
# paso 5 de `workflow/tasks/todo/la-calidad-de-la-musica.md`, elegida por taro
# el 2026-09-26. El DSP suma las ocho voces y satura la suma a 16 bits antes
# del volumen general, así que lo único que evita el recorte es el techo de
# cada voz; con uno solo para todos, lo fija el tema que más suma —`rshinld`,
# por su CC7 en 127— y los que no recortan bajan casi 4 dB sin necesidad. Con
# uno por tema, cada uno baja lo justo.
#
# **No se escribe a mano**: lo mide `tools/audio/techos.py` (`just techos`)
# tocando cada tema en la ROM, y lo que queda es un dato versionado, como las
# decisiones de `parches/auto/`. Un tema que no está en la tabla va con
# `sdsp.AIRE`. Cada cambio de la mezcla —las muestras, las envolventes, el
# reparto— la deja vieja, y eso lo cobra `test_musica_techos.py`.
TECHOS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "parches", "auto", "musica", "techos.toml")


def leer_techos(ruta=TECHOS):
    """{tema: aire} de la tabla versionada; vacío si no existe."""
    import tomllib
    try:
        with open(ruta, "rb") as archivo:
            tabla = tomllib.load(archivo)
    except FileNotFoundError:
        return {}
    return {nombre: fila["aire"] for nombre, fila in tabla["temas"].items()}


def huella_de_la_mezcla(escrituras_del_tema, banco):
    """De qué depende el pico de un tema, resumido: lo que le escribe al DSP
    —con su aire ya puesto— y las muestras que toca, con su loop. Lo que
    cambie esto puede mover el pico, y la tabla de techos lo guarda para que
    la prueba sepa si lo que se midió sigue siendo lo que suena. El driver
    no entra: no mezcla nada, pasa escrituras."""
    import hashlib
    h = hashlib.sha256(repr(escrituras_del_tema).encode())
    muestras = sorted({valor for _c, registro, valor in escrituras_del_tema
                       if registro < 0x80
                       and registro & 0x0F == sdsp.V_SRCN})
    for i in muestras:
        if i < len(banco.voces):
            v = banco.voces[i]
            h.update(b"%d:%d:" % (i, v.loop_block or 0) + bytes(v.data))
    return h.hexdigest()[:16]


def _enteros_entran(banco, paquetes, herencia, efectos, presupuestado,
                    nombres):
    """Que lo que los `SE_ENTEROS` ocupan de más entre, en cada paquete, en
    lo que la música dejó libre: el banco ya está repartido sin contarlo, así
    que si no entra no hay a quién sacárselo sin bajarle la tasa a un
    instrumento, y el conversor se corta diciendo cuál.

    Y dice —sin cortarse— con qué tema que puede venir sonando los efectos de
    un paquete entraban al lado con el tamaño de siempre y enteros ya no: ahí
    esperan al próximo `PlayBGM` (ver
    `decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md`)."""
    claves_de = {}
    for paquete in paquetes:
        nombre, suyos = paquete[0], paquete[1]
        claves_de[nombre] = set().union(
            *[set(banco.asignacion[t].values()) for t in suyos])
    no_entran = []
    banco.enteros_de_mas = {}
    for paquete in paquetes:
        nombre, suyas = paquete[0], set(paquete[2]) & set(efectos)
        enteros = sorted(e for e in suyas
                         if e in SE_ENTEROS and e not in SE_ENTEROS_PAGADOS)
        if not enteros:
            continue
        ocupan = sum(len(efectos[e].data) for e in suyas)
        banco.enteros_de_mas[str(nombre)] = ocupan - sum(presupuestado[e]
                                                         for e in suyas)
        musica = banco.ocupa(claves_de[nombre])
        if musica + ocupan > banco.libre:
            no_entran.append("%s en el paquete %s (%d B de más)" % (
                ", ".join(enteros), nombre, musica + ocupan - banco.libre))
    if no_entran:
        raise SystemExit(
            "los efectos enteros no entran sin bajarle la tasa a un "
            "instrumento: %s. Bajarles la tasa en SE_ENTEROS, o sacarlos"
            % "; ".join(no_entran))
    efectos_de = {p[0]: set(p[2]) & set(efectos) for p in paquetes}
    for nombre, heredado in herencia:
        suyas = efectos_de[nombre]
        if not any(e in SE_ENTEROS and e not in SE_ENTEROS_PAGADOS
                   for e in suyas):
            continue
        musica = banco.ocupa(claves_de[nombre]
                             | set(banco.asignacion[heredado].values()))
        antes = musica + sum(presupuestado[e] for e in suyas)
        ahora = musica + sum(len(efectos[e].data) for e in suyas)
        if antes <= banco.libre < ahora:
            print("  con %s sonando, los efectos enteros del paquete %s no "
                  "entran al lado: esperan al PlayBGM"
                  % (nombres[heredado], nombre))


def build_varios(nombres, game_dir=GAME_DIR, efectos=(), paquetes=None,
                 herencia=(), techos=None, aire_de_medida=None):
    """Todos los temas de la ROM, compartiendo un solo banco de muestras.

    Devuelve (driver, las voces —las del banco y detrás los efectos, cada una
    con su número de muestra—, temas, banco). Hay un dict por tema en el
    orden en que vinieron: los índices son los de `Temas`, el bytecode ya los
    lleva emitidos, así que **no se pueden reordenar**.

    **Todos los temas pedidos salen en el cartucho, y todos con todas sus
    muestras.** Un índice no cuesta ARAM: cuesta su stream, que vive en el
    cartucho. Lo que compite por la ARAM son las muestras, y eso se reparte
    por paquete: ver `Banco` y `repartir`.

    `paquetes` son los de la ROM, por nombre: (nombre, índices de sus temas,
    nombres de sus efectos[, índices de sus temas de salida]). Cada uno
    tiene que entrar solo en la ARAM, con sus efectos, y lo que ocupan sus
    efectos se resta antes de repartir; cada tema de salida —ver
    `Temas.de_salida` en tools/port/eventos.py— tiene que entrar solo. Si
    no viene, cada tema es un paquete sin efectos.

    `herencia` son pares (nombre de un paquete, índice de un tema que puede
    venir sonando al cargarlo). `paquete_cargar_ya` no mueve las muestras
    del tema que suena, así que las del paquete tienen que entrar al lado;
    **los efectos no**: si no entran, esperan al próximo `PlayBGM`, que
    completa el paquete —ver `tema_asegurar`—. Es la decisión
    `workflow/decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md`.

    `techos` es el aire de cada tema, por nombre —si no viene, el que está
    versionado: ver `leer_techos`—, y `aire_de_medida` lo pisa para todos: es
    con lo que `tools/audio/techos.py` arma la ROM en que mide los picos.
    """
    driver = spc700.assemble(DRIVER, DRIVER_ADDR)
    if techos is None:
        techos = leer_techos()
    leidos = [leer_tema(n, game_dir) for n in nombres]
    teclas = zonas_mas_usadas(leidos)
    claves_de = [claves_del_tema(t, teclas) for t in leidos]
    # Los efectos van **todos**: cuáles caben lo decide la ROM mapa por mapa,
    # al armar su paquete de audio. Se arman antes que el banco porque lo que
    # ocupan los de cada paquete es lo primero que se resta.
    efectos_hechos = build_efectos(list(efectos), game_dir, 1 << 30)
    lista = sorted(efectos_hechos.values(), key=lambda e: list(efectos).index(
        e.name) if e.name in efectos else 0)
    # Lo que la música le presupuesta a cada efecto: el de siempre, aunque
    # vaya entero. Ver `SE_ENTEROS`.
    presupuestado = {n: len(e.data) for n, e in efectos_hechos.items()}
    for n in efectos_hechos:
        if n in SE_ENTEROS and n not in SE_ENTEROS_PAGADOS:
            presupuestado[n] = len(build_efecto(n, game_dir, enteros={}).data)

    # Las claves que el SoundFont tiene; las demás no suenan en ningún lado.
    claves_de = [{k for k in ks if _muestra(k, NATIVA) is not None}
                 for ks in claves_de]
    if paquetes is None:
        paquetes = [(nombre, [i], []) for i, nombre in enumerate(nombres)]
    # Qué tiene que entrar junto: cada paquete con sus efectos; cada tema de
    # salida solo —lo sube su `PlayBGM`, callando lo demás: ver
    # `extra_de_salida` en rom/src/paquete_de_audio.s—; y cada paquete con
    # el tema que puede venir sonando, sin sus efectos.
    grupos, temas_de = [], {}
    for paquete in paquetes:
        nombre, suyos, suyas = paquete[:3]
        salida = paquete[3] if len(paquete) > 3 else ()
        temas_de[nombre] = list(suyos)
        ocupan = sum(presupuestado[e] for e in set(suyas)
                     if e in efectos_hechos)
        grupos.append(Grupo(str(nombre), tuple(suyos), ocupan))
        for t in salida:
            grupos.append(Grupo("%s>%s" % (nombre, nombres[t]), (t,), 0))
    for nombre, heredado in herencia:
        grupos.append(Grupo("%s+%s" % (nombre, nombres[heredado]),
                            tuple(temas_de[nombre]) + (heredado,), 0))
    asignacion = copias(claves_de, grupos, len(lista))
    todas = {k for a in asignacion for k in a.values()}
    libre = libre_para(len(todas), len(lista))
    banco = Banco(todas, restricciones_de(asignacion, grupos, libre))
    banco.libre = libre
    banco.asignacion = asignacion
    _enteros_entran(banco, paquetes, herencia, efectos_hechos, presupuestado,
                    nombres)

    temas = []
    for nombre, leido, suya in zip(nombres, leidos, asignacion):
        if leido is None:
            temas.append({"nombre": nombre, "stream": bytes([OP_END]),
                          "sonidos": [], "escrituras": [],
                          "segundos": 0.0, "resumen": {}})
            continue
        reparto = []
        aire = aire_de_medida or techos.get(nombre, sdsp.AIRE)
        del_tema = banco.del_tema(suya)
        frames = build_events(leido["notas"], leido["voces"],
                              leido["programas"], del_tema,
                              leido["controles"], reparto, aire)
        referencia = escrituras(frames, leido["largo"], init_writes())
        stream, sonidos = pack(frames, leido["largo"], init_writes())
        verificar_formato(nombre, stream, sonidos, referencia)
        temas.append({"nombre": nombre, "stream": stream, "sonidos": sonidos,
                      "escrituras": referencia, "aire": aire,
                      "huella": huella_de_la_mezcla(referencia, banco),
                      "segundos": leido["largo"] / TICKS_PER_SECOND,
                      "resumen": resumen_del_tema(leido, del_tema, reparto)})
    # Los efectos van detrás del banco en el mismo directorio: su `V_SRCN` es
    # el lugar que les toca después de las muestras de la música.
    banco.efectos = {e.name: (len(banco.voces) + i, e)
                     for i, e in enumerate(lista)}
    return (driver, list(banco.voces) + lista, temas, banco)


def resumen_del_tema(leido, banco, reparto=()):
    """Lo que imprime la receta: voces, timbres y cuánto se llega a tocar."""
    voices, programs = leido["voces"], leido["programas"]
    return {
        "voices": {c: v for c, v in sorted(voices.items())},
        "sounds": {c: programs.get(c, 0)
                   for c in sorted(voices) if c != midi.DRUM_CHANNEL},
        "bank": ["%s (%.0f Hz, %d B)" % (v.name.strip(), v.rate, len(v.data))
                 for v in banco.voces],
        # Cuánto del tiempo-nota se pierde por falta de voces, y cuánto se
        # perdería sin remedio con ocho: ver `tiempo_perdido`.
        "perdido": tiempo_perdido(reparto),
        # Y cuántas de sus notas llegan al stream. Una nota cuyo programa no
        # está en el banco **no suena más bajo: no existe** —el `continue` de
        # `build_events`—, así que esto es la voz que el jugador no oye. Es un
        # número distinto de `perdido`, que mide la polifonía; hasta el
        # 2026-09-26 ése era `coverage`, una cuenta del reparto fijo por canal,
        # y se confundieron el 2026-09-14: por un rato pareció que compartir
        # el banco no costaba nada, porque `coverage` daba igual con el banco
        # entero o compartido.
        "notas": notas_que_suenan(leido, banco),
    }


def tiempo_perdido(reparto):
    """(lo que se pierde, el piso): qué fracción del tiempo-nota de las notas
    con muestra no suena por falta de voces, y qué fracción no podría sonar
    con ninguna regla —lo que pasa de ocho notas a la vez—.

    El tiempo-nota es lo que la nota sostiene su voz: del arranque al fin en
    el MIDI, o al fin de la muestra si es un golpe que se acaba antes. Se
    pierde entero si la nota no consigue voz, y desde que se la roban si le
    roban la suya antes de ese fin. La cola del release no cuenta: no está en
    el MIDI. Es la cuenta del prototipo, que en `escape_newyork` dio 55% con
    el reparto fijo por canal contra un piso de 23%.
    """
    total = perdido = 0
    tramos = []
    for nota, voz, robada, fin in reparto:
        largo = fin - nota.start
        total += largo
        tramos.append(_Tramo(nota.start, fin))
        if voz is None:
            perdido += largo
        elif robada is not None:
            perdido += max(0, fin - robada)
    spans = musica.note_time(tramos)
    piso = sum(max(0, n - sdsp.VOICES) * cuadros for n, cuadros in spans.items())
    return perdido / float(max(1, total)), piso / float(max(1, total))


_Tramo = collections.namedtuple("_Tramo", "start end")


def notas_que_suenan(leido, banco):
    """Qué fracción de las notas del MIDI tiene su muestra en el banco."""
    total = suenan = 0
    for nota in leido["notas"]:
        if nota.channel not in leido["voces"]:
            continue
        total += 1
        if nota.channel == midi.DRUM_CHANNEL:
            suenan += banco.golpes.get(nota.pitch) is not None
        else:
            programa = leido["programas"].get(nota.channel, 0)
            suenan += banco.melodicas.get(programa) is not None
    return suenan / max(1, total)


def tabla_de_sonidos(sonidos, banco):
    """Una fila por entrada de `Temas.sonidos`: la muestra —$FF si no entró—,
    la altura, el volumen de cada lado y cuántos cuadros dura."""
    filas = []
    efectos = getattr(banco, "efectos", {}) if banco is not None else {}
    for nombre, volumen, tempo, balance in sonidos:
        hecho = efectos.get(nombre)
        if hecho is None:
            filas.append((0xFF, 0, 0, 0, 0))
            continue
        srcn, efecto = hecho
        izquierda, derecha = volumen_de_efecto(volumen, balance)
        filas.append((srcn, altura_de_efecto(efecto, tempo), izquierda,
                      derecha, cuadros_de_efecto(efecto, tempo)))
    return filas


# El silencio: un bloque BRR con los bits de fin y de loop, y ocho bytes en
# cero. Es adonde apunta en el directorio toda muestra que no está en la ARAM.
SILENCIO = bytes([0x03]) + bytes(8)
# Y hasta dónde se sube: los últimos 64 bytes de la ARAM son los que la ROM de
# arranque tapa cuando está prendida, y así el tope entra en dieciséis bits.
ARAM_FIN = 0x10000 - 64


def muestras_del_tema(tema):
    """Qué muestras usa un tema: los valores que su stream escribe en los
    registros SRCN de las voces. Es lo que la ROM tiene que tener en la ARAM
    para tocarlo, sacado de lo que el tema hace —su stream, decodificado— y
    no de cómo se armó."""
    return sorted({valor for _cuadro, registro, valor
                   in decodificar(tema["stream"], tema["sonidos"])
                   if _es_de_voz(registro)
                   and registro & 0x0F == sdsp.V_SRCN})


# Lo que cuesta subir al SPC700, en cuadros, para la cuenta del arranque. Las
# muestras de un paquete van de a ternas por el comando 3 del driver —ver
# `subir_muestra` en rom/src/paquete_de_audio.s—: medido en la ROM el
# 2026-09-26, de 1,33 a 1,42 cuadros por KB en dieciocho paquetes, y acá va
# un poco más. El driver y el directorio van byte a byte por el IPL, que
# medía 1,4. Y cargar el mapa, sin audio y sin descomprimir, son unos 8
# cuadros (medido con el mapa 6 de `test-special`, que no tiene paquete); acá
# van 10. Lo que cuesta descomprimir depende del mapa y va aparte.
CUADROS_POR_KB_PAQUETE = 1.45
CUADROS_POR_KB_IPL = 1.5
CUADROS_DEL_MAPA = 10
# Dónde vive `BOOT_CUADROS`, que es de la ROM y no de acá.
RAM_LEJANA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "rom", "src", "ram_lejana.s")


def cuadros_del_arranque(driver, voces, temas, paquete, descomprimir=0.0):
    """Cuánto tarda el arranque, por lo alto: el mapa, el driver y el
    directorio por el IPL, y las muestras del paquete del mapa de arranque
    —(índices de temas, índices de muestras de efectos, temas de salida), el
    de `emit`—. Los de salida cuentan: se suben si hay lugar, y con la ARAM
    vacía lo hay. `descomprimir` son los cuadros que se lleva descomprimir los
    bloques LZ2 del mapa de arranque, que `CUADROS_DEL_MAPA` no cuenta: ver
    `cuadros_de_descomprimir` en snes_convert.py.
    Devuelve (cuadros, bytes del paquete)."""
    suyos, efectos = paquete[:2]
    salida = paquete[2] if len(paquete) > 2 else ()
    indices = set(efectos)
    for t in list(suyos) + list(salida):
        if temas[t]["sonidos"]:
            indices |= set(muestras_del_tema(temas[t]))
    del_paquete = sum(len(voces[i].data) for i in indices)
    ipl = len(driver) + 4 * max(1, len(voces)) + len(SILENCIO)
    return (CUADROS_DEL_MAPA + descomprimir
            + ipl * CUADROS_POR_KB_IPL / 1024.0
            + del_paquete * CUADROS_POR_KB_PAQUETE / 1024.0, del_paquete)


def boot_cuadros(ruta=RAM_LEJANA):
    """El `BOOT_CUADROS` de la ROM, leído del fuente."""
    import re
    with open(ruta) as archivo:
        return int(re.search(r"^BOOT_CUADROS\s*=\s*(\d+)", archivo.read(),
                             re.M).group(1))


def emit(path, temas, driver, voces, arranque=0xFF, titulo=0xFF,
         sonidos=(), paquetes=(), tema_de_mapa=()):
    """El .inc que arma el ensamblador junto con main.s.

    `temas` son los de `build_varios`, en el orden de `Temas`: el bytecode ya
    lleva esos índices emitidos. `arranque` es cuál suena desde el primer
    cuadro, o $FF si la ROM arranca callada y lo prende un `PlayBGM`.

    `voces` son todas las muestras del cartucho, numeradas: las de la música y
    detrás los efectos. Ninguna se sube al arrancar: van al SPC700 de a
    **paquetes**, uno por mapa —`paquetes`, en el orden de la tabla de mapas,
    cada uno con sus temas, las muestras de sus efectos y sus temas de
    salida—, y el directorio
    arranca con todas apuntando al silencio. Ver `paquete_cargar` en rom/src/paquete_de_audio.s.

    `tema_de_mapa` es el tema que prende cada mapa al entrar, en el mismo
    orden, o $FF si entrar no cambia lo que suena. Ver `mapa_tema_callar`.
    """
    def block(label, data, bloque=False):
        # Sin `.bloque` salvo en las muestras: eso es relleno para que un DMA
        # no cruce de banco, y nada de acá se sube por DMA. El driver va byte a
        # byte por los puertos —`spc_block` hace el salto de banco a mano— y el
        # stream lo recorre `advance`, que hace el mismo salto. Las muestras sí
        # lo llevan, y no por el DMA: `subir_a_aram` las recorre con un puntero
        # de 24 bits que no salta de banco, a cambio de ser más corta.
        out = ([".bloque %d" % len(data)] if bloque else []) + ["%s:" % label]
        for i in range(0, len(data), 16):
            out.append("    .byte " + ",".join("$%02X" % b for b in data[i:i + 16]))
        return "\n".join(out)

    etiquetas = ["tema_stream_%d" % i for i in range(len(temas))] or \
        ["tema_stream_0"]
    streams = [t["stream"] for t in temas] or [bytes([OP_END])]
    tabla = "\n".join(
        "%s:\n    .byte %s" % (nombre, ", ".join(prefijo + e for e in etiquetas))
        for nombre, prefijo in (("tema_lo", "<"), ("tema_hi", ">"),
                                ("tema_bk", "^")))
    # El prólogo del DSP, para el camino del MSU-1. Con pista el stream no
    # corre nunca, y es el comienzo del stream el que saca al DSP del mute con
    # que arranca el SPC700, le pone el volumen general y le dice dónde está el
    # directorio de muestras. Sin esto los efectos de sonido se disparan contra
    # un DSP mudo y no se oyen.
    #
    # KON y KOF quedan afuera a propósito: con pista, la ROM deja KOF en $FF
    # para que las voces de la música no suenen, y `se_despues` lo limpia solo
    # cuando arranca un efecto. Escribir acá KOF en cero volvería a encender
    # las voces de un tema que no está sonando.
    #
    # Van en dos tablas paralelas y no en una de pares porque el 65816 las
    # recorre con un índice: `lda dsp_init_reg, y`.
    init = [(r, v) for r, v in init_writes()
            if r not in (sdsp.KON, sdsp.KOF)]
    tabla += "\ndsp_init_reg:\n    .byte " + ", ".join(
        "$%02X" % r for r, _ in init) + ", $FF"
    tabla += "\ndsp_init_val:\n    .byte " + ", ".join(
        "$%02X" % v for _, v in init) + ", $00"
    # Y qué pista de MSU-1 le toca a cada uno, o $FF: ver PISTAS_MSU.
    tabla += "\ntema_msu:\n    .byte " + ", ".join(
        "$%02X" % PISTAS_MSU.get(t["nombre"], 0xFF)
        for t in (temas or [{"nombre": ""}]))
    # Y el tema propio de cada mapa. Fuera del banco 0: se lee una vez por
    # teletransporte, con `lda f:mapa_tema, x`.
    tabla_mapa_tema = "mapa_tema:\n    .byte " + ", ".join(
        "$%02X" % t for t in (list(tema_de_mapa) or [0xFF]))
    # Y los sonidos de la música —los de `pack`: seis bytes, la altura,
    # SRCN, ADSR1, ADSR2 y el GAIN del release—, los de todos los temas en una
    # tabla y dónde empiezan los de cada uno. En un solo banco, porque
    # `music_frame` llega con `lda f:musica_sonidos, x` y la X de dieciséis
    # bits no cruza de banco.
    cuerpo, bases = bytearray(), []
    for t in temas:
        bases.append(len(cuerpo))
        for sonido in t["sonidos"]:
            cuerpo += bytes(sonido)
    if len(cuerpo) > 0x8000:
        raise SystemExit("los sonidos de la música pasan de un banco: %d B"
                         % len(cuerpo))
    tabla_mapa_tema += ("\ntema_sonidos:\n    .word "
                        + ", ".join("%d" % b for b in bases or [0]) + "\n"
                        + block("musica_sonidos", bytes(cuerpo) or bytes(6),
                                bloque=True))
    # Y los efectos de sonido: siete bytes por entrada de `Temas.sonidos`.
    # Fuera del banco 0: `op_sound` los lee con `lda f:sonido_tabla, x`.
    filas = list(sonidos) or [(0xFF, 0, 0, 0, 0)]
    tabla_se = "sonido_tabla:\n" + "\n".join(
        "    .byte $%02X, <%d, >%d, %d, %d, <%d, >%d" % (
            srcn, altura, altura, izquierda, derecha, cuadros, cuadros)
        for srcn, altura, izquierda, derecha, cuadros in filas)

    # El directorio del SPC700, con todas en el silencio, y el silencio
    # detrás. Es lo único que sube `spc_upload` además del driver.
    n = max(1, len(voces))
    if n > 255:
        raise SystemExit("hay %d muestras y el SRCN es de un byte" % n)
    silencio = SAMPLES_ADDR + 4 * n
    datos = silencio + len(SILENCIO)
    samples = (silencio.to_bytes(2, "little") * 2) * n + SILENCIO
    # Cada muestra, suelta, y su fila: el puntero, cuánto mide y dónde vuelve.
    muestras = [block("muestra_%d" % i, v.data, bloque=True)
                for i, v in enumerate(voces)] or [block("muestra_0", SILENCIO)]
    filas_m = []
    for i, v in enumerate(voces or [None]):
        largo = len(v.data) if v is not None else len(SILENCIO)
        loop = v.loop_block * muestras_brr.BLOQUE_BYTES if v is not None else 0
        filas_m.append("    .byte <(muestra_%d), >(muestra_%d), ^(muestra_%d), "
                       "<%d, >%d, <%d, >%d" % (i, i, i, largo, largo, loop, loop))
    # Qué muestras usa cada tema, y el paquete de cada mapa. Dos bloques con
    # un índice de desplazamientos adelante, y cada lista cerrada con $FF.
    def listas(label, grupos):
        cuerpo, ofs = bytearray(), []
        for grupo in grupos:
            ofs.append(2 * len(grupos) + len(cuerpo))
            for parte in grupo:
                cuerpo += bytes(parte) + b"\xFF"
        datos_ = b"".join(o.to_bytes(2, "little") for o in ofs) + bytes(cuerpo)
        return block(label, datos_ or b"\xFF", bloque=True)
    tema_muestras = listas("tema_muestras",
                           [[muestras_del_tema(t)] for t in temas] or [[[]]])
    # Cada paquete, tres listas: sus temas, las muestras de sus efectos y sus
    # temas de salida —ver `extra_de_salida` en rom/src/paquete_de_audio.s—.
    paquetes = [tuple(p) + ((),) * (3 - len(p)) for p in paquetes] or \
        [([], [], [])]
    bloque_paquetes = listas("paquetes", [[list(t), list(m), list(s)]
                                           for t, m, s in paquetes])

    with open(path, "w") as handle:
        handle.write(
            "; Generado por tools/audio/snes_music.py. No editar.\n"
            "; Temas: %s\n\n"
            "; Cuántos temas lleva el cartucho y cuál suena desde el arranque.\n"
            "; Los índices son los de `Temas` en eventos.py, o sea los que el\n"
            "; bytecode de los PlayBGM ya trae emitidos.\n"
            "; $FF en TEMA_ARRANQUE es 'la ROM arranca callada': el tema del\n"
            "; mapa donde arranca no existe, así que lo tiene que prender un\n"
            "; evento.\n"
            "TEMA_TOTAL       = %d\n"
            "TEMA_ARRANQUE    = $%02X\n"
            "; Y el de la pantalla de título, que sale de `title_music` del\n"
            "; LDB. $FF quiere decir que esta ROM no lleva pantalla de título.\n"
            "TEMA_TITULO      = $%02X\n"
            "; El volumen general con que suena el tema y los dos registros\n"
            "; del DSP donde va. Los emite `sdsp.py`, que es de donde salen:\n"
            "; el stream ya los escribe al arrancar, y un `FadeOutBGM` los\n"
            "; vuelve a escribir bajándolos. Escribirlos también en rom/src/\n"
            "; serían dos lados que se pueden equivocar igual.\n"
            "TEMA_VOLUMEN     = $%02X\n"
            "DSP_MVOL_L       = $%02X\n"
            "DSP_MVOL_R       = $%02X\n"
            "SPC_DRIVER_ADDR  = $%04X\n"
            "SPC_DRIVER_SIZE  = %d\n"
            "SPC_SAMPLES_ADDR = $%04X\n"
            "SPC_SAMPLES_SIZE = %d\n"
            "; Las muestras van al SPC700 de a paquetes: ver `paquete_cargar`.\n"
            "; El directorio está en SPC_SAMPLES_ADDR, el silencio detrás, y\n"
            "; las muestras se acomodan entre ARAM_DATOS y ARAM_FIN.\n"
            "MUESTRAS_N       = %d\n"
            "ARAM_SILENCIO    = $%04X\n"
            "ARAM_DATOS       = $%04X\n"
            "ARAM_FIN         = $%04X\n"
            "PAQUETES_N       = %d\n"
            "; Los efectos de sonido: en qué voz suenan y cuántas entradas\n"
            "; tiene `sonido_tabla`. Ver `build_efectos`.\n"
            "SE_VOZ           = %d\n"
            "SE_BIT           = $%02X\n"
            "SE_REG           = $%02X\n"
            "SE2_BIT          = $%02X\n"
            "SE2_REG          = $%02X\n"
            "SONIDOS_N        = %d\n\n"
            "; Dónde arranca el stream de cada tema, partido en tres tablas\n"
            "; porque se leen con un índice: van en el banco 0 como todo lo\n"
            "; que la CPU recorre con `lda tabla, x`.\n"
            '.segment "TABLAS"\n%s\n\n'
            '.segment "RODATA"\n%s\n%s\n%s\n%s\n'
            '.bloque %d\nmuestra_tabla:\n%s\n%s\n%s\n%s\n%s\n'
            % (", ".join(t["nombre"] or "sin música" for t in temas)
               or "ninguno",
               len(temas), arranque, titulo,
               sdsp.MASTER, sdsp.MVOL_L, sdsp.MVOL_R,
               DRIVER_ADDR, len(driver),
               SAMPLES_ADDR, len(samples),
               n, silencio, datos, ARAM_FIN, len(paquetes),
               SE_VOZ, 1 << SE_VOZ, SE_VOZ * 16, 1 << SE_VOZ2, SE_VOZ2 * 16,
               len(list(sonidos)),
               tabla, tabla_se, tabla_mapa_tema,
               block("spc_driver", driver),
               block("spc_samples", samples),
               7 * len(filas_m), "\n".join(filas_m),
               tema_muestras, bloque_paquetes,
               "\n".join(muestras),
               "\n".join(block(e, st) for e, st in zip(etiquetas, streams))))
