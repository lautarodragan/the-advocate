---
name: "El release lleva MSU-1 siempre"
description: "Las pistas van al lado de release/abl.sfc, y es el arnés el que decide si el core las ve"
---

taro decidió el 2026-09-25 que **el release lleva MSU-1 siempre**:
`rom/build/release-msu/` desaparece, y `just build release` deja al lado de
`rom/build/release/abl.sfc` el `abl.msu` y los `abl-N.pcm`. No puede haber dos
maneras de tener la ROM con pistas.

Lo que obligó a separarlos en `5a22c81` (2026-09-24): el emulador busca el
`.msu` al lado del `.sfc`, así que con las pistas en `release/` la tanda corría
con el SPC700 callado o no según si alguien había corrido `just msu`. Ahora lo
controla el arnés: `retro.Consola` le da al core un directorio propio sin
pistas, salvo que se le pida el MSU-1.

# Hecho

- `retro.Consola(msu=False)`: por omisión el core recibe una copia del `.sfc`
  en un `tempfile.mkdtemp` propio, que es también su directorio de sistema y
  partidas; se borra con `weakref.finalize`. `msu=True` carga el path real.
  Copia y no symlink: medido que snes9x y bsnes no siguen un symlink hasta el
  directorio de verdad —mesen-s no se pudo medir, su audio no repite—, pero
  la copia no depende de eso y sale gratis: los bytes ya están leídos.
- `retro.Consola.tasa()`: snes9x entrega 44100 muestras por segundo con MSU-1 y
  32040 sin él. `video.py` la pregunta en vez de la constante que tenía.
- `video.py` graba con el MSU-1 por omisión —es para escuchar la ROM como se
  juega— y `--sin-msu` para el SPC700 solo. `Partida(msu=...)` lo pasa.
- `cartuchos.py release` corre `msu.armar` siempre, aunque la ROM esté al día.
  La receta `msu` se fue: una sola manera de tener la ROM con pistas.
- `msu.py` escribe cada `.pcm` al lado y lo reemplaza, en vez de truncarlo.
- `pruebas/abl/test_msu.py`: con las pistas al lado, `tanda.encender` da el
  mismo audio que una copia sin pistas, y con `msu=True` da otro.

# Medido

- Antes del cambio, 1200 cuadros del título: snes9x y bsnes dan otro audio con
  las pistas al lado que sin ellas. Después, por omisión, el mismo que sin
  ellas, y con `msu=True` el mismo que antes con ellas. mesen-s también cambia
  con `msu=True`, pero su audio no repite entre corridas.
- `release/abl.sfc` igual byte por byte que antes del cambio, y las 22 pistas
  re-renderizadas iguales a las de `release-msu/`.
