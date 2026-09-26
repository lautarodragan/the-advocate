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
