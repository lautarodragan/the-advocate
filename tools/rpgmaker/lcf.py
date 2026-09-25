"""El juego, leído del volcado a JSON de `data/`.

Hasta el 2026-09-14 esto parseaba los binarios de RPG Maker 2000 en cada build
—ese lector se borró cuando dejó de tener quien lo usara—. Desde
entonces el formato se lee **una sola vez**, en Ditto, y lo que hay en `data/`
es el resultado: `maps/MapNNNN.json` con su `.tiles` al lado, `maps.json` con el
árbol y `db/*.json` con las quince secciones de la base. El porqué está en
`DITTO.md`; lo que hay adentro de `data/`, en `data/README.md`.

**Los consumidores no se enteraron.** Las clases de acá —`Map`, `Database`,
`TreeMap` y todo lo que cuelga— tienen los mismos atributos que antes, con los
mismos tipos, y siguen recibiendo la ruta a un `.lmu` o a un `RPG_RT.ldb`: de
esa ruta sólo se usa **el nombre**, para saber qué mapa es, y el directorio
sólo si tiene adentro un volcado propio (un `ditto.json`). Los gráficos y el
audio siguen saliendo del juego de verdad, que es lo que `--game-dir` nombra.

**Y de este archivo no sale ninguna regla del formato.** Lo que hay en `data/`
es la *vista resuelta* que emite Ditto: **todos los campos escritos**, con su
default ya aplicado, y los enums como el número que guarda el binario. Así que
leer es leer: `datos["max_hp"]` y listo. Un campo que falte es un `KeyError`, y
eso es lo que se quiere —quiere decir que `data/` quedó viejo, no que valga
cero—.

Hasta el 2026-09-20 acá se leía el *volcado exacto* —defaults omitidos, enums
por nombre— y hacía falta el esquema del formato para entenderlo:
`ditto_schema.py` y su JSON, que publicaba `ditto schema`. Los dos se fueron
con este cambio. El volcado exacto se sigue generando, en la misma corrida,
porque es de donde Ditto rearma el binario; lo que no se versiona más es él.

Lo que sí sigue siendo de acá es **adivinar la codificación de un texto**: ver
`texto`. Eso no es una regla del formato, es lo contrario —el formato no dice
en qué juego de caracteres está una cadena—.
"""

import json
import os

from rpgmaker import fork
from rpgmaker.event_codes import EVENT_CODES

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATOS = os.path.join(REPO, "data")
MANIFIESTO = "ditto.json"


def volcado(path):
    """De dónde se lee: el volcado propio del directorio, o el del repo.

    Los llamadores pasan una ruta adentro del juego original —`--game-dir`—,
    que es de donde siguen saliendo los PNG y los MIDI. Si ese directorio
    tiene un volcado de Ditto adentro se usa ése, que es como se lee un juego
    que no es éste; si no, el de `data/`, que es el del repo.
    """
    directorio = os.path.dirname(os.path.abspath(path))
    if os.path.isfile(os.path.join(directorio, MANIFIESTO)):
        return directorio
    return DATOS


def leer(*partes):
    with open(os.path.join(*partes), encoding="utf-8") as handle:
        return json.load(handle)


# --- Acceso a un campo ------------------------------------------------------
#
# Tres líneas, y ésa es la idea: la vista resuelta trae todos los campos, así
# que no hay default que aplicar ni enum que traducir. Lo único que queda es el
# texto, que no es del formato.

def campo(datos, nombre):
    """Un campo. Que no esté es un error, no un default."""
    valor = datos[nombre]
    return texto(valor) if isinstance(valor, str) else valor


def lista(datos, nombre):
    return datos[nombre]


def sub(datos, nombre):
    return datos[nombre]


def por_id(elementos):
    """Un array de structs como `{id: elemento}`, que es como se lo indexa.

    En el binario el id es la etiqueta con la que el array nombra a cada
    elemento; en el JSON es un campo más del objeto.
    """
    return {elemento["id"]: elemento for elemento in elementos}


# Los cinco bytes que cp1252 no define. Ditto los escribe como su control C1
# para que la tabla sea una biyección y no se pierda ningún byte; acá son la
# señal de que ese texto no es cp1252.
C1 = {"\x81": 0x81, "\x8d": 0x8D, "\x8f": 0x8F, "\x90": 0x90, "\x9d": 0x9D}


