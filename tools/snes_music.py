#!/usr/bin/env python3
"""Convierte el MIDI de un mapa a muestras BRR y un stream para el S-DSP.

Es el equivalente de musica.py para la Super Nintendo, y comparte con él todo
lo que no depende del chip: leer el MIDI, pasar los tiempos a cuadros y repartir
las voces entre los canales según cuánta cobertura gana cada una.

Lo que cambia es el final. El YM2612 pide construir cada timbre con cuatro
operadores; el S-DSP pide una forma de onda, que está en sdsp.py. Y son ocho
voces contra las nueve de la Mega Drive —seis de FM más tres del PSG—, sólo que
acá las ocho son iguales y buenas, en vez de seis decentes y tres de onda
cuadrada.

Salen dos cosas: el bloque que se sube a la memoria del SPC700 (el directorio
de muestras más las muestras en BRR) y el stream de escrituras al DSP, que el
65816 va escupiendo cuadro a cuadro.

Uso:
    python3 tools/snes_music.py --map-id 67 -o rom/build/inc/musicdata.inc
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bancos
import lcf
import musica
import midi
import muestras_brr
import sdsp
import snes_samples
import spc700
from render_map import GAME_DIR, REPO, find_resource

TICKS_PER_SECOND = musica.TICKS_PER_SECOND

# Dónde vive cada cosa en los 64 KB del SPC700. Los primeros $200 bytes se los
# queda la ROM de arranque para sus variables, así que se empieza más arriba.
DRIVER_ADDR = 0x0200
SAMPLES_ADDR = 0x0400

BLOQUE = muestras_brr.BLOQUE_MUESTRAS   # 16 muestras por bloque de BRR

# Y cuánto queda para las muestras: de $0400 hasta el final de los 64 KB.
# Entero, sin reserva: el eco está apagado —FLG con el bit de "no escribir el
# buffer"— y la pila del SPC700 vive en $0100, o sea debajo. Es el límite que
# decide cuántos temas entran, porque el banco es uno solo y lo comparten
# todos: ver `Banco`.
ARAM_LIBRE = 0x10000 - SAMPLES_ADDR
# Y lo que se le deja libre igual. No lo necesita nadie: es para que el último
# golpe de percusión, que se pide por presupuesto y se guarda redondeado a
# bloques de BRR, no se pase de los 64 KB por unos cientos de bytes.
ARAM_MARGEN = 1024

# Los opcodes del stream **no se declaran acá**: salen de
# `protocol/music.toml`, que es del que escribe el stream y del que lo lee, y
# de ninguno. Hasta el 2026-09-15 estaban escritos a mano de los dos lados, en
# este archivo y en main.s, sin nada que los atara.
from music_opcodes import *   # noqa: E402,F401,F403

# La percusión se lleva dos voces. Con una sola, un bombo y un charles que caen
# en el mismo cuadro se pisan, y en un patrón de batería eso pasa todo el
# tiempo. Cuesta una voz melódica y se nota menos que perder la mitad de los
# golpes.
DRUM_VOICES = 2


# Los temas que además tienen pista de MSU-1, y con qué número. El MSU-1 no es
# hardware de la consola sino una extensión que soportan el FX Pak Pro y los
# emuladores: la música sale de un archivo PCM al lado de la ROM
# —`<rom>-<pista>.pcm`, habilitado por un `<rom>.msu`— en vez de sintetizarse
# en el SPC700. Cuando el tema tiene pista, la ROM calla el SPC700 y la toca;
# los efectos siguen sonando en el SPC700, así que la ARAM les queda entera.
#
# Es el experimento que pidió taro el 2026-09-11, porque la música
# sintetizada suena fea. Las pistas las arma `tools/msu.py` desde los mismos
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
# main.s. El puntero y la cuenta viven en $00-$03 de la página cero, que la
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
    from render_map import RTP_DIR
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


def build_efecto(nombre, game_dir=GAME_DIR, tasa=SE_TASA):
    leido = leer_wav(nombre, game_dir)
    if not leido or not leido[0]:
        return None
    crudo, fuente = leido
    segundos = len(crudo) / float(fuente)
    guardar = min(len(crudo), int(SE_MAX_SEGUNDOS * fuente))
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
    v = max(0, min(100, volumen)) * 0x60 // 100
    izquierda = v * min(50, 100 - balance) // 50
    derecha = v * min(50, balance) // 50
    return max(0, min(0x7F, izquierda)), max(0, min(0x7F, derecha))


# --- reparto de voces -------------------------------------------------------

def assign(notes):
    """Qué voz del DSP le toca a cada canal del MIDI.

    La percusión se lleva un par de voces fijas al final. Las demás se reparten
    entre los canales melódicos por la misma cuenta que en la Mega Drive: de a
    una, siempre a la que más tiempo-nota agregue.
    """
    melodic = collections.defaultdict(list)
    for note in notes:
        if note.channel != midi.DRUM_CHANNEL:
            melodic[note.channel].append(note)

    drums = any(n.channel == midi.DRUM_CHANNEL for n in notes)
    budget = sdsp.VOICES - (DRUM_VOICES if drums else 0)

    spans = {channel: musica.note_time(ns) for channel, ns in melodic.items()}
    busiest = sorted(spans, key=lambda c: -sum(a * b for a, b in spans[c].items()))
    kept = busiest[:budget]

    voices, next_voice = {}, 0
    for channel, count in musica.share_voices({c: spans[c] for c in kept},
                                                budget).items():
        voices[channel] = list(range(next_voice, next_voice + count))
        next_voice += count

    if drums:
        voices[midi.DRUM_CHANNEL] = list(range(sdsp.VOICES - DRUM_VOICES,
                                               sdsp.VOICES))
    return voices


# --- el banco compartido ----------------------------------------------------

class Banco:
    """Las muestras que comparten **todos** los temas de la ROM.

    Es uno solo, y no por ahorrar cartucho —de ése sobra— sino por ARAM: las
    muestras viven en los 64 KB del SPC700 y se suben una sola vez al arrancar,
    con el protocolo del IPL, que después de saltar al driver ya no está. Un
    banco por tema pediría un driver que sepa recibir datos y, con 32 KB por
    banco, del orden de medio segundo de transferencia en cada `PlayBGM`. Eso
    último es lo que lo decide y no el trabajo: la ROM se compara cuadro contra
    cuadro con la referencia, y un freno de treinta cuadros a mitad de una
    escena habría que modelarlo en Python, que es justo lo que no se puede
    medir honestamente.

    Compartirlo sale casi gratis porque el banco es por **programa** de General
    MIDI: dos temas que tocan piano usan la misma muestra. Lo que crece es la
    cantidad de programas distintos, y de que eso no se pague en calidad se
    ocupa el reparto de sobrantes de `snes_samples.build_bank`. Medido con los
    cuatro temas de las primeras secuencias: doce programas y dieciocho golpes
    ocupan 62310 de los 64512 B, y ninguna muestra melódica baja de 21 kHz, que
    es donde estaban con un tema solo.

    Y conviene tener claro cuál es el límite de verdad. Lo melódico está topado
    en `ARAM_BUDGET` y la percusión se lleva lo que sobre, así que el que crece
    con cada tema nuevo es el **directorio** —4 B por muestra— y, sobre todo,
    el piso: cada programa y cada golpe ocupan algo aunque se les dé casi nada.
    Con los once temas de la demo de hoy son 54 muestras y 56952 B; con los
    diecinueve que la demo pide, 89 y 66353, y ahí el lazo de `build_varios`
    que saca aportantes se dispara de verdad.

    Lo que se degrada mientras tanto es la resolución, y sin aviso: los mismos
    40 KB melódicos repartidos entre diecinueve temas en vez de once bajan la
    tasa mediana de 12,5 a 8,4 kHz. Por eso el recorte existe, y por eso no
    alcanza con subirlo: para que entren todos hace falta presupuestar por
    paquete de mapa en vez de por banco, anotado en "Lo que falta" del README.
    """

    def __init__(self, programas, golpes, reserva=0):
        melodicas = snes_samples.build_bank(sorted(programas))
        # A la percusión se le da **lo que sobre**, y no los 16 KB fijos de
        # `DRUM_BUDGET`. Con un tema solo daba igual; compartiendo, no: los
        # ocho golpes de `evilrhys` pasaban a ser catorce entre los tres temas
        # de la demo y su plato chino bajaba de 18,3 a 11,9 kHz, que se oye.
        # Repartiendo lo libre vuelve a 20,2. Y no le cuesta un tema a nadie:
        # el que se queda corto es el golpe, no el tema, que es lo que pasaría
        # subiendo `DRUM_BUDGET` a secas.
        golpes = sorted(golpes)
        libre = (ARAM_LIBRE - ARAM_MARGEN - 4 * (len(melodicas) + len(golpes))
                 - sum(len(v.data) for v in melodicas) - reserva)
        percusion = []
        while golpes and libre > 0:
            percusion = snes_samples.build_drum_bank({n: 1 for n in golpes},
                                                     budget=libre)
            if sum(len(v.data) for v in percusion) <= libre:
                break
            # Se pasó: el presupuesto es una guía y el largo real se redondea
            # a bloques. Se pide menos y se vuelve a preguntar.
            libre = libre * 9 // 10
        self.voces = melodicas + percusion
        # De programa de MIDI a índice en el banco, que es lo que va en
        # `V_SRCN`; los golpes van después de los melódicos, así que el DSP no
        # distingue percusión de nada más.
        self.melodicas = {v.program: i for i, v in enumerate(melodicas)}
        self.golpes = {d.program: len(melodicas) + i
                       for i, d in enumerate(percusion)}

    @property
    def bytes(self):
        """Cuánto ocupa en ARAM: el directorio más las muestras."""
        return 4 * len(self.voces) + sum(len(v.data) for v in self.voces)


# --- eventos ----------------------------------------------------------------

class Frame:
    """Todo lo que pasa en un cuadro, separado por cuándo hay que escribirlo.

    El orden importa: primero se prepara cada voz —volumen, altura, timbre— y
    recién al final se tocan KON y KOF, que son los que disparan. Si se hiciera
    al revés, la nota arrancaría con los valores de la anterior.
    """

    __slots__ = ("release", "setup", "kon", "kof")

    def __init__(self):
        self.release = []       # las notas que se sueltan en este cuadro
        self.setup = []
        self.kon = 0
        self.kof = 0


def build_events(notes, voices, programs, drum_voices, banco):
    """Las escrituras al DSP, cuadro por cuadro.

    Cada canal tiene su grupo de voces; una nota que arranca toma la que lleve
    más tiempo libre, y si están todas ocupadas se la saca a la que termina
    antes. Es lo mismo que hace un sintetizador cuando se le acaba la polifonía,
    y lo mismo que ya hacíamos en la Mega Drive.

    El banco viene de afuera y no se arma acá: lo comparten todos los temas de
    la ROM, así que los índices de `V_SRCN` que este stream escribe son los de
    ese banco y no los de uno propio. Ver `Banco`.
    """
    frames = collections.defaultdict(Frame)
    bank, index_of, drum_index = banco.voces, banco.melodicas, banco.golpes

    busy = {}
    for note in sorted(notes, key=lambda n: n.start):
        group = voices.get(note.channel)
        if not group:
            continue

        free = [v for v in group if busy.get(v, 0) <= note.start]
        voice = min(free or group, key=lambda v: busy.get(v, 0))
        busy[voice] = note.end

        start, end = frames[note.start], frames[note.end]
        base = voice * 0x10
        program = programs.get(note.channel, 0)

        if voice in drum_voices:
            # En General MIDI la nota elige el instrumento, no la altura, así
            # que cada golpe tiene su propia muestra y se toca a su tasa
            # original: transponerla convertiría un bombo en otra cosa.
            source = drum_index.get(note.pitch)
            if source is None:
                continue
            drum = bank[source]
            step = sdsp.pitch_for(drum.root, drum.root, drum.rate)
            level = sdsp.volume(note.velocity, sdsp.CEILING_DRUM)
            start.setup += [(base + sdsp.V_VOL_L, level),
                            (base + sdsp.V_VOL_R, level),
                            (base + sdsp.V_PITCH_L, step & 0xFF),
                            (base + sdsp.V_PITCH_H, step >> 8),
                            (base + sdsp.V_SRCN, source),
                            # Ataque instantáneo y sin decaimiento: el golpe ya
                            # trae su propia forma, la envolvente sólo lo apaga
                            # al final para que no siga leyendo memoria.
                            (base + sdsp.V_ADSR1, 0x8F),
                            (base + sdsp.V_ADSR2, 0xE0)]
        else:
            source = index_of.get(program)
            if source is None:
                continue                # el SoundFont no trae ese programa
            instrument = bank[source]
            step = sdsp.pitch_for(note.pitch, instrument.root, instrument.rate)
            level = sdsp.volume(note.velocity)
            adsr1, adsr2 = sdsp.adsr(sdsp.for_program(program))
            start.setup += [(base + sdsp.V_VOL_L, level),
                            (base + sdsp.V_VOL_R, level),
                            (base + sdsp.V_PITCH_L, step & 0xFF),
                            (base + sdsp.V_PITCH_H, step >> 8),
                            (base + sdsp.V_SRCN, source),
                            (base + sdsp.V_ADSR1, adsr1),
                            (base + sdsp.V_ADSR2, adsr2)]

        start.kon |= 1 << voice
        if voice not in drum_voices:
            end.release.append((base, sdsp.fade(sdsp.for_program(program))))

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


def pack(frames, length, init):
    """Los eventos como stream de opcodes, con las esperas entre medio.

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
    stream = bytearray()
    state = {}

    def write(register, value):
        value &= 0xFF
        if state.get(register) == value:
            return
        state[register] = value
        stream.extend([OP_DSP, register & 0xFF, value])

    def wait_until(at, previous):
        wait = at - previous
        while wait > 0:
            step = min(255, wait)
            stream.extend([OP_WAIT, step])
            wait -= step

    for register, value in init:
        write(register, value)

    previous, sounding = 0, 0
    for at in sorted(frames):
        if at > length:
            break
        frame = frames[at]
        if not (frame.release or frame.setup or frame.kon or frame.kof):
            continue

        wait_until(at, previous)
        previous = at

        if sounding:                       # bajar el disparo del cuadro anterior
            stream.extend([OP_DSP, sdsp.KON, 0x00])
            sounding = 0
        write(sdsp.KOF, 0x00)
        for base, gain in frame.release:
            write(base + sdsp.V_ADSR1, 0x00)    # apagar ADSR: manda GAIN
            write(base + sdsp.V_GAIN, gain)
        for register, value in frame.setup:
            write(register, value)
        if frame.kof:
            write(sdsp.KOF, frame.kof)
        if frame.kon:
            stream.extend([OP_DSP, sdsp.KON, frame.kon])
            sounding = frame.kon

    # Al final se apaga todo, si no la última nota queda sonando en el loop.
    wait_until(length, previous)
    stream.extend([OP_DSP, sdsp.KON, 0x00])
    stream.extend([OP_DSP, sdsp.KOF, 0xFF])
    stream.append(OP_END)
    return bytes(stream)


