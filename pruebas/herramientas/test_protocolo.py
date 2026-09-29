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

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")

import pytest  # noqa: E402

from port import event_opcodes  # noqa: E402
from port import eventos  # noqa: E402
from rpgmaker import lcf  # noqa: E402
from rpgmaker.recursos import GAME_DIR  # noqa: E402
from ensamblado import ensamblar  # noqa: E402
from audio import music_opcodes  # noqa: E402
from ensamblado import cartuchos  # noqa: E402
import tanda  # noqa: E402

# Cada bytecode: su declaración, su módulo de Python y su .inc.
GENERADOS = [
    ("events", event_opcodes, "rom/src/event_opcodes.inc",
     "tools/port/event_opcodes.py"),
    ("music", music_opcodes, "rom/src/music_opcodes.inc",
     "tools/audio/music_opcodes.py"),
]
MAIN = os.path.join(REPO, "rom", "src", "main.s")
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
         os.path.join(REPO, "tools", "protocol", nombre + ".toml"),
         "--python", os.path.join(REPO, py),
         "--asm", os.path.join(REPO, inc), "--check"]
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
    for linea in open(os.path.join(REPO, inc), encoding="utf-8"):
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
    assert usados, "no se encontró un solo uso de un opcode en rom/src/"
    todos = set()
    for _, modulo, _, _ in GENERADOS:
        todos |= set(declarados(modulo))
    # Y que no haya vuelto a aparecer uno escrito a mano en la propia ROM.
    propios = set(re.findall(r"^(OP_[A-Z0-9_]+)\s*=", fuente, re.M))
    assert not propios, (
        "rom/src/ declara %s a mano: eso va en tools/protocol/"
        % ", ".join(sorted(propios)))
    sin_declarar = usados - todos
    assert not sin_declarar, (
        "rom/src/ compara contra %s, que no está declarado en tools/protocol/"
        % ", ".join(sorted(sin_declarar)))


def desde_la_rom(datos, direccion):
    """El byte de LoROM que cae en `direccion`, sea del banco que sea o de su
    espejo rápido (`$80xxxx`)."""
    return ((direccion >> 16) & 0x7F) * 0x8000 + (direccion & 0x7FFF)


@pytest.mark.parametrize("nombre", sorted(cartuchos.CARTUCHOS))
def test_la_entrada_k_de_la_tabla_salta_al_manejador_del_opcode_k(nombre):
    """El despacho de `correr_codigo` es `jmp (manejadores_de_opcode, x)`.

    Que cada `op_x` exista lo cobra el ensamblador: la tabla es una macro que
    los nombra. Esto mira la ROM armada: que la entrada k, leída como la lee
    el `jmp`, sea la dirección del manejador del opcode k, y que ése esté en
    el banco de `correr_codigo`, porque la entrada es de dieciséis bits y el
    `jmp` salta adentro del banco del programa. Un manejador que alguien
    mande a otro banco ensamblaría igual si el `.addr` lo trunca.
    """
    uno = tanda.cartucho(nombre)
    with open(uno.sfc, "rb") as archivo:
        datos = archivo.read()
    tabla = uno.simbolos["manejadores_de_opcode"]
    banco = uno.simbolos["correr_codigo"] >> 16
    codigos = {v: n for n, v in declarados(event_opcodes).items()}
    assert sorted(codigos) == list(range(len(codigos))), (
        "los números de events.toml tienen huecos: la tabla no puede ser")
    for k in sorted(codigos):
        manejador = codigos[k].lower()
        direccion = uno.simbolos[manejador]
        en = desde_la_rom(datos, tabla + 2 * k)
        entrada = datos[en] | datos[en + 1] << 8
        assert entrada == direccion & 0xFFFF, (
            "la entrada $%02X de la tabla apunta a $%04X y %s está en $%06X"
            % (k, entrada, manejador, direccion))
        assert direccion >> 16 == banco, (
            "%s está en el banco $%02X y correr_codigo en el $%02X: el `jmp` "
            "de la tabla no llega" % (manejador, direccion >> 16, banco))


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


