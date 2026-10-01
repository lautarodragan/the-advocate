---
name: "El volumen y el tempo de PlayBGM"
description: "La ROM ignora el volumen y el tempo que pide un PlayBGM: 69 de los 168 del juego piden otro volumen y 13 otro tempo"
type: feature
assignee: taro
---

De taro, el 2026-09-30, como siguiente tarea después de
`testing/la-musica-que-ya-suena-sigue.md` (Yacaré), que lo dejó medido: de
los 168 `PlayBGM` del juego, 69 piden un volumen distinto del de por omisión
y 13 un tempo distinto, y la ROM no usa ninguno de los dos. Además, en
RM2k, un `PlayBGM` del tema que ya suena con otro volumen o tempo los ajusta
sin reiniciar (`Game_System::BgmPlay`), y eso Yacaré ya lo dejó preparado.

## Qué hace RM2k

Leído en easyrpg (`src/game_system.cpp`, `src/audio_decoder_midi.cpp`,
`src/audio_decoder_base.cpp`). No se pudo confirmar con el RPG_RT bajo Wine:
ahí el MIDI no suena —Yacaré ya lo vio—, y lo que dice de un WAV (que el
tempo cambia también la altura) no es lo que pasa con un MIDI, que son todos
los temas de este juego.

- **`BgmPlay`** acota el volumen a 0–100, el tempo a 10–400 (el editor da
  50–150) y el balance a 0–100. Con el mismo nombre y sin un fundido de por
  medio sólo ajusta los tres que cambiaron, sin reiniciar.
- **El volumen de un MIDI** es el CC7 de cada canal por `volume/100`
  (`AudioDecoderMidi::SetVolume`), lineal **en el CC7**. El stream de la ROM
  ya pasó el CC7 al cuadrado —`volume` en `rm2k-snes-audio/src/sdsp.rs`, como
  fluidsynth—, así que en amplitud es `(v/100)²`: 80 es 0,64, 50 es un
  cuarto, 40 es 0,16. (Para lo que no es MIDI easyrpg usa otra curva, la de
  DirectSound: 35 dB de rango, `AdjustVolume`.)
- **El tempo de un MIDI** apura el reloj del secuenciador (`mtime +=
  delta * pitch / 100`): más rápido, **la misma altura**. Con un WAV
  remuestrea, y ahí sí cambia la altura.
- **El balance de un MIDI** corre el paneo de cada canal `(b − 50) × 2`; sin
  mensajes MIDI, baja el lado opuesto 6 dB cada 10 (`ApplyLogVolume`).

## Lo que pide el juego

En los mapas de `release` hay 62 `PlayBGM`: 12 con otro volumen —el 80 es
el más común: `TF3_1_awe` en la apertura (mapa 2), `evilrhys` en el 3,
`dcbest`, `tsmedit`, `bubstix`, `jackalstg2`— y uno solo con otro tempo,
`Kfmus5` a 110 (mapa 37, al entrar al 41). El 93 tiene el caso de "el
mismo tema con otro volumen": su automática pide `jackalstg2` a 50 y, a
mitad de la escena, a 80. Los del bosque de noche (`nightbg` a 40 y tempo
80, mapas 218–222, y a 50/50 en el 108) no están en el cartucho.

**El balance no lo usa nadie**: el único `PlayBGM` con balance distinto de
50 es un `(OFF)` del mapa 128.

## Lo que se hizo

- **El bytecode**: `OP_BGM` lleva, además del tema, la ganancia de cada lado
  en 128avos y el paso del tempo en 256avos (`events.toml`). Las cuentas
  están en un solo lado, `bgm_level` del compilador de eventos, con lo de
  arriba en su comentario: volumen al cuadrado, balance con la curva de 6 dB
  (la aproximación barata: el stream ya horneó el paneo de cada voz), tempo
  acotado a 50–150.
- **El nivel** son esos cuatro bytes, en la RAM lejana: el que se pide
  (`BGM_ASK`), el que suena (`BGM_NOW`), el de antes de la pelea y el del
  `MemorizeBGM`. `music_play` aplica el pedido con `bgm_level_set`
  (`bgm_level.s`, fuera del banco 0): con el mismo tema sólo cambia el nivel,
  y con otro lo arranca a ese nivel. `music_start` —el título, la partida
  cargada, el tema propio de un mapa— lo arranca como está escrito.
- **Sin MSU-1, el volumen** escala el `VOL_L`/`VOL_R` de cada voz de la
  música con el multiplicador de la PPU, igual que el fundido y encima de él
  (`song_gain_scale`). Los efectos de sonido no se tocan. Si el tema sigue
  con otro volumen, `GAIN_DIRTY` le pide a `irq_music` que reescriba todas
  las voces en el cuadro siguiente.
- **Sin MSU-1, el tempo**: `music_tempo` suma el paso en un acumulador y
  corre un cuadro de música por cada entero. A 100 es exactamente lo de
  antes; a 150, dos cuadros cada dos; la altura no cambia.
- **Con MSU-1, el volumen** es el de la pista: `MSU_VOLUME_MAX` por el lado
  más fuerte (`MSU_BASE`), que usan `msu_start`, el fundido y el `PlayBGM`
  que baja el tema que sigue. **El tempo se ignora con MSU-1**: una pista PCM
  no cambia de velocidad sin cambiar la altura. La opción cara, una pista
  por tempo, hoy sería una sola —`Kfmus5` a 110, cuya pista, la 100, pesa
  25,8 MB—: unos 23 MB más para un tema que va un 10% más rápido. Aplica
  `decisiones/primero-el-juego-entero-despues-la-calidad.md`. Tampoco hay
  balance en el MSU-1: toma el lado más fuerte.
