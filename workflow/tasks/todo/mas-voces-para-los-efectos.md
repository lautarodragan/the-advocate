---
name: "Más voces para los efectos"
description: "Con MSU-1 las ocho voces del DSP quedan libres para efectos; sin él, evaluar; y los efectos de cola larga, recortados por parche"
type: feature
---

Pedido de taro el 2026-09-26, para después de la tanda de hoy (no ahora).
Hoy los efectos tienen dos voces (la 6 y la 7). Al verificar el mapa 3 se vio
un momento de la escena de `evilrhys` con tres efectos a la vez: uno no
suena.

1. **Con MSU-1, todas las voces para efectos.** Hecho el 2026-09-26, en
   `efectos-de-calidad-con-msu-1.md`: mientras el SPC700 no toca música, los
   efectos tienen también las voces 0 a 5. Lo que queda acá es sin MSU-1.
2. **Sin MSU-1, evaluarlo**: una tercera voz se le saca a la música, y el
   reparto de voces (`la-calidad-de-la-musica.md`, paso 5) pierde polifonía.
   Medir cuántas veces pasa en el juego que suenen tres efectos a la vez y
   cuánto le cuesta a la música.
3. **Tres efectos a la vez es raro**: si los casos se deben a un efecto con
   una cola (fade out) larga, lo más simple es **editar ese efecto** —
   recortarle la cola— con el sistema de parches que ya existe
   (`parches/manual/`, ver `parches/README.md`), en vez de agregar voces.
