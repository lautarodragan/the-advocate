#!/usr/bin/env python3
"""Exporta los mapas de A Blurred Line a JSON + una grilla de tiles en texto.

La idea es tener los datos del juego en un formato que git pueda versionar de
verdad: diffeable, revisable y editable a mano, sin depender del editor de RM2k
ni de un parser binario para ver qué cambió.

Por mapa salen dos archivos:

    data/maps/Map0001.json    metadata, chipset, y los eventos con sus scripts
    data/maps/Map0001.tiles   las dos capas de tiles, una fila por línea

Más dos archivos compartidos, data/maps.json (el árbol de mapas y la posición
inicial) y data/chipsets.json (la tabla de chipsets con su passability).

Uso:
    python3 tools/export_json.py            # todo a data/
    python3 tools/export_json.py --verify   # además, releer y comparar
"""

import argparse
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lcf
from event_codes import EVENT_CODES
from render_map import GAME_DIR, REPO

TILE_WIDTH = 5  # los IDs llegan a 10143, y alineados en columnas se leen mejor


# --- JSON con listas de una sola línea ------------------------------------

class Inline:
    """Valor que se serializa en una línea, aunque el resto vaya indentado.

    Un comando de evento por línea es lo que hace que un diff de git sea
    legible; con la indentación normal de json cada parámetro ocuparía su
    propia línea y no se entendería nada.
    """

    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


def dumps(obj):
    """json.dumps con indent=2, pero respetando los Inline."""
    inlines = []
    token = "@@inline-%s-%%d@@" % uuid.uuid4().hex

    def unwrap(node):
        """Un Inline dentro de otro ya está en la misma línea: no hace falta marcarlo."""
        if isinstance(node, Inline):
            return unwrap(node.value)
        if isinstance(node, dict):
            return {k: unwrap(v) for k, v in node.items()}
        if isinstance(node, list):
            return [unwrap(v) for v in node]
        return node

    def replace(node):
        if isinstance(node, Inline):
            inlines.append(json.dumps(unwrap(node.value), ensure_ascii=False))
            return token % (len(inlines) - 1)
        if isinstance(node, dict):
            return {k: replace(v) for k, v in node.items()}
        if isinstance(node, list):
            return [replace(v) for v in node]
        return node

    text = json.dumps(replace(obj), indent=2, ensure_ascii=False)
    for i, inline in enumerate(inlines):
        text = text.replace('"%s"' % (token % i), inline)
    return text + "\n"


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def tree_size(directory):
    return sum(os.path.getsize(os.path.join(root, name))
               for root, _, names in os.walk(directory) for name in names)


# --- Conversión a estructuras JSON ----------------------------------------

def condition_json(condition):
    """Sólo las condiciones activas, con sus valores. Vacío si no tiene."""
    result = {}
    for name in condition.active:
        if name == "variable":
            result["variable"] = Inline([
                condition.ids["variable"],
                lcf.enum_name(lcf.COMPARISONS, condition.operator),
                condition.variable_value])
        else:
            result[name] = condition.ids[name]
    return result


def page_json(page):
    """Una página. Se omite todo lo que esté en su valor por defecto."""
    result = {}

    conditions = condition_json(page.condition)
    if conditions:
        result["conditions"] = conditions

    if page.character_name:
        result["sprite"] = {
            "charset": page.character_name,
            "index": page.character_index,
            "direction": lcf.enum_name(lcf.DIRECTIONS, page.character_direction),
            "pattern": lcf.enum_name(lcf.PATTERNS, page.character_pattern),
        }
    else:
        # Sin CharSet el evento se dibuja como un tile de la página alta.
        result["tile"] = page.character_index

    result["layer"] = lcf.enum_name(lcf.LAYERS, page.layer)
    result["trigger"] = lcf.enum_name(lcf.TRIGGERS, page.trigger)

    if page.move_type:
        result["move"] = {
            "type": lcf.enum_name(lcf.MOVE_TYPES, page.move_type),
            "speed": lcf.enum_name(lcf.MOVE_SPEEDS, page.move_speed),
            "frequency": page.move_frequency,
        }
    if page.animation_type:
        result["animation"] = lcf.enum_name(lcf.ANIM_TYPES, page.animation_type)
    if page.translucent:
        result["translucent"] = True
    if page.overlap_forbidden:
        result["overlap_forbidden"] = True

    if page.commands:
        result["script"] = [
            Inline([c.indent, EVENT_CODES.get(c.code, c.code),
                    c.string, Inline(c.parameters)])
            for c in page.commands]
    return result


def event_json(event):
    return {
        "id": event.id,
        "name": event.name,
        "at": Inline([event.x, event.y]),
        "pages": [page_json(p) for p in event.pages],
    }


