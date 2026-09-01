"""Lector de SoundFont 2, lo justo para sacar una muestra por instrumento.

Un .sf2 es un archivo RIFF con tres partes: metadatos, un bloque enorme de PCM
crudo, y una base de datos que dice qué pedazo de ese PCM le corresponde a cada
instrumento y a cada rango de notas.

Esa base de datos —la "hydra"— son nueve tablas que se encadenan:

    phdr  presets       cada uno es un programa de General MIDI
     |    pbag  zonas   un preset puede tener varias
     |     |    pgen    generadores: los parámetros de la zona
     v          |
    inst  instrumentos  a lo que apunta el generador 41
          ibag  zonas   una por rango de notas y de velocidad
           |    igen    generadores, incluido el 53: qué muestra usar
           v
    shdr  muestras      dónde empieza y termina en el PCM, y su loop

Un instrumento de verdad está multi-muestreado: un piano tiene una grabación
distinta cada pocas notas. Nosotros tenemos 64 KB para todo el banco, así que
hay que elegir una sola por instrumento y transponerla; por eso `zone_for` pide
una nota de referencia y devuelve la zona que la cubre.

El archivo pesa 148 MB, casi todo PCM. Se lee la hydra entera, que es chica, y
el audio se busca con seek sólo cuando se pide.
"""

import struct

# Los generadores que nos importan. La lista completa tiene 60 y está en la
# especificación; el resto son modulaciones que acá no se usan.
GEN_START_OFFSET = 0
GEN_END_OFFSET = 1
GEN_STARTLOOP_OFFSET = 2
GEN_ENDLOOP_OFFSET = 3
GEN_START_COARSE = 4
GEN_END_COARSE = 12
GEN_PAN = 17
GEN_ATTACK = 34
GEN_HOLD = 35
GEN_DECAY = 36
GEN_SUSTAIN = 37
GEN_RELEASE = 38
GEN_INSTRUMENT = 41
GEN_KEY_RANGE = 43
GEN_VEL_RANGE = 44
GEN_STARTLOOP_COARSE = 45
GEN_ATTENUATION = 48
GEN_ENDLOOP_COARSE = 50
GEN_COARSE_TUNE = 51
GEN_FINE_TUNE = 52
GEN_SAMPLE_ID = 53
GEN_SAMPLE_MODES = 54
GEN_ROOT_KEY = 58

# Los offsets vienen partidos en dos generadores, uno fino y otro de a 32768
# muestras, y hay que sumarlos.
COARSE = {
    GEN_START_COARSE: (GEN_START_OFFSET, 32768),
    GEN_END_COARSE: (GEN_END_OFFSET, 32768),
    GEN_STARTLOOP_COARSE: (GEN_STARTLOOP_OFFSET, 32768),
    GEN_ENDLOOP_COARSE: (GEN_ENDLOOP_OFFSET, 32768),
}

LOOP_NONE = 0
LOOP_CONTINUOUS = 1
LOOP_UNTIL_RELEASE = 3


class Error(Exception):
    pass


class Sample:
    """Una entrada de shdr: dónde vive el audio y cómo se toca."""

    __slots__ = ("name", "start", "end", "loop_start", "loop_end", "rate",
                 "root_key", "correction", "kind")

    def __init__(self, fields):
        (name, self.start, self.end, self.loop_start, self.loop_end,
         self.rate, self.root_key, self.correction, _link, self.kind) = fields
        self.name = name.split(b"\0")[0].decode("latin-1")

    @property
    def frames(self):
        return self.end - self.start

    def __repr__(self):
        return "<Sample %r %d muestras a %d Hz, nota %d>" % (
            self.name, self.frames, self.rate, self.root_key)


class Zone:
    """Una zona de instrumento, ya con sus generadores resueltos."""

    def __init__(self, generators):
        self.generators = generators

    def get(self, operator, default=None):
        return self.generators.get(operator, default)

    def covers(self, key):
        low, high = self.generators.get(GEN_KEY_RANGE, (0, 127))
        return low <= key <= high

    @property
    def sample_id(self):
        return self.generators.get(GEN_SAMPLE_ID)


def _split(value):
    """Un genAmount leído como rango: byte bajo y byte alto."""
    return value & 0xFF, (value >> 8) & 0xFF


