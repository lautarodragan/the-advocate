---
name: "Más voces para los efectos"
description: "Con MSU-1 las ocho voces del DSP quedan libres para efectos; sin él, evaluar; y los efectos de cola larga, recortados por parche"
type: feature
---

Pedido de taro el 2026-09-26, para después de la tanda de hoy (no ahora).
Hoy los efectos tienen dos voces (la 6 y la 7). Al verificar el mapa 3 se vio
un momento de la escena de `evilrhys` con tres efectos a la vez: uno no
suena.

1. **Con MSU-1, todas las voces para efectos.** Cuando el tema suena por la
   pista, el SPC700 no toca música y las ocho voces están libres. Que los
   efectos puedan usarlas (las muestras de música ya no se suben con MSU-1:
   `done/con-msu-1-no-se-suben-las-muestras-del-tema.md`, o `testing/`).
2. **Sin MSU-1, evaluarlo**: una tercera voz se le saca a la música, y el
   reparto de voces (`la-calidad-de-la-musica.md`, paso 5) pierde polifonía.
   Medir cuántas veces pasa en el juego que suenen tres efectos a la vez y
   cuánto le cuesta a la música.
3. **Tres efectos a la vez es raro**: si los casos se deben a un efecto con
   una cola (fade out) larga, lo más simple es **editar ese efecto** —
   recortarle la cola— con el sistema de parches que ya existe
   (`parches/manual/`, ver `parches/README.md`), en vez de agregar voces.