def map_json(map_id, game_map, tree, chipset):
    result = {
        "id": map_id,
        "name": tree.map_names.get(map_id, ""),
        "size": Inline([game_map.width, game_map.height]),
        "chipset": Inline([game_map.chipset_id, chipset.filename]),
        "tiles": "Map%04d.tiles" % map_id,
    }
    if game_map.parallax_flag and game_map.parallax_name:
        result["parallax"] = {
            "name": game_map.parallax_name,
            "loop_x": game_map.parallax_loop_x,
            "loop_y": game_map.parallax_loop_y,
            "scroll_x": game_map.parallax_sx if game_map.parallax_auto_loop_x else 0,
            "scroll_y": game_map.parallax_sy if game_map.parallax_auto_loop_y else 0,
        }
    if game_map.scroll_type:
        result["scroll_type"] = game_map.scroll_type

    result["events"] = [event_json(e) for e in game_map.events]
    return result


# --- La grilla de tiles ----------------------------------------------------

def tiles_text(map_id, game_map, chipset):
    """Las dos capas como texto, una fila de mapa por línea.

    En binario esto ocuparía menos de la mitad, pero sería opaco para git. En
    texto un cambio de un tile es un cambio de una línea, y el archivo entero
    del juego son unos pocos MB que comprimen muy bien.
    """
    lines = ["# Map%04d  %dx%d  %s" % (map_id, game_map.width, game_map.height,
                                       chipset.filename),
             "# IDs de tile: 0-2999 agua, 3000+ animados, 4000+ terreno,",
             "# 5000+ capa baja, 10000+ capa alta."]

    for name, layer in (("lower", game_map.lower_layer),
                        ("upper", game_map.upper_layer)):
        lines.append("# %s" % name)
        for y in range(game_map.height):
            row = layer[y * game_map.width:(y + 1) * game_map.width]
            lines.append(" ".join("%*d" % (TILE_WIDTH, t) for t in row))
    return "\n".join(lines) + "\n"


def parse_tiles(text):
    """Vuelve del texto a las dos capas. Es lo que usa --verify."""
    layers = {}
    current = None
    for line in text.splitlines():
        if line.startswith("#"):
            name = line[1:].strip()
            if name in ("lower", "upper"):
                current = layers.setdefault(name, [])
        elif current is not None and line.strip():
            current.extend(int(t) for t in line.split())
    return layers


# --- La base de datos ------------------------------------------------------

def script_json(commands):
    """Los comandos de un evento común, en el mismo formato que los de un mapa."""
    return [Inline([c["indent"], EVENT_CODES.get(c["code"], c["code"]),
                    c["string"], Inline(c["parameters"])])
            for c in commands]


def normalize(value, key=None):
    """Acomoda lo que sale del decodificador genérico para que el JSON se lea.

    Las listas de structs vienen como {id: campos}; las pasamos a listas con el
    id adentro. Las listas de números planos van en una línea. Y los scripts,
    un comando por línea, igual que en los mapas.
    """
    if key == "event_commands":
        return script_json(value)

    if isinstance(value, dict):
        if value and all(isinstance(k, int) for k in value):
            return [normalize(dict(id=i, **entry) if isinstance(entry, dict)
                              else {"id": i, "value": entry})
                    for i, entry in sorted(value.items())]
        return {k: normalize(v, k) for k, v in value.items()}

    if isinstance(value, list):
        if all(isinstance(v, (int, float, bool, str)) for v in value):
            return Inline(value)
        return [normalize(v) for v in value]

    return value


def database_json(database, unknown):
    """Cada sección de la LDB en su propio archivo, para que los diffs sirvan."""
    decoded = database.decode(unknown)
    sections = {}
    for name, section in decoded.items():
        value = normalize(section, name)
        # switches y variables son sólo nombres: 1200 entradas de un campo cada
        # una son 4800 líneas de ruido si no se aplastan.
        if name in ("switches", "variables") and isinstance(value, list):
            value = [Inline(entry) for entry in value]
        sections[name] = value
    return sections


# --- Los archivos compartidos ---------------------------------------------

def nodo_del_arbol(tree, i, exported):
    """Un nodo del árbol: un mapa o un **área de encuentros**.

    El tipo 2 no es una carpeta del editor, que es lo que este volcado decía
    hasta el 2026-09-14: es un **área**, o sea un rectángulo dentro del mapa
    padre con su propia lista de tropas y su propio contador de pasos. taro las
    buscó ese día y no las encontró en ningún lado —ni acá ni en los
    `MapNNNN.json`— porque viven en el árbol, `RPG_RT.lmt`, y este volcado
    exportaba nada más que el nombre y el padre.

    `encounters`, `encounter_steps` y `area_rect` los trae **cualquier** nodo,
    mapa o área: un mapa puede tener sus propias tropas además de las de las
    áreas que lo tapan. Se exportan sólo cuando dicen algo, para no llenar de
    ceros los 328 nodos.
    """
    nodo = {"id": i,
            "name": tree.map_names[i],
            "parent": tree.map_parents[i],
            "type": "area" if tree.map_types[i] == 2 else "map",
            "file": "maps/Map%04d.json" % i if i in exported else None}
    tropas = tree.encounters.get(i) or []
    if tropas:
        nodo["encounters"] = [Inline([t]) if not isinstance(t, (list, tuple))
                              else Inline(list(t)) for t in tropas]
        nodo["encounter_steps"] = tree.encounter_steps.get(i, 25)
    rect = tree.area_rect.get(i)
    if rect and any(rect):
        nodo["area_rect"] = Inline(list(rect))
    return nodo


