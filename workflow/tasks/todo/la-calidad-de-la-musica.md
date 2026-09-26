---
name: "La calidad de la música"
description: "Por qué escape_newyork suena mal por el SPC700, once versiones grabadas para comparar, y en qué orden arreglarlo"
type: feature
---

**Lo que taro eligió escuchando, el 2026-09-25**: lo que más le importa, y
mucho, es **el reparto de voces** (la variante 09 "es muy aceptable"); después
**las envolventes**; después **la batería**; y **las muestras a 22 kHz** hacen
una diferencia notoria pero importan menos. Quiere **todas juntas**, sabiendo
que aun así se nota la diferencia con la referencia (para eso está el MSU-1).

El orden de implementación no es el de sus prioridades por el espacio: el
reparto suma +74% de stream en el formato de hoy (~436 KB, todo el margen del
cartucho unido). Así que: batería → notas que se sueltan antes de tiempo →
envolventes → velocidad y CC → **el formato por nota, diseñado para todo lo de
arriba y para el reparto** → reparto y rampa → muestras por mapa. **Hechos
el 0, el 1 y el 2**, el 2026-09-25, **y el 3** el 2026-09-26: ver cada uno
abajo.


taro, el 2026-09-25: *"`escape_newyork` se escucha particularmente mal, y tal
vez incluir las envolventes lo mejore mucho. Y hay notas que se cortan muy
abruptamente."* Esto es la investigación: **el diagnóstico, once versiones
del tema grabadas saliendo de la ROM, y el plan**. No hay nada mergeado.

* Las grabaciones y lo que cambió en cada una:
  `/shared/audio/2026-09-25-escape-newyork/` y su `LEEME.txt`.
* Los prototipos: rama local `proto-calidad-musica` (commit `0067f7c`), **no
  para mergear**. `tools/audio/proto_musica.py` arma cada variante según
  `PROTO_MUSICA`; `tools/audio/proto/` tiene cómo se armó, grabó y midió
  cada una.

Los números de abajo son del 2026-09-25, sobre `9602035`, con los 22 temas
del `release`: los scripts que los midieron están en esa rama, y antes de
implementar hay que volver a correrlos.

# El diagnóstico

## La batería no suena, en ningún tema: es un bug

`dsp_musica` (`rom/src/efectos_de_sonido.s`) recibe el valor en B, y el
`rep #$20` / `and #$000F` con el que arma el índice de la sombra lo pone en
cero: **toda escritura de la música a las voces 6 y 7 llega al DSP como
cero**. Esas dos son las de la percusión (`DRUM_VOICES`, y también las de los
efectos). Grabando la ROM con un stream de sólo batería sale silencio de
principio a fin; con el arreglo, suena.

`git blame`: la voz 7 desde `854dba96` (2026-09-11, la música en la IRQ), la 6
desde `8c9c182e` (2026-09-24, la segunda voz de efectos). O sea que desde
ayer no suena ninguna voz de batería, y antes no sonaba la mitad. No lo cobró
nada porque ninguna prueba mira el audio de la música.

El arreglo, tres líneas por voz, está en el prototipo: guardar el valor en la
pila antes del `rep` (`xba` / `pha` / `xba`) y sacarlo con `pla` en vez del
`xba` que sigue al `sep`.

## Se pierde la mitad de lo que el MIDI toca

`escape_newyork`: 195 s, 2.660 notas, nueve canales, 80 negras por minuto. La
polifonía que pide va de 8 a 12 casi todo el tiempo, con picos de 20, contra
8 voces. El reparto de hoy (`assign`) le da **una voz fija a cada canal
melódico** y dos a la batería:

| Canal | Programa | Pide a la vez | Tiene |
|---|---|---:|---:|
| 2 | cuerdas (48), acordes de 3 notas de 12 s, velocidad 29 | 3 | 1 |
| 4 | polysynth (90), acordes | hasta 6 | 1 |
| 0 | piano (0) | 2 | 1 |
| 3 | bajo sintético (38), notas de 6 cuadros en octavas | 2 | 1 |
| 6 | polysynth (90) | 2 | 1 |
| 1 | sierra (81), la línea de bajo | 1 | 1 |
| 5 | clavinet (7) | 2 | **0** |
| 7 | onda cuadrada (80) | 1–3 | **0** |
| 9 | batería | 3 | 2 |

Se pierde el **55% del tiempo-nota**: 6% de canales sin voz y 50% de notas que
pierden la voz. Con 8 voces el piso es 23% —lo que pasa de 8 a la vez—.
Cuando un acorde arranca en un solo cuadro sobre una voz, las tres
preparaciones se pisan y suena la última: 864 notas.

## Los cortes en seco

Todo robo de una voz que suena es un `KON`, que pone la envolvente en cero de
golpe: un clic. Hoy son **204 notas cortadas mientras suenan**, **~1.100 colas
de release cortadas** al reusar la voz, y las **329 notas que se sueltan antes
de tiempo** de `notas-que-se-sueltan-antes-de-tiempo.md`. Es lo que mejor
explica "notas que se cortan muy abruptamente".

