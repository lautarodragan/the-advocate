"""The bytecode declarations and their generated files must not drift apart.

There are two bytecodes in this port: the event one, which
`tools/port/events.py` emits and the ROM interprets, and the music stream,
which `tools/audio/snes_music.py` writes and `irq_music` reads. They are
declared by `tools/protocol/`, which belongs to neither side, and from there
the files in `GENERADOS` are generated. The generator is a Rust binary
installed with `just -f tools/justfile install` and used from the PATH,
so these cases need it installed; the generated output is committed, so
**building the ROM does not even need that**.

That moves the problem instead of solving it if the generated files can go
stale, so here it is required that regenerating changes nothing and that
both ends of each bytecode say the same. What **cannot** be generated is
what each opcode does: that is hand-written 65816.
"""

import os
import re
import subprocess

import pytest  # noqa: E402

from port import event_opcodes  # noqa: E402
from port import events  # noqa: E402
from rpgmaker import lcf  # noqa: E402
from audio import music_opcodes  # noqa: E402
from common import project  # noqa: E402


def _relative(ruta):
    return os.path.relpath(ruta, project.root())


# Each bytecode: its declaration, its Python module and its .inc. Relative to
# the root, which is how they appear in each case's name.
GENERADOS = [
    ("events", event_opcodes,
     _relative(os.path.join(project.runtime(), "event_opcodes.inc")),
     _relative(os.path.join(project.tools(), "port",
                            "event_opcodes.py"))),
    ("music", music_opcodes,
     _relative(os.path.join(project.runtime(), "music_opcodes.inc")),
     _relative(os.path.join(project.tools(), "audio",
                            "music_opcodes.py"))),
]
# What each one needs on top, as in the `protocol` recipe of tools/justfile:
# without this `--check` compares against an `.inc` without the dispatch table
# and reports it as stale.
BANDERAS = {"events": ["--jump-table"]}


def declared(modulo):
    return {n: v for n, v in vars(modulo).items()
            if n.startswith("OP_") and isinstance(v, int)}


@pytest.mark.parametrize("nombre,modulo,inc,py", GENERADOS)
def test_the_generated_files_are_up_to_date(nombre, modulo, inc, py):
    """Regenerating changes nothing: otherwise the tree has two truths."""
    hecho = subprocess.run(
        ["protocol",
         os.path.join(project.tools(), "protocol", nombre + ".toml"),
         "--python", os.path.join(project.root(), py),
         "--asm", os.path.join(project.root(), inc), "--check"]
        + BANDERAS.get(nombre, []),
        capture_output=True, text=True)
    assert hecho.returncode != 2, (
        "the generator could not run —is `just -f tools/justfile install` missing?—:\n%s"
        % hecho.stderr)
    assert hecho.returncode == 0, (
        "a generated file is out of date:\n%s%s" % (hecho.stdout, hecho.stderr))


@pytest.mark.parametrize("nombre,modulo,inc,py", GENERADOS)
def test_the_inc_and_the_py_say_the_same_numbers(nombre, modulo, inc, py):
    """The two ends of the contract, each read on its own.

    A tree where only one was regenerated —and only one committed— builds and
    runs: the reader measures one opcode and the writer emits another.
    """
    del_inc = {}
    for linea in open(os.path.join(project.root(), inc), encoding="utf-8"):
        m = re.match(r"^(OP_[A-Z0-9_]+)\s*=\s*\$([0-9A-Fa-f]+)\s*$", linea)
        if m:
            del_inc[m.group(1)] = int(m.group(2), 16)
    assert del_inc, "not a single opcode was read from %s" % inc
    assert del_inc == declared(modulo)