def texto(valor):
    """Un texto del juego, con los restos del RTP japonés leídos como tales.

    ABL se hizo con el RPG Maker 2000 de Don Miguel, así que casi todo es
    cp1252; un par de mensajes que el autor nunca tocó siguen en Shift-JIS.
    Ditto los guarda tal cual vinieron —decodificar adivinando le costaría la
    vuelta exacta, que es lo único que lo hace útil—, así que el que adivina es
    éste: si el texto trae alguno de los cinco bytes que cp1252 no define, se
    lo vuelve a armar y se lo lee en Shift-JIS. Son cuatro strings del LDB.
    """
    if not any(c in valor for c in C1):
        return valor
    crudo = bytearray()
    for ch in valor:
        if ch in C1:
            crudo.append(C1[ch])
        else:
            try:
                crudo.extend(ch.encode("cp1252"))
            except UnicodeEncodeError:
                return valor
    try:
        return bytes(crudo).decode("shift_jis")
    except UnicodeDecodeError:
        return valor


def to_string(payload):
    """Lo que queda del lector de binarios: `db.terminos` sigue dando bytes."""
    return texto(payload.decode("cp1252", errors="replace"))



# --- Enums, para nombrarlos en un volcado o en un mensaje -------------------
#
# Los nombres son los de liblcf y el orden es el de sus números. **No se usan
# para leer nada**: `data/` trae los enums en número, que es lo que el port
# quiere. Éstas están para nombrarlos —un volcado, un mensaje de error— y para
# los que hay que recorrer por índice.

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

# Las condiciones de una página, en el orden de sus bits. `timer2` sólo existe
# en RPG Maker 2003: en un archivo de 2000 no tiene bit y nunca está prendida.
CONDITION_NAMES = ("switch_a", "switch_b", "variable", "item",
                   "actor", "timer", "timer2")
# Y con qué campo se contesta cada una. El de `timer` es su cantidad de
# segundos, que es lo que el formato guarda; `timer2` es de 2003 y no está.
CONDITION_CAMPOS = {"switch_a": "switch_a_id", "switch_b": "switch_b_id",
                    "variable": "variable_id", "item": "item_id",
                    "actor": "actor_id", "timer": "timer_sec"}
# `compare_operator` es el chunk 0x0A de `EventPageCondition` y **es de RPG
# Maker 2003** (liblcf, `generator/csv/fields.csv`: "Integer - RPG2003").
# Ditto apunta a 2000 y no lo genera, así que en este juego nunca está escrito
# y vale siempre su default, que esa misma línea da en 1.
CONDITION_OPERATOR_DEFAULT = 1


# --- Los tipos del juego ---------------------------------------------------

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


# Los cuadros de texto rearmados para otra pantalla: una función que recibe
# los comandos de una página tal como están en el JSON y devuelve otros. El
# port pone `textos.reajustar_comandos`; el lector no sabe de pantallas, y
# sin nadie que la ponga el juego se lee tal cual.
#
# Es un paso aparte de `parches/`, y corre después: lee lo que sea que haya
# quedado, y un cuadro que ya entra lo deja como está. Así un texto corregido a
# mano en un fork de `parches/manual/` gana siempre.
#
# Se aplica a las páginas de los mapas y a los eventos comunes, y no a las de
# las tropas: la ventana de la pelea tiene otro ancho.
REAJUSTAR_TEXTOS = None


def comandos(datos, reajustar=False):
    """La lista de comandos de una página o de un evento común. Con
    `reajustar`, pasados por REAJUSTAR_TEXTOS si alguien la puso."""
    crudos = lista(datos, "event_commands")
    if reajustar and REAJUSTAR_TEXTOS:
        crudos = REAJUSTAR_TEXTOS(crudos)
    return [EventCommand(campo(c, "code"),
                         campo(c, "indent"),
                         campo(c, "string"),
                         campo(c, "parameters") or [])
            for c in crudos]


def comandos_escritos(datos):
    """Lo mismo, pero de una lista **escrita a mano**: `pruebas/casos/*.json`.

    Esos archivos no salen de `data/`: los escribimos nosotros, y por eso
    están en la taquigrafía que se puede escribir —el comando por su nombre,
    `ShowMessage`, y sólo los campos que dicen algo—. Un caso convertido a la
    vista resuelta sería ilegible y nadie lo editaría, así que la taquigrafía
    se queda y lo que se le pone al lado es este lector, que son seis líneas.

    Los tres campos que faltan valen lo obvio —sangría 0, sin texto, sin
    parámetros— y no hay esquema que consultar: el único dato de afuera es el
    número de cada nombre, que sale de `event_codes.json`, la tabla de liblcf
    que se queda justamente para esto y para los mensajes de error.
    """
    numero = {nombre: codigo for codigo, nombre in EVENT_CODES.items()}
    return [EventCommand(numero[c["code"]] if isinstance(c["code"], str)
                         else c["code"],
                         c.get("indent", 0), texto(c.get("string", "")),
                         c.get("parameters") or [])
            for c in datos["event_commands"]]


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

    def __init__(self, datos):
        flags = sub(datos, "flags")
        self.active = [n for n in CONDITION_NAMES if flags.get(n)]
        self.ids = {n: campo(datos, c)
                    for n, c in CONDITION_CAMPOS.items()}
        self.ids["timer2"] = 0
        self.variable_value = campo(datos, "variable_value")
        self.operator = CONDITION_OPERATOR_DEFAULT

    def __bool__(self):
        return bool(self.active)


