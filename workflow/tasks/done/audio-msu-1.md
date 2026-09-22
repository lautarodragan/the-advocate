---
name: "Música por MSU-1"
description: "Las pistas de CD que reemplazan a la música sintetizada"
---

### El MSU-1

La música sintetizada suena fea, y la causa está medida: los ocho temas de la
demo comparten 53 KB de ARAM, así que cada instrumento es una muestra corta y
recortada. El **MSU-1** es la salida: no es hardware de la
consola sino una extensión que soportan el FX Pak Pro y los emuladores, con la
música en archivos PCM al lado de la ROM. El tema sale de un archivo de 44,1
kHz estéreo en vez de las ocho voces del SPC700.

Lo usan **los 21 temas que suenan hasta salir de Lashe City**, más el del
título: `PISTAS_MSU` en `snes_music.py` dice cuáles tienen pista y con qué
número, y el conversor emite `tema_msu`, un byte por tema —`$FF` el que no
tiene—. Los del juego entero son 43, noventa y un minutos, 923 MB de PCM;
entran el día que haya una ROM que los toque. Que los lleven todos importa
porque un tema sin pista suena por el SPC700 y ahí puede faltarle del 28% al 88%
de las notas: ver "Varios temas en el cartucho". **Los números del 1 al 8 no se
mueven nunca**: son los que ya están en la tarjeta, y renumerarlos obligaría a
renombrar archivos.

Dos de los temas **no son de ningún mapa** y por eso se escapan de cualquier
barrido de `PlayBGM`: salen del LDB. `title_music` es el de la pantalla de
título y `battle_music` el de **todas** las peleas —`T_VGFighterMAX_Masako`—.

Cuestan 10,6 MB por minuto, o sea unos **423 MB por cartucho** para los 21. Y
no hay atajo por el loop: de los 21 el único que repite exacto a la mitad es
`C3classi`, medido nota por nota sobre las dos mitades del MIDI, y son 8,6 MB
de 423.

Cómo funciona, del lado de la ROM:

* **La firma se mira una vez, en el reset** (`msu_detectar`): "S-MSU1" en
  `$2002..$2007`. Si no está —o sea, siempre que no haya MSU-1— `MSU_HAY` queda
  en cero y **nada más del sistema se enciende**: la música sigue saliendo del
  SPC700 como antes de todo esto. Esa es la propiedad que importa, porque la
  ROM tiene que andar igual en una consola sin tarjeta preparada.
* **`PlayBGM` prueba primero con la pista** (`msu_arrancar`): espera a que el
  MSU-1 esté libre, escribe el número, espera a que termine de cargarla, y si
  el MSU-1 dice que la pista no está en la tarjeta se vuelve sin hacer nada y
  suena el SPC700. Con pista, en cambio, el SPC700 **se calla**:
  `music_apagada` y un `KOF` de las ocho voces. Los efectos de sonido siguen en
  el SPC700, así que la ARAM les queda libre.
* **La espera de `AUDIO_BUSY` es un camino que ningún emulador ejecuta**, y
  conviene saberlo antes de tocarlo. bsnes no pone `io.audioBusy` nunca —nace
  en falso en `power()` y no se escribe en ningún lado:
  `bsnes/sfc/coprocessor/msu1/msu1.cpp`—, así que en toda la tanda y en todas
  las pruebas de estado el lazo sale en la primera vuelta. En el FX Pak la
  pista sale de la tarjeta SD y abrirla lleva tiempo de verdad. En el mismo
  archivo está el porqué de esperar **antes** de escribir y no sólo después:
  `case 0x2007: if(io.audioBusy) break;`, o sea que con `AUDIO_BUSY` puesto el
  hardware **ignora** las escrituras a los registros de audio, y un `PlayBGM`
  que llega mientras la pista anterior todavía se abre se pierde entero. Con
  pantalla de título eso pasa: se piden dos pistas con 1,8 s de diferencia.
  El tope de la espera son `$FFFF` vueltas, unas tres décimas de segundo, y
  quedarse corto no cuesta un cuadro sino el tema entero.
* **El `FadeOutBGM` baja el volumen del MSU-1**, no el del DSP: el nivel del
  fundido ya va de 255 a 0, que es justo la escala de `$2006`, y al llegar a
  cero se corta la pista. El volumen del DSP no se toca **porque es el que
  oyen los efectos de sonido**: bajarlo en el fundido los dejaba mudos hasta
  el `PlayBGM` siguiente, que es el único que lo repone. Y el comando tiene
  que dejarse arrancar con `music_apagada` puesto, que con pista vale 1: sin
  eso un `FadeOutBGM` no hacía nada y la pista seguía para siempre.
