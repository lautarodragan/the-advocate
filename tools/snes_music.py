#!/usr/bin/env python3
"""Convierte el MIDI de un mapa a muestras BRR y un stream para el S-DSP.

Es el equivalente de md_music.py para la Super Nintendo, y comparte con él todo
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
    python3 tools/snes_music.py --map-id 67 -o snes/src/musicdata.inc
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import brr
import lcf
import md_music
import midi
import sdsp
import snes_samples
import spc700
from render_map import GAME_DIR, REPO, find_resource

TICKS_PER_SECOND = md_music.TICKS_PER_SECOND

# Dónde vive cada cosa en los 64 KB del SPC700. Los primeros $200 bytes se los
# queda la ROM de arranque para sus variables, así que se empieza más arriba.
DRIVER_ADDR = 0x0200
SAMPLES_ADDR = 0x0400

# Opcodes del stream, los mismos que interpreta music_frame en main.s.
OP_DSP = 0x00
OP_WAIT = 0x01
OP_END = 0xFF

# La percusión se lleva dos voces. Con una sola, un bombo y un charles que caen
# en el mismo cuadro se pisan, y en un patrón de batería eso pasa todo el
# tiempo. Cuesta una voz melódica y se nota menos que perder la mitad de los
# golpes.
DRUM_VOICES = 2


# --- el driver del SPC700 ---------------------------------------------------
# Se queda esperando que el 65816 le deje un par (registro, valor) en los
# puertos 0 y 1, y lo copia a los del DSP. El testigo del puerto 3 es lo que
# distingue "hay un dato nuevo" de "el mismo de recién": el 65816 lo incrementa
# en cada escritura y el driver se lo devuelve como acuse.

DRIVER = """
    mov x, $F7          ; arrancar con el testigo que ya esté, sin disparar
espera:
    cmp x, $F7
    beq espera
    mov x, $F7
    mov a, $F4          ; registro del DSP
    mov $F2, a
    mov a, $F5          ; el valor que va en ese registro
    mov $F3, a
    mov $F7, x          ; acusar recibo devolviendo el testigo
    bra espera
