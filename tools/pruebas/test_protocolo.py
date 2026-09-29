"""Las declaraciones del bytecode y sus generados no se pueden ir separando.

Hay dos bytecodes en este port: el de eventos, que emite `tools/port/eventos.py`
e interpreta la ROM, y el stream de música, que escribe
`tools/audio/snes_music.py` y lee `irq_musica`. Los declara `tools/protocol/`,
que no es de ninguno de los dos lados, y de ahí salen generados los archivos
de `GENERADOS`. El
generador es un binario de Rust que se instala con `just -f tools/justfile herramientas` y se usa
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

import pytest  # noqa: E402

from port import event_opcodes  # noqa: E402
from port import eventos  # noqa: E402
from rpgmaker import lcf  # noqa: E402
from ensamblado import ensamblar  # noqa: E402
from audio import music_opcodes  # noqa: E402
from comun import proyecto  # noqa: E402


def _relativa(ruta):
    return os.path.relpath(ruta, proyecto.raiz())


# Cada bytecode: su declaración, su módulo de Python y su .inc. Relativos a la
# raíz, que es como salen en el nombre de cada caso.
GENERADOS = [
    ("events", event_opcodes,
     _relativa(os.path.join(proyecto.runtime(), "event_opcodes.inc")),
     _relativa(os.path.join(proyecto.herramientas(), "port",
                            "event_opcodes.py"))),
    ("music", music_opcodes,
     _relativa(os.path.join(proyecto.runtime(), "music_opcodes.inc")),
     _relativa(os.path.join(proyecto.herramientas(), "audio",
                            "music_opcodes.py"))),
]
MAIN = os.path.join(proyecto.runtime(), "main.s")
# Lo que cada uno pide de más, igual que en la receta `protocolo` de tools/justfile:
# sin esto el `--check` compara contra un `.inc` sin la tabla del despacho y lo
# da por viejo.
BANDERAS = {"events": ["--jump-table"]}


def declarados(modulo):
    return {n: v for n, v in vars(modulo).items()
            if n.startswith("OP_") and isinstance(v, int)}


@pytest.mark.parametrize("nombre,modulo,inc,py", GENERADOS)
def test_los_generados_estan_al_dia(nombre, modulo, inc, py):
    """Regenerar no cambia nada: si no, el árbol tiene dos verdades."""
    hecho = subprocess.run(
        ["protocol",
         os.path.join(proyecto.herramientas(), "protocol", nombre + ".toml"),
         "--python", os.path.join(proyecto.raiz(), py),
         "--asm", os.path.join(proyecto.raiz(), inc), "--check"]
        + BANDERAS.get(nombre, []),
        capture_output=True, text=True)
    assert hecho.returncode != 2, (
        "el generador no pudo correr —¿falta `just -f tools/justfile herramientas`?—:\n%s"
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
    for linea in open(os.path.join(proyecto.raiz(), inc), encoding="utf-8"):
        m = re.match(r"^(OP_[A-Z0-9_]+)\s*=\s*\$([0-9A-Fa-f]+)\s*$", linea)
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
    fuente = ensamblar.texto_de_la_fuente(MAIN)
    # Sólo los usos como operando: los nombres sueltos de los comentarios no.
    usados = set(re.findall(r"#(OP_[A-Z0-9_]+)\b", fuente))
    assert usados, "no se encontró un solo uso de un opcode en tools/runtime/"
    todos = set()
    for _, modulo, _, _ in GENERADOS:
        todos |= set(declarados(modulo))
    # Y que no haya vuelto a aparecer uno escrito a mano en la propia ROM.
    propios = set(re.findall(r"^(OP_[A-Z0-9_]+)\s*=", fuente, re.M))
    assert not propios, (
        "tools/runtime/ declara %s a mano: eso va en tools/protocol/"
        % ", ".join(sorted(propios)))
    sin_declarar = usados - todos
    assert not sin_declarar, (
        "tools/runtime/ compara contra %s, que no está declarado en tools/protocol/"
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


# --- el destino de un teletransporte entra en dos bytes --------------------
#
# `OP_TELEPORT` guardaba el índice del mapa destino en **un byte**, así que el
# formato no podía nombrar más de 256 mapas: era un techo escrito en el
# bytecode, y esto lo saca. Que el emisor y el intérprete cuenten los mismos
# bytes en todas las páginas de un juego lo mira la tanda del juego.

# Un índice que **no entra en un byte**, que es de lo que se trata. El juego
# tiene 328 mapas: el 300 es uno de los que el formato viejo no podía nombrar.
LEJOS = 300


def compilar_un_teleport(destino):
    cmd = lcf.EventCommand(eventos.TELEPORT, 0, "", [7, 12, 34])
    return eventos._compilar(cmd, lambda m: destino)


def test_un_destino_que_no_entra_en_un_byte_no_se_trunca():
    """El caso que el formato viejo no podía: 300 & 0xFF es 44."""
    assert compilar_un_teleport(LEJOS) != compilar_un_teleport(LEJOS & 0xFF)


def test_ningun_opcode_comparte_numero_con_otro():
    """Dos `OP_*` con el mismo valor son dos programas distintos.

    No es una precaución abstracta: el 2026-09-13 tres ramas de sub-agente
    eligieron el siguiente número libre a la vez, sin verse, y salieron dos
    colisiones —`OP_STOP_ROUTES` con `OP_ACTOR_SPRITE` en $23, `OP_IF_ACTOR` con
    `OP_KEY` en $24—. Git las mergeó **sin un solo conflicto**, porque cada
    una está en su línea, y lo que se rompía era el recorrido del bytecode: el
    intérprete leía un opcode de tres bytes creyendo que medía siete.

    Lo cazó `test_los_largos_de_opcode_cuadran_en_todo_el_juego`, pero de
    rebote y sólo porque alguna página del juego usaba los dos. Esto lo dice
    directamente y sin depender de que el juego los ejercite.
    """
    numeros = {}
    for nombre, valor in sorted(vars(eventos).items()):
        if not nombre.startswith("OP_") or not isinstance(valor, int):
            continue
        assert valor not in numeros, (
            "%s y %s son los dos $%02X: el bytecode no se puede recorrer"
            % (numeros[valor], nombre, valor))
        numeros[valor] = nombre
    assert len(numeros) > 30, "no se miró ni un opcode"