class MoveRoute:
    """La ruta propia de una página: las órdenes, si se repite y si una orden
    bloqueada se saltea.

    De cada orden se guarda sólo el código; ninguna de las cuatro que llevan
    operandos se ejecuta.
    """

    def __init__(self, datos):
        self.repeat = campo(datos, "repeat")
        self.skippable = campo(datos, "skippable")
        self.commands = [campo(c, "command_id")
                         for c in lista(datos, "move_commands")]


class EventPage:
    """Una de las versiones que puede adoptar un evento."""

    def __init__(self, datos):
        self.character_name = campo(datos, "character_name")
        self.translucent = campo(datos, "translucent")
        self.character_index = campo(datos, "character_index")
        self.character_direction = campo(datos, "character_direction")
        self.character_pattern = campo(datos, "character_pattern")
        self.move_type = campo(datos, "move_type")
        self.move_frequency = campo(datos, "move_frequency")
        self.move_speed = campo(datos, "move_speed")
        self.trigger = campo(datos, "trigger")
        self.layer = campo(datos, "layer")
        self.overlap_forbidden = campo(datos, "overlap_forbidden")
        self.animation_type = campo(datos, "animation_type")
        self.commands = comandos(datos, reajustar=True)
        self.move_route = MoveRoute(sub(datos, "move_route"))
        self.condition = EventPageCondition(sub(datos, "condition"))
        self.unconditional = not self.condition


class Event:
    def __init__(self, datos, map_id=0):
        self.id = campo(datos, "id")
        self.name = campo(datos, "name")
        self.x = campo(datos, "x")
        self.y = campo(datos, "y")
        self.pages = [EventPage(p) for _, p
                      in sorted(por_id(lista(datos, "pages")).items())]
        if DECORAR_TRANSLUCIDO:
            # Ver DECORAR_TRANSLUCIDO: para el port, un CharSet translúcido es
            # otro gráfico, y si va horneado también depende de dónde está.
            for page in self.pages:
                if page.translucent and page.character_name:
                    page.character_name = DECORAR_TRANSLUCIDO(
                        page.character_name, map_id, self.x, self.y)

    def active_page(self):
        """La página que mostraría el motor en una partida recién empezada.

        RM2k usa la página de número más alto cuyas condiciones se cumplen
        todas. Sin switches ni variables seteadas, eso es la última página que
        no tiene ninguna condición. Puede no haber ninguna.
        """
        for page in reversed(self.pages):
            if page.unconditional:
                return page
        return None


def capas(path, datos, ancho, alto):
    """Las dos capas de tiles, del `.tiles` de al lado o del propio JSON.

    Ditto las saca del JSON y las escribe como una grilla de texto, una fila
    por línea, para que un tile cambiado se vea en el diff donde está en el
    mapa. Una capa que no entre en una grilla de `ancho * alto` se queda
    adentro del JSON, así que hay que mirar los dos lados.
    """
    if not os.path.isfile(path):
        return (campo(datos, "lower_layer") or [],
                campo(datos, "upper_layer") or [])

    todas = [[]]
    with open(path, encoding="utf-8") as handle:
        for linea in handle:
            if linea.startswith("#"):
                if todas[-1]:
                    todas.append([])
                continue
            todas[-1].extend(int(t) for t in linea.split())
    esperado = ancho * alto
    if len(todas) != 2 or any(len(c) != esperado for c in todas):
        raise ValueError("%s: %s tiles para un mapa de %dx%d"
                         % (path, [len(c) for c in todas], ancho, alto))
    return todas[0], todas[1]