class SoundFont:

    def __init__(self, path):
        self.handle = open(path, "rb")
        self.chunks = {}
        self._read_riff()
        self._read_hydra()

    # --- RIFF ---

    def _read_riff(self):
        header = self.handle.read(12)
        if header[:4] != b"RIFF" or header[8:12] != b"sfbk":
            raise Error("no parece un SoundFont")

        total = struct.unpack("<I", header[4:8])[0] + 8
        position = 12
        while position < total:
            self.handle.seek(position)
            tag = self.handle.read(4)
            size = struct.unpack("<I", self.handle.read(4))[0]
            if tag == b"LIST":
                kind = self.handle.read(4)
                if kind in (b"sdta", b"pdta"):
                    self._read_list(position + 12, position + 8 + size)
            # Los chunks van alineados a dos bytes.
            position += 8 + size + (size & 1)

    def _read_list(self, start, end):
        position = start
        while position < end:
            self.handle.seek(position)
            tag = self.handle.read(4)
            size = struct.unpack("<I", self.handle.read(4))[0]
            # Del PCM se guarda dónde está, no el contenido: son 140 MB.
            if tag == b"smpl":
                self.pcm_offset = position + 8
                self.pcm_size = size
            else:
                self.chunks[tag] = self.handle.read(size)
            position += 8 + size + (size & 1)

    # --- la hydra ---

    def _table(self, tag, fmt):
        """Una tabla de registros de largo fijo."""
        data = self.chunks.get(tag)
        if data is None:
            raise Error("al archivo le falta el chunk %s" % tag.decode())
        size = struct.calcsize(fmt)
        return [struct.unpack_from(fmt, data, i)
                for i in range(0, len(data) - size + 1, size)]

    def _read_hydra(self):
        # El último registro de phdr, inst y shdr es un terminador que sólo
        # sirve para saber dónde termina el anterior.
        self.presets = self._table(b"phdr", "<20sHHHIII")
        self.preset_bags = self._table(b"pbag", "<HH")
        self.preset_gens = self._table(b"pgen", "<HH")
        self.instruments = self._table(b"inst", "<20sH")
        self.inst_bags = self._table(b"ibag", "<HH")
        self.inst_gens = self._table(b"igen", "<HH")
        self.samples = [Sample(f) for f in self._table(b"shdr", "<20sIIIIIBbHH")]

    # --- consultas ---

    def find_preset(self, program, bank=0):
        """El preset de un programa de General MIDI, o None."""
        for index, entry in enumerate(self.presets[:-1]):
            if entry[1] == program and entry[2] == bank:
                return index
        return None

    def preset_name(self, index):
        return self.presets[index][0].split(b"\0")[0].decode("latin-1")

    def _zones(self, bags, gens, first, last, terminal):
        """Las zonas de un preset o instrumento, con sus generadores.

        La primera zona puede ser global: si no trae el generador que apunta a
        lo siguiente (instrumento o muestra), sus valores son el default de las
        que siguen y hay que arrastrarlos.
        """
        zones, common = [], {}
        for index in range(first, last):
            start = bags[index][0]
            end = bags[index + 1][0] if index + 1 < len(bags) else len(gens)
            generators = dict(common)

            for operator, amount in gens[start:end]:
                if operator in (GEN_KEY_RANGE, GEN_VEL_RANGE):
                    generators[operator] = _split(amount)
                elif operator in COARSE:
                    target, scale = COARSE[operator]
                    signed = amount - 65536 if amount >= 32768 else amount
                    generators[target] = generators.get(target, 0) + signed * scale
                elif operator in (GEN_COARSE_TUNE, GEN_FINE_TUNE, GEN_ATTACK,
                                  GEN_DECAY, GEN_RELEASE, GEN_HOLD, GEN_PAN):
                    generators[operator] = (amount - 65536 if amount >= 32768
                                            else amount)
                elif operator in (GEN_START_OFFSET, GEN_END_OFFSET,
                                  GEN_STARTLOOP_OFFSET, GEN_ENDLOOP_OFFSET):
                    signed = amount - 65536 if amount >= 32768 else amount
                    generators[operator] = generators.get(operator, 0) + signed
                else:
                    generators[operator] = amount

            if terminal not in generators and index == first:
                common = generators      # zona global: sus valores se heredan
                continue
            zones.append(Zone(generators))
        return zones

    def preset_zones(self, index):
        first = self.presets[index][3]
        last = self.presets[index + 1][3]
        return self._zones(self.preset_bags, self.preset_gens, first, last,
                           GEN_INSTRUMENT)

    def instrument_zones(self, index):
        first = self.instruments[index][1]
        last = self.instruments[index + 1][1]
        return self._zones(self.inst_bags, self.inst_gens, first, last,
                           GEN_SAMPLE_ID)

    def zone_for(self, program, key, bank=0):
        """La zona de instrumento que cubre esa nota, con su muestra.

        Devuelve (zona, muestra) o (None, None). Cuando varias zonas cubren la
        nota —suelen ser capas por velocidad— se queda con la primera, que en
        FluidR3 es la más suave y la que menos ruido de ataque trae.
        """
        preset = self.find_preset(program, bank)
        if preset is None:
            return None, None

        for zone in self.preset_zones(preset):
            instrument = zone.get(GEN_INSTRUMENT)
            if instrument is None or not zone.covers(key):
                continue
            for inner in self.instrument_zones(instrument):
                if inner.sample_id is None or not inner.covers(key):
                    continue
                return inner, self.samples[inner.sample_id]
        return None, None

    def pcm(self, start, end):
        """Las muestras de 16 bits con signo entre esos dos índices."""
        count = end - start
        if count <= 0:
            return []
        self.handle.seek(self.pcm_offset + start * 2)
        raw = self.handle.read(count * 2)
        return list(struct.unpack("<%dh" % (len(raw) // 2), raw))
