---
name: "La pista del título sigue al empezar"
description: "Con MSU-1, la pista del título sigue sonando al empezar la partida si el primer mapa arranca callado"
type: bug
---

Encontrado el 2026-09-26 por el agente de "con MSU-1 no se suben las muestras
del tema", sin arreglar. Con MSU-1, la pista del título
(`Fantasia_Of_The_Wind`) sigue sonando al empezar la partida: `music_boot`
(`rom/src/musica.s`), cuando el mapa arranca callado, calla el SPC700 pero no
llama a `msu_parar`. La pista sigue hasta el primer `PlayBGM`, y la pelea la
anota como el tema a reponer al salir. El arreglo parece ser llamar a
`msu_parar` en ese camino. Cobrarlo con una prueba con `msu=True`
(`pruebas/abl/test_msu.py`).

## Hecho, el 2026-09-26

`music_boot_ya` llama a `msu_parar` en su camino callado. Lo cobra
`test_con_msu_la_pista_del_titulo_no_sigue_en_la_partida`
(`pruebas/abl/test_msu.py`): con MSU-1, mira que el título toque su pista, elige
"Begin the Story" y pide que 120 cuadros después la pista del título ya no
suene. Sin el arreglo da rojo: `MSU_SUENA` sigue en 1 con `tema_actual` en el
del título.

Lo que queda para taro: con las pistas al lado, empezar una partida y oír que
`Fantasia_Of_The_Wind` se corta al entrar al pasillo.

Visto de paso y no arreglado: una partida guardada **mientras suena una pista
del MSU-1** guarda `music_apagada` en 1 —el SPC700 está callado a
propósito—, así que al cargarla `music_boot` toma el camino callado y la
partida arranca muda hasta el próximo `PlayBGM` (antes de este arreglo, seguía
la pista del título). Anotado en
`workflow/tasks/todo/la-partida-guardada-con-msu-arranca-muda.md`.