class Map:
    def __init__(self, path):
        # El número de mapa no está adentro del archivo: sale del nombre, que
        # es de donde lo saca todo el resto del port. Lo necesitan los eventos
        # translúcidos horneados, que llevan en el nombre de su gráfico dónde
        # están parados.
        base = os.path.basename(path)
        self.map_id = int(base[3:7]) if base[3:7].isdigit() else 0
        raiz = volcado(path)
        # El fork es sólo de **este** juego: un juego ajeno se lee pasándole su
        # propio volcado, y ahí `parches/manual/` no pinta nada.
        forkeado = fork.mapa(self.map_id) if raiz == DATOS else None
        if forkeado:
            ruta_json, ruta_tiles = forkeado
            datos = leer(ruta_json)
        else:
            ruta_json = os.path.join(raiz, "maps", "Map%04d.json" % self.map_id)
            ruta_tiles = os.path.join(raiz, "maps",
                                      "Map%04d.tiles" % self.map_id)
            datos = leer(ruta_json)

        self.chipset_id = campo(datos, "chipset_id")
        self.width = campo(datos, "width")
        self.height = campo(datos, "height")
        self.scroll_type = campo(datos, "scroll_type")
        self.parallax_flag = campo(datos, "parallax_flag")
        self.parallax_name = campo(datos, "parallax_name")
        self.parallax_loop_x = campo(datos, "parallax_loop_x")
        self.parallax_loop_y = campo(datos, "parallax_loop_y")
        self.parallax_auto_loop_x = campo(datos, "parallax_auto_loop_x")
        self.parallax_auto_loop_y = campo(datos, "parallax_auto_loop_y")
        self.parallax_sx = campo(datos, "parallax_sx")
        self.parallax_sy = campo(datos, "parallax_sy")
        self.lower_layer, self.upper_layer = capas(
            ruta_tiles, datos, self.width, self.height)
        self.events = [Event(e, self.map_id) for _, e
                       in sorted(por_id(lista(datos, "events")).items())]


def passability(datos, nombre):
    """La transitabilidad de un chipset: un byte por tile.

    El chipset que no la trae la tiene igual —15 es transitable por los cuatro
    lados y por debajo del héroe, y el 31 del primer tile alto lo pone por
    encima—, y eso ya viene resuelto de `data/`: acá no hay nada que completar.
    """
    return bytes(campo(datos, nombre))


class Chipset:
    def __init__(self, datos):
        self.name = campo(datos, "name")
        self.filename = campo(datos, "chipset_name")
        self.passable_lower = passability(datos, "passable_data_lower")
        self.passable_upper = passability(datos, "passable_data_upper")
        self.terrain = campo(datos, "terrain_data")
        self.animation_type = campo(datos, "animation_type")
        self.animation_speed = campo(datos, "animation_speed")


# Las cinco ranuras de equipo, en el orden en que las numera el port.
RANURAS_EQUIPO = ("weapon_id", "shield_id", "armor_id", "helmet_id",
                  "accessory_id")
# Y las seis curvas de `Parameters`, en el orden del formato.
CURVAS = ("maxhp", "maxsp", "attack", "defense", "spirit", "agility")


class Actor:
    """Un personaje de la base: de acá sale con qué gráfico se lo dibuja."""

    def __init__(self, datos):
        self.name = campo(datos, "name")
        self.charset = campo(datos, "character_name")
        self.charset_index = campo(datos, "character_index")
        self.face_name = campo(datos, "face_name")
        self.face_index = campo(datos, "face_index")
        # Los parámetros por nivel, desde el 1: `maxhp`, `attack`, `defense`,
        # `spirit`, `agility`, cada uno una lista.
        parametros = sub(datos, "parameters")
        self.params = {c: campo(parametros, c) or []
                       for c in CURVAS}
        self.hp_max = self.params.get("maxhp", [])
        self.sp_max = self.params.get("maxsp", [])
        # **El nivel con el que arranca**, que en el ABL no es el 1: Kersh
        # arranca en 20 y Core y Manta en 15. Hasta el 2026-09-13 este port
        # tenía a todos en 1 —una constante `titulo.NIVEL`— y de ahí salían los
        # HP, los parámetros y la conclusión de que nadie sabía ninguna
        # habilidad.
        self.initial_level = campo(datos, "initial_level") or 1
        # Hasta dónde sube y con qué curva de experiencia: los tres números de
        # `Game_Actor::CalculateExp`. Ver `port.experiencia`.
        self.final_level = campo(datos, "final_level")
        self.exp_base = campo(datos, "exp_base")
        self.exp_inflation = campo(datos, "exp_inflation")
        self.exp_correction = campo(datos, "exp_correction")
        # Qué habilidad aprende en cada nivel, en el orden del LDB:
        # `Game_Actor::LearnLevelSkills` las recorre así.
        # `skill_id` vale **1** cuando el archivo no lo trae, que es lo que
        # dice el formato: es el único dato del juego que cambió al mudarse a
        # Ditto. Alex —el actor 1, del RTP, que este juego no usa— aprende la
        # habilidad 1 en el nivel 1, y antes eso llegaba como la 0 y se caía.
        # Es un par más de `eventos.HABILIDAD_RANURA`; sin eso el `mapdata.inc`
        # es idéntico.
        self.skills = [(campo(l, "level"),
                        campo(l, "skill_id"))
                       for _, l in sorted(por_id(lista(datos, "skills")).items())]
        # Cómo se llama su orden de habilidades en el menú de batalla:
        # `Game_Actor::GetSkillName` devuelve `skill_name` si `rename_skill`
        # está puesto y si no el `command_skill` del LDB. Los cuatro actores de
        # la intro lo tienen puesto: "AgentTrain", "Telepathy", "Slicing" y
        # "Special".
        self.rename_skill = campo(datos, "rename_skill")
        self.skill_name = campo(datos, "skill_name")
        # El equipo con el que arranca: arma, escudo, armadura, casco y
        # accesorio, por número de ítem, 0 si nada.
        equipo = sub(datos, "initial_equipment")
        self.initial_equipment = [campo(equipo, r)
                                  for r in RANURAS_EQUIPO]


