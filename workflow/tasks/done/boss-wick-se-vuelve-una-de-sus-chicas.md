---
name: "Boss Wick se vuelve una de sus chicas"
description: "Al volver de los vidcasts, Boss Wick cambia su gráfico al de una de sus chicas; taro cree que anduvo bien en algún momento y después se rompió"
type: bug
agents: [Hurón, Tijereta]
assignee: taro
---

De taro, el 2026-10-05: "boss wick cambia su gráfico a una de sus chicas al
volver de los vidcasts. creo que eso anduvo bien en algún momento, y luego
se rompió". De la misma familia que el tanque de Dalia y las compuertas de
los misiles: un evento que termina con el gráfico de otro. Si es una
regresión, se bisecta: candidatos de los últimos días, la caché de ranuras
(Yaguareté), las poses compartidas del 108, los que giran (Cotorra).

# Lo medido (Tijereta, 2026-10-05)

Base: ABL `c988101`, herramientas `d0e2e16c`.

**Se reproduce** en el 40 con el 156 y el 160 prendidos, sin pasar por los
vidcasts: el evento 3 —`RightGirl/BossWick`, que con el 160 pasa a
`People7` 2, Wick— se dibuja con `Chara3` 7, la chica de su página 1,
desde que se llega, y gira con ella cuando la escena lo hace girar.

**La causa.** Al evento 3 lo gira una ruta de la escena (el evento 7), así
que es de los que caminan: su fila lleva las doce poses de **un** gráfico,
el de la página activa al cargar o el de la primera que dibuja algo, y
caminar gana sobre el gráfico de la página
(`divergencias/un-evento-que-camina-no-cambia-de-grafico.md`, en las
herramientas). Con el 160 la página trae a Wick y la fila se queda con la
chica. (Los eventos 1 y 2 con el 160 dibujan `BLPeople` 3, un hueco de la
hoja: en RM2k no se ven, y en la ROM tampoco.)

# La bisección

No es de los sospechosos de estos días: con las herramientas del
2026-10-02 (817037ee) y ABL `bdd0d83` ya estaba igual. Con las del
2026-09-27 (062ea4fd), cuando el 40 entró al cartucho, **se veía a Wick,
pero en la celda de al lado**: era el evento 1, Wick en su página 1, que con
el 160 dibuja el hueco, y la ROM lo dejaba con su gráfico. Desde `f0e0dc2e`
(2026-09-30, los que entran al auditorio) un hueco cuenta como "no dibuja",
el evento 1 se esconde como en RM2k, y quedó a la vista la chica del 3. Lo
que andaba era un error tapando otro.

# El arreglo

En las herramientas, rama `worktree-agent-ac0c3db5dd60db962`: el +30 de la
página lleva, también para los eventos que caminan, la entrada de su
gráfico en el banco de poses, y el +31 su paleta; al cambiar de página la
fila toma ese banco y esa paleta y sube la pose de la página
(`walker_graphic`). Ya no gana caminar: la divergencia se borró.

Comparado con el original con Wine (copia que arranca en el 40 con la
página del 160 sin condición): Wick en la celda 18, girando; la ROM ahora
igual. Capturas en `/shared/capturas/2026-10-05-compuertas-y-wick/`.

La prueba es `rpgmaker/test_grafico_de_pagina.py`: la silueta del evento 3
en la VRAM contra `People7` 2. Roja con las herramientas de main, verde con
las de la rama.

**Lo que no cubre la tanda**: los otros eventos del juego que caminan y
cambian de gráfico con la página, que el arreglo también cambia y ninguna
golden mira —el compañero del Sector 35 (37, evento 17: Arden, Saldra o
AG7), el 64, el 105 y el 114—; y volver de una pelea o de una imagen grande
con uno de ésos sin lugar de ruta (lo cubre un refresco de páginas en
`npc_poses_forget`, que nada ejecuta).

**Al mergear**: instalar `cartridge`, `convert`, `mapdata` y `wally`.