## Las muestras, a 4-8 kHz

El banco lo comparten los 22 temas y lo melódico tiene 40 KB: el piano queda a
6 kHz, las cuerdas a 5,5, la sierra a 6,1, el polysynth a 8,4, contra los
22 kHz del SoundFont. Y cada programa lleva **una sola muestra, la de la zona
del do central**: la línea de bajo con sierra (notas 24 a 40) toca `SAW0_60`
dos octavas abajo, con menos de 1 kHz de ancho de banda, cuando el SF2 trae
`SAW0_48` para esa zona. Es lo que más apaga el sonido: ver la medida de
abajo.

## Lo que el MIDI no tiene

Ni pitch bend, ni paneo, ni expresión, ni reverb ni chorus: sólo CC7 en los
últimos 20 s, para el fundido del final. La referencia de fluidsynth sale
seca, igual que la ROM, así que el eco del DSP no es lo que falta acá.

## Envolventes y volumen

Las familias de `sdsp.py` no están tan lejos del SF2. Lo que más difiere: el
bajo sintético y la sierra se sueltan en 25–30 ms en el SF2 y en la ROM
arrastran colas de 2,4 s (GAIN 14); el piano baja al 50% en 110 ms en vez de
apagarse en unos seis segundos.

La velocidad se convierte lineal, y fluidsynth atenúa 40·log10(127/v) dB —al
cuadrado—. Las cuerdas a velocidad 29 quedan 26 dB abajo en la referencia y
13 dB en la ROM: la mezcla sale corrida hacia los colchones.

**El atenuador del SF2 y el pico de las muestras no cambian nada acá**: medido,
los siete programas y los golpes del tema están normalizados de fábrica y su
atenuación inicial es ~0.

# Las variantes grabadas

Once, en `/shared/audio/2026-09-25-escape-newyork/`. Del 02 al 08 cada una
suma un cambio sobre la anterior, en el orden en que se harían; el 09 y el 10
aíslan los dos que más pesan. Cómo se grabaron —la pantalla de título tocando
el tema, snes9x, sin MSU-1, sin otra cosa encima, el tema entero— está en el
`LEEME.txt`.

| # | Qué suma | Stream del tema | Los 22 temas |
|---|---|---:|---:|
| 00 | referencia: fluidsynth + el SF2 | | |
| 01 | la ROM de hoy | 34.329 | 626.319 |
| 02 | la batería (el arreglo de `dsp_musica`) | +0 | +0 |
| 03 | no soltar a la que robó; sin muestra no ocupa voz | −1.760 | −71.072 |
| 04 | envolventes del SF2, y aire en la mezcla | +624 | +10.011 |
| 05 | curva de velocidad de fluidsynth, CC7/10/11 | +48 | +22.086 |
| 06 | reparto de las 8 voces en un solo grupo | +16.391 | +436.356 |
| 07 | rampa de 12 ms antes de reusar una voz que suena | +4.814 | +124.146 |
| 08 | banco con sólo este tema, a 22 kHz | −93 | (no aplica) |
| 09 | sólo el reparto, sobre 03 | +15.837 sobre 02 | +371.719 |
| 10 | sólo el banco a 22 kHz, sobre 02 | −1.131 | (no aplica) |

"Aire" es bajar el techo de cada voz un 20% y subir `MASTER` de `$60` a
`$78`: con la batería sonando y los sostenidos del SF2, la suma de las voces
saturaba el DSP, que recorta antes del volumen general —1.000 muestras
recortadas en el 04 sin esto; con esto, menos de 100 en todas—.

La diferencia espectral media contra la referencia (24 bandas, ventanas de
0,25 s), que orienta y no reemplaza al oído: 7,8 dB la ROM de hoy, 7,2 con
envolventes y volumen, 6,3 con el reparto, **4,2 con todo y las muestras a
22 kHz**; la tasa sola baja los agudos de 9 dB a 5, y el reparto solo, graves
y medios.

# Qué haría, en qué orden, y cuánto cuesta

## 0. El arreglo de `dsp_musica`: hecho

Hecho el 2026-09-25, en `1d8a2ba`. No es el del prototipo: el índice de la
sombra se arma con X en ocho bits (`sep #$10` / `tax` / `rep #$10`) y A no se
ensancha, así que B no se toca; sale tres bytes más corto por voz y pisa la
parte alta de Y, que `music_frame` no usa. Lo cobra
`pruebas/rpgmaker/test_bateria_suena.py`: toca el tema del título y exige que
la sombra de las voces 6 y 7 tenga lo que el stream les escribe, con volumen y
pitch distintos de cero. Sin el arreglo da rojo.