- **La pelea** guarda el nivel del mapa y lo repone al volver; su tema y el
  de victoria van como están escritos (el LDB dice 100, 100 y 50). Y el
  `MemorizeBGM` recuerda el nivel con el tema, como RM2k.

## Las pruebas

Vistas en rojo antes del arreglo, con el bytecode nuevo y el `op_bgm` que
sólo salteaba los cuatro bytes:

- `rpgmaker/test_volumen_y_tempo.py`, con tres casos nuevos
  (`tema-a-volumen-50`, `tema-a-tempo-150`, `tema-que-baja`):
  - a volumen 50, cada `VOL` que llega a `dsp_music` es un cuarto del que
    el stream escribió. Rojo: "el registro $00 quedó en 33 y el stream le
    escribió 33: tenía que quedar en 8";
  - a tempo 150, en 120 cuadros de video corren 180 de música. Rojo: "corrieron
    120";
  - el mismo tema a 100 y después a 50 no se reinicia y las voces bajan sin
    esperar su próxima nota. Rojo: "el registro $00 quedó en 45 … tenía que
    quedar en 11".
- `abl/test_msu.py::test_con_msu_el_volumen_de_un_tema_que_sigue_baja_la_pista`:
  con las pistas, `tema-que-baja` contra `tema-pedido-dos-veces`, el mismo
  audio después del segundo `PlayBGM`; la amplitud tiene que quedar en un
  cuarto. Rojo: "dejó la pista a 1.00".
- `cargo test -p rm2k-snes-events`: `a_play_bgms_level_in_the_consoles_units`.
  **Cambian dos hashes de `tests/python.json`** —`scan.maps` y
  `compile.maps`—, a propósito: medido con los dos compiladores sobre el
  juego chico, lo único que cambia son los cuatro bytes nuevos detrás de cada
  `OP_BGM` (128, 128, 0, 1: todos sus `PlayBGM` van como están escritos) y
  los destinos de salto que quedan después, corridos en 4.

`test_musica_techos.py` pasó: con todo a 100 la mezcla es la misma, y un
`PlayBGM` sólo puede bajarla.

## Lo que queda

- **El tema propio de un mapa y el del título no usan su nivel.** El árbol de
  mapas trae volumen para la música de algunos (`worlds5` a 70,
  `MML2_MotherZone` a 80, `Turrican_1_-_Loader` a 50…, en 18 mapas), y el
  LDB dice que el del título va a 90 y **a tempo 130**. Los dos pasan por
  `music_start`, que los toca como están escritos. El del título, además,
  es por donde `test_musica_escrituras.py` y la medición de techos tocan los
  temas: aplicarle su nivel cambia esas dos.
- Un mapa cuyo tema es el que ya suena no le cambia el nivel (RM2k sí:
  `Game_Map::PlayBgm` pasa por `BgmPlay` con el volumen del mapa).
- **El nivel no viaja en la partida guardada**: al cargar, el tema suena
  como está escrito. Agregarlo cambia el formato de la SRAM.
- Con MSU-1, los efectos que usan las voces 0 a 5 devuelven al terminar el
  volumen del stream sin la ganancia (`se_extras_before`, que tampoco
  aplicaba el fundido). Con MSU-1 todo tema tiene pista y el SPC700 no toca
  música, así que no debería oírse.
- `ChangeSystemBGM` sigue sin hacerse, desde antes.

## Para escuchar

`/shared/audio/2026-09-30-volumen-y-tempo/`, con su `LEEME.txt`: el mapa 93
(`jackalstg2` a 50 y después a 80, sin reiniciar) y la entrada al 41 desde
el 37 (`Kfmus5` a tempo 110), antes y después, con MSU-1 y sin él. Medido
sobre las grabaciones: el 93 queda en un cuarto y en 0,64 de lo de antes, y
con MSU-1 el `Kfmus5` sale igual que antes, a propósito.

## Al mergear

- **Instalar `events` en el global** (`just -f tools/justfile install
  events`): el compilador emite el `OP_BGM` nuevo, y con el viejo el
  intérprete leería cuatro bytes de más. `cartridge` no hace falta: sólo
  cambió `tools/runtime/`, que el global lee del checkout principal.
- `bgm_level.s` es un archivo nuevo de `tools/runtime/`, incluido en
  `main.s` después de `remembered_place_and_song.s`.
- RAM lejana: $25C6 a $25DF.
- No hay goldens nuevas ni movidas, y `test_musica_techos.py` pasó.
- Con `main` mergeado (`4a94948c`): `NO_CACHE=1 just cartuchos` igual byte
  por byte que con caché, `just pruebas` 919 en verde, `just -f
  tools/justfile test` 46, `cargo test -p rm2k-snes-events` en verde.
  `just espacio` en `release`: banco 0 de 581 a 364 B, banco 1 de 4.544 a
  4.233 B, bancos de datos 120 de 124 como antes.

## Qué escuchar jugando

La apertura y el mapa 3 tienen su tema a 80, un poco más bajo que antes. En
la agencia (mapa 93) el tema arranca bajo y sube cuando el guardia avisa del
misil. Y sin MSU-1, el `Kfmus5` del 41 un poco más rápido.