# Los tipos de habilidad, en el orden de `rpg::Skill::Type`. Las siete que el
# grupo de la intro sabe son `normal` o `switch`.
SKILL_TIPO_NORMAL, SKILL_TIPO_TELEPORT, SKILL_TIPO_ESCAPE, \
    SKILL_TIPO_SWITCH, SKILL_TIPO_SUBSKILL = range(5)
# Y los alcances, `rpg::Skill::Scope`. `SkillTargetsEnemies` de algo.h es
# "enemy o enemies"; todo lo demás apunta al propio bando.
SKILL_SCOPE_ENEMIGO, SKILL_SCOPE_ENEMIGOS, SKILL_SCOPE_UNO_MISMO, \
    SKILL_SCOPE_ALIADO, SKILL_SCOPE_GRUPO = range(5)

SKILL_CAMPOS = ("name", "description", "using_message1", "using_message2",
                "type", "sp_cost", "scope", "switch_id", "animation_id",
                "physical_rate", "magical_rate", "variance", "power", "hit",
                "affect_hp", "affect_sp", "affect_attack", "affect_defense",
                "affect_spirit", "affect_agility", "ignore_defense")


class Skill:
    """Una habilidad: lo que la pantalla muestra y lo que la cuenta necesita.

    Los defaults no son todos cero —`magical_rate` vale 3, `variance` 4, `hit`
    100, `switch_id` y `animation_id` 1— y ya no están escritos acá: salen del
    esquema, que es de donde tienen que salir.
    """

    def __init__(self, datos):
        for nombre in SKILL_CAMPOS:
            setattr(self, nombre, campo(datos, nombre))

    @property
    def apunta_a_enemigos(self):
        """`Algo::SkillTargetsEnemies`."""
        return self.scope in (SKILL_SCOPE_ENEMIGO, SKILL_SCOPE_ENEMIGOS)


# Los tipos de ítem, en el orden de `rpg::Item::Type`.
ITEM_TIPO_COMUN, ITEM_TIPO_ARMA, ITEM_TIPO_ESCUDO, ITEM_TIPO_ARMADURA, \
    ITEM_TIPO_CASCO, ITEM_TIPO_ACCESORIO, ITEM_TIPO_MEDICINA, \
    ITEM_TIPO_LIBRO, ITEM_TIPO_MATERIAL, ITEM_TIPO_UNICO, \
    ITEM_TIPO_SWITCH = range(11)

ITEM_CAMPOS = ("name", "description", "type", "uses", "switch_id",
               "occasion_field2", "price", "two_handed", "recover_hp_rate",
               "recover_hp", "occasion_field1", "ko_only",
               "recover_sp_rate", "recover_sp")
# Lo que suma al equipárselo: ataque, defensa, espíritu, agilidad.
ITEM_PUNTOS = ("atk_points1", "def_points1", "spi_points1", "agi_points1")


class Item:
    """Un ítem: lo que el menú muestra de él y lo poco que hace hoy.

    `recover_hp_rate` es por ciento del máximo y `recover_hp` es a secas, y
    lo mismo los de SP; `occasion_field1` es "sólo fuera de batalla" y
    `ko_only` "sólo sobre un muerto". `state_set` son los estados que saca,
    uno por estado del LDB desde el 1, que es el de muerto: es lo que decide
    si levanta a un caído. Ver `batalla.item_usable_en_batalla` y
    `medicina_usar` en main.s.
    """

    def __init__(self, datos):
        for nombre in ITEM_CAMPOS:
            setattr(self, nombre, campo(datos, nombre))
        self.puntos = [campo(datos, p) for p in ITEM_PUNTOS]
        self.actor_set = campo(datos, "actor_set") or []
        self.state_set = campo(datos, "state_set") or []

    def equipable_por(self, actor):
        """`actor_set`, con los que no alcanza la lista en sí: es lo que
        hace RM2k con un ítem que se hizo antes de agregar actores."""
        return self.actor_set[actor - 1] if actor - 1 < len(self.actor_set) \
            else True


ENEMY_CAMPOS = ("name", "battler_name", "battler_hue", "max_hp", "max_sp", "attack",
                "defense", "spirit", "agility", "exp", "gold", "critical_hit",
                "miss")


