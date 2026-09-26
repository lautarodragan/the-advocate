---
name: "Notas que se sueltan antes de tiempo"
description: "Cuando una nota le roba la voz a otra, el release agendado de la robada suelta a la nueva"
type: bug
---

Visto midiendo el stream de música el 2026-09-25 (ver `la-musica-pesa-789-kb.md`),
sin oírlo todavía. En `tools/audio/snes_music.py` (`build_events`): cuando
una nota le gana la voz a otra, el release que la nota robada tenía agendado
sigue en pie y suelta a la nueva antes de tiempo. **686 notas, 10.308 cuadros**
en los temas de `test-main`; 329 en `escape_newyork`.

Y otro del mismo lugar: una nota cuya muestra no está en el banco igual ocupa
la voz, porque `busy` se anota antes del `continue`.

Conviene arreglarlo **antes o después** del cambio de formato del stream (la
idea 1 de `la-musica-pesa-789-kb.md`), no junto: ese cambio se verifica con que
las escrituras al DSP salgan idénticas, y este arreglo las cambia a propósito.

# Hecho, el 2026-09-25

Los dos, en `build_events`: el release se agenda al final y sólo para las
notas que siguen siendo dueñas de su voz, y la nota sin muestra sale antes de
elegir voz. En los 22 temas del `release` eran 564 notas soltadas antes de
tiempo y 11.024 notas sin muestra ocupando voz; el stream bajó 11,3%. Los
números tema por tema y cómo se midieron, en el punto 1 de
`todo/la-calidad-de-la-musica.md`; lo cobra
`pruebas/herramientas/test_musica_stream.py`.

**Para taro**: está en `testing/` porque se oye —poco: sobre todo el bajo de
`escape_newyork` y el de `cd4`, que ya no se cortan antes—. Las grabaciones,
en `/shared/audio/2026-09-25-pasos-1-y-2/` (las `-1-`).

**taro escuchó las grabaciones y lo dio por bueno el 2026-09-26.**
