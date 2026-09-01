"""Los seis canales de FM de la Mega Drive: parches y registros.

El YM2612 sintetiza cada voz con cuatro operadores. El "algoritmo" dice cómo se
conectan —en cadena, en paralelo, o mezclas— y cuáles de ellos salen al parlante
(los portadores) y cuáles sólo modulan a otro (los moduladores). Subirle el
volumen a un modulador no lo hace más fuerte: lo hace más brillante.

No hay forma de calcular un parche a partir de un instrumento de General MIDI
como se calcula el color más cercano de una paleta: hay que elegirlo de oído.
Lo que hay acá abajo es un punto de partida por familia de instrumento, pensado
para tocarlo y volver a generar.

Los operadores van en el orden en que los espera el chip, que es 1, 3, 2, 4.
"""

# --- registros --------------------------------------------------------------

REG_KEY = 0x28              # key on/off, siempre en la parte 1
REG_DT_MUL = 0x30
REG_TL = 0x40
REG_RS_AR = 0x50
REG_AM_D1R = 0x60
REG_D2R = 0x70
REG_D1L_RR = 0x80
REG_SSG = 0x90
REG_FNUM_LOW = 0xA0
REG_BLOCK_FNUM = 0xA4
REG_FB_ALGO = 0xB0
REG_PANNING = 0xB4

CHANNELS = 6
YM_CLOCK = 7670453          # el reloj del YM2612 en la Mega Drive

# Qué ranuras de operador salen al parlante en cada algoritmo, en el orden del
# chip (1, 3, 2, 4). Sólo a esas les afecta la velocidad de la nota.
CARRIERS = {
    0: (3,), 1: (3,), 2: (3,), 3: (3,),
    4: (2, 3), 5: (1, 2, 3), 6: (1, 2, 3), 7: (0, 1, 2, 3),
}


def operator(mul, dt=0, tl=0, ar=31, d1r=0, d2r=0, d1l=0, rr=15, rs=0):
    """Un operador. mul es la relación armónica y tl cuánto se atenúa."""
    return {"mul": mul, "dt": dt, "tl": tl, "ar": ar, "d1r": d1r,
            "d2r": d2r, "d1l": d1l, "rr": rr, "rs": rs}


def patch(name, algorithm, feedback, operators):
    return {"name": name, "algorithm": algorithm, "feedback": feedback,
            "operators": operators}


# --- el banco ---------------------------------------------------------------
#
# Uno por familia de General MIDI. Son ocho porque con más, sin poder
# escucharlos, sería inventar. Ajustar de oído y regenerar.

PIANO = patch("piano", 4, 5, [
    operator(mul=1, tl=36, ar=31, d1r=8, d2r=4, d1l=3, rr=8),
    operator(mul=1, tl=0, ar=31, d1r=10, d2r=5, d1l=2, rr=9),
    operator(mul=2, tl=40, ar=31, d1r=9, d2r=4, d1l=3, rr=8),
    operator(mul=1, tl=0, ar=31, d1r=9, d2r=4, d1l=2, rr=9),
])

BASS = patch("bajo", 4, 7, [
    operator(mul=1, tl=30, ar=31, d1r=12, d2r=6, d1l=4, rr=10),
    operator(mul=1, tl=0, ar=31, d1r=8, d2r=3, d1l=2, rr=10),
    operator(mul=2, tl=34, ar=31, d1r=12, d2r=6, d1l=4, rr=10),
    operator(mul=1, tl=0, ar=31, d1r=6, d2r=2, d1l=1, rr=10),
])

ORGAN = patch("órgano", 7, 0, [
    operator(mul=1, tl=20, ar=31, rr=8),
    operator(mul=2, tl=28, ar=31, rr=8),
    operator(mul=4, tl=34, ar=31, rr=8),
    operator(mul=1, tl=16, ar=31, rr=8),
])

STRINGS = patch("cuerdas", 4, 4, [
    operator(mul=1, tl=38, ar=18, d1r=4, d2r=1, d1l=2, rr=6),
    operator(mul=1, tl=8, ar=16, d1r=3, d2r=0, d1l=1, rr=5),
    operator(mul=1, tl=42, ar=18, d1r=4, d2r=1, d1l=2, rr=6),
    operator(mul=1, tl=6, ar=15, d1r=2, d2r=0, d1l=1, rr=5),
])

BRASS = patch("metales", 2, 6, [
    operator(mul=1, tl=32, ar=24, d1r=6, d2r=2, d1l=2, rr=8),
    operator(mul=1, tl=30, ar=26, d1r=6, d2r=2, d1l=2, rr=8),
    operator(mul=1, tl=28, ar=25, d1r=5, d2r=2, d1l=2, rr=8),
    operator(mul=1, tl=4, ar=22, d1r=5, d2r=1, d1l=1, rr=7),
])

REED = patch("caña", 4, 5, [
    operator(mul=2, tl=34, ar=28, d1r=6, d2r=2, d1l=2, rr=9),
    operator(mul=1, tl=6, ar=26, d1r=4, d2r=1, d1l=1, rr=8),
    operator(mul=1, tl=38, ar=28, d1r=6, d2r=2, d1l=2, rr=9),
    operator(mul=1, tl=4, ar=25, d1r=4, d2r=1, d1l=1, rr=8),
])

