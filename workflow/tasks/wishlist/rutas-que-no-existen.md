---
name: "Rutas que no existen"
description: "Una prueba que falle si un .md o un comentario nombra un archivo que ya no está"
type: test
---

# Qué

Una prueba chica que busque rutas del repo entre comillas invertidas —en los
`.md` y en los comentarios del código— y falle si alguna no existe.

# Por qué

El 2026-09-24, después de mover y renombrar varias cosas, quedaron referencias
a rutas que ya no estaban: `juego/`, `pruebas-manuales/capturas-batalla/`, una
explicación de `cartuchos.py` que se había borrado. taro las encontró leyendo,
y lo confundieron. Nada las cazaba.

Se miró la alternativa de un linter de markdown —markdownlint, mdformat,
Prettier— y no ataca esto: revisan la forma, no si lo nombrado existe. Si
algún día molesta la forma, mdformat sólo para los `.md` es lo más barato.

Otro caso, el 2026-09-25: el índice de `README.md` enlaza a una sección
"El MSU-1" que no existe, y el docstring de `tools/audio/msu.py` la cita.
Un ancla de markdown es una ruta más: la prueba debería mirarlas también.

# Lo que no cubre

Las afirmaciones que dejaron de ser ciertas sin nombrar una ruta: ésas salen
de leer.

# Status

Anotada el 2026-09-24 en wishlist: taro no la considera importante.
