"""Las declaraciones del bytecode y sus generados no se pueden ir separando.

Hay dos bytecodes en este port y los dos tenían el mismo problema. El de
eventos: el número lo decidía `tools/eventos.py` y le llegaba al intérprete de
`main.s` **adentro de los datos de un mapa**. El del stream de música, más
crudo todavía: los tres opcodes estaban escritos a mano de los dos lados, en
`tools/snes_music.py` y en `main.s`, sin nada que atara las copias.

Desde el 2026-09-15 los declara `protocol/`, que no es de ninguno de los dos
lados, y de ahí salen generados los cuatro archivos de `GENERADOS`. El
generador es un binario de Rust que se instala con `just herramientas` y se usa
desde el PATH, así que estos casos lo necesitan instalado; lo generado está
commiteado, así que **compilar la ROM no necesita ni eso**.

Eso mueve el problema en vez de resolverlo si los generados se pueden quedar
viejos, así que acá se exige que regenerar no cambie nada y que las dos puntas
de cada bytecode digan lo mismo. Lo que **no** se puede generar es qué hace
cada opcode: eso es 65816 escrito a mano.
"""

import os
import re
import subprocess
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(REPO, "tools"))

import pytest  # noqa: E402

import event_opcodes  # noqa: E402
import music_opcodes  # noqa: E402

# Cada bytecode: su declaración, su módulo de Python y su .inc.
GENERADOS = [
    ("events", event_opcodes, "rom/src/event_opcodes.inc",
     "tools/event_opcodes.py"),
    ("music", music_opcodes, "rom/src/music_opcodes.inc",
     "tools/music_opcodes.py"),
]
MAIN = os.path.join(REPO, "rom", "src", "main.s")


def declarados(modulo):
    return {n: v for n, v in vars(modulo).items()
            if n.startswith("OP_") and isinstance(v, int)}


@pytest.mark.parametrize("nombre,modulo,inc,py", GENERADOS)
def test_los_generados_estan_al_dia(nombre, modulo, inc, py):
    """Regenerar no cambia nada: si no, el árbol tiene dos verdades."""
    hecho = subprocess.run(
        ["protocol",
         os.path.join(REPO, "protocol", nombre + ".toml"),
         "--python", os.path.join(REPO, py),
         "--asm", os.path.join(REPO, inc), "--check"],
        capture_output=True, text=True)
    assert hecho.returncode != 2, (
        "el generador no pudo correr —¿falta `just herramientas`?—:\n%s"
        % hecho.stderr)
    assert hecho.returncode == 0, (
        "hay un generado desactualizado:\n%s%s" % (hecho.stdout, hecho.stderr))


@pytest.mark.parametrize("nombre,modulo,inc,py", GENERADOS)
def test_el_inc_y_el_py_dicen_los_mismos_numeros(nombre, modulo, inc, py):
    """Las dos puntas del contrato, leídas cada una por su lado.

    Un árbol donde se regeneró uno solo —y se commiteó uno solo— compila y
    corre: el que lee mide un opcode y el que escribe emite otro.
    """
    del_inc = {}
    for linea in open(os.path.join(REPO, inc), encoding="utf-8"):
        m = re.match(r"^(OP_[A-Z_]+)\s*=\s*\$([0-9A-Fa-f]+)\s*$", linea)
        if m:
            del_inc[m.group(1)] = int(m.group(2), 16)
    assert del_inc, "no se leyó un solo opcode de %s" % inc
    assert del_inc == declarados(modulo)


def test_ningun_opcode_de_la_rom_quedo_sin_declarar():
    """Un `cmp #OP_X` contra algo que nadie declara no ensambla...

    ...hoy. Pero el día que alguien vuelva a meter equates a mano, o en un
    archivo que genera el conversor, volvería a ensamblar leyendo un número
    escrito dos veces, que es lo que esto deja atrás. Los dos bytecodes juntos:
    para la ROM son un solo espacio de símbolos, y de hecho por eso `OP_FIN`
    tuvo que llamarse `OP_DONE` —`OP_END` ya era del stream de música—.
    """
    fuente = open(MAIN, encoding="utf-8").read()
    # Sólo los usos como operando: los nombres sueltos de los comentarios no.
    usados = set(re.findall(r"#(OP_[A-Z_]+)\b", fuente))
    assert usados, "no se encontró un solo uso de un opcode en main.s"
    todos = set()
    for _, modulo, _, _ in GENERADOS:
        todos |= set(declarados(modulo))
    # Y que no haya vuelto a aparecer uno escrito a mano en la propia ROM.
    propios = set(re.findall(r"^(OP_[A-Z_]+)\s*=", fuente, re.M))
    assert not propios, (
        "main.s declara %s a mano: eso va en protocol/"
        % ", ".join(sorted(propios)))
    sin_declarar = usados - todos
    assert not sin_declarar, (
        "main.s compara contra %s, que no está declarado en protocol/"
        % ", ".join(sorted(sin_declarar)))


def test_los_dos_bytecodes_no_comparten_un_nombre():
    """Los dos caen en el mismo espacio de símbolos del ensamblador.

    Los números sí pueden repetirse —`OP_DSP` y `OP_DONE` son los dos $00, y
    son cosas distintas en streams distintos—; los nombres no.
    """
    de_eventos = set(declarados(event_opcodes))
    de_musica = set(declarados(music_opcodes))
    compartidos = de_eventos & de_musica
    assert not compartidos, (
        "%s está en los dos bytecodes: en la ROM son un solo símbolo"
        % ", ".join(sorted(compartidos)))


@pytest.mark.parametrize("nombre,modulo,inc,py", GENERADOS)
def test_los_largos_se_derivan_del_layout(nombre, modulo, inc, py):
    """El largo no se escribe: es el opcode más sus argumentos."""
    for op_nombre, codigo in declarados(modulo).items():
        args = modulo.LAYOUT[codigo]
        cuenta = 1 + sum(bytes_ for _, bytes_, _ in args)
        if codigo in modulo.VARIABLE_SIZE:
            base, _, _ = modulo.VARIABLE_SIZE[codigo]
            assert base == cuenta, op_nombre
        else:
            assert modulo.OPCODE_SIZE[codigo] == cuenta, op_nombre
