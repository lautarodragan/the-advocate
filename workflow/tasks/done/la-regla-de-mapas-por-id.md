---
name: "La regla de mapas por id"
description: "release lleva los mapas de id menor a 65, menos una exclusión corta, más los agregados: deja de ser una lista escrita a mano"
type: refactor
---

# Qué

La segunda mitad del hito 4 de `todo/la-carrera-y-lo-que-sigue.md`. La
primera —los dos errores latentes del conversor— ya está en `main`
(`9d6c0d3`).

`release` deja de llevar la lista escrita a mano de `MAPAS_DEL_JUEGO` en
`tools/ensamblado/cartuchos.py` y pasa a llevar **los mapas con id menor a
X, sin los excluidos, más los agregados**. Decidido por taro: X = 65, la
exclusión 15, 22, 46, 55 y 58 —chica, a pedido suyo— y el 164 como agregado.
Los mapas de prueba y `test-special` quedan como estaban.

**No mueve la ROM**: la lista que sale de la regla tiene que ser la misma, en
el mismo orden, que la escrita a mano del hito 1.

# Cómo

## "Los mapas" son los del árbol, no todos los ids

Del 1 al 64 faltan en la lista escrita a mano, además de los cinco
excluidos, el 24, el 25, el 27, el 31 y el 35: son **áreas** del árbol
(`RPG_RT.lmt`, tipo 2), nodos sin `.lmu` que sólo le tapan un rectángulo a su
padre para los encuentros. La regla cuenta los de tipo 1, que son los que
tienen mapa: si no, la exclusión tendría diez ids y cinco serían "no es un
mapa".

## Dónde vive cada cosa

Los tres valores —`MENOR_A`, `EXCLUIDOS` y `AGREGADOS`— viven en
`cartuchos.py`, y la regla se expande **ahí**, con el árbol del volcado de
`data/`. Al conversor le sigue llegando la lista explícita en `--mapas`,
como hasta ahora. No hay flag `--exclude-maps`, y es a propósito:

* **Nadie más llama al conversor**: el único que lo invoca es `cartuchos.py`
  (grep de `snes_convert` en `justfile`, `tools/` y `pruebas/`). Un flag le
  daría una segunda manera de recibir los mapas a un programa que ya tiene
  una, para un solo llamador.
* **Los que leen la lista en Python la necesitan sin correr el conversor**:
  `test_horneados.py` (`cartuchos.MAPAS`), `test_parches.py`
  (`MAPAS_DEL_JUEGO`) y `parches.mapas_de_prueba`. Con la regla en el
  conversor habría que expandirla en dos lados.
* **El sello**: el sello del cartucho lleva sus flags, y `data/` no entra en
  la huella. Con la lista expandida en los flags, un cambio en el árbol que
  cambie qué mapas entran deja viejo al cartucho; con `--menores-a 65` en los
  flags, no se enteraría.

Y si algún día hace falta el flag, el nombre en `tools/` va en castellano
(`--excluir-mapas`): la regla de AGENTS.md dice que los flags ingleses son
los de los proyectos aparte.

Un mapa que se sale de la regla —un tutorial de otro capítulo, una
carpeta— va a `EXCLUIDOS` **con su razón al lado**; uno de más allá de
`MENOR_A` que haga falta, a `AGREGADOS`. `test_ensamblar.py` cobra que cada
excluido sea un mapa que la regla metería y cada agregado uno que no: un
número de adorno en cualquiera de las dos listas no dice nada y envejece.

## Comprobación

* La lista que da la regla es la misma tupla, en el mismo orden, que la
  escrita a mano (comparada en Python contra la vieja).
* **Las ROMs, byte por byte**: `just cartuchos` sobre `69e66ed` y sobre el
  cambio —los dos cartuchos se rearmaron, porque `cartuchos.py` entra en la
  huella— y `cmp` de `rom/build/release/abl.sfc`, `abl.msu`,
  `rom/build/tests/special/prueba.sfc` y `prueba.msu` contra las copias de
  antes: iguales los cuatro.
* `just pruebas` sobre el resultado: todas en verde.

No hay nada que taro tenga que jugar: la ROM es la misma.
