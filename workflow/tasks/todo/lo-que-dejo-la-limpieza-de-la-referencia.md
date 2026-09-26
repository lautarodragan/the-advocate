---
name: "Lo que dejó la limpieza de la referencia"
description: "Cuatro cosas que la limpieza de los restos de la referencia dejó afuera a propósito, porque no eran comentarios"
type: refactor
---

La limpieza del 2026-09-26 (`done/restos-de-la-referencia-en-eventos-py.md`)
sacó los comentarios que se apoyaban en la referencia de Python y dejó
afuera, a propósito, estas cuatro cosas: cada una pide algo más que
reescribir un comentario.

1. **`KeyInputProc` sin espera** (`tools/port/eventos.py`, el comentario
   largo y el mensaje de `NoSePuede`): cita una medición (55%) hecha contra
   la referencia. Hay que volver a medir con `TECLA_SIN_ESPERA=1` contra la
   ROM y RM2k antes de reescribirlo, o decidir si el comando sin espera se
   acepta (ver también la carrera, que lo pide: `RaceController2`).
2. **Las animaciones que no entran en la VRAM cortan el build**
   (`tools/port/snes_convert.py`), en vez de avisar y seguir como con las
   paletas. La única razón era la referencia. Decidir si pasa a aviso (y qué
   se dibuja entonces) o si cortar sigue siendo lo correcto, y dejar el porqué.
3. **`titulo.render` y `ventana.pagina` no tienen llamadores** y describen la
   comparación vieja: borrarlas (`titulo.render` ya está nombrada en
   `wishlist/inventario-de-imagenes-en-python.md`). `git blame` y `git grep`
   antes.
4. **"Topado en 999 como en la referencia"** (`rom/src/batalla.s`): no se sabe
   si habla de la referencia de Python o del dibujo de `escena`. Averiguar con
   `git log -S` y reescribir contra RM2k (¿RM2k topa el daño en 999?).