def build(map_id, game_dir=GAME_DIR):
    """El tema de un mapa, listo para la ROM.

    Devuelve (nombre, driver, bloque de muestras, stream, segundos, resumen).
    """
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    music = tree.map_music(map_id)
    return build_nombre(music["name"] if music else "", game_dir)


def tema_del_mapa(map_id, game_dir=GAME_DIR):
    """El nombre del tema que le toca a un mapa por el árbol, o "" si no tiene."""
    tree = lcf.TreeMap(os.path.join(game_dir, "RPG_RT.lmt"))
    music = tree.map_music(map_id)
    return music["name"] if music else ""


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
    notes, tempos, division, programs = midi.read(path)
    voices = assign(notes)
    return {
        "nombre": name,
        "notas": notes,
        "largo": musica.timeline(notes, tempos, division),
        "voces": voices,
        "programas": programs,
        "percusion": set(voices.get(midi.DRUM_CHANNEL, [])),
        # Lo que aporta al banco compartido: los programas de sus canales
        # melódicos y las teclas de percusión que toca.
        "melodicos": {programs.get(c, 0) for c in voices
                      if c != midi.DRUM_CHANNEL},
        "golpes": {n.pitch for n in notes if n.channel == midi.DRUM_CHANNEL},
    }


def build_varios(nombres, game_dir=GAME_DIR, efectos=(), prioridad=(),
                 tope=None):
    """Todos los temas de la ROM, compartiendo un solo banco de muestras.

    Devuelve (driver, las voces —las del banco y detrás los efectos, cada una
    con su número de muestra—, temas, banco, los que no aportan al banco).
    Hay un dict por tema en el orden en que vinieron: los índices son los de
    `Temas`, el bytecode ya los lleva emitidos, así que **no se pueden
    reordenar**.

    **Todos los temas pedidos salen en el cartucho, siempre.** Un índice no
    cuesta ARAM: cuesta su stream, que vive en el cartucho, y de ése sobra.
    Hasta el 2026-09-12 el que no entraba en el banco se caía de la lista
    entera, y con eso se caían dos cosas que no tenían por qué: el `PlayBGM`
    quedaba apuntando a un tema que no existe, y —peor— **la pista de MSU-1 de
    ese tema quedaba inalcanzable**, cuando una pista no gasta ni una muestra
    de ARAM: lo único que necesita es que el tema tenga número. Así se quedó
    muda la pantalla de título al agregar los 29 mapas de Lashe City.

    Lo que sí compite por la ARAM son las **muestras**, y por eso lo que se
    recorta acá es quién aporta programas al banco y no quién existe. Un tema
    que no aporta suena con lo que otros ya pusieron —los programas se
    comparten por número de General MIDI— y en el peor caso sale mudo, que es
    exactamente lo que hacía antes, sólo que ahora con MSU-1 suena igual.

    `prioridad` son los índices que aportan primero, y el recorte se lleva a
    los últimos: el del título va ahí, porque es la primera pantalla del juego
    y no un tema de un mapa que el jugador puede no visitar nunca.

    `tope` es contra cuánto se mide el banco. Con `ARAM_LIBRE`, que es lo de
    siempre, entran los primeros y los últimos quedan mutilados: una nota cuyo
    programa no está en el banco **se cae del stream** —ver el `continue` de
    `build_events`—, y en `demo-ciudad` eso son nueve temas a los que les
    sobrevive entre el 12% y el 72% de las notas. Con un tope más alto aportan
    todos y lo que se paga es resolución para todos, porque los mismos 40 KB
    melódicos se reparten entre más programas. **Cuál de las dos suena peor lo
    dice el oído**, y por eso hay con qué armar las dos: `--banco-entero` en el
    conversor. Ver "Varios temas en el cartucho" en el README.

    El límite sigue siendo el banco entero contra `ARAM_LIBRE`, que es más
    estricto de lo que el hardware pide desde que el audio sube por paquetes de
    mapa —en la ARAM viven el directorio y **un** paquete, no el banco—; queda
    así a propósito, porque es el que mantiene la resolución de las muestras:
    repartir 40 KB melódicos entre diecinueve temas en vez de once baja la tasa
    mediana de 12,5 a 8,4 kHz, y eso se oye en los once que hoy suenan bien.
    Aflojarlo de verdad pide presupuestar por paquete: ver el README.
    """
    driver = spc700.assemble(DRIVER, DRIVER_ADDR)
    leidos = [leer_tema(n, game_dir) for n in nombres]

    orden = [i for i in prioridad if 0 <= i < len(leidos)]
    orden += [i for i in range(len(leidos)) if i not in orden]
    tope = ARAM_LIBRE if tope is None else tope
    aportan, afuera = [i for i in orden if leidos[i]], []
    while True:
        banco = Banco(set().union(*[leidos[i]["melodicos"] for i in aportan])
                      if aportan else set(),
                      set().union(*[leidos[i]["golpes"] for i in aportan])
                      if aportan else set())
        if banco.bytes <= tope or not aportan:
            break
        afuera.insert(0, nombres[aportan.pop()])

    temas = []
    for nombre, leido in zip(nombres, leidos):
        if leido is None:
            temas.append({"nombre": nombre, "stream": bytes([OP_END]),
                          "segundos": 0.0, "resumen": {}})
            continue
        frames = build_events(leido["notas"], leido["voces"],
                              leido["programas"], leido["percusion"], banco)
        stream = pack(frames, leido["largo"], init_writes())
        temas.append({"nombre": nombre, "stream": stream,
                      "segundos": leido["largo"] / TICKS_PER_SECOND,
                      "resumen": resumen_del_tema(leido, banco)})
    # Los efectos, con lo que la música dejó libre. Van detrás del banco en
    # el mismo directorio: su `V_SRCN` es el lugar que les toca después de las
    # muestras de la música.
    # Van **todos**: cuáles caben lo decide la ROM mapa por mapa, al armar
    # su paquete de audio. Ver `paquete_cargar` en main.s.
    efectos_hechos = build_efectos(list(efectos), game_dir, 1 << 30)
    lista = sorted(efectos_hechos.values(), key=lambda e: list(efectos).index(
        e.name) if e.name in efectos else 0)
    banco.efectos = {e.name: (len(banco.voces) + i, e)
                     for i, e in enumerate(lista)}
    return (driver, list(banco.voces) + lista, temas, banco, afuera)