De paso: **la sombra no se inicializa**, así que antes de la primera
escritura de la música tiene lo que traía la WRAM ($55 en snes9x). Si un
efecto termina antes de que la música le haya escrito a su voz, se le
devuelve esa basura al DSP. Pendiente, chico.

**La saturación, con sólo el arreglo** (sin tocar la mezcla). Cómo se midió:
el `release` de `1d8a2ba` con el `lda #TEMA_TITULO` de `titulo.s` parcheado
en la ROM a cada tema —así cada uno suena solo, con sus muestras subidas por
`tema_asegurar`; se comprobó que no le falta ninguna—, snes9x, sin MSU-1, el
stream entero una vez, contando las muestras del audio del core (L+R) en el
tope. **El tope no es 32767 sino 24575**: el DSP recorta la suma de las voces
a 16 bits y recién después multiplica por `MASTER` (`$60`), así que un audio
que llega a ±24575 está recortado. El script es descartable; volver a medir
antes de fijar el aire.

| Tema | Sin el arreglo | Con el arreglo |
|---|---:|---:|
| T_VGFighterMAX_Masako (batalla) | 168.213 | 309.040 |
| hzbreach | 70.186 | 146.578 |
| TF3_1_awe | 60.996 | 110.894 |
| hzstream | 6.370 | 57.672 |
| rshinld | 2.876 | 10.344 |
| evilrhys | 148 | 6.920 |
| Lunar_Pyramid | 0 | 4.574 |
| 3D-Galax | 0 | 3.404 |
| lufsorr | 268 | 2.336 |
| cd4 | 102 | 1.036 |
| cd2 | 0 | 894 |
| Astpgmarch | 24 | 858 |
| Fantasia_Of_The_Wind (título) | 2 | 542 |
| wb3shop | 0 | 382 |
| escape_newyork | 0 | 140 |
| C3classi | 0 | 112 |
| wb3mlair, Gaden, KSSMKEND, vswar, dcbest, golden_axe-turtlevillage2 | 0 | 0 |

O sea: **16 de los 22 temas recortan con la batería de vuelta**, y tres ya
recortaban fuerte sin ella —el de batalla el que más—, así que el aire del
paso 2 no es sólo por la batería. `golden_axe-turtlevillage2` es todo
percusión: sin el arreglo su pico era 0, silencio entero. `dcbest` no tiene
batería y da igual en las dos.

## 1. Las notas que se sueltan antes de tiempo: hecho