def test_no_opcode_in_the_rom_is_undeclared(runtime_source):
    """A `cmp #OP_X` against something nobody declares does not assemble...

    ...today. But the day someone puts equates back by hand, or in a file the
    converter generates, it would assemble again reading a number written
    twice, which is what this leaves behind. Both bytecodes together: to the
    ROM they are a single symbol space, and in fact that is why `OP_FIN` had
    to be called `OP_DONE` —`OP_END` already belonged to the music stream—.
    """
    fuente = runtime_source
    # Only the uses as an operand: bare names in comments do not count.
    usados = set(re.findall(r"#(OP_[A-Z0-9_]+)\b", fuente))
    assert usados, "not a single use of an opcode was found in tools/runtime/"
    todos = set()
    for _, modulo, _, _ in GENERADOS:
        todos |= set(declared(modulo))
    # And that no hand-written one has reappeared in the ROM itself.
    propios = set(re.findall(r"^(OP_[A-Z0-9_]+)\s*=", fuente, re.M))
    assert not propios, (
        "tools/runtime/ declares %s by hand: that goes in tools/protocol/"
        % ", ".join(sorted(propios)))
    sin_declarar = usados - todos
    assert not sin_declarar, (
        "tools/runtime/ compares against %s, which is not declared in tools/protocol/"
        % ", ".join(sorted(sin_declarar)))


def test_the_two_bytecodes_share_no_name():
    """Both land in the same assembler symbol space.

    The numbers may repeat —`OP_DSP` and `OP_DONE` are both $00, and they are
    different things in different streams—; the names may not.
    """
    de_eventos = set(declared(event_opcodes))
    de_musica = set(declared(music_opcodes))
    compartidos = de_eventos & de_musica
    assert not compartidos, (
        "%s is in both bytecodes: in the ROM they are a single symbol"
        % ", ".join(sorted(compartidos)))


@pytest.mark.parametrize("nombre,modulo,inc,py", GENERADOS)
def test_the_lengths_come_from_the_layout(nombre, modulo, inc, py):
    """The length is not written: it is the opcode plus its arguments."""
    for op_nombre, codigo in declared(modulo).items():
        args = modulo.LAYOUT[codigo]
        cuenta = 1 + sum(bytes_ for _, bytes_, _ in args)
        if codigo in modulo.VARIABLE_SIZE:
            base, _, _ = modulo.VARIABLE_SIZE[codigo]
            assert base == cuenta, op_nombre
        else:
            assert modulo.OPCODE_SIZE[codigo] == cuenta, op_nombre


# --- a teleport's destination fits in two bytes ---------------------------
#
# `OP_TELEPORT` stored the destination map's index in **one byte**, so the
# format could not name more than 256 maps: it was a ceiling written into the
# bytecode, and this removes it. That the emitter and the interpreter count
# the same bytes in every page of a game is checked by the game's suite.

# An index that **does not fit in a byte**, which is the point. The game has
# 328 maps: 300 is one of those the old format could not name.
LEJOS = 300


def compile_a_teleport(destino):
    cmd = lcf.EventCommand(events.TELEPORT, 0, "", [7, 12, 34])
    return events._compile(cmd, lambda m: destino)


def test_a_destination_that_does_not_fit_a_byte_is_not_truncated():
    """The case the old format could not handle: 300 & 0xFF is 44."""
    assert compile_a_teleport(LEJOS) != compile_a_teleport(LEJOS & 0xFF)


def test_no_opcode_shares_a_number_with_another():
    """Two `OP_*` with the same value are two different programs.

    It is not an abstract precaution: on 2026-09-13 three sub-agent branches
    picked the next free number at the same time, without seeing each other,
    and two collisions came out —`OP_STOP_ROUTES` with `OP_ACTOR_SPRITE` at
    $23, `OP_IF_ACTOR` with `OP_KEY` at $24—. Git merged them **without a
    single conflict**, because each is on its own line, and what broke was
    walking the bytecode: the interpreter read a three-byte opcode believing
    it was seven long.

    It was caught by `test_los_largos_de_opcode_cuadran_en_todo_el_juego`,
    but indirectly and only because some page of the game used both. This
    says it directly and without depending on the game exercising them.
    """
    numeros = {}
    for nombre, valor in sorted(vars(events).items()):
        if not nombre.startswith("OP_") or not isinstance(valor, int):
            continue
        assert valor not in numeros, (
            "%s and %s are both $%02X: the bytecode cannot be walked"
            % (numeros[valor], nombre, valor))
        numeros[valor] = nombre
    assert len(numeros) > 30, "not a single opcode was looked at"
