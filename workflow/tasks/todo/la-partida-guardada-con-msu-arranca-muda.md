---
name: "La partida guardada con MSU-1 arranca muda"
description: "Guardar mientras suena una pista del MSU-1 guarda music_apagada en 1, y al cargar la partida no suena nada"
type: bug
---

Visto leyendo el código el 2026-09-26, al arreglar "la pista del título sigue
al empezar"; no se corrió. La partida guarda `music_apagada` y `tema_actual`
(`partida_tabla`, en `rom/src/banco1.s`), y con una pista del MSU-1 sonando
`music_apagada` vale 1 porque el SPC700 está callado a propósito. Al cargar,
`music_boot_ya` (`rom/src/musica.s`) ve `music_apagada` y toma el camino
callado: la partida arranca muda hasta el próximo `PlayBGM` o el tema propio
de un mapa. Antes del arreglo de la pista del título seguía sonando la pista
del título, que tampoco era la que correspondía.

Es la misma pregunta que ya contestan `mapa_tema_callar` y `op_battle`
—"¿está sonando?" es `MSU_SUENA` o `music_apagada` en cero—, y se la puede
contestar al guardar o al cargar. Cobrarlo con una prueba con `msu=True`
(`pruebas/abl/test_msu.py`), guardando en un mapa con tema de pista.
