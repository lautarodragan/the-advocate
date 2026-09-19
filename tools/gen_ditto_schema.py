#!/usr/bin/env python3
"""Genera tools/ditto_schema.py a partir del esquema de Ditto.

Desde el 2026-09-14 el juego se lee del volcado a JSON de `data/`, que escribe
Ditto (ver DITTO.md). Ese JSON **omite todo campo que valga su default**, así
que para leerlo hay que conocer los defaults; y guarda los enums **por nombre**
—`"same"`, `"ShowMessage"`— así que para volver al número hay que conocer las
tablas. Las dos cosas están declaradas en `ditto/src/schema/mod.rs`, que es el
código que escribió el JSON, y de ahí salen: no se copian a mano.

Es la misma idea con la que se generaba el esquema del lector viejo —leer el
esquema de quien lo tiene en vez de transcribirlo—, con la fuente corrida un
lugar: liblcf genera el esquema de Ditto y Ditto genera éste. Un nombre o un default que cambien allá aparecen acá
como un diff que se lee, no como un dato que llega distinto.

Uso:
    python3 tools/gen_ditto_schema.py [ruta/a/ditto] > tools/ditto_schema.py
"""

import os
import re
import sys

DITTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ditto")

STRUCT_RE = re.compile(
    r"schema_struct! \{(.*?)\n\}\n\}", re.S)
NAME_RE = re.compile(r"pub struct (\w+) \{")
FIELD_RE = re.compile(
    r"((?:^[ \t]*///.*\n)*)[ \t]*pub (\w+|r#\w+): (.+?) = (.+),\s*$", re.M)
CHUNK_RE = re.compile(r"field (0x[0-9a-fA-F]+) of the binary")
PERSIST = "stored even when it holds the default"

ENUM_RE = re.compile(
    r"pub enum (\w+) \{(.*?)\n\}\n\nimpl \1 \{\s*pub fn to_i32.*?match self \{"
    r"(.*?)\n        \}", re.S)
VARIANT_RE = re.compile(r'#\[serde\(rename = "([^"]+)"\)\]\s*\n\s*(\w+),')
ARM_RE = re.compile(r"(\w+)::(\w+) => (-?\d+),")

# Las constantes con nombre del esquema, que son tres y salen del mismo archivo.
CONST_RE = re.compile(r"pub const (k\w+): \w+ = (-?[\d.]+)")


def rust_string(literal):
    """El valor de un literal de Rust `"..."`, con los escapes que aparecen."""
    body = literal[1:-1]
    out = []
    i = 0
    while i < len(body):
        if body[i] != "\\":
            out.append(body[i])
            i += 1
            continue
        nxt = body[i + 1]
        if nxt == "u":
            end = body.index("}", i)
            out.append(chr(int(body[i + 3:end], 16)))
            i = end + 1
        else:
            out.append({"n": "\n", "t": "\t", "r": "\r",
                        "0": "\0"}.get(nxt, nxt))
            i += 2
    return "".join(out)


def parse_default(expr, consts):
    """El default de un campo, como valor de Python.

    `None` quiere decir "el default del tipo": una lista vacía, o un struct
    todo en default, que el lector arma solo.
    """
    expr = expr.strip()
    if expr in ("Default::default()", "Vec::new()"):
        return None
    if expr in ("true", "false"):
        return expr == "true"
    if expr in consts:
        return consts[expr]
    if re.fullmatch(r"-?\d+", expr):
        return int(expr)
    if re.fullmatch(r"-?\d+\.\d+", expr):
        return float(expr)
    if expr.endswith(".to_string()") and expr.startswith('"'):
        return rust_string(expr[:-len(".to_string()")])
    match = re.fullmatch(r"\w+::from_i32\((-?\d+)\)", expr)
    if match:
        return int(match.group(1))
    match = re.fullmatch(r"vec!\[(-?\d+); (\d+)\]", expr)
    if match:
        return [int(match.group(1))] * int(match.group(2))
    match = re.fullmatch(r"\((\d+)\.\.(\d+)\)\.collect\(\)", expr)
    if match:
        return list(range(int(match.group(1)), int(match.group(2))))
    match = re.fullmatch(
        r"\[vec!\[(-?\d+); (\d+)\], vec!\[(-?\d+); (\d+)\]\]\.concat\(\)", expr)
    if match:
        a, na, b, nb = (int(g) for g in match.groups())
        return [a] * na + [b] * nb
    raise ValueError("no sé leer el default %r" % expr)


