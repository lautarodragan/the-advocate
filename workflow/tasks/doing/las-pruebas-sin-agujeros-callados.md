---
name: "Las pruebas sin agujeros callados"
description: "Que falte una golden del recorrido se declare en vez de pasar en verde, y los helpers que se importan de otros test_* se mudan al arnés"
type: test
assignee: Irupé
---

Las dos mejoras de la inspección de Codex
(`docs/research/inspeccion-integral-del-repo.md`) que Hornero marcó como las
que más rinden por lo que cuestan, y con las que taro coincidió el
2026-09-28:

- `Recorrido.foto` no falla si falta la golden (`rom/pruebas/arnes/recorrido.py`,
  `_contra_golden`): a propósito, para poder agregar un hito antes de
  aprobar su imagen, pero así no se distingue "todavía no aprobada" de
  "borrada". Tiene que haber una lista explícita de las pendientes.
- Varias pruebas importan de otras `test_*` (`test_eventos_de_tropa` de
  `test_tropa` y `test_victoria`, `test_recorrido_carrera_golden` de
  `test_recorrido_lashe_golden`, y más): lo compartido se muda a
  `rom/pruebas/arnes/`.

Ninguna golden cambia: si hoy falta alguna, queda en la lista de pendientes.

## Lo hecho

### 1. Que falte una golden del recorrido se declare

Medido el 2026-09-29 con `just pruebas` sobre `74fe48d5` —867 casos en
verde—: las jugadas sacaron 135 fotos y sólo 8 tenían golden, las de
`apertura/` y `talan/`. Las otras 127 están en
`rom/pruebas/golden/playthrough/pendientes.txt`, agrupadas por la prueba que
las saca y con su porqué: las de los recorridos de Lashe City en adelante
"no están bendecidas: son para que taro las mire", según el docstring de
cada una, y las 14 de `test_mapa_de_debug.py` son sin golden **a
propósito** —la que cuenta es la de la tanda—, así que ésas quizás no sean
pendientes sino permanentes: es de taro decidirlo. Huérfanas no había
ninguna.

Tres redes, las tres probadas en rojo a mano y revertidas:

* `Recorrido.foto`: una foto sin golden falla si no está en la lista, y una
  que está en la lista y tiene golden también (sacando `talan/03`, agregando
  una foto a `lashe-pad`, y anotando `apertura/02`);
* `Recorrido.verificar_el_tramo`, que llama un fixture autouse del conftest
  al terminar una prueba que pasó: cada golden y cada renglón del tramo tiene
  que haber sido una foto (con una golden `apertura/03-fantasma.png` y un
  renglón `vipers/99-no-existe.png`);
* `herramientas/test_goldens_del_recorrido.py`, sin emular: cada tramo con
  goldens o pendientes lo nombra alguna prueba (con una carpeta
  `tramo-borrado/`).
