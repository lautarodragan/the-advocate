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

import os
import struct

from lcf_schema import FLAGS, SCHEMA, SKIP


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
    """El texto del juego es cp1252, pero quedan restos del RTP japonés.

    ABL se hizo con el RPG Maker 2000 de Don Miguel, así que casi todo es
    cp1252; un par de mensajes que el autor nunca tocó siguen en Shift-JIS. Los
    bytes que cp1252 no define (0x81, 0x8D, 0x8F, 0x90, 0x9D) son la señal para
    reintentar: no aparecen en texto occidental y sí en Shift-JIS.
    """
    try:
        return payload.decode("cp1252")
    except UnicodeDecodeError:
        pass
    try:
        return payload.decode("shift_jis")
    except UnicodeDecodeError:
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
PAGE_MOVE_ROUTE = 0x29
PAGE_COMMANDS = 0x34

# La ruta propia de la página —la que camina sola con move_type 6— es un
# struct MoveRoute: liblcf, src/generated/lcf/lmu/chunks.h.
ROUTE_COMMANDS = 0x0C
ROUTE_REPEAT = 0x15
ROUTE_SKIPPABLE = 0x16

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

DB_ACTORS = 0x0B
DB_ITEMS = 0x0D
DB_CHIPSETS = 0x14
DB_SYSTEM = 0x16
# Los términos del juego: los textos que el motor pone y no un evento. La
# pantalla de título usa tres. Los códigos salen de `chunks.h` de liblcf, igual
# que todo lo demás de este archivo.
DB_TERMS = 0x15
TERMS_NEW_GAME = 0x72
TERMS_LOAD_GAME = 0x73
TERMS_EXIT_GAME = 0x75
TERMS_LOAD_MESSAGE = 0x93
TERMS_SAVE_MESSAGE = 0x92
TERMS_FILE = 0x94
TERMS_LEVEL = 0x7B
# El nivel abreviado —"L" en el ABL— que es lo que el menú de archivos escribe
# delante del número: `lcf::Data::terms.lvl_short` en `Window_SaveFile`.
TERMS_LVL_SHORT = 0x80
# Los del menú de pausa (liblcf: ldb/chunks.h, ChunkTerms). En el ABL dicen
# 'Use Item', 'Tech Skill', 'Equipment', 'Save', 'End Game', 'Cr', 'Normal'
# y 'HP'.
TERMS_GOLD = 0x5F
TERMS_COMMAND_ITEM = 0x6A
TERMS_COMMAND_SKILL = 0x6B
TERMS_MENU_EQUIPMENT = 0x6C
TERMS_MENU_SAVE = 0x6E
TERMS_MENU_QUIT = 0x70
TERMS_NORMAL_STATUS = 0x7E
TERMS_HP_SHORT = 0x81
# Los del equipo: los cuatro parámetros y las cinco ranuras. En el ABL dicen
# 'Attack', 'Defense', 'Mental', 'Agility' y 'Right Hand', 'Left Hand',
# 'Body', 'Head', 'Other'.
TERMS_PARAMS = (0x84, 0x85, 0x86, 0x87)
TERMS_EQUIPO = (0x88, 0x89, 0x8A, 0x8B, 0x8C)