def resumen_del_tema(leido, banco):
    """Lo que imprime la receta: voces, timbres y cuánto se llega a tocar."""
    notes, voices = leido["notas"], leido["voces"]
    programs = leido["programas"]
    spans = {c: musica.note_time([n for n in notes if n.channel == c])
             for c in {n.channel for n in notes}}
    total = sum(sum(a * b for a, b in spans[c].items()) for c in spans)
    return {
        "voices": {c: v for c, v in sorted(voices.items())},
        "sounds": {c: programs.get(c, 0)
                   for c in sorted(voices) if c != midi.DRUM_CHANNEL},
        "bank": ["%s (%.0f Hz, %d B)" % (v.name.strip(), v.rate, len(v.data))
                 for v in banco.voces],
        "coverage": sum(musica.coverage(spans[c], len(voices.get(c, [])))
                        * sum(a * b for a, b in spans[c].items())
                        for c in spans) / max(1, total),
        # Y cuántas de sus notas llegan al stream. Una nota cuyo programa no
        # está en el banco **no suena más bajo: no existe** —el `continue` de
        # `build_events`—, así que esto es la voz que el jugador no oye. Es un
        # número distinto de `coverage`, que mide la polifonía; se confundieron
        # el 2026-09-14 y por un rato pareció que compartir el banco no costaba
        # nada, porque `coverage` da igual con el banco entero o compartido.
        "notas": notas_que_suenan(leido, banco),
    }


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


