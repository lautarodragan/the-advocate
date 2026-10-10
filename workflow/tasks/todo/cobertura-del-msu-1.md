---
name: "Cobertura del MSU-1"
description: "Ninguna prueba corre bsnes ni mesen-s con las pistas al lado, ni cubre just video"
type: test
---

Desde el 2026-09-25 `release` lleva siempre sus pistas de MSU-1 y el arnés se
las esconde al core (`retro.Console(..., msu=False)`, en
`pruebas/arnes/emulator/retro.py`). Lo cobra `pruebas/abl/test_msu.py`, **sólo en
snes9x**. Lo que quedó medido a mano y sin prueba:

* **bsnes y mesen-s con las pistas al lado.** Se midió a mano que bsnes da el
  mismo audio que sin pistas; mesen-s cambia con `msu=True` pero su audio no
  sale igual entre corridas, así que no se compara por igualdad. Una prueba
  para bsnes es barata si `test_cores.py` ya lo levanta; mesen-s necesita otra
  comparación (¿silencio del SPC700?, ¿los registros del MSU-1?).
* **`just video`** (`pruebas/arnes/video.py`). No la corre ninguna prueba. Tiene
  un bug ya arreglado que ninguna red cobraría si vuelve: usaba una tasa fija
  de 32.040 y snes9x pasa a 44.100 con el MSU-1 encendido, así que el sonido
  se corría del video. Una prueba chica que arme unos cuadros con y sin
  `--sin-msu` y compare la duración del audio con la de la imagen alcanza.
