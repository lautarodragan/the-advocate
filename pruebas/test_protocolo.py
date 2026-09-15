"""La declaración del bytecode y sus dos generados no se pueden ir separando.

El número de un opcode lo decidía `tools/eventos.py` y le llegaba al intérprete
de `main.s` **adentro de los datos de un mapa**: el compilador le declaraba al
intérprete los números que el intérprete implementa. Desde el 2026-09-14 los
declara `protocol/events.toml`, que no es de ninguno de los dos, y de ahí salen
generados `tools/opcodes.py` y `rom/src/opcodes.inc`.

Eso mueve el problema en vez de resolverlo si los generados se pueden quedar
viejos, así que acá se exige que regenerar no cambie nada, y que las dos puntas
digan lo mismo. Lo que **no** se puede generar es qué hace cada opcode: eso es
65816 escrito a mano, y por eso el último caso pregunta al revés —que el
intérprete no compare contra un opcode que nadie declaró—.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "tools"))

import opcodes  # noqa: E402

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INC = os.path.join(REPO, "rom", "src", "opcodes.inc")
MAIN = os.path.join(REPO, "rom", "src", "main.s")


def declarados():
    """Los opcodes de `tools/opcodes.py`, que es uno de los dos generados."""
    return {n: v for n, v in vars(opcodes).items()
            if n.startswith("OP_") and isinstance(v, int)}


def test_los_generados_estan_al_dia():
    """Regenerar no cambia nada: si no, el árbol tiene dos verdades."""
    hecho = subprocess.run(
        [sys.executable, os.path.join(REPO, "protocol", "generate.py"), "--check"],
        capture_output=True, text=True)
    assert hecho.returncode == 0, (
        "hay un generado desactualizado:\n%s%s" % (hecho.stdout, hecho.stderr))


def test_el_inc_y_el_py_dicen_los_mismos_numeros():
    """Las dos puntas del contrato, leídas cada una por su lado.

    Un árbol donde se regeneró uno solo —y se commiteó uno solo— compila y
    corre: el intérprete mide un opcode y el compilador emite otro.
    """
    del_inc = {}
    for linea in open(INC, encoding="utf-8"):
        m = re.match(r"^(OP_[A-Z_]+)\s*=\s*\$([0-9A-Fa-f]+)\s*$", linea)
        if m:
            del_inc[m.group(1)] = int(m.group(2), 16)
    assert del_inc, "no se leyó un solo opcode de opcodes.inc"
    assert del_inc == declarados()


def test_ningun_opcode_del_interprete_quedo_sin_declarar():
    """Un `cmp #OP_X` de main.s contra algo que nadie declara no ensambla...

    ...hoy. Pero el día que alguien vuelva a meter equates en un archivo
    generado por el conversor, volvería a ensamblar leyendo un número que viene
    de los datos de un mapa, que es justo lo que esto deja atrás.
    """
    fuente = open(MAIN, encoding="utf-8").read()
    # Sólo los usos como operando: los nombres sueltos de los comentarios no.
    usados = set(re.findall(r"#(OP_[A-Z_]+)\b", fuente))
    assert usados, "no se encontró un solo uso de un opcode en main.s"
    # El stream del SPC700 tiene sus propios OP_ —OP_DSP, OP_WAIT, OP_END—,
    # que son otro protocolo y los declara main.s mismo. Quedan afuera.
    propios = set(re.findall(r"^(OP_[A-Z_]+)\s*=", fuente, re.M))
    sin_declarar = usados - set(declarados()) - propios
    assert not sin_declarar, (
        "main.s compara contra %s, que no está en protocol/events.toml"
        % ", ".join(sorted(sin_declarar)))


def test_los_largos_se_derivan_del_layout():
    """El largo no se escribe: es el opcode más sus argumentos.

    Es lo que dejó de estar escrito a mano en dos lugares a la vez. Si alguien
    edita el generado —que dice bien grande que no—, esto lo dice.
    """
    for nombre, codigo in declarados().items():
        args = opcodes.LAYOUT[codigo]
        cuenta = 1 + sum(bytes_ for _, bytes_, _ in args)
        if codigo in opcodes.LARGO_VARIABLE:
            base, _, _ = opcodes.LARGO_VARIABLE[codigo]
            assert base == cuenta, nombre
        else:
            assert opcodes.LARGO_DE_OPCODE[codigo] == cuenta, nombre
