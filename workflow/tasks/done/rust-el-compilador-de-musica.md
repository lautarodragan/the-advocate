---
name: "Rust: el compilador de música"
description: "La cadena de audio del MIDI al stream del S-DSP y el paquete de audio por mapa, en Rust (rm2k-snes-audio), con las ROMs byte por byte iguales; msu y ceilings quedan en Python por ahora"
type: refactor
assignee: taro
---

Tercer paso del camino a Rust de `docs/research/las-herramientas-hoy.md`,
en paralelo con Carancho. Lo decidió Hornero: el audio va por partes, y ésta
es la primera, el compilador de música —`midi`, `music`, `sdsp`, `spc700`,
`snes_music`, `snes_samples`, `brr_samples`, `msu_effects`—. `msu.py` y
`ceilings.py` (las pistas PCM y la medición de techos, que usan fluidsynth y
ffmpeg) quedan en Python para una segunda parte. Los puentes a `gunter`
(`brr_samples`, `snes_samples`) desaparecen: el crate nuevo usa `gunter`
como biblioteca.

## Cómo quedó

**El crate es `tools/rm2k-snes-audio/`**, biblioteca y ejecutable, y usa
`gunter` (el SoundFont y el BRR) y `rm2k-project` (el archivo de proyecto)
como bibliotecas por `path`. Para eso Gunter pasó a tener `lib.rs`, y la
extracción de `sf2 --extract` —selector, zona, contrato, PCM— salió de su
`main.rs` a `gunter::extract`; su binario dice lo mismo que antes. Y
`protocol` aprendió `--rust`: `rm2k-snes-audio/src/music_opcodes.rs` sale de
`music.toml` como los otros dos lados, y la receta `protocol` lo chequea.

**El conversor le pasa un pedido y lee lo que escribe.** Arma el pedido
—temas, efectos, paquetes con sus salidas y aparte, herencia, el aire de
medición, las canciones de `System` y lo que va a `musicdata.inc`—, lo deja
en `audio-job.json` al lado del cartucho y corre `rm2k-snes-audio compile`,
que escribe `musicdata.inc`, `musica.json` y `audio.json`. De ahí el
conversor saca lo que le falta: el arranque contra `BOOT_FRAMES` (que sigue
leyendo él de `far_ram.s`) y las versiones de calidad de los efectos para el
`.msu`, que sigue armando él porque lleva también los fondos de batalla.

**La comparación, primera corrida**: `NO_CACHE=1 just cartuchos` en `release`
y `test-special`, contra la foto de `main` mergeado (`fdae002f`): los 991
archivos de `rom/build/` que había salen iguales byte por byte —los `.sfc`,
el `.msu`, los 43 `.pcm`, `musicdata.inc`, `musica.json`, `efectos.json`—, y
aparecen los cuatro nuevos (`audio-job.json` y `audio.json` de cada uno). El
log del conversor tiene las mismas líneas, en otro orden: el informe de temas
y banco lo imprime ahora el ejecutable, antes que las líneas del conversor.

El audio de `release` entero tarda **2,3 s** en Rust, en un hilo y sin caché
en disco.

**Las decisiones**:

* **Lo que igualar costaba.** El Python redondeaba al par, dividía con piso,
  filtraba con numpy —el kernel sumado por pares, en bloques de ocho— y
  elevaba al cuadrado con el `pow` de la libc; el Rust hace lo mismo, a
  propósito, y `src/num.rs` lo dice. La convolución circular del lazo, que
  numpy hacía por FFT, acá es directa: difiere en el último bit y no cambió
  ningún redondeo en los dos cartuchos. Lo que en Python dependía del orden
  de un `set` —el orden de las sumas de `allocate` y de las copias, que
  cambia con `PYTHONHASHSEED`— acá va por orden de clave.
* **Sin caché en disco.** Se van las categorías `muestras` y `brr`: 2,3 s
  para `release` entero no lo piden. Así que no hay clave que tenga que
  llevar el binario nuevo; lo que sí lo lleva es la huella de los cartuchos
  (`tools/cartridge/`), donde reemplaza a `gunter`, que el armado ya no corre.
* **Las tablas de efectos que lee `events.py`** —por mapa, de rutas, de
  tropa— las lee `events.py` del archivo de proyecto; los temas aparte y los
  temas de cada mapa del árbol, el conversor. No se le piden al ejecutable:
  son perillas del juego, no música.
* **`msu.py` y `ceilings.py` quedan en Python**, sin importar nada borrado:
  `msu.py` busca el archivo de cada tema con `rm2k-snes-audio find-song` y se
  queda con la huella del SoundFont, que es de su caché; `ceilings.py` le
  pide el aire y el volumen general a `rm2k-snes-audio constants`.
* **El `.msu` lo sigue armando el conversor** (`write_msu`), porque lleva los
  fondos de batalla; qué versión de cada efecto va en cada paquete, sus filas
  y sus alturas las decide el ejecutable y las deja en `audio.json`.
* **Las pruebas de ABL** preguntan por `rom/pruebas/arnes/musica.py`, con la
  forma de `cartuchos.py`. Cuatro salen de la lista de `test_lado_de_abl.py`.
* **`tools/tests/test_music_stream.py` pasa al crate**, en Rust: sus veinte
  pruebas están en `src/voices/tests.rs`, `src/midi.rs`, `src/sdsp.rs` y
  `tests/soundfont.rs` (las dos del SoundFont, con `SOUNDFONT`). Y como
  `rm2k-render`, `tests/python.rs` guarda el SHA-256 de lo que el Python
  escribía para un juego chico armado en la prueba.
* **`music_opcodes.py` se queda**: lo genera `protocol` y lo lee
  `test_protocol.py`, que ahora chequea también el módulo de Rust.
* **`musicdata.inc` cambió cuatro líneas de comentario**, en un commit
  aparte: decía que lo generaba `snes_music.py`.

**La comparación completa**, con el script de huellas de
`rust-chingolo/` del scratchpad: `NO_CACHE=1 just cartuchos`, `release` y
`test-special`, contra la foto de `fdae002f`, después de cada paso —el
cambio al Rust, el borrado del Python, la prosa—: todo igual. Después del
último commit, los `.sfc`, `.msu` y `.pcm` iguales, y `musicdata.inc`
distinto en esas cuatro líneas.

## Al mergear

Instalar `protocol` (tiene `--rust`, y `test_protocol.py` lo usa),
`cartridge` (la huella) y `rm2k-snes-audio`: `just -f tools/justfile install
protocol cartridge rm2k-snes-audio`. `gunter` no hace falta: su binario hace
lo mismo, y lo que cambió es que ahora es una biblioteca, que va adentro de
`rm2k-snes-audio`. `install-scripts` no: ningún script cambió de nombre.

## Lo que falta

La segunda parte: `msu.py` y `ceilings.py` (fluidsynth y ffmpeg) a Rust.
