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