class Enemy:
    """Un enemigo: sus parámetros y con qué acierta.

    `miss` y `critical_hit` salen de `Game_Enemy::GetHitChance` y
    `Game_Enemy::GetCriticalHitChance` de easyrpg-player: el que falla acierta
    70 de 100 y el que no, 90, y el crítico es una vez cada
    `critical_hit_chance`.

    Los seis parámetros valen **10** cuando el archivo no los trae, que es lo
    que dice el formato. Acá estaban escritos en 1 y 0, y no era una diferencia
    teórica: taro encontró el 2026-09-14, jugando, que el DirtShadow moría de
    un golpe. Son 24 enemigos de los 175, casi todos separadores del editor,
    pero el DirtShadow es uno de verdad. Es el error que originó a Ditto.
    """

    def __init__(self, datos):
        for nombre in ENEMY_CAMPOS:
            setattr(self, nombre, campo(datos, nombre))
        self.critical_hit_chance = campo(datos, "critical_hit_chance") or 30

    @property
    def hit(self):
        """`Game_Enemy::GetHitChance`."""
        return 70 if self.miss else 90


class Troop:
    """Una tropa: qué enemigos la forman y dónde va cada uno.

    Las posiciones (x, y) son del **centro** de cada battler en la pantalla de
    320x240 de RM2k. Las páginas de evento de la tropa van en `pages`, en el
    orden del LDB, que es el orden en que `ScheduleNextPage` las prueba.
    """

    def __init__(self, datos):
        miembros = sorted(por_id(lista(datos, "members")).items())
        self.name = campo(datos, "name")
        self.members = [campo(m, "enemy_id")
                        for _, m in miembros]
        self.posiciones = [(campo(m, "x"),
                            campo(m, "y"))
                           for _, m in miembros]
        self.pages = [TroopPage(p) for _, p in
                      sorted(por_id(lista(datos, "pages")).items())]


# Los disparadores de una página de tropa, con los nombres de liblcf
# (`TroopPageCondition::Flags`). Los de 2003 —`turn_enemy`, `turn_actor`,
# `command_actor`— no están en el volcado de un juego de 2000.
TROPA_DISPARADORES = ("switch_a", "switch_b", "variable", "turn", "fatigue",
                      "enemy_hp", "actor_hp")


class TroopPage:
    """Una página de evento de tropa: cuándo corre y qué hace.

    `activos` son los disparadores prendidos; los números con que se contesta
    cada uno quedan en `condicion`, que es el objeto del volcado tal cual: son
    muchos campos y cada uno lo lee sólo quien lo necesita.
    """

    def __init__(self, datos):
        condicion = sub(datos, "condition")
        flags = sub(condicion, "flags")
        self.activos = [n for n in TROPA_DISPARADORES if flags.get(n)]
        self.condicion = condicion
        self.commands = comandos(datos)


# Las quince secciones del LDB, cada una en su archivo. Los nombres son los
# campos de `Database`, que es como se llaman los archivos de `db/`.
SECCIONES = ("actors", "skills", "items", "enemies", "troops", "terrains",
             "attributes", "states", "animations", "chipsets", "terms",
             "system", "switches", "variables", "commonevents")
# Y las que son una lista de elementos numerados; `system` y `terms` son un
# objeto solo.
SECCIONES_LISTA = tuple(s for s in SECCIONES if s not in ("system", "terms"))

# Los efectos de sonido que `Game_System::GetSystemSE` reparte, en el orden que
# recorre `eventos.AUDIO_BATALLA_SE`.
SYSTEM_SE = ("battle_se", "escape_se", "enemy_attack_se", "enemy_damaged_se",
             "actor_damaged_se", "dodge_se", "enemy_death_se", "item_se")

# Los términos que el port usa por nombre. El resto sigue estando en
# `db.terminos`, por chunk, que es como los pide la tienda.
TERM_MENU = ("command_item", "command_skill", "menu_equipment", "menu_save",
             "menu_quit")
TERM_PARAMS = ("attack", "defense", "spirit", "agility")
TERM_EQUIPO = ("weapon", "shield", "armor", "helmet", "accessory")
TERM_SUELTOS = {
    "term_new_game": "new_game", "term_load_game": "load_game",
    "term_load_message": "load_game_message",
    "term_save_message": "save_game_message", "term_file": "file",
    "term_level": "level", "term_lvl_short": "lvl_short", "term_gold": "gold",
    "term_normal_status": "normal_status", "term_hp_short": "hp_short",
}


def sonido(datos):
    """Un `Music` o un `Sound` como la tupla que espera el port."""
    return (campo(datos, "name"), campo(datos, "volume"),
            campo(datos, "tempo"), campo(datos, "balance"))


