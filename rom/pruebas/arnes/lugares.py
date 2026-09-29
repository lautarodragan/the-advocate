"""Dónde están las cosas de A Blurred Line, para sus pruebas.

Las pruebas son del juego y saben dónde están por su propia ubicación: la
raíz del juego es la carpeta de arriba de `pruebas/`. Las herramientas, en
cambio, encuentran el proyecto buscando su archivo desde el directorio
actual; importar esto les dice cuál es, así una prueba corre igual desde
cualquier directorio.

Y lo de la máquina —dónde está el juego original, el RTP, el SoundFont—,
que las herramientas reciben por flags: acá sale de las mismas variables
que traduce `justfile` —`ABL_GAME_DIR` y las demás—, que él exporta con los
valores de esta máquina. Sin ellas no hay de dónde sacarlo, así que una
prueba corrida sin `just` corta diciendo cuál falta.

Se importa antes que nada que lea el archivo de proyecto al importarse
—`cartuchos` lo hace—: `conftest.py` y `video.py` lo importan primero.
"""

import os

from common import environment
from common import project

# `pruebas/`, y la raíz del juego arriba: donde está su archivo de proyecto.
PRUEBAS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ABL = os.path.dirname(PRUEBAS)

project.use(ABL)

# Lo que es sólo de las pruebas, y no lo lee ninguna herramienta: por eso no
# está en el archivo de proyecto. Los casos sí, porque los lee
# `rm2k-snes-cartridges`: son `cartuchos.CASOS`.
#
# Las capturas congeladas: `tanda/`, `playthrough/`…
GOLDENS = os.path.join(PRUEBAS, "golden")
# Lo que dejan las pruebas para mirar: no se versiona.
SNAPSHOTS = os.path.join(PRUEBAS, "snapshots")


def _de_la_maquina(variable):
    valor = os.environ.get(variable)
    if not valor:
        raise SystemExit(
            "falta %s: dice dónde está algo en esta máquina, y la pone "
            "`justfile` con su valor. Las pruebas se corren con `just "
            "pruebas`, o con la variable puesta." % variable)
    return valor


# `rpgmaker.resources.GAME_DIR` y los demás, que las pruebas leen igual que el
# conversor. El caché y los cartuchos de prueba tienen su lugar en el
# `build` del proyecto; las variables sólo los mueven.
environment.configure(game_dir=_de_la_maquina("ABL_GAME_DIR"),
                      rtp_dir=_de_la_maquina("ABL_RTP_DIR"),
                      soundfont=_de_la_maquina("ABL_SOUNDFONT"),
                      cache=os.environ.get("ABL_CACHE") or None,
                      test_cartridges=os.environ.get("CARTUCHOS") or None)
