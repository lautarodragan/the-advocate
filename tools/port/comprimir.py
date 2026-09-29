"""LZ2, the binary that compresses what the ROM decompresses when loading a map.

The format is Nintendo's LC_LZ2, and taro chose it on 2026-09-26 with what
was measured in `workflow/tasks/*/la-compresion-de-mapas-y-graficos.md`: it
stays within 20% of zlib on the tiles and within 10 KB on the grids, and its
repeat with an absolute address into the output is what an `mvn` does in one
go. The decompressor is `lz2_descomprimir`, in `tools/runtime/descomprimir.s`.

The compressor is a separate project, `tools/lz2/`, in Rust and in English,
by the rule in AGENTS.md: it does not need to know anything about this game.
And in Rust rather than here because it is an optimal parser —the shortest
encoding the format allows, with a suffix array— and in Python it would take
minutes per build. It is used from the PATH, like `voodoo` and `gunter`: it
is installed with `just herramientas` and no script calls `cargo`.

The reference it is tested against is a different one, on purpose: `lz2.py`
in `rom/pruebas/arnes/`, written separately and without looking at the
binary.
"""

import os
import shutil
import subprocess
import tempfile

FALTA = """`lz2` is missing, the compressor of the tiles and the grids.

It is a Rust binary that lives in `tools/lz2/` and is installed as a system
tool:

    just -f tools/justfile herramientas"""

# The longest a stream can expand to: the repeat names the output position
# with sixteen bits. It is the format's, not ours.
SALIDA_MAX = 0x10000


def binario():
    """The path of the `lz2` on the PATH. Exits with the message if it is
    not there."""
    ruta = shutil.which("lz2")
    if ruta is None:
        raise SystemExit(FALTA)
    return ruta


def comprimir_varios(bloques):
    """Each block compressed, in the same order. A single process for all of
    them: there are hundreds per cartridge and launching one per block
    shows."""
    bloques = [bytes(b) for b in bloques]
    for b in bloques:
        if len(b) > SALIDA_MAX:
            raise SystemExit("a block of %d bytes does not fit in an LZ2 stream: "
                             "the limit is %d" % (len(b), SALIDA_MAX))
    if not bloques:
        return []
    with tempfile.TemporaryDirectory(prefix="lz2-") as d:
        args = [binario(), "compress", "--no-increasing"]
        for k, b in enumerate(bloques):
            entrada = os.path.join(d, "%d.bin" % k)
            with open(entrada, "wb") as f:
                f.write(b)
            args += [entrada, entrada + ".lz2"]
        hecho = subprocess.run(args, capture_output=True, text=True)
        if hecho.returncode:
            raise SystemExit("lz2 exited with %d: %s"
                             % (hecho.returncode, hecho.stderr.strip()))
        salida = []
        for k in range(len(bloques)):
            with open(os.path.join(d, "%d.bin.lz2" % k), "rb") as f:
                flujo = f.read()
            falta = lo_que_la_rom_no_lee(flujo)
            if falta:
                raise SystemExit("lz2 emitted %s, which `lz2_descomprimir` does not read"
                                 % falta)
            salida.append(flujo)
        return salida


def comprimir(bloque):
    return comprimir_varios([bloque])[0]


def recorrer(flujo):
    """The commands of a stream, as (command, length). Reads only the
    headers."""
    i = 0
    while flujo[i] != 0xFF:
        encabezado = flujo[i]
        if encabezado >> 5 == 7:
            comando = (encabezado >> 2) & 7
            largo = ((encabezado & 3) << 8 | flujo[i + 1]) + 1
            i += 2
        else:
            comando, largo = encabezado >> 5, (encabezado & 31) + 1
            i += 1
        i += {0: largo, 1: 1, 2: 2, 3: 1, 4: 2}[comando]
        yield comando, largo


def comandos(flujo):
    """How many commands a stream has: what it costs to decompress it
    depends on this and on how many bytes come out."""
    return sum(1 for _ in recorrer(flujo))


# The two commands the format has and `lz2_descomprimir` does not read, on
# purpose: no block used them, and a path no test runs is the one that has
# bitten this repo the most times. The compressor does not emit the
# increasing one (3) with `--no-increasing`, and it costs almost nothing; it
# never picks the one-byte word, because a literal of one costs less. If
# either shows up, it stops here and not on the console.
def lo_que_la_rom_no_lee(flujo):
    for comando, largo in recorrer(flujo):
        if comando == 3:
            return "an increasing fill"
        if comando == 2 and largo == 1:
            return "a one-byte word"
    return None
