"""Dónde están las cosas de A Blurred Line, para sus pruebas.

Las pruebas son del juego y saben dónde están por su propia ubicación: la
raíz del juego es la carpeta de arriba de `pruebas/`. Las herramientas, en
cambio, encuentran el proyecto buscando su archivo desde el directorio
actual; importar esto les dice cuál es, así una prueba corre igual desde
cualquier directorio.

Se importa antes que nada que lea el archivo de proyecto al importarse
—`cartuchos` lo hace—: `conftest.py` y `video.py` lo importan primero.
"""

import os

from comun import proyecto

# `pruebas/`, y la raíz del juego arriba: donde está su archivo de proyecto.
PRUEBAS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ABL = os.path.dirname(PRUEBAS)

proyecto.fijar(ABL)

# Lo que es sólo de las pruebas, y no lo lee ninguna herramienta: por eso no
# está en el archivo de proyecto. Los casos sí, porque los lee
# `rm2k-snes-cartridges`: son `cartuchos.CASOS`.
#
# Las capturas congeladas: `tanda/`, `playthrough/`…
GOLDENS = os.path.join(PRUEBAS, "golden")
# Lo que dejan las pruebas para mirar: no se versiona.
SNAPSHOTS = os.path.join(PRUEBAS, "snapshots")
