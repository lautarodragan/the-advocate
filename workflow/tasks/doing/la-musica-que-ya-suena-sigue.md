---
name: "Un tema que ya suena no vuelve a empezar"
description: "En RM2k, PlayBGM con el tema que ya está sonando no lo reinicia; en la ROM sí: la victoria de la pelea y la caminata a la fábrica"
type: bug
assignee: Yacaré
---

De taro, el 2026-09-30: "creo que en el RPG Maker, cuando se ejecuta un play
bgm o algo transiciona a un nuevo tema, si el tema es el mismo que ya está
sonando, no comienza de cero, simplemente sigue sonando". Lo nota en dos
lugares:

- **La pelea**: el tema de batalla y el de "ganar batalla" son el mismo. En
  el original, probablemente, no cambiaba nada al ganar.
- **La cinemática de la caminata hacia la fábrica**: la música se reinicia
  en una de las transiciones.

A confirmar en easyrpg (`Game_System::BgmPlay` y cómo la pelea pide el tema
de victoria) y, si se puede, con el RPG_RT bajo Wine, grabando su audio.

## Qué hace RM2k

**easyrpg** (`src/game_system.cpp`, `Game_System::BgmPlay`): si el nombre es
el que suena y no hay un fundido en curso (`music_stopping`, que prende
`BgmFade` y apaga el siguiente `BgmPlay`), **no reinicia**: sólo ajusta el
volumen, el tempo y el balance que hayan cambiado. "El mismo tema" es **sólo
el nombre**: con otro volumen o tempo sigue igual, ajustado. `fadein` no
cuenta. La pelea pasa por la misma función: `Scene_Battle` anota
`before_battle_music` y pide `BGM_Battle` al construirse;
`Scene_Battle_Rpg2k` pide `BGM_Victory` al ganar; `Game_Map::OnContinueFromBattle`
repone el de antes. Y `Game_Map::PlayBgm`, al entrar a un mapa, también.

**El RPG_RT de 2015 bajo Wine** dice lo mismo, medido. El MIDI no suena acá
adentro —Wine no tiene sintetizador MIDI sin el secuenciador de ALSA—, así
que el tema fue un WAV puesto en `Music/`: un barrido de frecuencia, donde la
altura dice por dónde va. Una página en el mapa de arranque lo pidió así, y
la grabación (`/shared/audio/2026-09-30-tema-que-sigue/`) dice:

    PlayBGM igual                 sigue
    PlayBGM con volumen 50        sigue, más bajo
    PlayBGM con tempo 150         sigue, más rápido (y vuelve al volumen 100)
    otro tema, y después éste     empieza de cero
    a mitad de un FadeOutBGM      empieza de cero

Las dos fuentes coinciden en todo. Lo que no se pudo: el runtime de 2000
—el del autor— necesita la `Harmony.dll` de verdad, y con MIDI.

## Los casos del juego

- **La victoria**: `battle_music` y `battle_end_music` del LDB son los dos
  `T_VGFighterMAX_Masako`, y la ROM lo reiniciaba al ganar. Hay 130
  `ChangeSystemBGM` en el juego, que la ROM ignora desde antes; con eso los
  dos siguen siendo el mismo.
- **La caminata a la fábrica**: la puerta del mapa 8 salta al 16 ("Running
  To Work Scene"), que trae `hzbreach` como tema; el mapa lo prende al
  cargar, y la automática del 16 empieza con un `PlayBGM hzbreach`, que lo
  reiniciaba con la escena ya andando. Las transiciones de adentro del 16 son
  saltos al mismo mapa y no tocan la música; la del final funde, pide
  `wb3mlair` y salta al 17. (El mapa 14 también pide `hzbreach` y salta al
  16, pero ninguna puerta lleva a él.)
- **Cuántos PlayBGM piden el que ya suena**, estático y sin seguir ramas: de
  168, **10** repiten el que la misma página acababa de pedir sin un fundido
  entre medio, **5** son el primero de una automática que pide el tema de su
  mapa, y **8** pares salto→automática del destino piden el mismo. Ninguna
  pelea arranca con el tema de batalla ya sonando.

## Lo que se hizo

`song_playing` (en `music.s`) es la pregunta de `BgmPlay`: el tema es el que
suena —por la pista del MSU-1 o por el SPC700— y no se está fundiendo.
`music_play` la hace antes de `music_start`, y la usan el `PlayBGM`, el
`PlayMemorizedBGM` y `battle_bgm` —la entrada, la victoria, la vuelta, el
Game Over—. `music_start` sigue reiniciando siempre: lo usan el título y la
partida cargada. `map_song_mute` y `remembered_song` tenían cada uno su
copia de la pregunta: ahora preguntan lo mismo.

**Con MSU-1** vale igual: `song_playing` mira `MSU_PLAYING` antes que
`music_off`, y la pista no se reinicia (lo cobra
`test_con_msu_el_tema_pedido_dos_veces_no_reinicia_la_pista`, escuchando).

**Sin MSU-1, la pelea cambia el paquete de audio al entrar**, y para eso
calla lo que suena: si el mapa estuviera tocando el tema de batalla, se
reiniciaría al entrar igual. No pasa en el juego —ver arriba—, así que no se
tocó `battle_audio_load`; si alguna vez hace falta, `package_load` ya deja
en su lugar las muestras del tema que suena, y alcanzaría con no callarlo
cuando es el mismo.

## Las pruebas

- `rpgmaker/test_tema_que_ya_suena.py`, con el caso `tema-pedido-dos-veces`:
  dos `PlayBGM evilrhys` en una página. Rojo antes del arreglo: el stream
  volvió de `$65C296` a `$65C1A6`.
- `test_batalla.py::test_ganar_deja_seguir_el_tema_de_la_victoria`: **antes
  pedía lo contrario**, que la victoria lo arrancara de cero
  (`546fb17d`, 2026-09-12). Rojo antes del arreglo con la condición dada
  vuelta: el cursor volvió de `$6781CB` a `$67808D`.
- `abl/test_msu.py::test_con_msu_el_tema_pedido_dos_veces_no_reinicia_la_pista`:
  compara lo que suena después de cada `PlayBGM`. Correlación 1,00 antes del
  arreglo y 0,12 después.

## Lo que queda

- **El volumen y el tempo de un `PlayBGM` la ROM no los lee**, ni antes ni
  ahora: 69 de los 168 piden otro volumen y 13 otro tempo. RM2k, con el
  mismo tema, los ajusta sin reiniciar.

## Para escuchar

`/shared/audio/2026-09-30-tema-que-sigue/`, con su `LEEME.txt`: la victoria
y la corrida al 16, antes y después, con MSU-1 y sin él, y la grabación del
RPG_RT.

## Al mergear

- Instalar `cartridge` en el global no hace falta: no se tocó Rust. Sólo
  cambió `tools/runtime/`, que el global ya lee del checkout principal.
- No hay goldens nuevas ni movidas, y `test_musica_techos.py` pasó.