* **El DSP hay que ponerlo a punto igual**, aunque no lo use la música. Lo
  hacía el comienzo del stream —sacarlo del mute con que arranca el SPC700, el
  volumen general, y dónde está el directorio de muestras— y con pista el
  stream no corre nunca. Sin eso los efectos de sonido se disparan contra un
  DSP mudo, y el síntoma es música por MSU-1 y **ningún efecto**.
  El prólogo sale de `dsp_init_reg`/`dsp_init_val`, que el conversor emite de
  `init_writes`, o sea de la misma lista que ya escribía el stream; copiarla a
  mano en el 65816 serían dos lados que se pueden equivocar igual. KON y KOF
  quedan afuera: con pista, KOF se deja en `$FF` para que las voces de la
  música no suenen, y `se_despues` lo limpia solo al arrancar un efecto.

* **La pista no suena a fondo, y eso no es cautela: es aritmética.** El MSU-1
  se **suma** a la salida del SPC700 en vez de mezclarse con ella, así que una
  música que llega al techo no deja lugar para un efecto de sonido. Con el
  volumen en `$FF`, en la apertura, 42 muestras llegaban al tope —las 42 en
  cuadros con un efecto sonando— mientras que la misma corrida por el SPC700 no
  clavetea ni una vez; y la música por pista picaba 28933 contra 23867, o sea
  1,21 veces más alta, que es lo mismo escuchado al revés: "los efectos se oyen
  mucho más bajos". `MSU_VOLUMEN_MAX` es `$D8` —ese 0,85— y con eso el clipping
  se va a cero y la música queda en 24508, al lado de los 23867 del SPC700. Va
  en el registro y no en las pistas: normalizarlas más abajo sería rehacer todos
  los PCM del cartucho, y perdería la referencia de nivel entre un tema y otro.
  El fundido escala contra ese techo y no contra 255, o su primer cuadro
  **subiría** la música antes de bajarla.

Y del lado del cartucho, `tools/audio/msu.py` (receta `msu`): renderiza el MIDI
con fluidsynth y **con el mismo soundfont con el que el juego sonaba en la PC**
—el que ya usa `snes_samples.py` para sacar las muestras—, así que no cambia el
arreglo: cambia que no haya que reducirlo a ocho voces. La pista es "MSU1", el
punto de loop en muestras, y el audio crudo.

Y correr la receta de nuevo no rehace nada: una pista no depende del
cartucho sino del MIDI, del soundfont, de fluidsynth y de cómo se normaliza, y
todo eso está en la clave. Lo que se guarda en `rom/build/cache/msu/` es el
sha256 del `.pcm`, no el `.pcm`, porque el archivo ya está escrito al lado de
la ROM.

Una cosa más del lado del cartucho: **la pista se normaliza a 0,97 de la
escala**. fluidsynth se corre bajo, en 0,6, porque con 1,0 los temas de muchas
voces saturan, y sin normalizar después la pista sale a un cuarto del volumen de
la música del SPC700 —pico 4632 contra 17012— y el cambio de un tema al otro da
un salto.

Cómo se verifica, porque la tanda no escucha: primero el protocolo solo, con
una ROM mínima aparte que pide la pista y deja los registros en la RAM —la
firma, el estado antes y después, y cuántas vueltas tardó en cargar—. Y después
la ROM de verdad, corriendo 1800 cuadros con el núcleo de libretro y grabando
la salida:

* **el nivel**: picos de 17096 a 20118 en las ventanas de 300 cuadros, contra
  los 17012 de la música del SPC700;
* **que suene esa pista y no otra cosa**: la envolvente de energía del audio
  grabado contra la del WAV renderizado da una correlación de **0,927 con cero
  desfase**;
* **el fundido**: pinchando el pedido de `FadeOutBGM`, la pista se corta a los
  84 cuadros y el pico baja 19059 → 3464 → 0.

**Y para los efectos de sonido hay que aislarlos, porque la música los tapa.**
La forma que sirve es la misma ROM con los dos bytes de volumen de cada fila de
`sonido_tabla` puestos en cero, y comparar las dos salidas muestra por muestra:
lo que difiere **son** los efectos. Así se comprobó que el prólogo del DSP es lo
que los hace sonar con pista: con el prólogo puesto difieren 714382 muestras de
1027098 desde el cuadro 212, y con un `$FF` en el primer byte de `dsp_init_reg`
—que lo deshabilita— difieren **cero**.

Y la tanda entera sigue en verde **sin** los archivos de MSU-1, que es el
camino que recorre cualquier prueba de acá.

## Pendiente

Lo que falta: el punto de loop. El MSU-1 vuelve al principio del archivo, así
que un tema con introducción la repite cada vuelta; hoy loopean enteros. Y los
temas que las demos no tocan.

## Compatibilidad

El MSU-1 es emulado correctamente en:
- FxPak, en SNES real
- snes9x
- Mesen

Y no en:
- Mednafen