# Del esquema de liblcf, igual que todo lo demás de este archivo: los números no
# se ponen de memoria. Ya pasó una vez con los códigos de comando de las puertas
# —tres estaban mal— y por eso event_codes.py se genera desde ahí.
ACTOR_NAME = 0x01
ACTOR_CHARSET = 0x03
ACTOR_CHARSET_INDEX = 0x04
# La cara del actor —el FaceSet y cuál de sus dieciséis— que es lo que el menú
# de archivos muestra por cada uno del grupo. `ChunkActor::face_name` y
# `face_index` en ldb/chunks.h de liblcf.
ACTOR_FACE_NAME = 0x0F
ACTOR_FACE_INDEX = 0x10
# Los parámetros por nivel: seis tablas de int16 seguidas —HP máximo, SP
# máximo, ataque, defensa, espíritu y agilidad—, una entrada por nivel.
ACTOR_PARAMETERS = 0x1F
ACTOR_INITIAL_EQUIPMENT = 0x33
SYSTEM_PARTY = 0x16
# El System del juego: el PNG con el marco de la ventana, los colores de texto
# y la sombra. Este juego usa `ablskin`, no el `BLSys` que también trae.
SYSTEM_NAME = 0x13
# La pantalla de título: qué imagen lleva y con qué tema suena. Los dos códigos
# salen de `src/generated/lcf/ldb/chunks.h` de liblcf, igual que el resto de
# este archivo; ponerlos de memoria es exactamente el error que este repo ya
# pagó con los códigos de comando de las puertas.
SYSTEM_TITLE_NAME = 0x11
SYSTEM_TITLE_MUSIC = 0x1F
# Con qué fuente dibuja el texto: 0 Gothic, 1 Mincho. easyrpg elige ttyp0 o
# rmg2000 con esto, y las letras salen distintas. Este juego pide Mincho.
SYSTEM_FONT_ID = 0x48

CHIPSET_NAME = 0x01
CHIPSET_FILENAME = 0x02
CHIPSET_TERRAIN = 0x03
CHIPSET_PASSABLE_LOWER = 0x04
CHIPSET_PASSABLE_UPPER = 0x05
# Los dos que gobiernan la animación del agua: el tipo elige entre el ciclo de
# cuatro pasos —0,1,2,1— y el de tres, y la velocidad entre 24 y 12 cuadros por
# paso. Los dos faltan en casi todos los chipsets, y faltar es el default: ver
# `paso_de_agua` en rm2k.py.
CHIPSET_ANIMATION_TYPE = 0x0B
CHIPSET_ANIMATION_SPEED = 0x0C

START_PARTY_MAP_ID = 0x01
START_PARTY_X = 0x02
START_PARTY_Y = 0x03

MAPINFO_NAME = 0x01
MAPINFO_MUSIC_TYPE = 0x0B   # 0 = heredar del padre, 1 = del evento, 2 = el de acá
MAPINFO_MUSIC = 0x0C

MUSIC_NAME = 0x01
MUSIC_FADEIN = 0x02
MUSIC_VOLUME = 0x03
MUSIC_TEMPO = 0x04
MUSIC_BALANCE = 0x05
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


# Si no es None, el nombre del CharSet de una página translúcida pasa por acá
# y para quien lo lea es otro gráfico. Lo prende el port —ver
# `rm2k.decorar_translucido`— y no el lector: el volcado a JSON tiene que
# seguir viendo el nombre de verdad.
#
# Recibe también **dónde está parado el evento** (mapa, x, y), porque el
# horneado necesita el fondo real de esa celda; por eso no se decora en la
# página, que no lo sabe, sino en el evento.
DECORAR_TRANSLUCIDO = None



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


class MoveRoute:
    """La ruta propia de una página: las órdenes, si se repite y si una orden
    bloqueada se saltea. Los defaults son los de liblcf: se repite y no se
    saltea.

    Las órdenes van con los mismos códigos que las de un `MoveEvent`, y se
    leen como `RawStruct<rpg::MoveCommand>::ReadLcf` de liblcf: el código, y
    según cuál, sus operandos —un entero para los switches, texto y entero
    para cambiar el gráfico, texto y tres enteros para el sonido—. Acá se
    guarda sólo el código; ninguna de las órdenes con operandos se ejecuta.
    """

    def __init__(self, fields):
        self.repeat = to_bool(fields.get(ROUTE_REPEAT, b"\x01"))
        self.skippable = to_bool(fields.get(ROUTE_SKIPPABLE))
        self.commands = []
        reader = Reader(fields.get(ROUTE_COMMANDS, b""))
        while not reader.eof():
            code = reader.read_int()
            if code in (32, 33):                # switch_on, switch_off
                reader.read_int()
            elif code == 34:                    # change_graphic
                reader.read_string(reader.read_int())
                reader.read_int()
            elif code == 35:                    # play_sound_effect
                reader.read_string(reader.read_int())
                reader.read_int(); reader.read_int(); reader.read_int()
            self.commands.append(code)


