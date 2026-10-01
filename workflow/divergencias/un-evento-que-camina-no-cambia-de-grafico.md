# Qué

Un evento que **camina** —tiene un banco de doce poses en el cartucho— y además
**cambia de gráfico** entre sus páginas se queda con un solo gráfico: en la fila
de NPC esas dos cosas se pelean por los mismos bytes, así que **gana caminar**.
En RM2k el gráfico sigue a la página.

Lo que sí sigue a la página es **si se ve**: la ROM copia de la página todo
menos el tile y la paleta cuando la fila camina —`+9` vale `NPC_STILL` o el
banco de sus poses—. Ver `page_graphic` en `tools/runtime/event_pages.s` y
"walking wins" en `tools/rm2k-snes/wally/src/map.rs`.

**Un hueco de la hoja no cuenta como gráfico.** Una página que muestra un
índice del CharSet sin un pixel dibuja en RM2k lo mismo que una sin gráfico,
así que la fila camina con el primer gráfico que tiene pixeles, y esa página
la esconde: ver `pin_walkers`. Hasta el 2026-09-30 le tocaba el hueco si era
el de la primera página, y caminaba sin verse: `WalkIn1` y `WalkIn2` en el
auditorio, el mapa 18, y Arden y Saldra en el 44.

# Medido

Antes de separar las dos cosas, el conversor elegía caminar también para
aparecer, y la fila, que nace escondida cuando al cargar el mapa ninguna página
cumple, no aparecía nunca: el `Bum` y el `Mechanic` de Lashe City, 245 y 191
pixeles contra la referencia. El primero que pidió caminar y cambiar de gráfico
a la vez fue el evento 10 del mapa 8.

# Cómo se ve hoy

El evento camina y aparece bien, con el gráfico fijo. Hacer las dos cosas a la
vez está en `tasks/wishlist/un-evento-que-camina-y-cambia-de-grafico.md`.