class Database:
    """RPG_RT.ldb: los chipsets, los personajes y el grupo con el que se arranca.

    Del `path` sólo se usa el directorio, y sólo para saber si trae un volcado
    propio: los datos salen de `db/` del volcado.
    """

    def __init__(self, path):
        raiz = os.path.join(volcado(path), "db")
        self.secciones = {s: leer(raiz, "%s.json" % s) for s in SECCIONES}

        crudas = {s: por_id(self.secciones[s]) for s in SECCIONES_LISTA}
        # Los ChipSets que agrega `parches/manual/`. Se **suman**: un id que ya
        # esté en la base es un error, porque un fork que pisa una entrada
        # envejece sin avisar el día que `just datos` la cambie. Ver `fork.py`.
        if raiz == os.path.join(DATOS, "db"):
            for numero, datos in fork.chipsets().items():
                if numero in crudas["chipsets"]:
                    raise ValueError(
                        "el ChipSet %d ya está en data/: el fork agrega, no "
                        "reemplaza" % numero)
                crudas["chipsets"][numero] = datos["chipset"]
        self.chipsets = {i: Chipset(f) for i, f in crudas["chipsets"].items()}
        self.actors = {i: Actor(f) for i, f in crudas["actors"].items()}
        # Los ítems, y el número más alto: `ITEMS_N` en eventos.py es éste
        # más uno, y test_items.py lo comprueba.
        self.items = {i: Item(f) for i, f in crudas["items"].items()}
        # Las habilidades, que `lcf.Actor.skills` nombra por número.
        self.skills = {i: Skill(f) for i, f in crudas["skills"].items()}
        self.items_max = max(self.items, default=0)
        # Los enemigos y las tropas: lo que una batalla necesita.
        self.enemies = {i: Enemy(f) for i, f in crudas["enemies"].items()}
        self.troops = {i: Troop(f) for i, f in crudas["troops"].items()}
        # Los eventos comunes, que antes se leían del chunk crudo: acá ya son
        # sus comandos, que es lo único que se les pide.
        self.common_events = {
            i: comandos(f, reajustar=True)
            for i, f in crudas["commonevents"].items()}

        # El grupo con el que empieza la partida. En RM2k el gráfico del héroe
        # es el del primero de la lista, así que este dato es el que decide con
        # qué sprite se dibuja.
        sistema = self.secciones["system"]
        self.party = campo(sistema, "party") or []
        # El System del juego: el PNG con el marco de la ventana, los colores
        # de texto y la sombra. Este juego usa `ablskin`.
        self.system_name = campo(sistema, "system_name")
        # Con qué fuente dibuja el texto: 0 Gothic, 1 Mincho. easyrpg elige
        # ttyp0 o rmg2000 con esto, y las letras salen distintas. Este juego
        # pide Mincho.
        self.font_id = campo(sistema, "font_id")
        # La imagen de la pantalla de título y su tema. En el ABL son
        # 'ABL20Title' y 'Fantasia_Of_The_Wind'; el otro PNG que hay en Title/
        # —'LineTitle'— es de una versión anterior y el juego no lo usa.
        self.title_name = campo(sistema, "title_name")
        self.title_music = campo(sub(sistema, "title_music"), "name")
        # El audio de la pelea. Sale de acá y no de un literal nuestro por lo
        # mismo que los términos: es un dato del juego. En el ABL el tema de
        # batalla y el de victoria son **el mismo** —T_VGFighterMAX_Masako—, y
        # `battle_se` está en "(OFF)", que es un nombre que no resuelve a
        # ningún archivo y sale mudo sin que haya que tratarlo aparte.
        self.battle_music = campo(sub(sistema, "battle_music"), "name")
        self.battle_end_music = campo(sub(sistema, "battle_end_music"), "name")
        self.system_se = {n: sonido(sub(sistema, n)) for n in SYSTEM_SE}

        # Los términos de la pantalla de título. En el ABL no son los de
        # fábrica: dicen 'Begin the Story' y 'Resume the Story', que es lo que
        # el juego eligió y por eso salen de acá y no de un literal nuestro.
        terminos = self.secciones["terms"]
        for atributo, nombre in TERM_SUELTOS.items():
            setattr(self, atributo, campo(terminos, nombre))
        self.term_menu = [campo(terminos, t) for t in TERM_MENU]
        self.term_params = [campo(terminos, t) for t in TERM_PARAMS]
        self.term_equipo = [campo(terminos, t) for t in TERM_EQUIPO]
        # Y todos los términos, por su nombre, que es lo que pide la tienda:
        # ahí no se los nombra de a uno sino por bloques —los trece de cada
        # juego de mensajes—. Hasta el 2026-09-20 la clave era el número de
        # chunk, y eso pedía saber en qué chunk cae cada término, que es dato
        # del formato: lo único que lo sabía era el esquema que Python ya no
        # tiene.
        self.terminos = {
            nombre: campo(terminos, nombre).encode("cp1252", "replace")
            for nombre in terminos}

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
        """La base entera como dicts, para el que la quiere campo por campo.

        Es `data/` tal cual, con dos retoques que no son del formato: los
        arrays de structs pasan a estar indexados por id, que es como se los
        busca, y los textos pasan por `texto`. Todo lo demás —los defaults
        aplicados, los enums en número— ya viene así.
        """
        return {seccion: normalizar(self.secciones[seccion])
                for seccion in SECCIONES}


