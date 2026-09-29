# El `justfile` del repo, no de ningún proyecto: deja correr las recetas de
# A Blurred Line desde la raíz —`just cartuchos`, `just pruebas`, `just
# entregar`— como antes de que se mudaran a `rom/`. `just` busca el
# `justfile` hacia arriba y no hacia abajo, así que sin éste habría que
# pararse en `rom/`.
#
# No lleva recetas, y no tiene que llevarlas: las de ABL están en
# `rom/justfile` y las de las herramientas en `tools/justfile`, y ninguno de
# los dos sabe que éste existe. Cuando el repo se parta, éste se borra.
#
# `working-directory` es lo que hace que las recetas importadas corran
# paradas en `rom/`, igual que si se llamaran desde ahí: sin eso correrían en
# la raíz y sus rutas relativas no encontrarían nada.
set working-directory := "rom"

import "rom/justfile"
