"""Lo que comparten las pruebas del MSU-1: dónde están las pistas.

`pistas_de` vivía en `test_msu.py` hasta el 2026-09-29, y de ahí lo importaba
`test_msu_efectos.py`.
"""

import glob


def pistas_de(base):
    """{número: ruta} de los `<base>-N.pcm` que hay al lado de la ROM."""
    return {int(ruta[len(base) + 1:-len(".pcm")]): ruta
            for ruta in glob.glob(glob.escape(base) + "-*.pcm")
            if ruta[len(base) + 1:-len(".pcm")].isdigit()}