def build_nombre(name, game_dir=GAME_DIR):
    """Un tema solo, con el banco armado nada más que para él.

    Queda para `music` y `audio-check`, que miran un tema suelto. La ROM no
    pasa por acá desde que lleva varios: ver `build_varios`.
    """
    driver, samples, temas, _banco, _afuera = build_varios([name], game_dir)
    tema = temas[0]
    return (name, driver, samples, tema["stream"], tema["segundos"],
            tema["resumen"])


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


def muestras_del_stream(stream):
    """Qué muestras usa un tema: los valores que su stream escribe en los
    registros SRCN de las voces. Es lo que la ROM tiene que tener en la ARAM
    para tocarlo, sacado de lo que el tema hace y no de cómo se armó."""
    usadas, i = set(), 0
    while i < len(stream):
        op = stream[i]
        if op == OP_END:
            break
        if op == OP_WAIT:
            i += 2
            continue
        registro, valor = stream[i + 1], stream[i + 2]
        if registro & 0x0F == sdsp.V_SRCN:
            usadas.add(valor)
        i += 3
    return sorted(usadas)


def emit(path, temas, driver, voces, arranque=0xFF, titulo=0xFF,
         sonidos=(), paquetes=()):
    """El .inc que arma el ensamblador junto con main.s.

    `temas` son los de `build_varios`, en el orden de `Temas`: el bytecode ya
    lleva esos índices emitidos. `arranque` es cuál suena desde el primer
    cuadro, o $FF si la ROM arranca callada y lo prende un `PlayBGM`.

    `voces` son todas las muestras del cartucho, numeradas: las de la música y
    detrás los efectos. Ninguna se sube al arrancar: van al SPC700 de a
    **paquetes**, uno por mapa —`paquetes`, en el orden de la tabla de mapas,
    cada uno con sus temas y las muestras de sus efectos—, y el directorio
    arranca con todas apuntando al silencio. Ver `paquete_cargar` en main.s.
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
                           [[muestras_del_stream(st)] for st in streams])
    paquetes = list(paquetes) or [([], [])]
    bloque_paquetes = listas("paquetes", [[list(t), list(m)]
                                           for t, m in paquetes])

    with open(path, "w") as handle:
        handle.write(
            "; Generado por tools/snes_music.py. No editar.\n"
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
            "; vuelve a escribir bajándolos. Escribirlos también en main.s\n"
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
            "SONIDOS_N        = %d\n\n"
            "; Dónde arranca el stream de cada tema, partido en tres tablas\n"
            "; porque se leen con un índice: van en el banco 0 como todo lo\n"
            "; que la CPU recorre con `lda tabla, x`.\n"
            '.segment "TABLAS"\n%s\n\n'
            '.segment "RODATA"\n%s\n%s\n%s\n'
            '.bloque %d\nmuestra_tabla:\n%s\n%s\n%s\n%s\n%s\n'
            % (", ".join(t["nombre"] or "sin música" for t in temas)
               or "ninguno",
               len(temas), arranque, titulo,
               sdsp.MASTER, sdsp.MVOL_L, sdsp.MVOL_R,
               DRIVER_ADDR, len(driver),
               SAMPLES_ADDR, len(samples),
               n, silencio, datos, ARAM_FIN, len(paquetes),
               SE_VOZ, 1 << SE_VOZ, SE_VOZ * 16, len(list(sonidos)),
               tabla, tabla_se,
               block("spc_driver", driver),
               block("spc_samples", samples),
               7 * len(filas_m), "\n".join(filas_m),
               tema_muestras, bloque_paquetes,
               "\n".join(muestras),
               "\n".join(block(e, st) for e, st in zip(etiquetas, streams))))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=67)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("-o", "--output",
                        default=os.path.join(REPO, "rom/build/inc/musicdata.inc"))
    args = parser.parse_args()

    name, driver, samples, stream, seconds, summary = build(args.map_id,
                                                            args.game_dir)
    if len(stream) <= 1:
        print("El mapa %d no tiene un MIDI propio (%s): sale mudo."
              % (args.map_id, name or "sin música"))
    else:
        print("Mapa %d: %s, %.0f s" % (args.map_id, name, seconds))
        print("  voces por canal: %s" % summary["voices"])
        print("  timbres:         %s" % summary["sounds"])
        print("  banco:           %s" % ", ".join(summary["bank"]))
        print("  se reproduce el %.0f%% del tiempo-nota"
              % (100 * summary["coverage"]))
        # Y el otro número, que es el que se oye como voces que faltan: ver
        # `notas_que_suenan`. Con un tema solo suele ser 100%, y justamente por
        # eso conviene que esté: la diferencia contra la ROM entera es el costo
        # de compartir el banco.
        print("  suenan el %.0f%% de las notas"
              % (100 * summary["notas"]))

    emit(args.output,
         [{"nombre": name, "stream": stream, "segundos": seconds,
           "resumen": summary}],
         driver, samples, arranque=0, paquetes=[([0], [])])
    # El acomodo de bancos, igual que cuando lo emite el conversor: acá la
    # música es lo único que hay en RODATA, así que se resuelve sola. Ver
    # `tools/bancos.py`.
    bancos.resolver([args.output])
    print("  driver %d B, muestras %d B, stream %d B -> %s"
          % (len(driver), sum(len(v.data) for v in samples), len(stream),
             args.output))


if __name__ == "__main__":
    main()
