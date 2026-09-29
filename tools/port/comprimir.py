"""LZ2, el binario que comprime lo que la ROM descomprime al cargar un mapa.

El formato es el LC_LZ2 de Nintendo, y lo decidió taro el 2026-09-26 con lo
medido en `workflow/tasks/*/la-compresion-de-mapas-y-graficos.md`: queda a un
20% de zlib en los tiles y a 10 KB en las grillas, y su repetición con
dirección absoluta en la salida es lo que un `mvn` hace de un saque. El
descompresor es `lz2_descomprimir`, en `tools/runtime/descomprimir.s`.

El compresor es un proyecto aparte, `tools/lz2/`, en Rust y en inglés, por la
regla de AGENTS.md: no necesita saber nada de este juego. Y en Rust y no acá
porque es un parser óptimo —la codificación más corta que admite el formato,
con un arreglo de sufijos— y en Python tardaría minutos por build. Se consume
desde el PATH, como `voodoo` y `gunter`: se instala con `just herramientas` y
ningún script llama a `cargo`.

La referencia contra la que se prueba es otra, a propósito: `lz2.py` en
`rom/pruebas/arnes/`, escrita aparte y sin mirar el binario.
"""

import os
import shutil
import subprocess
import tempfile

FALTA = """falta `lz2`, el compresor de los tiles y las grillas.

Es un binario de Rust que vive en `tools/lz2/` y se instala como herramienta
del sistema:

    just -f tools/justfile herramientas"""

# Lo más largo que puede salir de un flujo: la repetición nombra la posición
# de la salida con dieciséis bits. Es del formato, no nuestro.
SALIDA_MAX = 0x10000


def binario():
    """La ruta del `lz2` del PATH. Sale con el mensaje si no está."""
    ruta = shutil.which("lz2")
    if ruta is None:
        raise SystemExit(FALTA)
    return ruta


def comprimir_varios(bloques):
    """Cada bloque comprimido, en el mismo orden. Un solo proceso para todos:
    son cientos por cartucho y lanzar uno por bloque se nota."""
    bloques = [bytes(b) for b in bloques]
    for b in bloques:
        if len(b) > SALIDA_MAX:
            raise SystemExit("un bloque de %d bytes no entra en un flujo LZ2: "
                             "el tope es %d" % (len(b), SALIDA_MAX))
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
            raise SystemExit("lz2 salió con %d: %s"
                             % (hecho.returncode, hecho.stderr.strip()))
        salida = []
        for k in range(len(bloques)):
            with open(os.path.join(d, "%d.bin.lz2" % k), "rb") as f:
                flujo = f.read()
            falta = lo_que_la_rom_no_lee(flujo)
            if falta:
                raise SystemExit("lz2 emitió %s, que `lz2_descomprimir` no lee"
                                 % falta)
            salida.append(flujo)
        return salida


def comprimir(bloque):
    return comprimir_varios([bloque])[0]


def recorrer(flujo):
    """Los comandos de un flujo, como (comando, largo). Lee sólo los
    encabezados."""
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
    """Cuántos comandos tiene un flujo: lo que cuesta descomprimirlo depende
    de esto y de cuántos bytes salen."""
    return sum(1 for _ in recorrer(flujo))


# Los dos comandos que el formato tiene y `lz2_descomprimir` no lee, a
# propósito: ningún bloque los usaba y un camino que ninguna prueba ejecuta es
# el que más veces mordió en este repo. El creciente (3) no lo emite el
# compresor con `--no-increasing`, y casi no cuesta; la palabra de un solo
# byte no la elige nunca, porque un literal de uno cuesta menos. Si alguno
# aparece, se corta acá y no en la consola.
def lo_que_la_rom_no_lee(flujo):
    for comando, largo in recorrer(flujo):
        if comando == 3:
            return "un relleno creciente"
        if comando == 2 and largo == 1:
            return "una palabra de un byte"
    return None
