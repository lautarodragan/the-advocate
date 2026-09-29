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

# La raíz del juego: donde está su archivo de proyecto.
ABL = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

proyecto.fijar(ABL)