def parse_enums(source):
    """{Enum: {nombre en el JSON: número}} desde los `to_i32`."""
    enums = {}
    for name, body, arms in ENUM_RE.findall(source):
        renames = dict(
            (variant, rename) for rename, variant in VARIANT_RE.findall(body))
        table = {}
        for enum, variant, value in ARM_RE.findall(arms):
            if enum != name or variant not in renames:
                continue        # Other(v), que no tiene nombre
            table[renames[variant]] = int(value)
        enums[name] = table
    return enums


def parse_structs(source, consts):
    """{Struct: {campo: (chunk_id, default, enum, siempre, anidado)}}.

    `siempre` es el `PersistIfDefault` del formato: el binario escribe ese
    campo aunque valga el default, así que un lector del binario siempre lo
    veía. El JSON lo omite igual que a cualquier otro, y esa es la única
    diferencia de presencia entre los dos: rellenarlo es lo que hace que leer
    el JSON dé lo mismo que leer el `.ldb`.
    """
    structs = {}
    for body in STRUCT_RE.findall(source):
        name = NAME_RE.search(body)
        if not name:
            continue
        fields = {}
        for docs, field, rust_type, default in FIELD_RE.findall(body):
            if field == "unknown":
                continue
            chunk = CHUNK_RE.search(docs)
            # `Vec<Enemy>` y `Enemy` llevan al mismo esquema: lo que importa
            # es de qué struct —o de qué enum— es cada valor.
            base = re.fullmatch(r"(?:Vec<)?(\w+)>?", rust_type.strip())
            fields[field.replace("r#", "")] = (
                int(chunk.group(1), 16) if chunk else None,
                parse_default(default, consts),
                base.group(1) if base else None,
                PERSIST in docs)
        structs[name.group(1)] = fields
    return structs


def main():
    ditto = sys.argv[1] if len(sys.argv) > 1 else DITTO
    with open(os.path.join(ditto, "src/schema/mod.rs"), encoding="utf-8") as fh:
        source = fh.read()

    consts = {k: float(v) if "." in v else int(v)
              for k, v in CONST_RE.findall(source)}
    enums = parse_enums(source)
    structs = parse_structs(source, consts)
    # Un campo lleva adentro **o** un enum **o** otro struct del esquema, y
    # hasta acá los dos venían en el mismo lugar: el nombre del tipo de Rust.
    for fields in structs.values():
        for field, (chunk, default, tipo, siempre) in list(fields.items()):
            fields[field] = (chunk, default, tipo if tipo in enums else None,
                             siempre, tipo if tipo in structs else None)

    out = ['"""Los nombres, los defaults y los enums del volcado a JSON.',
           "",
           "Generado por tools/gen_ditto_schema.py desde ditto/src/schema/mod.rs.",
           "No lo edites a mano.",
           "",
           "    CAMPOS[struct][campo] = (chunk, default, enum, siempre, anidado)",
           "    ENUMS[enum][nombre] = número",
           "",
           "`chunk` es el del binario, que ya no se lee pero sigue siendo cómo se",
           "nombran algunas cosas desde afuera —los términos de la tienda—.",
           "`default` es lo que vale un campo que el JSON no trae, y `None` es el",
           "default del tipo: una lista vacía o un struct todo en default.",
           "`siempre` es el `PersistIfDefault` del formato: el campo que el binario",
           "escribe aunque valga el default, y que por eso un lector del binario",
           "siempre veía. `anidado` es el struct que el campo lleva adentro, uno",
           "solo o una lista de ellos.",
           '"""',
           "",
           "CAMPOS = {"]
    for struct in sorted(structs):
        out.append("    %r: {" % struct)
        for field in sorted(structs[struct]):
            out.append("        %r: %r," % (field, structs[struct][field]))
        out.append("    },")
    out.append("}")
    out.append("")
    out.append("ENUMS = {")
    for enum in sorted(enums):
        out.append("    %r: {" % enum)
        for nombre in sorted(enums[enum], key=lambda n: enums[enum][n]):
            out.append("        %r: %r," % (nombre, enums[enum][nombre]))
        out.append("    },")
    out.append("}")

    print("\n".join(out))
    print("%d structs, %d campos, %d enums" % (
        len(structs), sum(len(v) for v in structs.values()), len(enums)),
        file=sys.stderr)


if __name__ == "__main__":
    main()
