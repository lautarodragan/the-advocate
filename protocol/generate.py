#!/usr/bin/env python3
"""Generates both ends of the event bytecode from `events.toml`.

    python3 protocol/generate.py            # writes the two files
    python3 protocol/generate.py --check    # fails if they are out of date

The declaration is owned by neither side, so neither side parses it: what is
committed is the generated code, and a test makes regenerating a no-op. That
way a changed opcode shows up as a readable diff on both ends at once, which
is the whole point — the number used to live in the compiler and reach the
interpreter inside a map's data.

The ROM still includes `mapdata.inc`: the map tables and the rest of the
constants are still emitted by the converter. What left is the bytecode.

The two outputs are written in the language of the tree they land in, which is
Spanish; only this directory is in English. Nothing else is generated here:
what an opcode *does* is hand-written 65816 and always will be.
"""

import argparse
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "protocol" / "events.toml"
PYTHON_OUT = ROOT / "tools" / "opcodes.py"
ASM_OUT = ROOT / "rom" / "src" / "opcodes.inc"

SIZES = {"byte": 1, "word": 2, "long": 3}


class Opcode:
    def __init__(self, entry):
        self.name = entry["name"]
        self.code = entry["code"]
        self.args = entry.get("args", [])
        self.repeated = entry.get("repeated")
        for a in self.args:
            if a["type"] not in SIZES:
                raise SystemExit(f"{self.name}: unknown type {a['type']!r}")

    @property
    def fixed_size(self):
        """The opcode byte plus its arguments."""
        return 1 + sum(SIZES[a["type"]] for a in self.args)

    @property
    def entry_size(self):
        return sum(SIZES[a["type"]] for a in self.repeated["args"])

    @property
    def count_offset(self):
        """Where the argument holding how many entries follow starts."""
        at = 1
        for a in self.args:
            if a.get("count"):
                return at
            at += SIZES[a["type"]]
        raise SystemExit(f"{self.name}: `repeated` with no argument counting it")


def load():
    with open(SOURCE, "rb") as f:
        opcodes = [Opcode(e) for e in tomllib.load(f)["opcode"]]
    seen = {}
    for o in opcodes:
        if o.code in seen:
            raise SystemExit(
                f"{o.name} and {seen[o.code]} both take 0x{o.code:02X}")
        seen[o.code] = o.name
        counted = {a["count"] for a in o.args if a.get("count")}
        if o.repeated and counted != {o.repeated["name"]}:
            raise SystemExit(f"{o.name}: nothing counts {o.repeated['name']!r}")
        if counted and not o.repeated:
            raise SystemExit(f"{o.name}: counts a group that is not declared")
    return opcodes


def python_source(opcodes):
    out = [
        '"""Los opcodes del bytecode de eventos: su número y su layout.',
        "",
        "Generado por protocol/generate.py desde protocol/events.toml.",
        "**No editar a mano**: el cambio se hace allá y se regenera. La prueba",
        "`test_protocolo.py` exige que regenerar no cambie nada.",
        '"""',
        "",
    ]
    for o in opcodes:
        out.append(f"{o.name:<16} = 0x{o.code:02X}")
    out += [
        "",
        "",
        "# Cuántos bytes ocupa cada instrucción de largo fijo, contando el opcode.",
        "# Se deriva de los argumentos declarados, no se escribe.",
        "LARGO_DE_OPCODE = {",
    ]
    for o in opcodes:
        if not o.repeated:
            out.append(f"    {o.name}: {o.fixed_size},")
    out += [
        "}",
        "",
        "# Las de largo variable, como (base, dónde está la cuenta, cuánto mide",
        "# cada entrada): el largo es base + cuenta * entrada.",
        "LARGO_VARIABLE = {",
    ]
    for o in opcodes:
        if o.repeated:
            out.append(
                f"    {o.name}: ({o.fixed_size}, {o.count_offset}, {o.entry_size}),")
    out += [
        "}",
        "",
        "# Los argumentos de cada uno, en orden, como (nombre, bytes, con signo).",
        "LAYOUT = {",
    ]
    for o in opcodes:
        args = ", ".join(
            f'("{a["name"]}", {SIZES[a["type"]]}, {bool(a.get("signed"))})'
            for a in o.args)
        out.append(f"    {o.name}: ({args}{',' if len(o.args) == 1 else ''}),")
    out += [
        "}",
        "",
        "",
        "def largo_de_opcode(codigo, i):",
        '    """Cuántos bytes ocupa el opcode que empieza en `codigo[i]`."""',
        "    op = codigo[i]",
        "    variable = LARGO_VARIABLE.get(op)",
        "    if variable is not None:",
        "        base, cuenta, entrada = variable",
        "        return base + entrada * codigo[i + cuenta]",
        "    largo = LARGO_DE_OPCODE.get(op)",
        "    if largo is None:",
        '        raise ValueError(f"opcode desconocido: 0x{op:02X}")',
        "    return largo",
        "",
    ]
    return "\n".join(out)


def asm_source(opcodes):
    out = [
        "; Los opcodes del bytecode de eventos.",
        ";",
        "; Generado por protocol/generate.py desde protocol/events.toml.",
        "; **No editar a mano.** Hasta el 2026-09-14 estos equates salían",
        "; adentro de mapdata.inc: el compilador le declaraba al intérprete",
        "; los números que el intérprete implementa, y se los mandaba dentro",
        "; de los datos de un mapa.",
        "",
    ]
    for o in opcodes:
        out.append(f"{o.name:<16} = ${o.code:02X}")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="do not write; fail if a generated file is stale")
    args = ap.parse_args()

    opcodes = load()
    wanted = {PYTHON_OUT: python_source(opcodes), ASM_OUT: asm_source(opcodes)}

    stale = []
    for path, text in wanted.items():
        current = path.read_text() if path.exists() else None
        if current == text:
            continue
        if args.check:
            stale.append(path.relative_to(ROOT))
        else:
            path.write_text(text)
            print(f"escrito {path.relative_to(ROOT)}")
    if stale:
        print("desactualizados: " + ", ".join(str(p) for p in stale),
              file=sys.stderr)
        print("correr: python3 protocol/generate.py", file=sys.stderr)
        return 1
    if args.check:
        print(f"{len(opcodes)} opcodes, los dos archivos al día")
    return 0


if __name__ == "__main__":
    sys.exit(main())
