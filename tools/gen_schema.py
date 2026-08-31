#!/usr/bin/env python3
"""Genera tools/lcf_schema.py a partir del código de liblcf.

La RPG_RT.ldb tiene ~20 listas con cientos de campos tipados. Escribir ese
esquema a mano sería tedioso y quedaría desactualizado, pero liblcf ya lo tiene
declarado en su código generado: los IDs de chunk en
src/generated/lcf/*/chunks.h y el tipo de cada campo en las declaraciones
TypedField de src/generated/*.cpp. Esto los cruza.

Uso:
    python3 tools/gen_schema.py [ruta/a/liblcf] > tools/lcf_schema.py
"""

import os
import re
import sys

LIBLCF = "/home/taro/git/gaming/easyrpg/liblcf"

# Cómo se lee cada tipo de C++. Los nombres de la derecha son los que entiende
# el decodificador en lcf.py.
TYPES = {
    "int32_t": "int",
    "bool": "bool",
    "DBString": "string",
    "std::string": "string",
    "DBBitArray": "bits",
    "int8_t": "i8",
    "uint8_t": "u8",
    "uint32_t": "u32",
    "double": "double",
    "std::vector<bool>": "bits",
    "std::vector<uint8_t>": "u8array",
    "std::vector<int16_t>": "i16array",
    "std::vector<int32_t>": "i32array",
    "std::vector<uint32_t>": "u32array",
    "rpg::Equipment": "equipment",
    "rpg::Parameters": "parameters",
    "rpg::Rect": "rect",
    "std::vector<rpg::EventCommand>": "commands",
    "std::vector<rpg::MoveCommand>": "movecommands",
}

CHUNK_RE = re.compile(r"struct Chunk(\w+)\s*\{\s*enum Index\s*\{(.*?)\}\s*;", re.S)
ENTRY_RE = re.compile(r"^\s*(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)", re.M)
FIELD_RE = re.compile(
    r"static TypedField<rpg::(\w+),\s*(.+?)>\s*static_\w+\(\s*"
    r"&[^,]+,\s*\w+_Reader::Chunk\w+::(\w+),\s*\"([^\"]*)\"", re.S)
SIZE_RE = re.compile(
    r"static SizeField<rpg::(\w+),.*?>\s*static_\w+\(\s*"
    r"&[^,]+,\s*\w+_Reader::Chunk\w+::(\w+),", re.S)
FLAGS_RE = re.compile(
    r"class (\w+) \{.*?struct Flags \{\s*union \{\s*struct \{(.*?)\}\s*;", re.S)


def read_all(directory, pattern):
    for name in sorted(os.listdir(directory)):
        if re.search(pattern, name):
            with open(os.path.join(directory, name), encoding="utf-8") as handle:
                yield name, handle.read()


def collect_chunks(liblcf):
    """{Struct: {campo: id}} desde los chunks.h."""
    chunks = {}
    base = os.path.join(liblcf, "src/generated/lcf")
    for group in sorted(os.listdir(base)):
        path = os.path.join(base, group, "chunks.h")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for struct, body in CHUNK_RE.findall(source):
            entries = chunks.setdefault(struct, {})
            for field, value in ENTRY_RE.findall(body):
                entries[field] = int(value, 0)
    return chunks


def collect_fields(liblcf, chunks):
    """{Struct: {id: (nombre, tipo)}} cruzando las declaraciones con los chunks."""
    schema = {}
    skip = {}
    unknown = set()
    directory = os.path.join(liblcf, "src/generated")

    for _, source in read_all(directory, r"\.cpp$"):
        for struct, ctype, chunk_field, name in FIELD_RE.findall(source):
            chunk_id = chunks.get(struct, {}).get(chunk_field)
            if chunk_id is None:
                continue

            ctype = " ".join(ctype.split())
            if ctype in TYPES:
                kind = TYPES[ctype]
            elif ctype.startswith("std::vector<rpg::"):
                kind = "array:" + ctype[len("std::vector<rpg::"):-1]
            elif ctype.endswith("::Flags"):
                kind = "flags:" + ctype[len("rpg::"):-len("::Flags")]
            elif ctype.startswith("rpg::"):
                kind = "struct:" + ctype[len("rpg::"):]
            else:
                unknown.add(ctype)
                kind = "raw"
            schema.setdefault(struct, {})[chunk_id] = (name, kind)

        # Los chunks "_size" duplican el largo de un array; el array ya lo trae.
        for struct, chunk_field in SIZE_RE.findall(source):
            chunk_id = chunks.get(struct, {}).get(chunk_field)
            if chunk_id is not None:
                skip.setdefault(struct, set()).add(chunk_id)

    return schema, skip, unknown


def collect_flags(liblcf):
    """{Struct: [nombres de los bits]} desde los headers de rpg."""
    flags = {}
    directory = os.path.join(liblcf, "src/generated/lcf/rpg")
    for _, source in read_all(directory, r"\.h$"):
        for struct, body in FLAGS_RE.findall(source):
            names = re.findall(r"bool (\w+);", body)
            if names:
                flags[struct] = names
    return flags


def main():
    liblcf = sys.argv[1] if len(sys.argv) > 1 else LIBLCF
    chunks = collect_chunks(liblcf)
    schema, skip, unknown = collect_fields(liblcf, chunks)
    flags = collect_flags(liblcf)

    if unknown:
        print("Tipos que no supe mapear: %s" % sorted(unknown), file=sys.stderr)

    out = ['"""Esquema de los formatos LCF: qué campo es cada chunk y de qué tipo.',
           "",
           "Generado por tools/gen_schema.py desde liblcf. No lo edites a mano.",
           '"""',
           "",
           "SCHEMA = {"]
    for struct in sorted(schema):
        out.append("    %r: {" % struct)
        for chunk_id in sorted(schema[struct]):
            name, kind = schema[struct][chunk_id]
            out.append("        0x%02X: (%r, %r)," % (chunk_id, name, kind))
        out.append("    },")
    out.append("}")
    out.append("")
    out.append("# Chunks que sólo repiten el largo de un array; se ignoran.")
    out.append("SKIP = {")
    for struct in sorted(skip):
        out.append("    %r: %r," % (struct, sorted(skip[struct])))
    out.append("}")
    out.append("")
    out.append("# Nombres de los bits de cada campo de flags, LSB primero.")
    out.append("FLAGS = {")
    for struct in sorted(flags):
        out.append("    %r: %r," % (struct, flags[struct]))
    out.append("}")

    print("\n".join(out))
    print("%d structs, %d campos" % (
        len(schema), sum(len(v) for v in schema.values())), file=sys.stderr)


if __name__ == "__main__":
    main()