def tree_json(tree, exported):


    # tree_order (el orden de los nodos en el árbol del editor) no se exporta:
    # es estado de UI, y la jerarquía ya está en "parent".
    return {
        "start": {"map": tree.start_map_id,
                  "at": Inline([tree.start_x, tree.start_y])},
        "maps": [nodo_del_arbol(tree, i, exported)
                 for i in sorted(tree.map_names) if i != 0],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", default=GAME_DIR)
    parser.add_argument("--maps-dir", default=GAME_DIR)
    parser.add_argument("-o", "--out-dir", default=os.path.join(REPO, "data"))
    parser.add_argument("--verify", action="store_true",
                        help="releer lo exportado y comparar contra los .lmu")
    args = parser.parse_args()

    database = lcf.Database(os.path.join(args.game_dir, "RPG_RT.ldb"))
    tree = lcf.TreeMap(os.path.join(args.game_dir, "RPG_RT.lmt"))
    os.makedirs(args.out_dir, exist_ok=True)
    # Un mapa por archivo son 656 archivos; en un directorio propio
    # para que `data/` deje ver de un vistazo qué otras cosas hay.
    mapas_dir = os.path.join(args.out_dir, "maps")
    os.makedirs(mapas_dir, exist_ok=True)

    exported = {}
    for map_id in sorted(tree.map_names):
        path = os.path.join(args.maps_dir, "Map%04d.lmu" % map_id)
        if not os.path.exists(path):
            continue

        game_map = lcf.Map(path)
        chipset = database.chipsets[game_map.chipset_id]
        exported[map_id] = game_map

        write(os.path.join(mapas_dir, "Map%04d.json" % map_id),
              dumps(map_json(map_id, game_map, tree, chipset)))
        write(os.path.join(mapas_dir, "Map%04d.tiles" % map_id),
              tiles_text(map_id, game_map, chipset))

    write(os.path.join(args.out_dir, "maps.json"), dumps(tree_json(tree, exported)))

    # La base de datos: una sección por archivo. Junta son 15 listas que no
    # tienen nada que ver entre sí; separadas, un cambio en los ítems no
    # ensucia el diff de las animaciones.
    unknown = set()
    db_dir = os.path.join(args.out_dir, "db")
    os.makedirs(db_dir, exist_ok=True)
    sections = database_json(database, unknown)
    for name, section in sorted(sections.items()):
        write(os.path.join(db_dir, "%s.json" % name), dumps(section))

    events = sum(len(m.events) for m in exported.values())
    commands = sum(len(p.commands) for m in exported.values()
                   for e in m.events for p in e.pages)
    print("%d mapas, %d eventos, %d comandos" % (len(exported), events, commands))
    print("base de datos: %s" % ", ".join(
        "%s %d" % (n, len(s)) for n, s in sorted(sections.items())
        if isinstance(s, (list, dict))))
    print("-> %s (%.1f MB)" % (args.out_dir, tree_size(args.out_dir) / 1e6))

    if unknown:
        print("Chunks o tipos que el esquema no cubre: %s" % sorted(unknown))

    if args.verify:
        return verify(args.out_dir, exported)
    return 0


def bad_strings(node, path="", found=None):
    """Strings con caracteres de control o de reemplazo.

    Es el síntoma de un parseo desfasado: si el decodificador se corre unos
    bytes, los nombres y diálogos salen con basura. Con el esquema bien, no
    tiene que aparecer ninguno.
    """
    if found is None:
        found = []
    if isinstance(node, str):
        if any(c < " " or c == "�" for c in node):
            found.append((path, node[:40]))
    elif isinstance(node, dict):
        for key, value in node.items():
            bad_strings(value, "%s.%s" % (path, key), found)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            bad_strings(value, "%s[%d]" % (path, i), found)
    return found


def verify(out_dir, exported):
    """Releer los .tiles y revisar que lo exportado tenga sentido."""
    bad = []
    for map_id, game_map in exported.items():
        with open(os.path.join(out_dir, "maps",
                               "Map%04d.tiles" % map_id)) as handle:
            layers = parse_tiles(handle.read())
        if (layers.get("lower") != game_map.lower_layer
                or layers.get("upper") != game_map.upper_layer):
            bad.append(map_id)
    print("Verificación de tiles: %s" % (bad or "los %d coinciden" % len(exported)))

    garbage = []
    for root, _, names in os.walk(out_dir):
        for name in sorted(names):
            if name.endswith(".json"):
                with open(os.path.join(root, name), encoding="utf-8") as handle:
                    garbage += bad_strings(json.load(handle), name)
    print("Strings con basura: %s" % (garbage[:5] or "ninguno"))

    return 1 if bad or garbage else 0


if __name__ == "__main__":
    sys.exit(main())