class EventPage:
    """Una de las versiones que puede adoptar un evento.

    Los defaults salen de liblcf (src/generated/lcf/rpg/eventpage.h): mirando
    hacia abajo (dirección 2) y con el frame del medio (patrón 1), que es la
    pose parada.
    """

    def __init__(self, fields):
        self.character_name = to_string(fields.get(PAGE_CHARACTER_NAME, b""))
        self.translucent = to_bool(fields.get(PAGE_TRANSLUCENT))
        self.character_index = to_int(fields.get(PAGE_CHARACTER_INDEX, b"\x00"))
        self.character_direction = to_int(fields.get(PAGE_CHARACTER_DIRECTION, b"\x02"))
        self.character_pattern = to_int(fields.get(PAGE_CHARACTER_PATTERN, b"\x01"))
        self.move_type = to_int(fields.get(PAGE_MOVE_TYPE, b"\x01"))
        self.move_frequency = to_int(fields.get(PAGE_MOVE_FREQUENCY, b"\x03"))
        self.move_speed = to_int(fields.get(PAGE_MOVE_SPEED, b"\x03"))
        self.trigger = to_int(fields.get(PAGE_TRIGGER, b"\x00"))
        self.layer = to_int(fields.get(PAGE_LAYER, b"\x00"))
        self.overlap_forbidden = to_bool(fields.get(PAGE_OVERLAP_FORBIDDEN))
        self.animation_type = to_int(fields.get(PAGE_ANIMATION_TYPE, b"\x00"))
        self.commands = read_commands(fields.get(PAGE_COMMANDS, b""))
        self.move_route = MoveRoute(
            Reader(fields.get(PAGE_MOVE_ROUTE, b"\x00")).read_struct())

        self.condition = EventPageCondition(
            Reader(fields.get(PAGE_CONDITION, b"\x00")).read_struct())
        self.unconditional = not self.condition


class Event:
    def __init__(self, event_id, fields, map_id=0):
        self.id = event_id
        self.name = to_string(fields.get(EVENT_NAME, b""))
        self.x = to_int(fields.get(EVENT_X, b"\x00"))
        self.y = to_int(fields.get(EVENT_Y, b"\x00"))
        self.pages = [EventPage(f) for _, f
                      in sorted(Reader(fields[EVENT_PAGES]).read_struct_array().items())]
        if DECORAR_TRANSLUCIDO:
            # Ver DECORAR_TRANSLUCIDO: para el port, un CharSet translúcido es
            # otro gráfico, y si va horneado también depende de dónde está.
            for page in self.pages:
                if page.translucent and page.character_name:
                    page.character_name = DECORAR_TRANSLUCIDO(
                        page.character_name, map_id, self.x, self.y)

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
        # El número de mapa no está adentro del archivo: sale del nombre, que
        # es de donde lo saca todo el resto del port. Lo necesitan los eventos
        # translúcidos horneados, que llevan en el nombre de su gráfico dónde
        # están parados.
        base = os.path.basename(path)
        self.map_id = int(base[3:7]) if base[3:7].isdigit() else 0
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
        self.events = [Event(i, f, self.map_id) for i, f in sorted(
            Reader(fields.get(MAP_EVENTS, b"\x00")).read_struct_array().items())]


# Passability por defecto, para los chipsets que dejaron el chunk sin escribir
# (liblcf: src/generated/lcf/rpg/chipset.h). 15 = transitable por los cuatro
# lados y por debajo del héroe; el 31 del primer tile alto lo pone por encima.
PASSABLE_LOWER_DEFAULT = bytes([15]) * 162
PASSABLE_UPPER_DEFAULT = bytes([31]) + bytes([15]) * 143


