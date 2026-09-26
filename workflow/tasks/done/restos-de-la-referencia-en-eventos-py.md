---
name: "Restos de la referencia"
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

**Y en `rom/src/`**: `grep -n -i referencia rom/src/*.s` da unas cincuenta
líneas. Una la vio taro depurando en Mesen2 el 2026-09-25, en `eventos_tick`
(`rom/src/cargar_mapa.s`, después de `espera_boton`): "sería un cuadro de
diferencia contra la referencia". Mismo criterio: si el porqué sigue valiendo
sin la referencia, se reescribe; si sólo existía por ella, se va.

## Cómo quedó (2026-09-26)

Se fue `LLUVIA_DX, LLUVIA_DY`, la única de las siete que sólo leía el modelo
borrado; las otras seis son miembros de enums de liblcf en la misma tupla que
sus hermanos usados, y se quedan. Los comentarios, en un commit por archivo o
por zona: el `git log` de esta tarea dice cuáles se reescribieron y cuáles se
fueron.

Lo que quedó mencionándola a propósito, o sin tocar:

* el comentario largo de `KeyInputProc` sin espera, en `eventos.py`, y su
  `NoSePuede`: la medición que cita era contra la referencia, y reescribirlo
  pide volver a medir con `TECLA_SIN_ESPERA=1` contra la golden de `heroe 52`;
* la VRAM de las animaciones en `snes_convert.py` corta el build en vez de
  avisar como las paletas, y la única razón era la referencia: el comentario
  lo dice, y cambiarlo es un cambio de comportamiento;
* `titulo.render` y `ventana.pagina` no tienen llamadores y sus comentarios
  describen la comparación de la referencia: lo que corresponde es borrarlas
  (la primera ya está en `wishlist/inventario-de-imagenes-en-python.md`);
* el "topado en 999 como en la referencia" de `batalla.s`: no se sabe si es la
  de Python o el dibujo de `escena`.
