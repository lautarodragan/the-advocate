"""Lector mínimo de formatos LCF de RPG Maker 2000 (.lmu / .ldb / .lmt).

Sólo lee lo que hace falta para renderizar un mapa: dimensiones, chipset y las
dos capas de tiles. Portado de liblcf (EasyRPG), que es la referencia del
formato: src/reader_struct_impl.h para el encoding de structs/arrays y
src/generated/lcf/{lmu,ldb,lmt}/chunks.h para los IDs de chunk.

Encoding del archivo:
  - Header: int BER con el largo, seguido del string ("LcfMapUnit", etc).
  - Struct: secuencia de chunks (id BER, largo BER, bytes) terminada en id 0.
  - Array de structs: count BER, y por cada elemento un ID BER + un Struct.
"""

import struct


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def eof(self):
        return self.pos >= len(self.data)

    def read(self, n):
        chunk = self.data[self.pos:self.pos + n]
        if len(chunk) != n:
            raise EOFError("lectura fuera de rango")
        self.pos += n
        return chunk

    def read_int(self):
        """Entero BER: 7 bits por byte, bit 8 indica "sigue"."""
        value = 0
        while True:
            byte = self.read(1)[0]
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value

    def read_string(self, length):
        return self.read(length).decode("cp1252", errors="replace")

    def read_header(self):
        return self.read_string(self.read_int())

    def chunks(self):
        """Itera (id, payload) hasta el chunk terminador 0 o el fin del archivo."""
        while not self.eof():
            chunk_id = self.read_int()
            if chunk_id == 0:
                return
            yield chunk_id, self.read(self.read_int())

    def read_struct(self):
        """Un struct completo como dict {chunk_id: bytes}."""
        return dict(self.chunks())

    def read_struct_array(self):
        """Array de structs con ID como dict {id: {chunk_id: bytes}}."""
        count = self.read_int()
        items = {}
        for _ in range(count):
            item_id = self.read_int()
            items[item_id] = self.read_struct()
        return items


def to_int(payload):
    """Los enteros dentro de un chunk también van en BER."""
    return Reader(payload).read_int()


def to_string(payload):
    return payload.decode("cp1252", errors="replace")