def _passability(payload, default):
    """Completa con los defaults lo que el archivo no traiga."""
    return payload + default[len(payload):]


# --- Decodificador genérico, guiado por el esquema -------------------------
#
# Los formatos LCF son todos el mismo mecanismo: structs de chunks tipados. Con
# el esquema que tools/gen_schema.py saca de liblcf se puede decodificar
# cualquiera de los 63 structs sin escribir una clase por cada uno. Es lo que
# usa el volcado de la base de datos, que tiene cientos de campos.

MOVE_COMMANDS = {
    32: "switch_on", 33: "switch_off", 34: "change_graphic", 35: "play_sound_effect",
}


def read_move_commands(payload):
    """Las órdenes de una ruta de movimiento. Casi todas son sólo un código."""
    reader = Reader(payload)
    commands = []
    while not reader.eof():
        code = reader.read_int()
        command = {"command": MOVE_COMMANDS.get(code, code)}
        if code in (32, 33):                       # switch_on / switch_off
            command["switch"] = reader.read_int()
        elif code == 34:                           # change_graphic
            command["charset"] = reader.read_string(reader.read_int())
            command["index"] = reader.read_int()
        elif code == 35:                           # play_sound_effect
            command["sound"] = reader.read_string(reader.read_int())
            command["volume"] = reader.read_int()
            command["tempo"] = reader.read_int()
            command["balance"] = reader.read_int()
        commands.append(command)
    return commands


