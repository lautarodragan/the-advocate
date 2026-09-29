---
name: "Rust: las pistas de MSU-1 y los techos"
description: "La segunda parte del audio: tools/audio/msu.py y ceilings.py a Rust, siguiendo con fluidsynth y ffmpeg por el PATH, con las pistas byte por byte iguales"
type: refactor
assignee: taro
---

Segunda parte del audio del camino a Rust. Lo decidió Hornero: `msu.py`
(`rm2k-snes-msu`, las pistas PCM de MSU-1) y `ceilings.py`
(`rm2k-snes-volume-ceilings`, la medición de techos) pasan a Rust, dentro
del crate `rm2k-snes-audio` o al lado. Siguen llamando a `fluidsynth` y a
`ffmpeg` por el PATH: otro sintetizador no daría las pistas byte por byte
iguales, y eso es lo que se verifica.

## Cómo quedó

**Dos binarios más del crate `rm2k-snes-audio`**, con los mismos nombres y
los mismos flags: `rm2k-snes-msu` (`src/bin/msu.rs`, la lógica en
`src/tracks.rs`) y `rm2k-snes-volume-ceilings` (`src/bin/volume_ceilings.rs`,
la lógica en `src/ceilings.rs` y la consola de libretro en `src/retro.rs`).
Nadie que los llama cambió: `rm2k-snes-cartridges` corre `rm2k-snes-msu` y
`rom/justfile` corre `rm2k-snes-volume-ceilings` como antes.

Por qué binarios y no subcomandos de `rm2k-snes-audio`:

* **Los nombres**: el que arma los cartuchos y la receta `techos` llaman a
  los ejecutables por nombre, y un subcomando pediría un wrapper o cambiar a
  los que llaman.
* **La clave de las pistas**: lo que en Python era `version_of("audio/msu.py")`
  —el código que normaliza y escribe la pista— en Rust es el sha256 del
  ejecutable que corre. Con un binario propio, la clave cambia cuando cambia
  lo que entra en ese binario, y no con cualquier cambio del compilador: las
  pistas cuestan un minuto y medio rehacerlas.
* **El mismo crate** porque comparten `Game` —dónde está un tema, el juego o
  el RTP— y los números del motor: `ceilings` le preguntaba a
  `rm2k-snes-audio constants` el `headroom` y el `master`, y ahora los lee
  de `sdsp` directamente; `msu` le preguntaba a `rm2k-snes-audio find-song`
  y ahora llama a `Game::song_path`.

**Los techos, enteros en Rust, con la consola incluida.** La pregunta era si
cargar un core de libretro desde Rust valía la pena o si esa parte convenía
dejarla en Python. Salió chica —`retro.rs`, unas doscientas líneas, con
`dlopen` de `libc` y sin otra dependencia— porque para medir alcanza con el
audio: no hace falta imagen, ni botones, ni memoria. Contesta al entorno lo
mismo que `emulator/retro.py` —el orden de las llamadas, el primer valor de
cada opción, un directorio propio sin pistas al lado— y **da las mismas
muestras**: ver la comparación abajo.

Lo que tiene de distinto: **un core es una consola por proceso** —su estado
son globales de la biblioteca—, así que los temas se tocan en paralelo en
procesos aparte, como hacía el `Pool` de Python: el mismo binario con
`--play ROM --song N --frames F`, que imprime en JSON los recortes, el pico
y el cuadro (y el LUFS con `--lufs`). `PROCESOS` sigue diciendo cuántos.

**`test_musica_techos.py` ya no importa `audio.ceilings`**: toca cada tema
cerca del tope con `rm2k-snes-volume-ceilings --play`, que es la misma
consola y las mismas cuentas con que se midió la tabla. Lo demás que tomaba
del módulo —dónde está la tabla, `musica.json`, la línea `; Songs:`— lo lee
la prueba sola: son tres líneas cada una.

`emulator/retro.py` no se toca: es el arnés de toda la tanda.

## La comparación

* **Las pistas**: `NO_CACHE=1 just cartuchos` con los binarios de Rust
  contra el mismo comando con los de Python, en este worktree: los `.pcm`,
  el `.msu` y los `.sfc` de `rom/build/` salen iguales byte por byte, y las
  líneas que imprime cada pista también. Entran las dos que vienen de un
  reemplazo por `ffmpeg`. Con caché, la segunda corrida dice que no hizo
  ninguna.
* **Los techos, `--measure`**: el informe de Rust es el de Python línea por
  línea —recortes, pico, LUFS de cada tema—. Y un tema suelto con `--play`
  da las mismas muestras que `ceilings.play` de Python.
* **Los techos, el camino entero** —la copia a medio aire, la tabla,
  rearmar, volver a medir—, corrido en Python y en Rust sobre **una copia
  del proyecto**, para no tocar la tabla del repo: las dos tablas salen
  iguales byte por byte, y los informes también.
* `just pruebas` y `just -f tools/justfile test` en verde, antes y después
  de borrar los `.py`; `cargo test` del crate en verde.

Lo que se vio de paso y no se tocó: la tabla versionada ya no es la que
daría medir hoy. Python y Rust coinciden en que ocho temas se movieron
entre 0,1 y 0,4 dB del pico escrito —`MML2_MotherZone`, de -1,0 a -0,6—, y
el camino entero cambia el aire de siete y la huella de seis. Ninguno
recorta, y la prueba de la huella pasa porque mira `musica.json`, no una
corrida nueva, así que es la deriva que la prueba ya espera. Y el
encabezado de la tabla del repo sigue en castellano, porque es de antes de
la traducción: la próxima `just techos` lo escribe en inglés, y cita
`build_all` y `sdsp.HEADROOM`, que eran nombres de Python —se dejaron como
estaban, para que las tablas salieran iguales—.

## Al mergear

* **Instalar `rm2k-snes-audio`**: `just -f tools/justfile install
  rm2k-snes-audio`, desde el checkout principal. Instala los tres binarios,
  y `_install` borra antes los symlinks `rm2k-snes-*`, así que los de
  `rm2k-snes-msu` y `rm2k-snes-volume-ceilings`, que apuntaban a los `.py`,
  no quedan colgando. Sin reinstalar, el global se queda con symlinks a
  archivos que ya no existen.
* **`tools/port/snes_convert.py` cita dos veces a `tools/audio/`** —la ayuda
  de `--measure-headroom` y un comentario sobre `musica.json`—: no se tocó
  porque lo está partiendo Ñacurutú.
* La primera corrida con el binario nuevo rehace las 43 pistas —la clave
  cambió—: un minuto y medio, una vez.
