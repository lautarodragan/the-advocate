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


def to_signed(value):
    """BER no tiene signo: los negativos vienen en complemento a dos de 32 bits."""
    return value - 0x100000000 if value >= 0x80000000 else value


def to_int(payload):
    """Los enteros dentro de un chunk también van en BER."""
    return to_signed(Reader(payload).read_int())


def to_bool(payload):
    return bool(payload and payload[0])


def to_string(payload):
    return payload.decode("cp1252", errors="replace")


def to_u16_array(payload):
    return list(struct.unpack("<%dH" % (len(payload) // 2), payload))


def to_i16_array(payload):
    return list(struct.unpack("<%dh" % (len(payload) // 2), payload))


# --- Chunk IDs (liblcf: src/generated/lcf/*/chunks.h) ---------------------

MAP_CHIPSET_ID = 0x01
MAP_WIDTH = 0x02
MAP_HEIGHT = 0x03
MAP_SCROLL_TYPE = 0x0B
MAP_PARALLAX_FLAG = 0x1F
MAP_PARALLAX_NAME = 0x20
MAP_PARALLAX_LOOP_X = 0x21
MAP_PARALLAX_LOOP_Y = 0x22
MAP_PARALLAX_AUTO_LOOP_X = 0x23
MAP_PARALLAX_SX = 0x24
MAP_PARALLAX_AUTO_LOOP_Y = 0x25
MAP_PARALLAX_SY = 0x26
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
PAGE_TRANSLUCENT = 0x19
PAGE_MOVE_TYPE = 0x1F
PAGE_MOVE_FREQUENCY = 0x20
PAGE_TRIGGER = 0x21
PAGE_LAYER = 0x22
PAGE_OVERLAP_FORBIDDEN = 0x23
PAGE_ANIMATION_TYPE = 0x24
PAGE_MOVE_SPEED = 0x25
PAGE_COMMANDS = 0x34

CONDITION_FLAGS = 0x01
# switch_a, switch_b, variable, item, actor, timer, timer2: un bit cada una,
# LSB primero (liblcf: src/reader_flags.cpp).
CONDITION_ALL = 0x7F
CONDITION_NAMES = ("switch_a", "switch_b", "variable", "item",
                   "actor", "timer", "timer2")
CONDITION_IDS = {"switch_a": 0x02, "switch_b": 0x03, "variable": 0x04,
                 "item": 0x06, "actor": 0x07, "timer": 0x08, "timer2": 0x09}
CONDITION_VARIABLE_VALUE = 0x05
CONDITION_OPERATOR = 0x0A

# Nombres de los enums (liblcf: src/generated/lcf/rpg/eventpage.h y
# eventpagecondition.h). Los guardamos como texto en el JSON: un `trigger: 3`
# no le dice nada a nadie, un `trigger: "auto_start"` sí.
DIRECTIONS = ("up", "right", "down", "left")
PATTERNS = ("left", "middle", "right", "middle2")
MOVE_TYPES = ("stationary", "random", "vertical", "horizontal",
              "toward", "away", "custom")
TRIGGERS = ("action", "touched", "collision", "auto_start", "parallel")
LAYERS = ("below", "same", "above")
ANIM_TYPES = ("non_continuous", "continuous", "fixed_non_continuous",
              "fixed_continuous", "fixed_graphic", "spin", "step_frame_fix")
MOVE_SPEEDS = (None, "eighth", "quarter", "half", "normal", "double", "fourfold")
COMPARISONS = ("equal", "greater_equal", "less_equal",
               "greater", "less", "not_equal")


def enum_name(names, value):
    """El nombre del enum, o el número crudo si está fuera de rango."""
    return names[value] if 0 <= value < len(names) and names[value] else value

DB_CHIPSETS = 0x14

CHIPSET_NAME = 0x01
CHIPSET_FILENAME = 0x02
CHIPSET_TERRAIN = 0x03
CHIPSET_PASSABLE_LOWER = 0x04
CHIPSET_PASSABLE_UPPER = 0x05

START_PARTY_MAP_ID = 0x01
START_PARTY_X = 0x02
START_PARTY_Y = 0x03

MAPINFO_NAME = 0x01
MAPINFO_PARENT = 0x02
MAPINFO_INDENTATION = 0x03
MAPINFO_TYPE = 0x04


class EventCommand:
    """Una línea del script de una página.

    El formato es uniforme para los ~130 comandos de RM2k, así que se pueden
    leer todos sin saber qué hace cada código: código, sangría, un string y una
    lista de enteros. Interpretarlos es harina de otro costal.
    """

    __slots__ = ("code", "indent", "string", "parameters")

    def __init__(self, code, indent, string, parameters):
        self.code = code
        self.indent = indent
        self.string = string
        self.parameters = parameters


def read_commands(payload):
    """La lista de comandos de una página. No lleva contador: termina en 4 ceros."""
    reader = Reader(payload)
    commands = []
    while not reader.eof() and reader.data[reader.pos] != 0:
        code = reader.read_int()
        indent = reader.read_int()
        string = reader.read_string(reader.read_int())
        parameters = [to_signed(reader.read_int())
                      for _ in range(reader.read_int())]
        commands.append(EventCommand(code, indent, string, parameters))
    return commands


class EventPageCondition:
    """Lo que tiene que pasar para que esta página sea la activa."""

    def __init__(self, fields):
        flags = fields.get(CONDITION_FLAGS, b"\x00")[0]
        self.active = [name for i, name in enumerate(CONDITION_NAMES)
                       if flags & (1 << i)]
        self.ids = {name: to_int(fields.get(chunk, b"\x01"))
                    for name, chunk in CONDITION_IDS.items()}
        self.variable_value = to_int(fields.get(CONDITION_VARIABLE_VALUE, b"\x00"))
        self.operator = to_int(fields.get(CONDITION_OPERATOR, b"\x01"))

    def __bool__(self):
        return bool(self.active)


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
        self.translucent = to_bool(fields.get(PAGE_TRANSLUCENT))
        self.move_type = to_int(fields.get(PAGE_MOVE_TYPE, b"\x01"))
        self.move_frequency = to_int(fields.get(PAGE_MOVE_FREQUENCY, b"\x03"))
        self.move_speed = to_int(fields.get(PAGE_MOVE_SPEED, b"\x03"))
        self.trigger = to_int(fields.get(PAGE_TRIGGER, b"\x00"))
        self.layer = to_int(fields.get(PAGE_LAYER, b"\x00"))
        self.overlap_forbidden = to_bool(fields.get(PAGE_OVERLAP_FORBIDDEN))
        self.animation_type = to_int(fields.get(PAGE_ANIMATION_TYPE, b"\x00"))
        self.commands = read_commands(fields.get(PAGE_COMMANDS, b""))

        self.condition = EventPageCondition(
            Reader(fields.get(PAGE_CONDITION, b"\x00")).read_struct())
        self.unconditional = not self.condition


class Event:
    def __init__(self, event_id, fields):
        self.id = event_id
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
        self.scroll_type = to_int(fields.get(MAP_SCROLL_TYPE, b"\x00"))
        self.parallax_flag = to_bool(fields.get(MAP_PARALLAX_FLAG))
        self.parallax_name = to_string(fields.get(MAP_PARALLAX_NAME, b""))
        self.parallax_loop_x = to_bool(fields.get(MAP_PARALLAX_LOOP_X))
        self.parallax_loop_y = to_bool(fields.get(MAP_PARALLAX_LOOP_Y))
        self.parallax_auto_loop_x = to_bool(fields.get(MAP_PARALLAX_AUTO_LOOP_X))
        self.parallax_auto_loop_y = to_bool(fields.get(MAP_PARALLAX_AUTO_LOOP_Y))
        self.parallax_sx = to_int(fields.get(MAP_PARALLAX_SX, b"\x00"))
        self.parallax_sy = to_int(fields.get(MAP_PARALLAX_SY, b"\x00"))
        self.lower_layer = to_u16_array(fields[MAP_LOWER_LAYER])
        self.upper_layer = to_u16_array(fields[MAP_UPPER_LAYER])
        self.events = [Event(i, f) for i, f in sorted(
            Reader(fields.get(MAP_EVENTS, b"\x00")).read_struct_array().items())]


# Passability por defecto, para los chipsets que dejaron el chunk sin escribir
# (liblcf: src/generated/lcf/rpg/chipset.h). 15 = transitable por los cuatro
# lados y por debajo del héroe; el 31 del primer tile alto lo pone por encima.
PASSABLE_LOWER_DEFAULT = bytes([15]) * 162
PASSABLE_UPPER_DEFAULT = bytes([31]) + bytes([15]) * 143


def _passability(payload, default):
    """Completa con los defaults lo que el archivo no traiga."""
    return payload + default[len(payload):]


class Chipset:
    def __init__(self, fields):
        self.name = to_string(fields.get(CHIPSET_NAME, b""))
        self.filename = to_string(fields.get(CHIPSET_FILENAME, b""))
        self.passable_lower = _passability(
            fields.get(CHIPSET_PASSABLE_LOWER, b""), PASSABLE_LOWER_DEFAULT)
        self.passable_upper = _passability(
            fields.get(CHIPSET_PASSABLE_UPPER, b""), PASSABLE_UPPER_DEFAULT)
        self.terrain = to_i16_array(fields.get(CHIPSET_TERRAIN, b""))


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

        infos = reader.read_struct_array()
        self.map_names = {i: to_string(f.get(MAPINFO_NAME, b""))
                          for i, f in infos.items()}
        self.map_parents = {i: to_int(f.get(MAPINFO_PARENT, b"\x00"))
                            for i, f in infos.items()}
        # Tipo 0 = raíz del árbol, 1 = mapa de verdad, 2 = carpeta del editor.
        self.map_types = {i: to_int(f.get(MAPINFO_TYPE, b"\x00"))
                          for i, f in infos.items()}

        count = reader.read_int()
        self.tree_order = [reader.read_int() for _ in range(count)]
        reader.read_int()                   # active_node, cosa del editor

        start = reader.read_struct()
        self.start_map_id = to_int(start[START_PARTY_MAP_ID])
        self.start_x = to_int(start[START_PARTY_X])
        self.start_y = to_int(start[START_PARTY_Y])