# --- los largos, contra el juego -------------------------------------------
#
# El destino de un teletransporte entra en dos bytes, y los largos cuadran.
#
# `OP_TELEPORT` guardaba el índice del mapa destino en **un byte**, así que el
# formato no podía nombrar más de 256 mapas y el juego tiene 328: era un techo
# escrito en el bytecode, y esto lo saca.
#
# Lo que hace falta probar no es "el teletransporte anda", que eso ya lo miran la
# tanda de pixeles y `test_puerta_misma`: es que **el emisor y el intérprete
# cuenten los mismos bytes**. Si no coinciden, el intérprete lee el bytecode
# corrido y eso no da ningún error: da una página que hace cualquier cosa. Por eso
# el segundo test no mira sólo el teletransporte sino **todos los opcodes de todas
# las páginas del juego**: recorre el bytecode con los largos de
# `OPCODE_SIZE` y exige caer justo en el final. Un opcode al que el emisor le
# ponga un byte de más o de menos se cae ahí, sea cual sea.

# Un índice que **no entra en un byte**, que es de lo que se trata. El juego
# tiene 328 mapas: el 300 es uno de los que el formato viejo no podía nombrar.
LEJOS = 300


def compilar_un_teleport(destino):
    cmd = lcf.EventCommand(eventos.TELEPORT, 0, "", [7, 12, 34])
    return eventos._compilar(cmd, lambda m: destino)


def test_un_destino_que_no_entra_en_un_byte_no_se_trunca():
    """El caso que el formato viejo no podía: 300 & 0xFF es 44."""
    assert compilar_un_teleport(LEJOS) != compilar_un_teleport(LEJOS & 0xFF)


def paginas_del_juego():
    """Todas las páginas disparables de los 328 mapas, ya compiladas."""
    # **Todos** los índices que llena el conversor antes de compilar, y no sólo
    # el de variables: son globales de `eventos`, así que con uno solo las
    # páginas que compilan dependían de qué otra prueba había corrido antes en
    # el mismo proceso, y con xdist eso es el reparto.
    for indexar in (eventos.indexar_variables, eventos.indexar_animaciones,
                    eventos.indexar_comunes, eventos.indexar_audio_de_batalla,
                    eventos.indexar_terminos, eventos.indexar_actores,
                    eventos.indexar_habilidades):
        indexar(GAME_DIR)
    for nombre in sorted(os.listdir(GAME_DIR)):
        if not (nombre.startswith("Map") and nombre.endswith(".lmu")):
            continue
        game_map = lcf.Map(os.path.join(GAME_DIR, nombre))
        del_mapa = eventos.Eventos(game_map)
        for ev in game_map.events:
            for numero, page in enumerate(ev.pages):
                if page.trigger not in eventos.TRIGGERS \
                        or not eventos.puede_dispararse(page):
                    continue
                codigo = eventos.compilar_pagina(
                    page, lambda m: 0, eventos.Mensajes(),
                    del_mapa.para(ev.id), eventos.Temas(), eventos.Graficos(),
                    eventos.Imagenes(GAME_DIR))
                if codigo:
                    yield nombre, ev.id, numero, codigo


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


@pytest.mark.skipif(not os.path.isdir(GAME_DIR),
                    reason="hace falta el juego original en GAME_DIR")
def test_los_largos_de_opcode_cuadran_en_todo_el_juego():
    cuantas = 0
    for nombre, evento, numero, codigo in paginas_del_juego():
        cuantas += 1
        i = 0
        while i < len(codigo):
            i += eventos.opcode_size(codigo, i)
        assert i == len(codigo), (
            "%s evento %d página %d: el recorrido por OPCODE_SIZE termina "
            "en %d y la página mide %d" % (nombre, evento, numero, i,
                                           len(codigo)))
    # Que no pase por vacío: si `paginas_del_juego` dejara de devolver nada,
    # este test sería verde sin haber mirado ni un byte.
    assert cuantas > 3000
