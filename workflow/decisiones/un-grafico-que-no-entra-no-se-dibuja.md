> **Reemplazada en parte**, anotado el 2026-09-29 (Guayabo, al clasificar
> las decisiones por repo): desde el 2026-09-08 (`ac8f356b`) `fits`, en
> `tools/port/sprites.py`, les **presta** paleta a estos gráficos, igual
> que a los eventos (`se-dibujan-todos-los-eventos.md`). Un gráfico sólo queda
> sin dibujar si todas las paletas son de un líder, que es lo que dice
> `la-orden-34-sobre-el-heroe.md`. Lo que sigue valiendo es lo de abajo sobre
> los tres mapas: **no se les abre una paleta nueva**.

# Qué

**Un gráfico que no entra en las ocho paletas de sprite no se dibuja.** Lo
decide el conversor, con una sola función.

# Por qué

Vale para los eventos dibujados con un tile del chipset y, desde la orden 34,
para los gráficos a los que una ruta cambia: ahí la orden esconde al evento en
vez de cambiarlo.

**Forzarlos rompía tres mapas** —el 108, el 114 y el 207—.