LEAD = patch("solista", 4, 6, [
    operator(mul=2, tl=28, ar=31, d1r=6, d2r=2, d1l=2, rr=10),
    operator(mul=1, tl=2, ar=31, d1r=5, d2r=1, d1l=1, rr=9),
    operator(mul=1, tl=32, ar=31, d1r=6, d2r=2, d1l=2, rr=10),
    operator(mul=1, tl=0, ar=31, d1r=5, d2r=1, d1l=1, rr=9),
])

BELL = patch("campana", 5, 4, [
    operator(mul=4, tl=30, ar=31, d1r=10, d2r=6, d1l=4, rr=7),
    operator(mul=7, tl=24, ar=31, d1r=12, d2r=7, d1l=5, rr=7),
    operator(mul=3, tl=26, ar=31, d1r=11, d2r=6, d1l=4, rr=7),
    operator(mul=1, tl=8, ar=31, d1r=9, d2r=5, d1l=3, rr=7),
])

# Las 16 familias de General MIDI, de a 8 programas cada una.
BANK = [
    PIANO,      # 0-7    piano
    BELL,       # 8-15   percusión cromática
    ORGAN,      # 16-23  órgano
    LEAD,       # 24-31  guitarra
    BASS,       # 32-39  bajo
    STRINGS,    # 40-47  cuerdas
    STRINGS,    # 48-55  conjunto
    BRASS,      # 56-63  metales
    REED,       # 64-71  caña
    REED,       # 72-79  viento
    LEAD,       # 80-87  sintetizador solista
    STRINGS,    # 88-95  sintetizador de fondo
    BELL,       # 96-103 efectos
    BELL,       # 104-111 étnico
    BELL,       # 112-119 percusión
    LEAD,       # 120-127 efectos de sonido
]


def for_program(program):
    """El parche que le toca a un instrumento de General MIDI."""
    return BANK[min(15, max(0, program) // 8)]


# --- generación de registros ------------------------------------------------

def _slot(channel):
    """El canal dentro de su parte: 0 a 2, y qué parte del chip es."""
    return channel % 3, 1 if channel < 3 else 2


def load_patch(channel, patch_data, velocity=127):
    """Todos los registros de un parche en un canal. Se emite una sola vez."""
    index, part = _slot(channel)
    carriers = CARRIERS[patch_data["algorithm"]]
    writes = []

    for slot, op in enumerate(patch_data["operators"]):
        offset = slot * 4 + index
        total = op["tl"]
        if slot in carriers:
            # La velocidad sólo tiene sentido en los que salen al parlante.
            total = min(127, total + (127 - velocity) // 4)
        writes += [
            (part, REG_DT_MUL + offset, ((op["dt"] & 7) << 4) | (op["mul"] & 15)),
            (part, REG_TL + offset, total & 0x7F),
            (part, REG_RS_AR + offset, ((op["rs"] & 3) << 6) | (op["ar"] & 31)),
            (part, REG_AM_D1R + offset, op["d1r"] & 31),
            (part, REG_D2R + offset, op["d2r"] & 31),
            (part, REG_D1L_RR + offset, ((op["d1l"] & 15) << 4) | (op["rr"] & 15)),
            (part, REG_SSG + offset, 0),
        ]

    writes.append((part, REG_FB_ALGO + index,
                   ((patch_data["feedback"] & 7) << 3) | (patch_data["algorithm"] & 7)))
    writes.append((part, REG_PANNING + index, 0xC0))    # los dos parlantes
    return writes


def volume(channel, patch_data, velocity):
    """Sólo los TL de los portadores, que es lo que cambia con cada nota."""
    index, part = _slot(channel)
    carriers = CARRIERS[patch_data["algorithm"]]
    return [(part, REG_TL + slot * 4 + index,
             min(127, patch_data["operators"][slot]["tl"] + (127 - velocity) // 4))
            for slot in carriers]


def frequency(pitch):
    """El bloque y el F-number de una nota MIDI.

    La frecuencia sale de fnum * reloj / (144 * 2^(21-bloque)), así que se busca
    el bloque que deje el fnum en la parte alta de sus 11 bits, donde hay más
    resolución.
    """
    hertz = 440.0 * 2.0 ** ((pitch - 69) / 12.0)
    for block in range(8):
        fnum = int(round(hertz * 144.0 * (1 << (21 - block)) / YM_CLOCK))
        if fnum < 2048:
            if fnum >= 617 or block == 7:
                return block, max(1, fnum)
    return 7, 2047


def note_on(channel, pitch):
    index, part = _slot(channel)
    block, fnum = frequency(pitch)
    # El byte alto se escribe primero: el chip lo guarda y lo aplica con el bajo.
    return [(part, REG_BLOCK_FNUM + index, (block << 3) | (fnum >> 8)),
            (part, REG_FNUM_LOW + index, fnum & 0xFF),
            (1, REG_KEY, 0xF0 | _key_slot(channel))]


def note_off(channel):
    return [(1, REG_KEY, _key_slot(channel))]


def _key_slot(channel):
    """El key on/off numera los canales 0,1,2 y 4,5,6 — el 3 no existe."""
    return channel if channel < 3 else channel + 1


def init():
    """Lo mínimo para que el chip suene: sin LFO, sin timers, sin DAC."""
    return [(1, 0x22, 0x00), (1, 0x27, 0x00), (1, 0x2B, 0x00)] + [
        (1, REG_KEY, _key_slot(c)) for c in range(CHANNELS)]