def _unpack(fmt, payload, size):
    return list(struct.unpack("<%d%s" % (len(payload) // size, fmt), payload))


def decode_value(payload, kind, unknown):
    """Un chunk, según el tipo que le da el esquema."""
    if kind == "int":
        return to_int(payload)
    if kind == "bool":
        return to_int(payload) > 0
    if kind == "string":
        return to_string(payload)
    if kind == "u8":
        return payload[0] if payload else 0
    if kind == "i8":
        return struct.unpack("<b", payload[:1])[0] if payload else 0
    if kind == "u32":
        return struct.unpack("<I", payload)[0]
    if kind == "double":
        return struct.unpack("<d", payload)[0]
    if kind == "bits":
        return [bool(b) for b in payload]
    if kind == "u8array":
        return list(payload)
    if kind == "i16array":
        return to_i16_array(payload)
    if kind == "i32array":
        return _unpack("i", payload, 4)
    if kind == "u32array":
        return _unpack("I", payload, 4)
    if kind == "rect":
        return dict(zip(("l", "t", "r", "b"), _unpack("I", payload, 4)))
    if kind == "equipment":
        return dict(zip(("weapon", "shield", "armor", "helmet", "accessory"),
                        to_i16_array(payload)))
    if kind == "parameters":
        # Seis curvas de estadística por nivel, una atrás de la otra.
        levels = len(payload) // 12
        values = to_i16_array(payload)
        names = ("maxhp", "maxsp", "attack", "defense", "spirit", "agility")
        return {n: values[i * levels:(i + 1) * levels] for i, n in enumerate(names)}
    if kind == "commands":
        return [{"indent": c.indent, "code": c.code,
                 "string": c.string, "parameters": c.parameters}
                for c in read_commands(payload)]
    if kind == "movecommands":
        return read_move_commands(payload)
    if kind.startswith("flags:"):
        # Sólo los bits prendidos. Listar los ocho con su false no agrega nada
        # y llena el JSON de ruido: qué flags existen es cosa del esquema.
        names = FLAGS.get(kind[6:], [])
        return [n for i, n in enumerate(names)
                if i // 8 < len(payload) and payload[i // 8] & (1 << (i % 8))]
    if kind.startswith("struct:"):
        return decode_struct(Reader(payload).read_struct(), kind[7:], unknown)
    if kind.startswith("array:"):
        return {i: decode_struct(f, kind[6:], unknown)
                for i, f in Reader(payload).read_struct_array().items()}

    unknown.add(kind)
    return payload.hex()


def decode_struct(fields, struct_name, unknown=None):
    """Un struct entero como dict, con los nombres de campo de liblcf."""
    if unknown is None:
        unknown = set()
    schema = SCHEMA.get(struct_name, {})
    skip = SKIP.get(struct_name, ())

    result = {}
    for chunk_id, payload in fields.items():
        if chunk_id in skip:
            continue
        entry = schema.get(chunk_id)
        if entry is None:
            # Nada se pierde en silencio: los chunks que el esquema no conoce
            # quedan en hexa, con su ID a la vista.
            unknown.add("%s:0x%02X" % (struct_name, chunk_id))
            result["unknown_0x%02X" % chunk_id] = payload.hex()
            continue
        name, kind = entry
        result[name] = decode_value(payload, kind, unknown)
    return result


class Chipset:
    def __init__(self, fields):
        self.name = to_string(fields.get(CHIPSET_NAME, b""))
        self.filename = to_string(fields.get(CHIPSET_FILENAME, b""))
        self.passable_lower = _passability(
            fields.get(CHIPSET_PASSABLE_LOWER, b""), PASSABLE_LOWER_DEFAULT)
        self.passable_upper = _passability(
            fields.get(CHIPSET_PASSABLE_UPPER, b""), PASSABLE_UPPER_DEFAULT)
        self.terrain = to_i16_array(fields.get(CHIPSET_TERRAIN, b""))
        self.animation_type = to_int(
            fields.get(CHIPSET_ANIMATION_TYPE, b"\x00"))
        self.animation_speed = to_int(
            fields.get(CHIPSET_ANIMATION_SPEED, b"\x00"))


class Actor:
    """Un personaje de la base: de acá sale con qué gráfico se lo dibuja."""

    def __init__(self, fields):
        self.name = to_string(fields.get(ACTOR_NAME, b""))
        self.charset = to_string(fields.get(ACTOR_CHARSET, b""))
        self.charset_index = to_int(fields.get(ACTOR_CHARSET_INDEX, b"\x00"))
        self.face_name = to_string(fields.get(ACTOR_FACE_NAME, b""))
        self.face_index = to_int(fields.get(ACTOR_FACE_INDEX, b"\x00"))
        # Los parámetros por nivel, desde el 1: `maxhp`, `attack`, `defense`,
        # `spirit`, `agility`, cada uno una lista.
        self.params = decode_value(fields.get(ACTOR_PARAMETERS, b""),
                                   "parameters", set())
        self.hp_max = self.params.get("maxhp", [])
        # El equipo con el que arranca: arma, escudo, armadura, casco y
        # accesorio, por número de ítem, 0 si nada.
        equipo = decode_value(fields.get(ACTOR_INITIAL_EQUIPMENT, b""),
                              "equipment", set())
        self.initial_equipment = [equipo.get(k, 0) for k in (
            "weapon", "shield", "armor", "helmet", "accessory")]


# Un ítem de la base (liblcf: ldb/chunks.h, ChunkItem).
ITEM_NAME = 0x01
ITEM_DESCRIPTION = 0x02
ITEM_TYPE = 0x03
ITEM_USES = 0x06
ITEM_SWITCH_ID = 0x37
ITEM_OCCASION_FIELD2 = 0x39
ITEM_PRICE = 0x05
ITEM_ATK = 0x0B
ITEM_DEF = 0x0C
ITEM_SPI = 0x0D
ITEM_AGI = 0x0E
ITEM_TWO_HANDED = 0x0F
ITEM_ACTOR_SET = 0x3E
# Los tipos, en el orden de `rpg::Item::Type`.
ITEM_TIPO_COMUN, ITEM_TIPO_ARMA, ITEM_TIPO_ESCUDO, ITEM_TIPO_ARMADURA, \
    ITEM_TIPO_CASCO, ITEM_TIPO_ACCESORIO, ITEM_TIPO_MEDICINA, \
    ITEM_TIPO_LIBRO, ITEM_TIPO_MATERIAL, ITEM_TIPO_UNICO, \
    ITEM_TIPO_SWITCH = range(11)


class Item:
    """Un ítem: lo que el menú muestra de él y lo poco que hace hoy."""

    def __init__(self, fields):
        self.name = to_string(fields.get(ITEM_NAME, b""))
        self.description = to_string(fields.get(ITEM_DESCRIPTION, b""))
        self.type = to_int(fields.get(ITEM_TYPE, b"\x00"))
        self.uses = to_int(fields.get(ITEM_USES, b"\x01"))
        self.switch_id = to_int(fields.get(ITEM_SWITCH_ID, b"\x01"))
        self.occasion_field2 = to_bool(fields.get(ITEM_OCCASION_FIELD2,
                                                  b"\x01"))
        self.price = to_int(fields.get(ITEM_PRICE, b"\x00"))
        # Lo que suma al equipárselo: ataque, defensa, espíritu, agilidad.
        self.puntos = [to_int(fields.get(c, b"\x00"))
                       for c in (ITEM_ATK, ITEM_DEF, ITEM_SPI, ITEM_AGI)]
        self.two_handed = to_bool(fields.get(ITEM_TWO_HANDED, b"\x00"))
        self.actor_set = [bool(b) for b in fields.get(ITEM_ACTOR_SET, b"")]

    def equipable_por(self, actor):
        """`actor_set`, con los que no alcanza la lista en sí: es lo que
        hace RM2k con un ítem que se hizo antes de agregar actores."""
        return self.actor_set[actor - 1] if actor - 1 < len(self.actor_set) \
            else True


class Database:
    """RPG_RT.ldb: los chipsets, los personajes y el grupo con el que se arranca."""

    def __init__(self, path):
        reader = Reader(open(path, "rb").read())
        header = reader.read_header()
        if header != "LcfDataBase":
            raise ValueError("%s no es una base LCF (header %r)" % (path, header))

        self.fields = reader.read_struct()
        self.chipsets = {i: Chipset(f) for i, f in Reader(
            self.fields.get(DB_CHIPSETS, b"\x00")).read_struct_array().items()}
        self.actors = {i: Actor(f) for i, f in Reader(
            self.fields.get(DB_ACTORS, b"\x00")).read_struct_array().items()}
        # Los ítems, y el número más alto: `ITEMS_N` en eventos.py es éste
        # más uno, y test_items.py lo comprueba.
        self.items = {i: Item(f) for i, f in Reader(
            self.fields.get(DB_ITEMS, b"\x00")).read_struct_array().items()}
        self.items_max = max(self.items, default=0)

        # El grupo con el que empieza la partida. En RM2k el gráfico del héroe
        # es el del primero de la lista, así que este dato es el que decide con
        # qué sprite se dibuja: hasta ahora salía de un default de la línea de
        # comandos del conversor, que daba Future1[0] cuando el juego arranca
        # con el actor 10, 'DummyHero', que es Chubby2[2].
        sistema = Reader(self.fields.get(DB_SYSTEM, b"\x00")).read_struct()
        self.party = to_i16_array(sistema.get(SYSTEM_PARTY, b""))
        self.system_name = sistema.get(SYSTEM_NAME, b"").decode(
            "cp1252", "replace")
        self.font_id = sistema.get(SYSTEM_FONT_ID, b"\x00")[0]
        # La imagen de la pantalla de título y su tema. En el ABL son
        # 'ABL20Title' y 'Fantasia_Of_The_Wind'; el otro PNG que hay en Title/
        # —'LineTitle'— es de una versión anterior y el juego no lo usa.
        self.title_name = to_string(sistema.get(SYSTEM_TITLE_NAME, b""))
        titulo_music = Reader(
            sistema.get(SYSTEM_TITLE_MUSIC, b"\x00")).read_struct()
        self.title_music = to_string(titulo_music.get(MUSIC_NAME, b""))
        # Los términos de la pantalla de título. En el ABL no son los de
        # fábrica: dicen 'Begin the Story' y 'Resume the Story', que es lo que
        # el juego eligió y por eso salen de acá y no de un literal nuestro.
        terminos = Reader(self.fields.get(DB_TERMS, b"\x00")).read_struct()
        self.term_new_game = to_string(terminos.get(TERMS_NEW_GAME, b""))
        self.term_load_game = to_string(terminos.get(TERMS_LOAD_GAME, b""))
        self.term_load_message = to_string(
            terminos.get(TERMS_LOAD_MESSAGE, b""))
        self.term_save_message = to_string(
            terminos.get(TERMS_SAVE_MESSAGE, b""))
        self.term_file = to_string(terminos.get(TERMS_FILE, b""))
        self.term_level = to_string(terminos.get(TERMS_LEVEL, b""))
        self.term_lvl_short = to_string(terminos.get(TERMS_LVL_SHORT, b""))
        self.term_gold = to_string(terminos.get(TERMS_GOLD, b""))
        self.term_menu = [to_string(terminos.get(t, b"")) for t in (
            TERMS_COMMAND_ITEM, TERMS_COMMAND_SKILL, TERMS_MENU_EQUIPMENT,
            TERMS_MENU_SAVE, TERMS_MENU_QUIT)]
        self.term_normal_status = to_string(
            terminos.get(TERMS_NORMAL_STATUS, b""))
        self.term_hp_short = to_string(terminos.get(TERMS_HP_SHORT, b""))
        self.term_params = [to_string(terminos.get(t, b""))
                            for t in TERMS_PARAMS]
        self.term_equipo = [to_string(terminos.get(t, b""))
                            for t in TERMS_EQUIPO]
        self.terminos = terminos    # crudos, para la tienda

    def lider(self, party=None):
        """El CharSet del primero del grupo: (nombre, índice).

        Un grupo vacío no tiene con qué dibujar al héroe. Pasa en RM2k —se
        puede sacar a todos— y ahí el motor no dibuja nada; acá se corta, que es
        más honesto que inventar un sprite.
        """
        grupo = self.party if party is None else party
        if not grupo:
            raise ValueError("el grupo está vacío: no hay con qué dibujar al héroe")
        actor = self.actors[grupo[0]]
        return actor.charset, actor.charset_index

    def decode(self, unknown=None):
        """La base entera como dicts, para volcarla a JSON."""
        return decode_struct(self.fields, "Database", unknown)


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
        self.music = {}
        for i, f in infos.items():
            kind = to_int(f.get(MAPINFO_MUSIC_TYPE, b"\x00"))
            fields = Reader(f.get(MAPINFO_MUSIC, b"\x00")).read_struct()
            self.music[i] = (kind, {
                "name": to_string(fields.get(MUSIC_NAME, b"")),
                "volume": to_int(fields.get(MUSIC_VOLUME, b"\x64")),
                "tempo": to_int(fields.get(MUSIC_TEMPO, b"\x64")),
            })

        self.tree_order = [reader.read_int() for _ in range(count)]
        reader.read_int()                   # active_node, cosa del editor

        start = reader.read_struct()
        self.start_map_id = to_int(start[START_PARTY_MAP_ID])
        self.start_x = to_int(start[START_PARTY_X])
        self.start_y = to_int(start[START_PARTY_Y])

    def map_music(self, map_id):
        """El tema de un mapa, siguiendo la herencia hacia el padre.

        music_type 0 significa "el del padre"; 2, el que trae el mapa. El 1 es
        "lo pone un evento", que sin interpretar scripts es lo mismo que nada.
        """
        seen = set()
        while map_id and map_id not in seen:
            seen.add(map_id)
            kind, music = self.music.get(map_id, (0, None))
            if kind == 2 and music["name"]:
                return music
            if kind == 1:
                return None
            map_id = self.map_parents.get(map_id, 0)
        return None