def to_u16_array(payload):
    return list(struct.unpack("<%dH" % (len(payload) // 2), payload))


# --- Chunk IDs (liblcf: src/generated/lcf/*/chunks.h) ---------------------

MAP_CHIPSET_ID = 0x01
MAP_WIDTH = 0x02
MAP_HEIGHT = 0x03
MAP_PARALLAX_NAME = 0x20
MAP_LOWER_LAYER = 0x47
MAP_UPPER_LAYER = 0x48
MAP_EVENTS = 0x51

EVENT_NAME = 0x01
EVENT_X = 0x02
EVENT_Y = 0x03
EVENT_PAGES = 0x05

PAGE_CONDITION = 0x02
PAGE_CHARACTER_NAME = 0x15
PAGE_CHARACTER_INDEX = 0x16
PAGE_CHARACTER_DIRECTION = 0x17
PAGE_CHARACTER_PATTERN = 0x18
PAGE_LAYER = 0x22

CONDITION_FLAGS = 0x01
# switch_a, switch_b, variable, item, actor, timer, timer2: un bit cada una,
# LSB primero (liblcf: src/reader_flags.cpp).
CONDITION_ALL = 0x7F

DB_CHIPSETS = 0x14

CHIPSET_NAME = 0x01
CHIPSET_FILENAME = 0x02
CHIPSET_PASSABLE_LOWER = 0x04
CHIPSET_PASSABLE_UPPER = 0x05

START_PARTY_MAP_ID = 0x01
START_PARTY_X = 0x02
START_PARTY_Y = 0x03

MAPINFO_NAME = 0x01


class EventPage:
    """Una de las versiones que puede adoptar un evento.

    Los defaults salen de liblcf (src/generated/lcf/rpg/eventpage.h): mirando
    hacia abajo (dirección 2) y con el frame del medio (patrón 1), que es la
    pose parada.
    """

    def __init__(self, fields):
        self.character_name = to_string(fields.get(PAGE_CHARACTER_NAME, b""))
        self.character_index = to_int(fields.get(PAGE_CHARACTER_INDEX, b"\x00"))
        self.character_direction = to_int(fields.get(PAGE_CHARACTER_DIRECTION, b"\x02"))
        self.character_pattern = to_int(fields.get(PAGE_CHARACTER_PATTERN, b"\x01"))
        self.layer = to_int(fields.get(PAGE_LAYER, b"\x00"))

        condition = Reader(fields.get(PAGE_CONDITION, b"\x00")).read_struct()
        flags = condition.get(CONDITION_FLAGS, b"\x00")
        self.unconditional = not (flags[0] & CONDITION_ALL)


class Event:
    def __init__(self, fields):
        self.name = to_string(fields.get(EVENT_NAME, b""))
        self.x = to_int(fields.get(EVENT_X, b"\x00"))
        self.y = to_int(fields.get(EVENT_Y, b"\x00"))
        self.pages = [EventPage(f) for _, f
                      in sorted(Reader(fields[EVENT_PAGES]).read_struct_array().items())]

    def active_page(self, ignore_conditions=False):
        """La página que mostraría el motor en una partida recién empezada.

        RM2k usa la página de número más alto cuyas condiciones se cumplen
        todas. Sin switches ni variables seteadas, eso es la última página que
        no tiene ninguna condición. Puede no haber ninguna.
        """
        if ignore_conditions:
            return self.pages[0] if self.pages else None

        for page in reversed(self.pages):
            if page.unconditional:
                return page
        return None


class Map:
    def __init__(self, path):
        reader = Reader(open(path, "rb").read())
        header = reader.read_header()
        if header != "LcfMapUnit":
            raise ValueError("%s no es un mapa LCF (header %r)" % (path, header))

        # RM2k omite los chunks que quedaron en su valor por defecto
        # (liblcf: src/generated/lcf/rpg/map.h).
        fields = reader.read_struct()
        self.chipset_id = to_int(fields.get(MAP_CHIPSET_ID, b"\x01"))
        self.width = to_int(fields.get(MAP_WIDTH, b"\x14"))
        self.height = to_int(fields.get(MAP_HEIGHT, b"\x0f"))
        self.parallax_name = to_string(fields.get(MAP_PARALLAX_NAME, b""))
        self.lower_layer = to_u16_array(fields[MAP_LOWER_LAYER])
        self.upper_layer = to_u16_array(fields[MAP_UPPER_LAYER])
        self.events = [Event(f) for _, f in sorted(
            Reader(fields.get(MAP_EVENTS, b"\x00")).read_struct_array().items())]


class Chipset:
    def __init__(self, fields):
        self.name = to_string(fields.get(CHIPSET_NAME, b""))
        self.filename = to_string(fields.get(CHIPSET_FILENAME, b""))
        self.passable_lower = fields.get(CHIPSET_PASSABLE_LOWER, b"")
        self.passable_upper = fields.get(CHIPSET_PASSABLE_UPPER, b"")


class Database:
    """RPG_RT.ldb, del que sólo nos interesa la lista de chipsets."""

    def __init__(self, path):
        reader = Reader(open(path, "rb").read())
        header = reader.read_header()
        if header != "LcfDataBase":
            raise ValueError("%s no es una base LCF (header %r)" % (path, header))

        self.chipsets = {}
        for chunk_id, payload in reader.chunks():
            if chunk_id == DB_CHIPSETS:
                self.chipsets = {i: Chipset(f) for i, f
                                 in Reader(payload).read_struct_array().items()}
                break


class TreeMap:
    """RPG_RT.lmt: el árbol de mapas y la posición inicial del jugador.

    No es chunk-based en el nivel raíz; ver liblcf src/lmt_treemap.cpp.
    """

    def __init__(self, path):
        reader = Reader(open(path, "rb").read())
        header = reader.read_header()
        if header != "LcfMapTree":
            raise ValueError("%s no es un árbol LCF (header %r)" % (path, header))

        self.map_names = {i: to_string(f.get(MAPINFO_NAME, b""))
                          for i, f in reader.read_struct_array().items()}
        for _ in range(reader.read_int()):  # tree_order, no lo usamos
            reader.read_int()
        reader.read_int()                   # active_node, tampoco

        start = reader.read_struct()
        self.start_map_id = to_int(start[START_PARTY_MAP_ID])
        self.start_x = to_int(start[START_PARTY_X])
        self.start_y = to_int(start[START_PARTY_Y])