def normalizar(datos):
    """Un pedazo de `data/` indexado por id y con los textos adivinados.

    Un array de structs vuelve a ser `{id: elemento}`, que es como se lo busca;
    los que no tienen id —los comandos de un evento, que en el formato van uno
    atrás del otro y sin numerar— se quedan como lista. La vista resuelta
    escribe todos los campos, así que el `id` está siempre y no hay que saber
    de antemano qué struct es cada cosa: se ve.
    """
    if isinstance(datos, list):
        if not datos or not isinstance(datos[0], dict):
            return datos        # una lista de números: los tiles, una curva
        if "id" in datos[0]:
            return {e["id"]: normalizar(e) for e in datos}
        return [normalizar(e) for e in datos]
    if not isinstance(datos, dict):
        return texto(datos) if isinstance(datos, str) else datos
    return {nombre: normalizar(valor) for nombre, valor in datos.items()
            if nombre != "id"}  # el id es la clave, no un campo


class TreeMap:
    """RPG_RT.lmt: el árbol de mapas y la posición inicial del jugador."""

    def __init__(self, path):
        datos = leer(volcado(path), "maps.json")
        infos = por_id(lista(datos, "maps"))

        self.map_names = {i: campo(f, "name")
                          for i, f in infos.items()}
        self.map_parents = {i: campo(f, "parent_map")
                            for i, f in infos.items()}
        # Tipo 0 = raíz del árbol, 1 = mapa de verdad, 2 = **área**. Un área es
        # un nodo sin `.lmu` que cuelga de un mapa y le tapa un rectángulo.
        # Acá se usan para los encuentros al azar, que es lo único que ABL les
        # pone.
        self.map_types = {i: campo(f, "type")
                          for i, f in infos.items()}

        # Los encuentros al azar, que viven en el árbol y no en el `.lmu`:
        # la lista de tropas, cada cuántos pasos y —para las áreas— el
        # rectángulo que cubren.
        self.encounters = {}
        self.encounter_steps = {}
        self.area_rect = {}
        for i, f in infos.items():
            self.encounters[i] = [
                campo(e, "troop_id")
                for _, e in sorted(por_id(lista(f, "encounters")).items())]
            # El default de RM2k son 25 pasos; 0 es "sin encuentros".
            self.encounter_steps[i] = campo(f, "encounter_steps")
            rect = sub(f, "area_rect")
            self.area_rect[i] = tuple(campo(rect, c) for c in "ltrb")

        # El fondo de batalla de cada nodo: `background_type` 0 es "el del
        # padre", 1 "el del terreno" y 2 "éste", con el nombre al lado.
        self.background = {i: (campo(f, "background_type"),
                               campo(f, "background_name"))
                           for i, f in infos.items()}

        self.music = {}
        for i, f in infos.items():
            musica = sub(f, "music")
            self.music[i] = (campo(f, "music_type"), {
                "name": campo(musica, "name"),
                "volume": campo(musica, "volume"),
                "tempo": campo(musica, "tempo"),
            })

        self.tree_order = campo(datos, "tree_order") or []
        start = sub(datos, "start")
        self.start_map_id = campo(start, "party_map_id")
        self.start_x = campo(start, "party_x")
        self.start_y = campo(start, "party_y")

    def map_background(self, map_id):
        """El fondo de batalla de un encuentro en este mapa, o "".

        Es `Game_Map::SetupBattle` de easyrpg-player: se sube por el árbol
        mientras el nodo diga "el del padre", y sólo el 2 trae nombre. El 1 es
        el fondo del terreno que se pisa, que este port no tiene, así que da lo
        mismo que nada. Lo que se mira es **el mapa y no el área**: las áreas
        de ABL son todas "el del padre", y easyrpg arranca de `GetMapInfo()`.
        """
        seen = set()
        while map_id and map_id not in seen:
            seen.add(map_id)
            tipo, nombre = self.background.get(map_id, (0, ""))
            if tipo != 0:
                return nombre if tipo == 2 else ""
            map_id = self.map_parents.get(map_id, 0)
        return ""

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
