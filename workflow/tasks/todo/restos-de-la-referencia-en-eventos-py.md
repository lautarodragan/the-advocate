---
name: "Restos de la referencia en eventos.py"
description: "Comentarios que se apoyan en la referencia de Python, y constantes sin uso"
type: refactor
---

La referencia de Python se fue el 2026-09-16, y el 2026-09-25 se sacó lo que
quedaba de ella en `eventos.Estado`. Quedaron, vistos y sin tocar para no
hacer una barrida general, en `tools/port/eventos.py`:

* el comentario de `SENO_SACUDIDA`: "la ROM y la referencia coinciden exacto";
* el de `ChangePBG`: "la referencia tampoco lo modela y los dos lados quedan
  iguales";
* siete constantes sin uso en código: `ANIM_NO_CONTINUA`, `LLUVIA_DX`,
  `LLUVIA_DY`, `PAN_FIJAR`, `PAN_SOLTAR`, `SWITCH_INDIRECTO` y `SWITCH_OFF`.
  Pueden estar como documentación del formato de RM2k: `git blame` antes de
  borrarlas.

`grep -n -i 'referencia\|los dos lados' tools/port/*.py` da el resto de
candidatos: separar los que hablan de la referencia de Python de los que
hablan de otra cosa (los dibujos de `tools/port/` que comparan las pruebas
`_dibujo` también se llaman así a veces).
