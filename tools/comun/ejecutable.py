"""Lo que hace un script de `tools/` al arrancar desde el PATH.

`just herramientas` instala los scripts que se ejecutan como symlinks en el
mismo `bin/` que los binarios de Rust, y el `justfile` los llama por su
nombre. Un symlink apunta a **un** checkout —el último desde el que se corrió
`just herramientas`—, y cada worktree de un sub-agente es otro checkout con
su propia copia de `tools/` y de `rom/src/`. Si el script se quedara con el
checkout del symlink, `just cartuchos` en un worktree armaría las ROMs de
otro árbol, con el conversor de otro árbol, y la tanda del worktree se
negaría a correr contra las suyas, que seguirían viejas.

Así que el checkout del symlink es sólo el de último recurso: si el
directorio actual está adentro de un checkout que trae su propia copia del
mismo script, se corre ésa. Es lo que hace cualquier herramienta que prefiere
la versión del proyecto a la instalada.
"""

import os
import sys


def usar_el_del_checkout(archivo):
    """Si el directorio actual está adentro de otro checkout con este mismo
    script, lo reemplaza por el de ahí con `execv` y no vuelve. Si no, no
    hace nada.

    `archivo` es el `__file__` del script. Se busca hacia arriba desde el
    directorio actual y vale el primero que aparece, que es el checkout más
    adentro: los worktrees viven dentro del checkout principal."""
    real = os.path.realpath(archivo)
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(real)))
    relativo = os.path.relpath(real, raiz)
    directorio = os.getcwd()
    while True:
        candidato = os.path.join(directorio, relativo)
        if os.path.isfile(candidato):
            candidato = os.path.realpath(candidato)
            if candidato != real:
                os.execv(sys.executable,
                         [sys.executable, candidato] + sys.argv[1:])
            return
        padre = os.path.dirname(directorio)
        if padre == directorio:
            return
        directorio = padre
