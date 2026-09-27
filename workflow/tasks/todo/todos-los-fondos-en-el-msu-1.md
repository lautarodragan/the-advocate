---
name: "Todos los fondos de batalla en el MSU-1"
description: "Cada fondo del juego en el .msu en alta calidad; en la ROM sólo los que entran, y los demás comparten uno de reemplazo en baja calidad"
type: feature
---

De taro, el 2026-09-27, al ver que las peleas del mundo (66) salían en negro
porque el cartucho no lleva sus cinco terrenos:

- **Todos los fondos de batalla del juego van al `.msu`**, en alta calidad,
  estén o no en los mapas del cartucho. Con eso la parte del `.msu` dedicada
  a fondos queda fija: se sabe qué sector exacto ocupa, y no se mueve cuando
  entra un mapa.
- **En la ROM, cada pelea cuyo fondo no entra usa un mismo fondo de
  reemplazo**, uno de los que ya hay, en baja calidad. No negro: negro
  confunde.
- **Con MSU-1, cada pelea muestra su fondo correcto**, aunque no esté en la
  ROM.

Ver `docs/port/msu-datos.md` y `testing/msu-1-los-fondos-por-el-puerto-de-datos.md`
para cómo se leen hoy. Hay que medir cuánto pesan todos los fondos del juego
en el `.msu` y decidir el orden (por id del fondo, así el sector de cada uno
no depende de qué mapas entran).