Hecho el 2026-09-25 (commit "Música: una nota robada no suelta a la que le
robó la voz"). El release se agenda al final de `build_events`, sólo para las
notas que llegan a su fin siendo dueñas de la voz, y no va cuando la voz se
reusa en el mismo cuadro en que la nota termina; y una nota sin muestra ya
no ocupa voz.

**Lo que dejó de pasar**, contado con la lógica vieja sobre las mismas
entradas: **564 notas y 14.486 cuadros** se soltaban antes de su fin en los
22 temas —341 de `escape_newyork` (el prototipo contó 329 notas robadas; acá
se cuentan las que se soltaban), 168 de `cd4`, 31 de
`Fantasia_Of_The_Wind`, 19 de `3D-Galax` y 5 entre `hzstream`, `TF3_1_awe`
y `hzbreach`—, y **11.024 notas sin muestra** ocupaban voz en los nueve
temas que no aportan al banco. **El stream de los 22 bajó de 626.319 a
555.247 B (−11,3%)**, igual que en el prototipo. La saturación casi no
cambió. Lo cobra `pruebas/herramientas/test_musica_stream.py`.

## 2. Envolventes del SoundFont, con aire: hecho, con más aire que el pensado

Hecho el 2026-09-25 (commit "Música: las envolventes salen del SoundFont, y
la mezcla tiene aire"):

* **`gunter sf2 --extract --json` devuelve la envolvente de la zona**,
  generadores 33 a 40, ya resuelta —la del instrumento más la del preset, con
  los defaults y topes de la especificación— y en las unidades del SF2. **Hay
  que correr `just herramientas`**: el conversor se niega, con ese mensaje,
  con un `gunter` anterior.
* `sdsp.envelope` la traduce a ADSR1, ADSR2 y el GAIN del release, con las
  dos cosas que mostró la grabación —release lineal debajo de 100 ms, y la
  caída exponencial a cero donde el SF2 anda por -40 dB—. Da exactamente lo
  mismo que el prototipo en 3.456 combinaciones de programa y tecla —los
  programas que el SF2 tiene, una tecla de cada tres entre la 20 y la 98—.
  Las ocho familias de `sdsp.py` se fueron.
* **El aire**: con 0,8 y MASTER en `$78`, lo que proponía el prototipo, los
  16 temas seguían recortando —hzbreach 107.218 muestras, la batalla
  59.982—: el prototipo lo había medido en `escape_newyork`, que es de los
  que menos recortan. Quedó en **0,5**: techo de 48 por voz y 42 la
  percusión, MASTER en `$7F`, que es el tope del registro. Los efectos de
  sonido bajan su techo lo mismo que subió MASTER y suenan igual que antes.

**Cómo se midió** —el mismo método que el del punto 0—: el `release` con el
`lda #TEMA_TITULO` de `titulo.s` parcheado a cada tema, snes9x sin MSU-1, el
stream entero una vez, contando las muestras del audio del core (L+R) en el
tope, que es `32767·MASTER/128` —24.575 con `$60`, 30.719 con `$78`, 32.511
con `$7F`—. LUFS integrados con `ebur128` de ffmpeg sobre la misma
grabación. Los scripts, descartables, en el scratchpad de la sesión
(`audio-pasos-1-2/sat.py`).

| Tema | Stream hoy | Paso 1 | Paso 2 | Recortes hoy | Paso 1 | Aire 0,8 | Paso 2 (0,5) | Pico hoy → paso 2 | LUFS hoy → paso 2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| hzstream | 13.042 | 11.990 | 11.999 | 57.672 | 58.114 | 34.718 | 36 | -2.5 → -0.1 | -7.6 → -9.6 |
| escape_newyork | 34.329 | 32.569 | 33.193 | 140 | 108 | 190 | 0 | -2.5 → -2.6 | -15.6 → -17.3 |
| TF3_1_awe | 23.444 | 21.546 | 21.546 | 110.894 | 113.112 | 78.030 | 468 | -2.5 → -0.1 | -7.1 → -9.0 |
| T_VGFighterMAX_Masako | 156.304 | 147.088 | 148.312 | 309.040 | 311.370 | 59.982 | 70 | -2.5 → -0.1 | -6.6 → -10.7 |
| evilrhys | 36.338 | 35.126 | 35.876 | 6.920 | 6.864 | 4.314 | 0 | -2.5 → -0.5 | -11.0 → -13.6 |
| lufsorr | 16.161 | 10.533 | 11.529 | 2.336 | 2.346 | 2.202 | 0 | -2.5 → -0.4 | -11.2 → -12.6 |
| cd4 | 50.885 | 43.087 | 45.886 | 1.036 | 914 | 208 | 0 | -2.5 → -3.4 | -14.4 → -17.4 |
| C3classi | 33.498 | 26.532 | 27.537 | 112 | 100 | 38 | 0 | -2.5 → -3.7 | -14.8 → -15.9 |
| rshinld | 12.272 | 7.274 | 7.406 | 10.344 | 10.566 | 9.372 | 4 | -2.5 → -0.1 | -10.6 → -12.1 |
| cd2 | 30.461 | 29.225 | 29.261 | 894 | 892 | 348 | 0 | -2.5 → -2.7 | -12.5 → -15.0 |
| hzbreach | 30.758 | 29.620 | 29.626 | 146.578 | 148.166 | 107.218 | 858 | -2.5 → -0.1 | -6.8 → -8.6 |
| wb3mlair | 9.117 | 7.335 | 7.497 | 0 | 0 | 0 | 0 | -4.8 → -6.2 | -22.2 → -22.2 |
| Astpgmarch | 6.521 | 6.350 | 6.527 | 858 | 834 | 850 | 0 | -2.5 → -1.9 | -10.7 → -14.0 |
| Gaden | 7.271 | 5.357 | 5.639 | 0 | 0 | 0 | 0 | -7.5 → -12.7 | -19.0 → -23.0 |
| 3D-Galax | 60.346 | 49.146 | 49.080 | 3.404 | 3.490 | 1.022 | 0 | -2.5 → -2.3 | -14.7 → -16.9 |
| wb3shop | 9.916 | 9.046 | 9.046 | 382 | 368 | 422 | 0 | -2.5 → -3.0 | -16.9 → -19.2 |
| KSSMKEND | 12.942 | 10.980 | 10.980 | 0 | 0 | 0 | 0 | -6.1 → -9.0 | -22.2 → -23.7 |
| vswar | 21.289 | 20.536 | 20.536 | 0 | 0 | 0 | 0 | -3.7 → -5.3 | -15.1 → -16.9 |
| Lunar_Pyramid | 37.190 | 32.792 | 32.792 | 4.574 | 4.304 | 498 | 0 | -2.5 → -3.0 | -13.4 → -15.5 |
| dcbest | 5.017 | 5.017 | 5.017 | 0 | 0 | 0 | 0 | -7.7 → -10.5 | -20.8 → -21.1 |
| golden_axe-turtlevillage2 | 831 | 831 | 831 | 0 | 0 | 0 | 0 | -7.4 → -11.1 | -17.0 → -20.7 |
| Fantasia_Of_The_Wind | 18.387 | 13.267 | 14.902 | 542 | 592 | 2.018 | 0 | -2.5 → -0.6 | -12.1 → -13.1 |
| **Los 22** | 626.319 | 555.247 | 565.018 | 655.726 | 662.140 | 301.430 | 1.436 | | |


**Lo que cuesta el aire**: donde antes no recortaba, el nivel baja
20·log10(0,5·127/96) = −3,6 dB —`escape_newyork` de -15,6 a -17,3 LUFS,
con las envolventes nuevas en el medio—. Los que recortaban bajan más, pero
lo que perdieron era distorsión: la batalla, de -6,6 a -10,7 LUFS. Recortan
cinco, a lo sumo 858 muestras de 6,3 millones (hzbreach).

**Lo que no se pudo con un número global**: cero recortes en todos sin
bajar el nivel. Midiendo el pico verdadero de cada tema con el techo en un
cuarto —24 y 21, sin recortes en ninguno— y escalando, para que no recorte
ninguno el techo global tiene que ser 1,56 veces ese cuarto (hzbreach),
contra los 2 de hoy: otro −2,2 dB para todos. Un techo por tema dejaría a
los tranquilos donde están, pero el pico no se deja estimar desde el stream:
contra la suma de los volúmenes de las voces, la relación varía de 85 a 135
entre los temas densos, así que la regla necesita un margen que se come lo
que gana. Lo que sí funcionaría es una tabla de techos medida, que habría que
volver a medir con cada cambio de la mezcla —la curva de velocidad del 3, el
reparto del 5—. No se hizo: es una decisión para después del 5.

**Stream**: +9.771 B sobre el paso 1 (+1,8%), lo previsto: el piano cambia
de ADSR2 por tecla. Lo cobra `test_musica_stream.py`, con el SF2 de verdad:
el release del bajo sintético y el decaimiento del piano por tecla.

**Para escuchar**: `/shared/audio/2026-09-25-pasos-1-y-2/`, con su
`LEEME.txt`.

## 3. Curva de velocidad y controladores: hecho

Hecho el 2026-09-26 (commit "Música: la velocidad al cuadrado, y los
controladores del MIDI"). Medido sobre `55098bd`, con el `release` de hoy,
que tiene **32 temas** y no los 22 de las tablas de arriba: los diez nuevos
van al final de la tabla.

**La curva**, medida con fluidsynth y el SF2 —una nota sola, RMS, contra
velocidad 127—: la velocidad baja 40·log10(127/v) dB exactos (64 da -11,9;
29, -25,7). CC7 y CC11 igual, cada uno —CC7 medido contra 100, su valor de
GM, así que un canal en 127 suena **+4 dB**—; el paneo es seno y coseno con
el centro a -3 dB de un paneo total (0 da +3,0 dB y silencio; 32, +2,3 y
-5,3). Así quedó `sdsp.volume`; el piso bajó de 4 a 2.

**Qué entró** —`midi.py` ya no los tira; ver su encabezado—:

* **CC7, CC11 y CC10**, a la nota que arranca y a la que ya sonaba (también
  en su cola). CC7 hay 3.851 en 25 temas, CC10 1.532 en 21, CC11 4.427 en
  tres (`vswar`, `3D-Galax`, `Fire_Mustang`).
* **El pitch bend**, con el rango del RPN 0 (CC101 y CC100 en cero, y CC6/
  CC38). Lo usan de verdad tres temas: `3D-Galax` (194, la sierra de la
  melodía, 116 con la nota sonando), `dcbest` (396 en el bajo, casi todos
  **entre** notas: desafinan la que viene, hasta 1,2 semitonos) y `vswar`
  (445 en el canal 13, que no tiene voz: no suena). Entró porque cuesta
  **2.270 B** en los 32 temas y la altura al arrancar la nota es gratis.
  `3D-Galax` pide un rango de **95 semitonos**; fluidsynth lo respeta
  (medido: la caída llega a -20,6 semitonos) y un sintetizador GS lo topa en
  24. Se siguió a fluidsynth, que es la referencia y de donde sale la pista
  de MSU-1: si suena raro, es lo primero para mirar. Un CC101 sin su CC100
  no elige el RPN —medido; es el caso de `dcbest`, que queda en 2—.
* **El pedal (CC64)**, que no es un evento del stream: alarga las notas que
  se sueltan con el pedal abajo. Lo usan el título (`Fantasia_Of_The_Wind`,
  38, el piano) y `pn28year` (606). **Baja** el stream 5.481 B, porque una
  nota sostenida hasta que la roba otra ya no escribe su release.

**Qué no entró**, y quién lo usa:

* **Modulación (CC1)**: sólo `Tnt07` de verdad (392); `vswar` y `11h035`
  la mandan en 0. Es el vibrato del SF2, o sea una escritura de altura por
  cuadro mientras suena, o un LFO en el driver. Anotado para el formato.
* **Reverb y chorus (CC91, CC93)**: en 13 temas, casi siempre un valor fijo
  al principio. La referencia sale seca (`-R 0 -C 0`) y el eco del DSP está
  apagado: va con el eco, si alguna vez se prende.
* **Los NRPN del AWE32** de `TF3_1_awe` (4.134, MSB 127): corte y resonancia
  del filtro, que el DSP no tiene.
* **El aftertouch**: ningún tema lo usa.
* **El paneo por tecla del SF2** —el charles a un lado, el bombo al centro—:
  `gunter` no devuelve el generador 17. La batería suena al centro salvo por
  el CC10 de su canal.
* **Los cambios de programa a mitad del tema**, que ya se ignoraban (vale el
  primero de cada canal): `hzbreach`, `Astpgmarch` y `bubstix`.

**Bytes del stream**, antes → después, y **saturación** —muestras en el
tope, L+R, con el método del paso 2 y **el mismo aire**: 0,5 y MASTER
`$7F`—, con pico (dBFS) y LUFS integrados:

| Tema | Stream antes | Paso 3 | Recortes antes | Paso 3 | Pico | LUFS |
|---|---:|---:|---:|---:|---:|---:|
| hzstream | 11.999 | 11.999 | 36 | 36 | -0.1 → -0.1 | -9.6 → -9.6 |
| escape_newyork | 33.193 | 33.235 | 0 | 0 | -2.6 → -5.4 | -17.3 → -20.7 |
| TF3_1_awe | 21.546 | 30.054 | 460 | 0 | -0.1 → -1.8 | -9.0 → -13.4 |
| T_VGFighterMAX_Masako | 148.312 | 148.312 | 70 | 290 | -0.1 → -0.1 | -10.7 → -10.3 |
| evilrhys | 35.876 | 35.882 | 0 | 232 | -0.5 → -0.1 | -13.6 → -11.1 |
| lufsorr | 11.529 | 12.231 | 0 | 0 | -0.4 → -2.4 | -12.6 → -15.0 |
| cd4 | 45.886 | 45.799 | 0 | 0 | -3.4 → -3.7 | -17.4 → -17.9 |
| C3classi | 27.537 | 27.537 | 0 | 0 | -3.7 → -3.6 | -15.9 → -16.6 |
| rshinld | 7.406 | 8.906 | 0 | **4.552** | -0.1 → -0.1 | -12.1 → -8.7 |
| cd2 | 29.261 | 29.255 | 0 | 0 | -2.7 → -4.1 | -15.0 → -16.7 |
| hzbreach | 29.626 | 29.626 | 816 | 834 | -0.1 → -0.1 | -8.6 → -8.6 |
| wb3mlair | 7.497 | 7.497 | 0 | 0 | -6.2 → -9.3 | -22.2 → -24.7 |
| Astpgmarch | 6.527 | 6.527 | 0 | 0 | -1.9 → -1.7 | -14.0 → -14.0 |
| Gaden | 5.639 | 5.639 | 0 | 0 | -12.7 → -17.9 | -23.0 → -31.3 |
| 3D-Galax | 49.080 | 52.615 | 0 | 166 | -2.3 → -0.1 | -16.9 → -13.9 |
| wb3shop | 9.046 | 9.046 | 0 | 0 | -3.0 → -5.1 | -19.2 → -21.3 |
| KSSMKEND | 10.980 | 10.980 | 0 | 0 | -9.0 → -10.9 | -23.7 → -24.7 |
| vswar | 20.536 | 26.345 | 0 | 0 | -5.3 → -6.8 | -16.9 → -20.3 |
| Lunar_Pyramid | 32.792 | 32.792 | 0 | 0 | -3.0 → -0.3 | -15.5 → -14.1 |
| dcbest | 5.017 | 6.594 | 0 | 0 | -10.5 → -6.3 | -21.1 → -17.0 |
| golden_axe-turtlevillage2 | 831 | 831 | 0 | 0 | -11.2 → -8.2 | -20.7 → -17.7 |
| Fantasia_Of_The_Wind | 14.902 | 14.545 | 0 | 0 | -0.6 → -4.9 | -13.1 → -16.3 |
| Fire_Mustang_Intro_And_Level_2_By_Luiz_Vasco | 15.030 | 15.030 | 0 | 0 | -4.2 → -3.9 | -16.2 → -15.8 |
| bubstix | 29.988 | 29.988 | 0 | 0 | -2.3 → -3.4 | -15.8 → -17.1 |
| wb3town | 6.002 | 6.002 | 0 | 0 | -5.7 → -7.7 | -18.2 → -20.2 |
| 11h035 | 17.342 | 17.234 | 0 | 0 | -4.9 → -7.8 | -18.0 → -21.2 |
| prepara | 630 | 630 | 0 | 0 | -9.3 → -13.8 | -20.5 → -26.3 |
| T_ProjectJustice_DiscLoad | 15.819 | 15.819 | 0 | 0 | -6.5 → -7.9 | -22.9 → -24.3 |
| pn28year | 19.767 | 17.781 | 4 | 0 | -0.1 → -4.8 | -13.0 → -19.2 |
| Tnt07 | 8.299 | 8.299 | 0 | 0 | -7.5 → -9.6 | -21.8 → -23.8 |
| Deflector1 | 31.025 | 31.025 | 0 | 178 | -1.6 → -0.1 | -16.6 → -14.2 |
| MML2_MotherZone | 2.640 | 2.640 | 0 | 0 | -10.7 → -9.2 | -21.2 → -19.7 |
| **Los 32** | 711.560 | 730.695 | 1.386 | 6.288 | | |
| **Los 22 de las tablas de arriba** | 565.018 | 586.247 | 1.382 | 6.110 | | |

* **Stream: +19.135 B (+2,7%)** en los 32. Desglosado: la curva sola −12
  B, CC7/10/11 +22.328, el bend +2.270, el pedal −5.481. Los que cambian
  son los que usan CC de verdad: `TF3_1_awe` +39% (dos ondas cuadradas con
  CC7 de compuerta, 34 → 0 → 34 cada ~10 cuadros, y paneo en todo),
  `dcbest` +31% (el bend), `vswar` +28%, `rshinld` +20%. Seguir
  actualizando las colas —las voces cuya nota ya se soltó— cuesta 1.195 B
  de eso: no vale un caso aparte.
* **Saturación: de 1.386 a 6.288 muestras**, 4,5 veces más, y casi todo en
  **`rshinld` (4.552, de 3,1 millones)**: CC7 en 127 en casi todos sus
  canales, +4 dB sobre el techo que el aire suponía. Los demás que empiezan
  a recortar lo hacen poco (la batalla 290, `evilrhys` 232, `Deflector1`
  178, `3D-Galax` 166), y `TF3_1_awe` deja de recortar. **El aire no se
  tocó**, como pidió taro: la tabla de techos por tema del paso 2 había que
  volver a medirla después de este paso y del 5.
* **El nivel** baja en los que tienen colchones suaves (`escape_newyork`
  -3,4 LUFS, `Gaden` -8,3, `pn28year` -6,2) y sube en los que piden CC7
  alto (`rshinld` +3,4, `dcbest` +4,1). Contra la referencia —fluidsynth con
  el SF2, LUFS integrados—, en los 13 temas que aportan al banco, y por eso
  suenan enteros, la distancia ROM − referencia queda **más pareja entre
  temas: su desvío baja de 2,7 dB a 1,5**. Contando los 22 con los
  mutilados no cambia (4,1), porque ahí manda lo que no suena.
* **Hay estéreo**: `TF3_1_awe` pasa de mono a lado/centro -8,8 dB.
* **El fundido del final de `escape_newyork` existe**: baja unos 25 dB en
  los últimos 12 s, donde antes seguía al mismo nivel hasta el corte.

**Lo cobra** `pruebas/herramientas/test_musica_stream.py`: la curva, CC7 a
mitad de una nota, CC7 por CC11, el paneo, el bend antes y durante, que un
control no toque otro canal ni la altura de la batería, y en el lector el
RPN 0 y el pedal. Las ocho dan rojo con las `tools/` de `55098bd`.

**Para escuchar**: `/shared/audio/2026-09-26-paso-3/`, con su `LEEME.txt`:
`escape_newyork`, la batalla, el título (el pedal), `3D-Galax` (CC11 y el
bend), `vswar` (CC11), `rshinld` (el que más recorta) y `TF3_1_awe` (el
estéreo y la compuerta), antes y después.

### Lo que el stream lleva después del paso 3: la lista para el formato

Todo cuenta por voz del DSP; las cantidades son de los 32 temas del
`release`, 3.741 s de música, con el reparto de hoy.

**Por nota** (50.565 notas que arrancan):

* altura: 14 bits, `sdsp.pitch_for(tecla + bend del canal, raíz, tasa)`
  —con el bend es una altura cualquiera, no una tecla—; la batería no se
  transpone ni se dobla;
* muestra (SRCN), ADSR1 y ADSR2: juntos son "el instrumento", y ADSR2
  cambia por tecla dentro de un programa (el piano);
* volumen izquierdo y derecho: **distintos en 12.056 notas (24%)**, muchas
  por un paneo de 60 a 63, casi al centro. Salen de cinco cosas —velocidad,
  CC7, CC11 y CC10 del canal, y el techo melódico o de batería—, así que un
  formato que guarde la velocidad por nota y el estado del canal aparte los
  reconstruye; guardar L y R ya calculados es lo de hoy;
* KON.

**Por release** (15.450): ADSR1 en 0 y el GAIN del release, que es **por
instrumento y tecla** —sale de la misma envolvente que ADSR1 y ADSR2—, así
que puede vivir en la tabla del instrumento y el evento ser "soltar la voz".

**Por controlador, a una voz que ya suena** —en 3.976 cuadros, 1,06 por
segundo de música en promedio pero muy concentrados: `vswar` 9,3 cuadros
por segundo, `pn28year` 8,5, `TF3_1_awe` 7,6; 24 de los 32 no tienen
ninguno—:

* **volumen L y R de una voz**: 4.301. Va el par entero: un CC cambia el
  volumen o el paneo, y los dos lados se recalculan. Un CC7 de canal
  escribe **todas las voces de ese canal a la vez**, así que el peor cuadro
  son 8 voces × 2 registros = 16 escrituras (`rshinld`, que tiene pocos
  cuadros con controladores —36— pero cada uno toca las ocho). Un evento
  "volumen del canal" que el driver aplique a sus voces lo achicaría, pero
  el driver tendría que saber qué voz es de qué canal, y con el reparto del
  5 eso cambia nota a nota;
* **altura de una voz**: 563, los bends con la nota sonando (`dcbest` 395,
  `3D-Galax` 168). Los dos bytes de PITCH;
* nada más: la expresión y el volumen se funden en L y R, y el pedal ya
  viene aplicado a los fines de las notas.

**Lo que no lleva y el formato podría querer después**: la modulación (CC1,
`Tnt07`: vibrato, o sea altura por cuadro o un LFO del driver), el paneo por
tecla de la batería y la rampa del 5.

## 4. El formato por nota

`la-musica-pesa-789-kb.md`, idea 1. Va **acá, antes del reparto**, por los
bytes: el reparto del 5 suma **+74% de stream** en el formato de hoy —las
voces cambian de instrumento y de volumen seguido, y cada cambio son tres
bytes por registro—; en el formato por nota es un índice de instrumento de un
byte cuando cambia. Lo que este estudio le pide al formato, para diseñarlo
una sola vez:

* el instrumento como índice a (SRCN, ADSR1, ADSR2), y el ADSR2 puede variar
  por tecla dentro de un programa;
* volumen izquierdo y derecho distintos cuando hay paneo (24% de las
  notas desde el paso 3);
* el GAIN del release por instrumento, no uno por tema;
* un evento de "rampa" de un byte para el punto 5, o que el decodificador la
  deduzca;
* cambios de volumen de un canal que suena, por CC7/CC11/CC10, y de altura
  por el bend: la lista exacta, con cuántos hay, está al final del paso 3.

## 5. El reparto de las ocho voces, y la rampa

Las ocho en un solo grupo, robando por prioridad —lo del 06—, y la rampa de
12 ms antes de reusar una voz que suena —lo del 07—. Es lo que devuelve los
acordes, el clavinet y la onda cuadrada, y lo que más ataca los clics:
**287 robos en vez de 1.068**, y cada uno con rampa en vez de un `KON` en
seco. **Costos**:

* **Ciclos**: el peor cuadro pasa de 56 a 80 escrituras al DSP, +43% del peor
  caso de `irq_musica` —del orden de 20 a 29 líneas—.
* **ARAM**: los canales que hoy no tienen voz suman sus programas al banco:
  7 muestras más entre los 22 temas, que bajan la tasa de las demás —el piano
  de 6 a 4,5 kHz—. Eso lo compensa el 6.
* **Stream**: ver el 4.

La rampa se puede hacer también del lado del SPC700 —que el driver baje las
voces antes de cada `KON`—, pero le agrega un cuadro de latencia o un temporizador
al driver; conviene decidirlo con el formato.

## 6. Las muestras: presupuesto por paquete y zonas

Es lo que más cambia el sonido (el 10 solo ya se acerca más que el 07) y lo
más caro. Las 11 muestras del tema a 22 kHz ocupan 36,5 KB de ARAM contra
~12 KB de hoy; el mapa 1, donde suena, también sube la lluvia y el trueno
entero (23,8 KB), así que **hay que medir qué tasa entra de verdad** en su
paquete. Es `wishlist/presupuesto-de-muestras-por-paquete.md`, y detrás
`wishlist/una-muestra-por-instrumento.md`: la línea de bajo con sierra es el
caso que la justifica. Cuesta cuadros de carga al cambiar de mapa, que taro
ya dijo que prefiere pagar.

# Qué medir en los otros temas

Con los scripts de `tools/audio/proto/` en la rama del prototipo:

* **La batería que vuelve**: medido en el 0, con la tabla; volver a medirlo
  con las envolventes puestas antes de fijar el aire.
* **Polifonía contra 8 voces y tiempo-nota perdido**, con el reparto de hoy y
  con el del 06: `robos.py` lo da por canal. `escape_newyork` puede no ser el
  peor.
* **Qué temas usan CC7, CC10, CC11 y pitch bend**, y cuánto stream sumarían.
* **Golpes recortados sin fundido**: `_build_drum` corta en 0,5 s sin
  fundido, y el platillo, el ride y el charles abierto del SF2 duran más y
  hasta traen loop; eso es un corte en seco en cada platillo. En
  `escape_newyork` no pasa —sus cuatro golpes duran menos de 0,2 s—.
* **Notas lejos del do central**, que suenan con la zona equivocada.
* El de batalla, `T_VGFighterMAX_Masako`, que es el más pesado y el que más
  se oye.