"""


# --- muestras ---------------------------------------------------------------

def build_samples(voices):
    """El directorio y las muestras en BRR, tal como van en el SPC700.

    El directorio va primero: cuatro bytes por muestra, la dirección donde
    empieza y la dirección a la que vuelve. Con grabaciones las dos difieren —
    el ataque se toca una sola vez y el loop es la parte sostenida—, y por eso
    el punto de loop tenía que caer justo en un bloque: la dirección se cuenta
    de a nueve bytes y no hay forma de apuntar a media muestra.
    """
    directory = bytearray()
    address = SAMPLES_ADDR + 4 * len(voices)
    for voice in voices:
        loop = address + voice.loop_block * brr.BLOCK_BYTES
        directory += address.to_bytes(2, "little")
        directory += loop.to_bytes(2, "little")
        address += len(voice.data)

    return bytes(directory) + b"".join(v.data for v in voices)


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

    spans = {channel: md_music.note_time(ns) for channel, ns in melodic.items()}
    busiest = sorted(spans, key=lambda c: -sum(a * b for a, b in spans[c].items()))
    kept = busiest[:budget]

    voices, next_voice = {}, 0
    for channel, count in md_music.share_voices({c: spans[c] for c in kept},
                                                budget).items():
        voices[channel] = list(range(next_voice, next_voice + count))
        next_voice += count

    if drums:
        voices[midi.DRUM_CHANNEL] = list(range(sdsp.VOICES - DRUM_VOICES,
                                               sdsp.VOICES))
    return voices


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


def build_events(notes, voices, programs, drum_voices):
    """Las escrituras al DSP, cuadro por cuadro.

    Cada canal tiene su grupo de voces; una nota que arranca toma la que lleve
    más tiempo libre, y si están todas ocupadas se la saca a la que termina
    antes. Es lo mismo que hace un sintetizador cuando se le acaba la polifonía,
    y lo mismo que ya hacíamos en la Mega Drive.
    """
    frames = collections.defaultdict(Frame)

    # Un instrumento del banco por cada programa distinto que pida el MIDI. Se
    # comparte entre canales: si dos tocan piano, usan la misma muestra, que en
    # 64 KB de ARAM no es un detalle.
    wanted = sorted({programs.get(c, 0) for c in voices
                     if c != midi.DRUM_CHANNEL})
    bank = snes_samples.build_bank(wanted)
    index_of = {voice.program: index for index, voice in enumerate(bank)}

    # Y una muestra por cada golpe de percusión que aparezca. Van al final del
    # mismo banco, así que el DSP no distingue percusión de nada más: para él
    # son todas voces leyendo una muestra.
    hits = collections.Counter(n.pitch for n in notes
                               if n.channel == midi.DRUM_CHANNEL)
    drums = snes_samples.build_drum_bank(dict(hits)) if hits else []
    drum_index = {drum.program: len(bank) + i for i, drum in enumerate(drums)}
    bank = bank + drums

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

    return frames, bank


def init_writes(bank_size, drum_voices):
    """El estado del DSP antes de la primera nota."""
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
    name = music["name"] if music else ""
    path = (find_resource([game_dir], "Music", name, (".mid", ".wav"))
            if name else None)

    driver = spc700.assemble(DRIVER, DRIVER_ADDR)

    if not path or not path.lower().endswith(".mid"):
        return name, driver, build_samples([]), bytes([OP_END]), 0.0, {}

    notes, tempos, division, programs = midi.read(path)
    length = md_music.timeline(notes, tempos, division)
    voices = assign(notes)
    drum_voices = set(voices.get(midi.DRUM_CHANNEL, []))

    frames, bank = build_events(notes, voices, programs, drum_voices)
    stream = pack(frames, length, init_writes(len(bank), drum_voices))

    spans = {c: md_music.note_time([n for n in notes if n.channel == c])
             for c in {n.channel for n in notes}}
    total = sum(sum(a * b for a, b in spans[c].items()) for c in spans)
    summary = {
        "voices": {c: v for c, v in sorted(voices.items())},
        "sounds": {c: programs.get(c, 0)
                   for c in sorted(voices) if c != midi.DRUM_CHANNEL},
        "bank": ["%s (%.0f Hz, %d B)" % (v.name.strip(), v.rate, len(v.data))
                 for v in bank],
        "coverage": sum(md_music.coverage(spans[c], len(voices.get(c, [])))
                        * sum(a * b for a, b in spans[c].items())
                        for c in spans) / max(1, total),
    }
    return name, driver, build_samples(bank), stream, length / TICKS_PER_SECOND, summary


def emit(path, name, driver, samples, stream):
    """El .inc que arma el ensamblador junto con main.s."""
    def block(label, data):
        out = ["%s:" % label]
        for i in range(0, len(data), 16):
            out.append("    .byte " + ",".join("$%02X" % b for b in data[i:i + 16]))
        return "\n".join(out)

    with open(path, "w") as handle:
        handle.write(
            "; Generado por tools/snes_music.py. No editar.\n"
            "; Tema: %s\n\n"
            "SPC_DRIVER_ADDR  = $%04X\n"
            "SPC_DRIVER_SIZE  = %d\n"
            "SPC_SAMPLES_ADDR = $%04X\n"
            "SPC_SAMPLES_SIZE = %d\n\n"
            '.segment "RODATA"\n%s\n%s\n%s\n'
            % (name or "sin música", DRIVER_ADDR, len(driver),
               SAMPLES_ADDR, len(samples),
               block("spc_driver", driver),
               block("spc_samples", samples),
               block("md_music", stream)))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map-id", type=int, default=67)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("-o", "--output",
                        default=os.path.join(REPO, "snes/src/musicdata.inc"))
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

    emit(args.output, name, driver, samples, stream)
    print("  driver %d B, muestras %d B, stream %d B -> %s"
          % (len(driver), len(samples), len(stream), args.output))


if __name__ == "__main__":
    main()
