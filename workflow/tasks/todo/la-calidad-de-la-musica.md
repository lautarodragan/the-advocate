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
el 0, el 1 y el 2**, el 2026-09-25, **y el 3, el 4 y el 5** el 2026-09-26:
ver cada uno abajo. Después del 5, el mismo día: **el 5b**, la frase de la
batalla que el reparto cortaba, y **el aire por tema** (la opción B, al final
del 5). El 6, el mismo día, **medido, prototipado y con el plan**: hecho su
primer paso, lo demás espera que taro decida escuchando.


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

## 4. El formato por nota: hecho

Hecho el 2026-09-26 (commits "Música: el stream es por nota, y el 65816 lo
expande a las mismas escrituras" y "Música: la ROM anota lo que le pide al
DSP, y una prueba lo compara cuadro a cuadro"). Es la idea 1 de
`la-musica-pesa-789-kb.md`. El porqué de cada decisión está donde vive: "el
formato por nota" en `tools/audio/snes_music.py`, el encabezado de
`tools/protocol/music.toml` y `music_frame` en `rom/src/musica.s`.

**La propiedad que lo sostiene: la secuencia de escrituras al DSP, cuadro por
cuadro, es la de antes.** `escrituras` es lo que era `pack` —la
especificación—, y el conversor se corta si un tema, decodificado, no la da.
El SPC700 no cambió.

### El formato

Un tema es su stream y su tabla de **sonidos**: seis bytes —PITCH_L,
PITCH_H, SRCN, ADSR1, ADSR2 y el GAIN del release— por cada combinación que
el tema toca. La voz va en los tres bits bajos del opcode.

| Opcodes | Nombre | Argumentos | Qué escribe |
|---|---|---|---|
| `$00`-`$07` | `OP_NOTE_V0`-`V7` | sonido | PITCH, SRCN, ADSR1, ADSR2; KON al cerrar el cuadro |
| `$08`-`$0F` | `OP_NOTE_VOL_Vv` | volumen, sonido | VOL_L = VOL_R, y lo de `OP_NOTE` |
| `$10`-`$17` | `OP_NOTE_PAN_Vv` | izquierda, derecha, sonido | VOL_L, VOL_R, y lo de `OP_NOTE` |
| `$18`-`$1F` | `OP_RELEASE_Vv` | — | ADSR1 en 0 y el GAIN del sonido de la voz |
| `$20`-`$27` | `OP_RELEASE_GAIN_Vv` | GAIN | ADSR1 en 0 y ese GAIN |
| `$28`-`$2F` | `OP_SET_VOL_Vv` | volumen | VOL_L = VOL_R, a una voz que suena |
| `$30`-`$37` | `OP_SET_PAN_Vv` | izquierda, derecha | VOL_L y VOL_R, a una voz que suena |
| `$38`-`$3F` | `OP_SET_PITCH_Vv` | altura (palabra) | PITCH_L y PITCH_H, a una voz que suena |
| `$40`-`$5F` | `OP_WAIT_1`-`32` | — | cierra el cuadro —dispara el KON— y espera |
| `$60` | `OP_WAIT` | cuadros (palabra) | lo mismo, más largo; 0 dispara sin esperar |
| `$61` | `OP_DSP` | registro, valor | una escritura cruda, no de voz: el KOF del final |
| `$62` | `OP_INIT` | — | el arranque del DSP, la tabla `dsp_init_*`, y KON y KOF en 0 |
| `$63` | `OP_END` | — | vuelve a empezar |

Todas las escrituras de voz pasan por el caché del 65816 —`MUS_SOMBRA`, ocho
registros por voz—, así que el stream nunca dice lo que no cambia: una nota
en la misma voz y con el mismo volumen que la anterior son **dos bytes**, la
familia con la voz y el sonido, y escribe sólo lo que el caché no tiene —en
el caso típico la altura y el ADSR1 que el release había apagado—. Antes eran
tres bytes por escritura: una nota así eran 9 más su parte del KON.

**De qué está hecho**, en los 32 temas del `release`: notas sin volumen 50%,
esperas 16,5%, notas con volumen 11,7%, releases 7,4%, notas con paneo 5,9%,
la tabla de sonidos 4,5%, cambios de volumen y altura a una voz que suena 4%.
`OP_RELEASE_GAIN` no lo usa ningún tema todavía: está para la rampa del 5.

### Bytes

Del `conversor.log` de cada cartucho, que los imprime por tema. Antes: el
`release` de `fb12bbb`.

| Tema | Antes | Stream | Sonidos | Después | % |
|---|---:|---:|---:|---:|---:|
| T_VGFighterMAX_Masako | 148.312 | 40.796 | 540 | 41.336 | 28% |
| 3D-Galax | 52.615 | 14.548 | 276 | 14.824 | 28% |
| cd4 | 45.799 | 12.395 | 276 | 12.671 | 28% |
| evilrhys | 35.882 | 9.648 | 624 | 10.272 | 29% |
| escape_newyork | 33.235 | 8.539 | 426 | 8.965 | 27% |
| Lunar_Pyramid | 32.792 | 7.820 | 252 | 8.072 | 25% |
| Deflector1 | 31.025 | 8.455 | 528 | 8.983 | 29% |
| TF3_1_awe | 30.054 | 9.538 | 426 | 9.964 | 33% |
| bubstix | 29.988 | 7.793 | 540 | 8.333 | 28% |
| hzbreach | 29.626 | 8.645 | 630 | 9.275 | 31% |
| cd2 | 29.255 | 6.696 | 246 | 6.942 | 24% |
| C3classi | 27.537 | 7.262 | 438 | 7.700 | 28% |
| vswar | 26.345 | 8.992 | 192 | 9.184 | 35% |
| pn28year | 17.781 | 5.364 | 264 | 5.628 | 32% |
| 11h035 | 17.234 | 4.433 | 360 | 4.793 | 28% |
| T_ProjectJustice_DiscLoad | 15.819 | 4.230 | 78 | 4.308 | 27% |
| Fire_Mustang_Intro_And_Level_2_By_Luiz_Vasco | 15.030 | 3.870 | 114 | 3.984 | 27% |
| Fantasia_Of_The_Wind | 14.545 | 3.672 | 528 | 4.200 | 29% |
| lufsorr | 12.231 | 3.002 | 330 | 3.332 | 27% |
| hzstream | 11.999 | 3.434 | 594 | 4.028 | 34% |
| KSSMKEND | 10.980 | 2.885 | 114 | 2.999 | 27% |
| wb3shop | 9.046 | 2.469 | 132 | 2.601 | 29% |
| rshinld | 8.906 | 3.040 | 402 | 3.442 | 39% |
| Tnt07 | 8.299 | 2.511 | 102 | 2.613 | 31% |
| wb3mlair | 7.497 | 2.073 | 216 | 2.289 | 31% |
| dcbest | 6.594 | 2.696 | 30 | 2.726 | 41% |
| Astpgmarch | 6.527 | 1.835 | 330 | 2.165 | 33% |
| wb3town | 6.002 | 1.481 | 156 | 1.637 | 27% |
| Gaden | 5.639 | 1.203 | 114 | 1.317 | 23% |
| MML2_MotherZone | 2.640 | 509 | 24 | 533 | 20% |
| golden_axe-turtlevillage2 | 831 | 255 | 12 | 267 | 32% |
| prepara | 630 | 205 | 132 | 337 | 53% |
| **Los 32** | 730.695 | 200.294 | 9.426 | 209.720 | 28,7% |

`test-special`, con sus 5 temas: de 221.558 a 61.910 (27,9%).

**El cartucho `release`**, sumando los segmentos del `.dbg`: de 3.649.137 B
usados a 3.128.883 (87,0% a 74,6%), **520 KB libres más**. El banco 0 paga
el decodificador: de 1.825 B libres a 1.168 —581 del decodificador y 76 de
la bitácora—. Si hace falta, el decodificador se puede mudar al banco 1 con
un puente para `dsp_musica`, como la pelea.

### Ciclos

Medidos con una sonda en una copia descartable de los dos árboles —`fb12bbb`
y éste—: la línea de barrido al entrar y al salir de `music_tick`, en cada
cuadro de los 32 temas enteros, en snes9x. La IRQ cae en la línea 112.

* **El peor cuadro de todos baja de 94 líneas a 89.** Es la vuelta al
  principio del de batalla, con el arranque y las ocho voces escritas
  enteras; lo que manda ahí es la espera del SPC700 por cada escritura.
* Lo que sube es el cuadro con muchas notas y pocas escrituras: el de
  `escape_newyork` con 16 notas y 43 escrituras pasa de 65 líneas a 78.
* Por regresión sobre los 224.436 cuadros: antes, 1,05 + 1,59 líneas por
  escritura; ahora, 1,02 + 1,34 por escritura + 1,27 por evento de voz. En
  total la música ocupa un 7,8% más de líneas. Una nota cuyo sonido ya
  estaba entero en el caché cuesta del orden de una línea y cuarto.

Lo que queda para ganar, si el 5 lo pide: en `nota_sonido`, copiar el sonido
y comparar en línea, sin un `jsr` por registro —del orden de 75 ciclos por
nota, estimado—.

### RAM

Nada en la `BSS`, y la página cero **gana** el byte de `wait_frames`. Lo del
decodificador va a la RAM lejana, **`$6C00` a `$6FFF`**, que no usaba nadie
(`ram_lejana.s` tiene el mapa): `MUS_SOMBRA` 128 B —72 usados, ocho registros
y el GAIN del sonido por voz—, 11 B de estado —la espera de dieciséis bits, el
KON juntado, el que hay que bajar, dónde empiezan los sonidos del tema, qué
voces ya tuvieron nota y GAIN—, y la bitácora de la prueba, 4 B y 512 de
anillo.

### Cómo se verificó

* **En Python, en cada armado**: `build_varios` decodifica el stream de cada
  tema con `decodificar` —el modelo de `music_frame`, que imita también que
  el caché del 65816 no sabe decir "no sé"— y se corta si no da `escrituras`.
  Pasa en los 32 temas del `release` y los 5 de `test-special`. Antes de
  cambiar el formato, `escrituras` se comparó contra los streams viejos de
  los dos cartuchos: las mismas escrituras en los mismos cuadros.
* **En la ROM**: `dsp_musica` anota lo que recibe en `MUS_BITACORA` si la
  prueba la prende, y `test_musica_escrituras.py` toca temas enteros y lo
  compara cuadro por cuadro contra el modelo corriendo sobre los bytes del
  cartucho: el del título, prendido por el código principal al encender;
  `escape_newyork`, el de batalla, 3D-Galax y TF3_1_awe, prendidos por la
  IRQ al volver al principio. Y la segunda vuelta de cada uno.
* **Cómo se la vio fallar**, rompiendo el decodificador y armando cada vez:
  sin el `iny` entre los dos lados de `OP_NOTE_PAN`, rojo el título y
  TF3_1_awe en el cuadro 0; sin escribir sin mirar la primera nota de cada
  voz, rojo tres de cinco en la vuelta al principio; con la espera inicial
  cargada con B sucio, rojo el título en el cuadro 0.
* **Ese último fue el único error de verdad**: `music_start_ya` ponía la
  espera en cero con un `lda #0` de ocho bits y un `sta` de dieciséis. Lo
  encontró `test_bateria_suena`, porque la batería del título no llegaba: el
  tema esperaba miles de cuadros. El camino de la IRQ no lo ve —B llega en
  cero—, y por eso la prueba prende el título por el otro.

### Cómo encaja el 5

* **El reparto por prioridad no toca el formato.** El formato no sabe de
  canales: cada evento dice la voz, y la elige el conversor. Que una voz pase
  de un canal a otro es una nota más con su sonido, y cambiar de instrumento
  cuesta lo mismo que no cambiarlo —el sonido va en cada nota—. Lo que en el
  formato viejo sumaba +74% de stream acá es, a lo sumo, un byte de volumen
  más por nota cuando la voz viene de otro canal. No está medido.
* **La rampa es un `OP_RELEASE_GAIN`** con el GAIN de la rampa, en el cuadro
  antes de la nota: es lo que hacía el prototipo (`frames[at].release` con
  `RAMPA`), y en `Frame.release` ya entra tal cual, como (voz, GAIN). Queda
  del lado del 65816, sin latencia ni temporizador en el driver: la duda de
  abajo sobre hacerla en el SPC700 se contesta con que no hace falta.
* **Los ciclos**: el peor cuadro del prototipo pasaba de 56 a 80 escrituras.
  Con 1,34 líneas por escritura y 1,27 por evento, eso son del orden de 30
  líneas más en el peor cuadro, que hoy es de 89. Si no entra, lo de
  `nota_sonido` de arriba.
* **Lo que el formato no tiene y el 5 no necesita**: la modulación (CC1) y
  el paneo por tecla de la batería. Si entran, una altura por cuadro es un
  `OP_SET_PITCH`, y el paneo es el volumen del sonido de cada golpe.

## 5. El reparto de las ocho voces, y la rampa: hecho

Hecho el 2026-09-26, en dos commits que se pueden escuchar y medir por
separado: "Música: las ocho voces para todos los canales, repartidas nota a
nota" y "Música: una voz que suena se baja en 12 ms antes de dársela a otra
nota"; y un tercero que corrige cómo se cuenta el tiempo-nota de un golpe
("Música: el tiempo-nota de un golpe se cuenta hasta que suelta la voz"),
que no cambia la ROM. Medido sobre `92754ab`, con el `release` de 32 temas.
El porqué de cada regla está donde vive: `assign`, `_libre`, `_victima` y
`RAMPA` en `tools/audio/snes_music.py`.

**Para escuchar**: `/shared/audio/2026-09-26-paso-5/`, con su `LEEME.txt`:
`escape_newyork`, la batalla, el título, `cd4`, `Lunar_Pyramid` y
`T_ProjectJustice_DiscLoad`, antes, con el reparto, y con el reparto y la
rampa, todos a la misma sonoridad.

### El reparto

* **Las ocho voces son de todos los canales** (`assign`). Una nota toma una
  voz libre —la que nadie sostiene—, primero una callada y si no la que
  termina antes su cola; los golpes prefieren las voces 6 y 7 —las de los
  efectos, como cuando la batería las tenía fijas— y lo melódico las otras;
  y a igual, la que tuvo una nota del mismo canal, que sale más barata.
* **Si las ocho están sostenidas, la regla del prototipo** (`_victima`): la
  misma tecla del mismo canal se roba a sí misma; nunca a una nota que
  arrancó en ese cuadro ni a la última voz de otro canal; entre las demás,
  a la más débil —el volumen con que arrancó— y a la par a la más vieja; y
  la nota nueva cede si su canal ya suena y la víctima es la última de otro,
  o es más fuerte que ella y su canal no tiene más voces. En cada cuadro
  eligen primero las notas más fuertes.
* **Un golpe sostiene su voz hasta el fin de la nota en el MIDI** o el de su
  muestra, lo que llegue antes; lo que queda de la muestra es como una cola.
  Sostenerla hasta el fin de la muestra le hacía perder a lo melódico 8,3%
  del tiempo-nota en vez de 7,9% (Lunar_Pyramid 33% en vez de 23%).

**Las reglas que se probaron**, en los 32 temas, con un script descartable
(`audio-paso-5/evaluar.py`) que arma todo con cada regla. "Pesado" es el
tiempo-nota perdido pesado por la velocidad al cuadrado, que es como baja
el volumen; "robos" son las notas cortadas mientras sonaban:

| Regla | Perdido | Pesado | Robos | Stream |
|---|---:|---:|---:|---:|
| la del prototipo (la que quedó) | 7,4% | 6,74% | 2.883 | 322.752 |
| robarle a la más vieja, sin ceder nunca | 7,4% | 6,85% | 7.121 | 336.426 |
| robarle a la más débil, sin ceder nunca | 7,6% | 6,91% | 3.597 | 326.689 |
| la del prototipo, protegiendo la más grave y la más aguda | 7,4% | 6,73% | 2.636 | 321.687 |
| la del prototipo, robando primero dentro del propio canal | 7,4% | 6,75% | 2.905 | 322.761 |

(Con la rampa puesta, por eso el stream.) Proteger los extremos gana en
`escape_newyork`, `TF3_1_awe` y la batalla lo que pierde en `11h035` y
`evilrhys`: no entró. Lo que no se probó y podría ganar algo: estimar el
nivel actual de la víctima con su envolvente —el piano sostenido decae— en
vez del volumen con que arrancó, y dejar arrancar tarde una nota larga que
no consiguió voz (la onda cuadrada de `escape_newyork` pierde el 99%: sus
nueve notas caen en cuadros con nueve notas o más, y son de las más suaves).

**El formato no cambió** ni el driver: cada evento ya decía su voz. El
conversor imprime por tema cuánto tiempo-nota se pierde contra el piso de
ocho voces (`tiempo_perdido`), que reemplaza a `coverage`; `share_voices`
y `coverage` se fueron de `musica.py`.

**Lo cobran** tres pruebas nuevas en `test_musica_stream.py` —el acorde con
más canales que voces, que ninguna nota se quede sin voz con una libre, a
quién se le roba— y `pruebas/rpgmaker/test_musica_reparto.py`, sobre
`escape_newyork` de verdad: el primer acorde de las cuerdas dispara tres
voces, y el clavinet y la onda cuadrada están en el banco y suenan. Las
cinco dan rojo con el reparto de antes, reproducido en el script.

### La rampa

En el cuadro anterior a la nota que toma una voz que todavía suena
—sostenida o en su cola—, ADSR1 en cero y GAIN `RAMPA`: lineal, 64 pasos de
6 muestras, 12 ms. Es un `OP_RELEASE_GAIN` más. No va a una nota que arrancó
en ese mismo cuadro, ni a una voz callada. **Son 28.714 rampas contra
64.274 notas**: 20.331 sobre colas melódicas —14.298 a las que les quedaban
menos de 15 cuadros—, 5.138 sobre golpes, 2.815 sobre notas sostenidas.
Una rampa sólo donde la cola todavía se oiría achicaría el costo, pero pide
estimar su nivel; no se hizo.

**Lo cobran** dos pruebas en `test_musica_stream.py`: el robo de una nota
sostenida y el de una cola. Una medida grosera de clics sobre las
grabaciones —ventanas de 1 ms donde la segunda diferencia salta 8 veces
sobre su entorno, que también cuenta los golpes de batería— da, con reparto
→ con rampa: el título 116 → 8, la batalla 642 → 424, `escape_newyork`
3.497 → 3.407 (casi todo batería), `cd4` 519 → 522.

### Bytes, pérdida y ciclos

Bytes: stream más sonidos, del `conversor.log`. Pérdida: `tiempo_perdido`,
y la de antes con el reparto viejo reproducido en el script. Ciclos: la
sonda del paso 4 —la línea de barrido al entrar y salir de `music_tick`—,
cada tema entero desde su vuelta al principio, en snes9x; la IRQ cae en la
línea 112.

| Tema | Stream antes | Reparto | Rampa | Tiempo-nota perdido antes → después | Piso | Peor cuadro (líneas) antes → reparto → rampa |
|---|---:|---:|---:|---:|---:|---:|
| hzstream | 4.028 | 4.268 | 4.452 | 0.0% → 0.0% | 0.0% | 32 → 38 → 37 |
| escape_newyork | 8.965 | 10.458 | 12.329 | 57.6% → 40.8% | 19.9% | 78 → 76 → 78 |
| TF3_1_awe | 9.964 | 12.378 | 16.786 | 23.1% → 11.5% | 4.1% | 54 → 73 → 73 |
| T_VGFighterMAX_Masako | 41.336 | 50.212 | 72.203 | 53.2% → 48.9% | 35.4% | 89 → 100 → 100 |
| evilrhys | 10.272 | 11.556 | 16.436 | 44.7% → 33.6% | 14.5% | 81 → 98 → 98 |
| lufsorr | 3.332 | 4.319 | 6.168 | 0.0% → 0.0% | 0.0% | 36 → 47 → 48 |
| cd4 | 12.671 | 15.119 | 16.910 | 27.2% → 0.1% | 0.1% | 62 → 65 → 66 |
| C3classi | 7.700 | 10.369 | 14.883 | 17.8% → 0.0% | 0.0% | 58 → 64 → 65 |
| rshinld | 3.442 | 4.558 | 7.089 | 28.0% → 11.3% | 4.9% | 63 → 73 → 75 |
| cd2 | 6.942 | 7.168 | 8.083 | 4.8% → 0.0% | 0.0% | 50 → 61 → 61 |
| hzbreach | 9.275 | 10.019 | 14.047 | 0.0% → 0.0% | 0.0% | 40 → 49 → 48 |
| wb3mlair | 2.289 | 2.600 | 2.720 | 0.0% → 0.0% | 0.0% | 45 → 45 → 45 |
| Astpgmarch | 2.165 | 2.275 | 2.381 | 0.0% → 0.0% | 0.0% | 40 → 40 → 40 |
| Gaden | 1.317 | 2.010 | 2.189 | 69.4% → 0.0% | 0.0% | 23 → 29 → 29 |
| 3D-Galax | 14.824 | 17.869 | 17.914 | 0.4% → 0.0% | 0.0% | 34 → 38 → 38 |
| wb3shop | 2.601 | 2.874 | 3.252 | 5.4% → 0.0% | 0.0% | 74 → 81 → 81 |
| KSSMKEND | 2.999 | 3.328 | 3.454 | 1.0% → 0.0% | 0.0% | 44 → 43 → 43 |
| vswar | 9.184 | 14.179 | 15.007 | 54.7% → 0.0% | 0.0% | 33 → 48 → 49 |
| Lunar_Pyramid | 8.072 | 9.376 | 12.536 | 57.9% → 18.9% | 3.1% | 79 → 94 → 94 |
| dcbest | 2.726 | 3.979 | 3.979 | 0.0% → 0.0% | 0.0% | 25 → 27 → 27 |
| golden_axe-turtlevillage2 | 267 | 267 | 321 | 0.0% → 0.0% | 0.0% | 30 → 30 → 30 |
| Fire_Mustang_Intro_And_Level_2_By_Luiz_Vasco | 3.984 | 7.024 | 7.720 | 0.0% → 0.0% | 0.0% | 42 → 52 → 52 |
| bubstix | 8.333 | 11.295 | 13.064 | 0.0% → 0.0% | 0.0% | 30 → 55 → 55 |
| wb3town | 1.637 | 1.913 | 2.002 | 0.3% → 0.0% | 0.0% | 38 → 52 → 52 |
| Fantasia_Of_The_Wind | 4.200 | 5.337 | 7.879 | 18.9% → 11.5% | 8.9% | 61 → 79 → 78 |
| 11h035 | 4.793 | 5.362 | 6.875 | 13.4% → 8.9% | 1.4% | 70 → 76 → 77 |
| prepara | 337 | 668 | 778 | 15.5% → 0.0% | 0.0% | 38 → 48 → 48 |
| T_ProjectJustice_DiscLoad | 4.308 | 4.826 | 5.190 | 21.3% → 0.0% | 0.0% | 72 → 85 → 85 |
| pn28year | 5.628 | 6.349 | 9.224 | 60.9% → 50.6% | 49.9% | 46 → 47 → 55 |
| Tnt07 | 2.613 | 2.835 | 2.835 | 0.0% → 0.0% | 0.0% | 44 → 43 → 43 |
| Deflector1 | 8.983 | 11.184 | 11.844 | 31.0% → 0.0% | 0.0% | 37 → 52 → 51 |
| MML2_MotherZone | 533 | 1.629 | 2.202 | 28.4% → 0.0% | 0.0% | 29 → 42 → 42 |
| **Los 32** | 209.720 | 257.603 | 322.752 | | | |

* **Stream: de 209.720 a 257.603 B con el reparto (+23%) y a 322.752 con la
  rampa (+25% más)**. El +74% del prototipo era en el formato viejo; en el
  por nota, que una voz cambie de canal cuesta un byte de volumen. La
  batalla es la que más paga la rampa (50.212 → 72.203): es la más densa.
* **El cartucho `release`, de 74,6% a 75,7% con el reparto y a 77,3% con la
  rampa** (3.128.883 → 3.176.812 → 3.241.961 B usados, sumando los
  segmentos del `.dbg`). El banco 0 no cambia: 1.168 B libres.
* **Ciclos: el peor cuadro de todos, de 89 líneas a 100** con el reparto, y
  la rampa no lo mueve. Es la vuelta al principio del de batalla —el
  arranque y las ocho voces escritas enteras—, que termina en la línea 212,
  13 antes del vblank. El peor a mitad de un tema **baja** de 82 a 79 con el
  reparto (los acordes ya no se pisan en una voz) y queda en 78 con la
  rampa. En total la música ocupa 24% más de líneas con el reparto y 37%
  con la rampa. Lo de `nota_sonido` del paso 4 no hizo falta.
* **Pérdida de tiempo-nota: en promedio de 19,8% a 7,4%**, con un piso de
  4,4%. `escape_newyork` de 58% a 41% (piso 20%; el prototipo contaba
  55% → 39% y un piso de 23% midiendo los golpes por su largo en el MIDI);
  doce temas que perdían algo pasan a no perder nada.
* **El banco**: los canales que no tenían voz suman siete programas —la
  celesta, la guitarra de acero, el timbal, el shakuhachi, el fantasía, el
  space voice y el koto—, 67 muestras en vez de 60 en los mismos 57 KB, y
  las demás bajan de tasa: el piano de 6,1 a 4,5 kHz, las cuerdas de 5,5 a
  4,1, la sierra de 6,1 a 4,6, el bronce de 10,8 a 5,4. Siguen sin aportar
  los mismos 19 temas. Lo compensa el 6.

### La saturación, y las dos opciones del aire

Con el método de los pasos anteriores —cada tema en el título, snes9x sin
MSU-1, el tema entero, muestras de L+R en el tope, que con MASTER `$7F` es
32.511— y **sin tocar el aire** (0,5, MASTER `$7F`), como pidió taro:

| Tema | Recortes antes | Reparto | Rampa | Pico antes → rampa (dBFS) | LUFS antes → reparto → rampa |
|---|---:|---:|---:|---:|---:|
| hzstream | 36 | 84 | 88 | -0.1 → -0.1 | -9.6 → -9.5 → -9.5 |
| escape_newyork | 0 | 0 | 0 | -5.1 → -4.2 | -20.7 → -18.5 → -18.5 |
| TF3_1_awe | 0 | 6 | 7 | -1.8 → -0.1 | -13.4 → -11.3 → -11.4 |
| T_VGFighterMAX_Masako | 298 | 2.400 | 2.528 | -0.1 → -0.1 | -10.4 → -10.9 → -11.2 |
| evilrhys | 240 | 1.458 | 1.468 | -0.1 → -0.1 | -11.1 → -10.6 → -10.7 |
| lufsorr | 0 | 0 | 0 | -2.4 → -3.0 | -15.0 → -14.9 → -15.0 |
| cd4 | 0 | 0 | 0 | -3.7 → -1.4 | -17.9 → -16.1 → -16.1 |
| C3classi | 0 | 0 | 0 | -3.6 → -3.1 | -16.6 → -15.7 → -15.8 |
| rshinld | 4.724 | 7.888 | 7.786 | -0.1 → -0.1 | -8.7 → -8.1 → -8.2 |
| cd2 | 0 | 0 | 0 | -4.1 → -3.3 | -16.7 → -16.5 → -16.5 |
| hzbreach | 846 | 514 | 536 | -0.1 → -0.1 | -8.6 → -8.9 → -8.9 |
| wb3mlair | 0 | 0 | 0 | -9.6 → -9.5 | -24.7 → -24.9 → -24.9 |
| Astpgmarch | 0 | 0 | 0 | -1.7 → -1.2 | -14.0 → -14.2 → -14.2 |
| Gaden | 0 | 0 | 0 | -17.9 → -8.3 | -31.3 → -11.0 → -11.3 |
| 3D-Galax | 186 | 1.410 | 1.406 | -0.1 → -0.1 | -13.9 → -13.7 → -13.7 |
| wb3shop | 0 | 0 | 0 | -5.1 → -3.8 | -21.3 → -20.3 → -20.3 |
| KSSMKEND | 0 | 0 | 0 | -10.9 → -7.9 | -24.7 → -24.4 → -24.4 |
| vswar | 0 | 0 | 0 | -6.7 → -3.6 | -20.3 → -18.4 → -18.4 |
| Lunar_Pyramid | 28 | 5.723 | 5.852 | -0.1 → -0.1 | -14.1 → -11.6 → -11.6 |
| dcbest | 0 | 0 | 0 | -6.3 → -3.9 | -17.0 → -15.8 → -15.8 |
| golden_axe-turtlevillage2 | 0 | 0 | 0 | -8.1 → -8.1 | -17.7 → -17.7 → -17.7 |
| Fire_Mustang_Intro_And_Level_2_By_Luiz_Vasco | 0 | 8 | 11 | -4.1 → -0.1 | -15.8 → -13.5 → -13.5 |
| bubstix | 0 | 0 | 0 | -3.3 → -3.4 | -17.1 → -17.3 → -17.3 |
| wb3town | 0 | 0 | 0 | -8.0 → -6.2 | -20.2 → -20.1 → -20.1 |
| Fantasia_Of_The_Wind | 0 | 0 | 0 | -5.0 → -4.3 | -16.3 → -16.2 → -16.3 |
| 11h035 | 0 | 0 | 0 | -8.0 → -6.8 | -21.2 → -21.1 → -21.2 |
| prepara | 0 | 0 | 0 | -14.4 → -13.8 | -26.3 → -25.2 → -25.2 |
| T_ProjectJustice_DiscLoad | 0 | 0 | 0 | -7.9 → -4.9 | -24.3 → -20.9 → -20.9 |
| pn28year | 0 | 0 | 0 | -4.6 → -5.2 | -19.2 → -19.4 → -19.4 |
| Tnt07 | 0 | 0 | 0 | -9.6 → -8.6 | -23.8 → -23.7 → -23.7 |
| Deflector1 | 178 | 806 | 806 | -0.1 → -0.1 | -14.2 → -13.0 → -13.0 |
| MML2_MotherZone | 0 | 0 | 0 | -9.2 → -3.5 | -19.7 → -17.9 → -17.9 |
| **Los 32** | 6.536 | 20.297 | 20.488 | | |


**Los recortes se triplican**, de 6.536 a 20.488 muestras, casi todos en
cinco temas: `rshinld` (7.786, el que ya más recortaba, por CC7 en 127),
`Lunar_Pyramid` (28 → 5.852), la batalla (298 → 2.528), `evilrhys` (240 →
1.468) y `3D-Galax` (186 → 1.406). La rampa casi no cambia nada. El nivel
sube donde el reparto devolvió canales: `escape_newyork` +2,2 LUFS, `cd4`
+1,8, `Gaden` +20 (tenía casi todo lo que suena sin voz).

**Las dos opciones**, para que taro elija. Las dos salen del pico verdadero
de cada tema: se armó el mismo commit con el aire en 0,25 —el techo de cada
voz en un cuarto del original, 24 y 21—, que no recorta en ninguno, se midió
el pico y se lo multiplicó por 2 (el volumen es lineal; el redondeo del
registro a 0,25 lo hace aproximado). El LUFS de las opciones es el de esa
grabación más la ganancia; el de hoy, el medido.

* **A, un aire global**: 0,318 en vez de 0,5, **−3,9 dB para todos**. Lo fija
  `rshinld`, cuyo pico verdadero pasa 3,9 dB del tope. No recorta ninguno,
  y los 22 temas que hoy no recortan bajan 3,9 dB sin necesidad
  (`escape_newyork` a -22,7 LUFS).
* **B, un techo por tema**: cada uno con el aire más alto que no recorta,
  topado en el 0,5 de hoy. **22 temas quedan como están**; bajan los 10 que
  pasan del tope, de −0,5 dB (`TF3_1_awe`) a −3,9 (`rshinld`), la batalla
  −2,9. Cuesta una tabla —un volumen por tema que `build_events` aplique en
  `lados`— y **volver a medirla con cada cambio de la mezcla**: el paso 6
  cambia las muestras y con ellas los picos. Medirla es este mismo script
  con el aire en 0,25, 30 s de snes9x por tema en paralelo.

| Tema | Pico verdadero con 0,5 (dB sobre el tope) | B: aire del tema | B: dB | LUFS hoy | A: LUFS | B: LUFS |
|---|---:|---:|---:|---:|---:|---:|
| hzstream | +1.1 | 0.438 | -1.1 | -9.5 | -13.4 | -10.6 |
| escape_newyork | -4.2 | 0.500 | +0.0 | -18.5 | -22.7 | -18.8 |
| TF3_1_awe | +0.5 | 0.470 | -0.5 | -11.4 | -15.3 | -11.9 |
| T_VGFighterMAX_Masako | +2.9 | 0.358 | -2.9 | -11.2 | -15.0 | -14.0 |
| evilrhys | +2.3 | 0.382 | -2.3 | -10.7 | -14.6 | -13.0 |
| lufsorr | -2.9 | 0.500 | +0.0 | -15.0 | -18.8 | -14.9 |
| cd4 | -1.3 | 0.500 | +0.0 | -16.1 | -20.0 | -16.1 |
| C3classi | -3.0 | 0.500 | +0.0 | -15.8 | -19.8 | -15.9 |
| rshinld | +3.9 | 0.318 | -3.9 | -8.2 | -12.0 | -12.0 |
| cd2 | -3.3 | 0.500 | +0.0 | -16.5 | -20.3 | -16.4 |
| hzbreach | +2.2 | 0.390 | -2.2 | -8.9 | -12.8 | -11.0 |
| wb3mlair | -9.3 | 0.500 | +0.0 | -24.9 | -28.8 | -24.9 |
| Astpgmarch | -1.3 | 0.500 | +0.0 | -14.2 | -18.1 | -14.2 |
| Gaden | -8.0 | 0.500 | +0.0 | -11.3 | -15.1 | -11.2 |
| 3D-Galax | +2.2 | 0.388 | -2.2 | -13.7 | -17.5 | -15.8 |
| wb3shop | -3.7 | 0.500 | +0.0 | -20.3 | -24.3 | -20.4 |
| KSSMKEND | -7.8 | 0.500 | +0.0 | -24.4 | -28.5 | -24.6 |
| vswar | -3.5 | 0.500 | +0.0 | -18.4 | -22.3 | -18.4 |
| Lunar_Pyramid | +2.5 | 0.377 | -2.5 | -11.6 | -15.6 | -14.1 |
| dcbest | -3.8 | 0.500 | +0.0 | -15.8 | -19.7 | -15.8 |
| golden_axe-turtlevillage2 | -8.2 | 0.500 | +0.0 | -17.7 | -21.8 | -17.9 |
| Fire_Mustang_Intro_And_Level_2_By_Luiz_Vasco | +0.6 | 0.467 | -0.6 | -13.5 | -17.5 | -14.2 |
| bubstix | -3.4 | 0.500 | +0.0 | -17.3 | -21.2 | -17.3 |
| wb3town | -6.1 | 0.500 | +0.0 | -20.1 | -24.0 | -20.1 |
| Fantasia_Of_The_Wind | -4.3 | 0.500 | +0.0 | -16.3 | -20.2 | -16.3 |
| 11h035 | -6.6 | 0.500 | +0.0 | -21.2 | -25.1 | -21.2 |
| prepara | -13.5 | 0.500 | +0.0 | -25.2 | -28.9 | -25.0 |
| T_ProjectJustice_DiscLoad | -5.0 | 0.500 | +0.0 | -20.9 | -24.9 | -21.0 |
| pn28year | -4.9 | 0.500 | +0.0 | -19.4 | -23.3 | -19.4 |
| Tnt07 | -8.6 | 0.500 | +0.0 | -23.7 | -27.6 | -23.7 |
| Deflector1 | +2.4 | 0.379 | -2.4 | -13.0 | -16.9 | -15.4 |
| MML2_MotherZone | -3.3 | 0.500 | +0.0 | -17.9 | -21.7 | -17.8 |

### El aire: un techo por tema (la opción B): hecho

taro eligió la B. Hecho el 2026-09-26, después del 5b —que cambia la mezcla
de la batalla—, en el commit "Música: un techo de volumen por tema, medido".
El porqué vive en `leer_techos` (tools/audio/snes_music.py) y cómo se mide
en tools/audio/techos.py.

* **La tabla**: `parches/auto/musica/techos.toml`, versionada como las
  decisiones de `parches/auto/`: el aire de cada tema —los 32, los que no
  recortan con 0,5—, el pico y los LUFS con él, hasta qué cuadro hay que
  tocarlo para pasar por su pico y la huella de su mezcla. `build_varios` la
  lee y `build_events` multiplica el techo de cada voz por aire/0,5.
* **No se escribe a mano: `just techos`**, unos cuatro minutos. Arma una
  copia de `release` en `rom/build/techos/` con todos los temas a 0,25
  (`--aire-de-medida` del conversor), toca cada uno entero en snes9x sin
  MSU-1 —la pantalla de título parchada al tema, como los scripts de los
  pasos anteriores, ocho a la vez—, le da el aire más alto que deja su pico
  0,5 dB bajo el tope (topado en 0,5), escribe la tabla, rearma `release` y
  lo vuelve a medir; si alguno recortara todavía, lo baja y repite. La
  primera vez entraron todos en una vuelta. `just techos --medir` sólo mide
  el `release` armado.
* **El sello de los cartuchos mira los aires de la tabla** (`cartuchos.huella`):
  cambiar uno rearma, y reescribir los picos o las huellas no.
* **La prueba**, `pruebas/rpgmaker/test_musica_techos.py`:
  `test_la_tabla_de_techos_es_la_de_esta_mezcla` arma los 32 temas en
  memoria (3 s) y compara la huella de cada uno —lo que le escribe al DSP y
  las muestras que toca— con la de la tabla: cualquier cambio de la mezcla
  (el paso 6) la pone en rojo diciendo qué tema y que hay que correr `just
  techos`. Y `test_el_tema_no_recorta_en_su_pico`, uno por tema de los que
  quedaron a menos de 1,5 dB del tope —12—, toca el tema en la ROM hasta su
  `hasta` y pide cero muestras en el tope: 42.555 cuadros en total, **unos 21
  s de CPU, 5 s con los ocho procesos**; el más largo, 3D-Galax, 3,5 s. Tocar
  los 32 enteros serían unos 2 minutos de CPU.
* **Por qué sólo los cercanos**: con la mezcla igual (la huella), lo único
  que mueve el pico es en qué momento del cuadro cae cada escritura, que
  cambia con cualquier cambio de la ROM. Medido: `11h035`, `cd4` y `vswar`
  tienen el mismo stream antes y después de este cambio, y su pico se movió
  0,2 dB. Los que están a más de 1,5 dB no llegan al tope por eso.
* **Cómo se la vio fallar**: con el aire de la batalla cambiado a mano a
  0,45 en la tabla, rojo las dos: la huella de la batalla, y 224 muestras en
  el tope en sus primeros 8.700 cuadros.

Antes: el `release` con el 5b y el aire en 0,5 para todos, medido con `just
techos --medir`. Después: la tabla. "dB" es lo que baja cada tema.

| Tema | Aire | dB | Recortes antes → después | Pico antes → después (dB) | LUFS antes → después |
|---|---:|---:|---:|---:|---:|
| rshinld | 0,298 | -4,5 | 7790 → 0 | 0,0 → -0,7 | -8,2 → -12,7 |
| T_VGFighterMAX_Masako | 0,350 | -3,1 | 2384 → 0 | 0,0 → -0,5 | -10,1 → -13,1 |
| Lunar_Pyramid | 0,356 | -3,0 | 5436 → 0 | 0,0 → -0,5 | -11,5 → -14,5 |
| Deflector1 | 0,363 | -2,8 | 792 → 0 | 0,0 → -0,6 | -13,1 → -15,9 |
| 3D-Galax | 0,366 | -2,7 | 1380 → 0 | 0,0 → -0,5 | -13,7 → -16,4 |
| evilrhys | 0,380 | -2,4 | 538 → 0 | 0,0 → -0,5 | -10,5 → -12,9 |
| hzbreach | 0,381 | -2,4 | 556 → 0 | 0,0 → -0,4 | -8,9 → -11,2 |
| hzstream | 0,389 | -2,2 | 130 → 0 | 0,0 → -0,5 | -9,5 → -11,8 |
| Fire_Mustang_Intro_And_Level_2_By_Luiz_Vasco | 0,438 | -1,1 | 7 → 0 | 0,0 → -0,5 | -13,5 → -14,7 |
| TF3_1_awe | 0,440 | -1,1 | 14 → 0 | 0,0 → -0,5 | -11,4 → -12,5 |
| 11h035 | 0,500 | 0,0 | 0 → 0 | -6,6 → -6,4 | -21,2 → -21,2 |
| Astpgmarch | 0,500 | 0,0 | 0 → 0 | -1,2 → -1,2 | -14,2 → -14,2 |
| C3classi | 0,500 | 0,0 | 0 → 0 | -3,1 → -3,1 | -15,8 → -15,8 |
| Fantasia_Of_The_Wind | 0,500 | 0,0 | 0 → 0 | -4,4 → -4,4 | -16,3 → -16,3 |
| Gaden | 0,500 | 0,0 | 0 → 0 | -8,2 → -8,2 | -11,0 → -11,1 |
| KSSMKEND | 0,500 | 0,0 | 0 → 0 | -7,9 → -7,9 | -24,4 → -24,4 |
| MML2_MotherZone | 0,500 | 0,0 | 0 → 0 | -3,5 → -3,5 | -17,9 → -17,9 |
| T_ProjectJustice_DiscLoad | 0,500 | 0,0 | 0 → 0 | -5,0 → -5,0 | -20,9 → -20,9 |
| Tnt07 | 0,500 | 0,0 | 0 → 0 | -8,6 → -8,6 | -23,6 → -23,6 |
| bubstix | 0,500 | 0,0 | 0 → 0 | -3,1 → -3,1 | -17,2 → -17,2 |
| cd2 | 0,500 | 0,0 | 0 → 0 | -3,2 → -3,2 | -16,5 → -16,5 |
| cd4 | 0,500 | 0,0 | 0 → 0 | -1,3 → -1,1 | -16,2 → -16,2 |
| dcbest | 0,500 | 0,0 | 0 → 0 | -3,8 → -3,8 | -15,9 → -15,9 |
| escape_newyork | 0,500 | 0,0 | 0 → 0 | -5,1 → -5,1 | -18,5 → -18,5 |
| golden_axe-turtlevillage2 | 0,500 | 0,0 | 0 → 0 | -8,0 → -8,0 | -17,7 → -17,7 |
| lufsorr | 0,500 | 0,0 | 0 → 0 | -3,1 → -3,1 | -15,0 → -15,0 |
| pn28year | 0,500 | 0,0 | 0 → 0 | -5,1 → -5,1 | -19,5 → -19,5 |
| prepara | 0,500 | 0,0 | 0 → 0 | -13,7 → -13,7 | -25,3 → -25,3 |
| vswar | 0,500 | 0,0 | 0 → 0 | -3,6 → -3,8 | -18,4 → -18,4 |
| wb3mlair | 0,500 | 0,0 | 0 → 0 | -9,4 → -9,4 | -24,9 → -24,9 |
| wb3shop | 0,500 | 0,0 | 0 → 0 | -4,0 → -4,0 | -20,3 → -20,3 |
| wb3town | 0,500 | 0,0 | 0 → 0 | -6,1 → -6,1 | -20,2 → -20,2 |

**Los recortes, de 19.027 muestras a cero.** Los 22 que no recortaban
quedan igual (el pico de tres se movió 0,2 dB por lo de arriba). Los diez
que recortaban bajan entre 1,1 dB (`TF3_1_awe`, `Fire_Mustang`) y 4,5 dB
(`rshinld`), un poco más que lo que estimaba la opción B por el margen de
0,5 dB; la batalla, 3,1 dB, a -13,1 LUFS.

## 5b. La frase de la batalla, que el reparto cortaba: hecho

taro, el 2026-09-26, escuchando las grabaciones del 5: *"algunos mejoran
mucho, pero uno empeora: el tema de batalla. [...] la frase principal (que
empieza en el segundo 15 y termina en el segundo 22, aprox, y luego se
repite) se interrumpe constantemente, lo cual lo vuelve inescuchable."*
Hecho el mismo día, en el commit "Música: la melodía de la batalla no llega
última a su cuadro". El porqué vive en `_orden_del_cuadro` de
`tools/audio/snes_music.py`.

**Para escuchar**: `/shared/audio/2026-09-26-batalla/`, con su `LEEME.txt`:
la batalla (47 s: la referencia, antes del reparto, el paso 5 y las dos
variantes que la arreglan), y `escape_newyork` y el título enteros con el
paso 5 y las dos variantes.

### El diagnóstico

* **La frase es la voz de arriba de los acordes del órgano**, el canal 0
  (programa 20): acordes de tres notas —la de arriba con velocidad 127, las
  otras dos con 100—, que empiezan a los 15,43 s con un acorde de 1,7 s y
  bajan 72, 71, 69, 67... hasta los 22,2 s, y vuelven a empezar. Es el canal
  más fuerte de la mezcla: su CC7 lo deja en un nivel de 124 contra 114 del
  bajo y 82 de la batería. En la pista de MSU-1, el pico del espectro entre
  300 y 1200 Hz sigue exactamente esa línea (una octava arriba, el segundo
  armónico del órgano). El canal 1 es un eco: las mismas notas 9 cuadros
  después, con un tercio del nivel. Los canales 2 y 3 tocan el bajo
  **nota por nota igual**, con dos programas.
* **No la cortaba ni el robo ni la rampa: la nota no conseguía voz.** De sus
  536 notas en todo el tema, 290 sonaban enteras, 32 se las robaban a mitad
  y **214 no sonaban**; en la frase, 5 de 21 sin voz y 1 robada, una nota sí
  y otra no (17,57 s, 18,43 s, 21,00 s, 21,65 s, 21,97 s...). El órgano
  quedaba callado el 48% del tiempo en que el MIDI lo hace sonar (52% en la
  frase).
* **Las 214 son el mismo caso**: las ocho voces ya habían arrancado en ese
  mismo cuadro, y a una nota del cuadro no se le roba. Quién las tenía, en
  suma sobre los 214 cuadros: la batería 946 voces de 1.712 —4,4 por
  cuadro—, los dos bajos 214 cada uno, los metales 238, la guitarra 100. En
  cada tiempo el tema pega cinco o seis golpes juntos —35 y 36, dos bombos;
  38 y 40, dos cajas; el charles— y todo va con velocidad 127, así que el
  orden del cuadro —por velocidad y, a la par, el más grave primero— dejaba
  a la melodía, lo más agudo, para el final.
* **Con el reparto fijo de antes no pasaba**: el órgano tenía su voz fija y
  la batería dos, así que el órgano no se callaba nunca (0%), aunque sonara
  la nota de abajo del acorde y no la de arriba (la de arriba se "perdía" el
  94%, pero en su voz sonaba otra del mismo acorde, con el mismo ritmo). Lo
  que se oye como "se interrumpe" es el ritmo: que el canal calle.
* **Ni un tope de voces para la batería ni proteger las notas recién
  empezadas cambian nada**: la melodía no se perdía por robos entre cuadros
  sino por el orden dentro de uno. Lo confirman las grabaciones: en las
  ventanas de las notas 71 y 67 de la frase, la energía de la melodía es 24%
  y 10% del total entre 300 y 1200 Hz en el paso 5, contra 80% y 60% con el
  arreglo y 51% y 48% en la referencia.

### Las variantes

Con un script descartable (`audio-batalla/variantes.py` en el scratchpad),
que arma los 32 temas del `release` con cada regla. Como en el 5: "perdido"
es el tiempo-nota perdido en promedio por tema; "pesado", pesado por el
nivel con que arranca cada nota (con los controladores; el del 5 pesaba por
la velocidad sola); "arriba" y "abajo", en qué fracción de los cuadros no
suena la nota más aguda (más grave) de lo melódico que el MIDI tiene
sonando; "golpes", qué fracción de los golpes no suena, contando una sola
vez los de una familia en un mismo cuadro —dos bombos juntos son un
golpe—; "stream", stream más sonidos de los 32. La melodía de la batalla es
la voz de arriba del canal 0 en todo el tema, y entre paréntesis en la frase.

| Regla | Perdido | Pesado | Robos | Arriba | Abajo | Golpes | Stream | Batalla: melodía perdida (15-22 s) | Órgano callado |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| el reparto fijo por canal, de antes del paso 5 | 19,84% | 19,99% | 13.968 | 11,2% | 10,8% | 2,49% | 283.360 | 94% (91%) | 0% |
| el paso 5: por velocidad, y a la par el más grave primero | 7,38% | 6,06% | 2.883 | 10,7% | 3,3% | 0,39% | 322.752 | 48% (52%) | 48% |
| paso 5, y una nota con menos de 4 cuadros no se roba | 7,39% | 6,06% | 2.124 | 10,6% | 3,4% | 0,44% | 319.527 | 56% (57%) | 56% |
| ídem, 8 cuadros | 7,42% | 6,10% | 1.760 | 10,7% | 3,3% | 0,52% | 317.748 | 73% (63%) | 73% |
| paso 5, y la batería sostiene a lo sumo 2 voces | 7,31% | 6,00% | 2.811 | 10,7% | 3,3% | 0,64% | 322.764 | 48% (52%) | 48% |
| ídem, 3 voces | 7,33% | 6,02% | 2.851 | 10,7% | 3,3% | 0,52% | 322.833 | 48% (52%) | 48% |
| paso 5, y una nota de menos de 8 cuadros no roba | 6,94% | 5,76% | 1.559 | 9,8% | 3,1% | 2,58% | 308.736 | 25% (20%) | 25% |
| paso 5, y un golpe no le roba a lo melódico | 7,08% | 5,77% | 2.728 | 10,4% | 3,2% | 2,29% | 322.102 | 48% (52%) | 48% |
| paso 5, y el golpe repetido de una familia al final del cuadro | 7,09% | 5,79% | 2.815 | 9,4% | 3,1% | 0,35% | 323.081 | 31% (23%) | 31% |
| por nivel (con el CC7) en vez de velocidad | 7,06% | 5,60% | 3.051 | 8,3% | 3,3% | 2,52% | 326.081 | 22% (29%) | 22% |
| por nivel, y el golpe repetido al final | 6,90% | 5,48% | 3.064 | 7,4% | 3,3% | 2,14% | 326.174 | 22% (29%) | 22% |
| ronda: la primera de cada canal antes que la segunda de cualquiera | 6,92% | 5,97% | 1.998 | 4,4% | 3,7% | 2,54% | 315.482 | 0% (0%) | 0% |
| golpes primero, lo melódico por nivel / lugar en su canal | 7,39% | 6,12% | 2.761 | 7,5% | 3,9% | 0,15% | 320.540 | 25% (34%) | 25% |
| **ronda** por nivel, cada familia de golpes un canal, golpes primero a la par, repetidos al final | 6,94% | 5,91% | 2.511 | 5,6% | 3,7% | 0,18% | 318.665 | 0% (0%) | 0% |
| **nivel y lugar** (la que quedó): golpes primero uno por familia, lo melódico por nivel / lugar, repetidos al final | 7,05% | 5,82% | 2.528 | 6,9% | 3,7% | 0,12% | 319.160 | 0% (0%) | 0% |
| nivel y lugar, y el golpe repetido no roba | 6,91% | 5,73% | 2.446 | 6,7% | 3,6% | 0,12% | 318.586 | 0% (0%) | 0% |

* **Lo que decide es el orden del cuadro, no a quién se roba.** Todo lo que
  se hace en `_victima` —no robar lo recién empezado, un tope para la
  batería, que los golpes no roben, que lo corto no robe— deja la melodía
  igual o peor. La idea de detectar el canal de la melodía (el registro, el
  volumen, el que más suena solo) no hizo falta: ordenar por el nivel real
  ya la pone primera, porque es lo más fuerte.
* **La ronda estricta** salva la melodía, pero le cuesta a la batería
  (golpes 2,54%; la de la batalla pierde el 44% de sus golpes) si la
  batería es un canal más; con cada familia como un canal, 0,18%. Y en
  `escape_newyork` les da voz a las cuerdas de velocidad 29 —nivel 6, casi
  inaudibles— a costa del polysynth (nivel 36): el pesado de ese tema sube
  de 24,7% a 28,1%.
* **Nivel y lugar** —la elegida— es la ronda sin ese defecto: la segunda
  nota de un canal vale la mitad de su nivel, así que va antes que la
  primera de un canal que suena a menos de la mitad. Contra el paso 5:
  perdido 7,38% → 7,05%, robos 2.883 → 2.528, arriba 10,7% → 6,9%, golpes
  0,39% → 0,12%; lo que empeora es abajo, 3,3% → 3,7%. Por tema, lo que
  cambia: la batalla 48,9% → 47,0% (su batería pierde el 30% del tiempo de
  golpe, casi todo el segundo bombo y la segunda caja: por familia, 0,1%);
  `evilrhys` 33,6% → 29,4%; `Lunar_Pyramid` 18,9% → 14,0%; `escape_newyork`
  40,8% → 39,7% y sus golpes 6,9% → 3,3%; `11h035` 8,9% → 10,3% y
  `pn28year` pierde más el bajo (abajo 55,9% → 64,5%, con un piso de 50%).
  `cd4`, `vswar` y `Gaden` siguen en 0%.
* **Que el golpe repetido no robe** gana un poco más (6,91%, 2.446 robos)
  pero es una regla más en `_victima`: no entró. Las dos que quedan parejas
  para elegir escuchando son nivel y lugar (implementada) y la ronda (en las
  grabaciones, `-3-ronda`; es cambiar la clave de `_orden_del_cuadro`).

### Bytes, ciclos y la prueba

* **Stream: de 322.752 a 319.160 B** en los 32 temas (la batalla 72.203 →
  69.613): menos robos, menos rampas. El `release` usa 3,6 KB menos; el
  banco 0 no cambia (1.168 B libres).
* **Ciclos**, con la sonda del paso 4 en snes9x, cada tema entero desde su
  vuelta al principio: **el peor cuadro sigue en 100 líneas** —la vuelta al
  principio de la batalla—, el peor a mitad de un tema (sin los últimos 31
  cuadros) baja de 91 a 90, y la música ocupa 1,2% menos líneas en total.
  Lo que más sube es `cd2` (61 → 68) y `3D-Galax` (38 → 44), que no pierden
  nada pero reparten las voces en otro orden.
* **La prueba**: `test_la_melodia_de_la_batalla_no_pierde_notas`
  (`pruebas/rpgmaker/test_musica_reparto.py`) arma el tema y pide que cada
  nota de la voz de arriba del canal 0 suene entera, en todo el tema; con la
  regla del paso 5 da rojo con 214 + 32. Y
  `test_la_voz_de_arriba_del_acorde_no_llega_ultima_a_su_cuadro`
  (`pruebas/herramientas/test_musica_stream.py`), el caso armado a mano:
  once notas en un cuadro, cinco golpes de tres familias, y afuera quedan
  el segundo bombo, la segunda caja y la nota de abajo del acorde; con la
  regla del paso 5 el que queda afuera es el acorde entero.

## 6. Las muestras: presupuesto por paquete y zonas

Es lo que más cambia el sonido (el 10 solo ya se acerca más que el 07) y lo
más caro: es `wishlist/presupuesto-de-muestras-por-paquete.md`, y detrás
`wishlist/una-muestra-por-instrumento.md`. taro escuchó la variante 08/10 y
dijo que hace "una diferencia notoria", y aprobó arrancar.

**Estado, 2026-09-26**: medido, prototipado y grabado; el plan está abajo y
tiene decisiones para taro. **Hecho y listo para merge sólo el paso 1** —el
paquete que no entró se completa en el próximo `PlayBGM`—, que arregla algo
que pasa hoy en el juego y que el resto necesita. Medido sobre `03c21fb`, con
el `release` de 32 temas.

* **Para escuchar**: `/shared/audio/2026-09-26-paso-6/`, con su `LEEME.txt`:
  `escape_newyork`, la batalla, el título y `3D-Galax` (uno de los 19 que hoy
  no aportan) en cinco versiones —hoy, por paquete, por paquete con la zona
  más usada, con dos zonas, y el techo a 22 kHz—, a la misma sonoridad.
* **Los prototipos**: rama local `proto-paso-6` (commit `06a40ef`), **no para
  mergear**: una sonda de tiempos en `paquete_cargar_ya` y un `Banco` que arma
  cada muestra con el presupuesto de un JSON (`PROTO_PASO6`).
* **Los scripts**, descartables, en el scratchpad de la sesión
  (`audio-paso-6/`): `volcar.py` saca del conversor lo que recibe `emit`
  —paquetes, temas, muestras—, `reparto.py` hace el reparto, `herencia.py`
  el grafo de qué tema puede venir sonando, `medir_subida.py` y
  `herencia_rom.py` miden en la ROM, `grabar.py` y `distancia.py` graban y
  comparan contra la pista de MSU-1.

### Lo que no era como se pensaba: la subida ya no va por el IPL

* **El IPL sólo sube el driver y el directorio** —menos de 1 KB, menos de un
  cuadro—. Las muestras las sube `paquete_cargar_ya` por el comando 3 del
  driver: **ternas por los puertos 0, 1 y 2, con el testigo en el 3**. O sea
  que el "cargador de cuatro puertos" de
  `decisiones/el-arranque-esta-dimensionado-para-el-techo-de-aram.md` **ya
  existe** desde los paquetes por mapa.
* **Medido en la ROM**, con la sonda —cuadro y línea al entrar y salir de
  `paquete_cargar_ya`—, en dieciocho paquetes: **1,33 a 1,42 cuadros por
  KB**, unos 45 KB/s. Es casi lo mismo que el comentario de `BOOT_CUADROS`
  medía para el IPL byte a byte (1,4): la terna no ganó lo que prometía.
* **El techo es el SPC700**: su lazo de terna son 56 ciclos a 1,024 MHz, 55
  KB/s. Lo que falta hasta ahí es la latencia del acuse, la IRQ de la música
  —que sigue sonando durante la subida— y el rearmado del puntero cada 255 B.
  Un lazo más apretado (almacenar con `mov !abs+y` en vez de `[dp]+y`, acusar
  antes del último almacenamiento) llega a unos 48 ciclos: **entre 10 y 20%
  más rápido, estimado**. No se prototipó: no paga un comando nuevo del
  driver.
* **El arranque**: termina su trabajo en el cuadro 20 —el paquete del mapa 4,
  7,4 KB, son 10 cuadros— y espera hasta el 112. Con la ARAM llena por el
  comando 3 serían 62 KB × 1,36 + 9 = 94 cuadros, así que `BOOT_CUADROS`
  sigue cubriendo el techo, pero **lo que lo compraría de vuelta ya no es un
  cargador**: es dimensionarlo para el paquete de arranque y no para el techo.
  Es una decisión (ver abajo).

### El presupuesto por paquete, medido

**Cómo**: se corrió el conversor de `release` interceptando `emit` —los
paquetes de cada mapa y el de la pelea, los temas, las muestras de los
efectos— y más el paquete del título (el tema del título con el paquete del
mapa 4, que es lo que arma `tema_asegurar`). Para cada paquete, lo libre es
la ARAM menos el directorio, menos sus efectos, menos 1 KB de margen; y cada
muestra —una por programa y una por golpe, en todo el cartucho, como hoy—
tiene que entrar en **todos** los paquetes donde está. El reparto es un
llenado progresivo sobre la fracción de su tamaño a la tasa del SF2: se sube
a todas juntas hasta que un paquete se llena, esas quedan fijas, y se sigue
con las demás. Las voces salen de `build_voice` y `build_drum` con ese
presupuesto, o sea son las que armaría el conversor.

**Qué temas pueden sonar en cada mapa**: los del paquete —el propio y los que
prende un `PlayBGM` de sus páginas—, y **el que viene sonando del mapa
anterior**, porque casi ningún mapa del juego trae tema propio: lo prende una
página, y hasta entonces sigue el de antes. Seguir los `Teleport` sin mirar
condiciones da que cualquier tema puede llegar a cualquier mapa (el 4 es el
enrutador); con la regla "un mapa con `PlayBGM` se va con uno de los suyos"
queda la columna de abajo. Ningún evento común tiene `PlayBGM`.

Las variantes: **A**, una muestra por programa limitada por su peor paquete,
y los temas que vienen sonando pesan sólo como temas (sus muestras más las del
paquete tienen que entrar, sin los efectos: ver "La herencia"); **B**, una
copia por tema, limitada sólo por los paquetes de ese tema. "Subida" es la
música más los efectos del paquete a 1,36 cuadros por KB.

| Paquete | Temas | Puede venir sonando | Efectos | Música hoy | Música A | Música B | Libre A | Subida hoy → A (cuadros) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 4 | hzstream | Astpgmarch, Fantasia Of Th, dcbest, evilrhys, lufsorr | 0 | 7452 | 14490 | 13041 | 48093 | 10 → 19 |
| 1 | escape newyork | hzstream | 26289 | 9387 | 23472 | 35568 | 12822 | 47 → 66 |
| 2 | TF3 1 awe | escape newyork | 36765 | 10935 | 25731 | 24660 | 87 | 63 → 83 |
| 3 | evilrhys, lufsorr | TF3 1 awe, hzstream | 43029 | 14598 | 19404 | 18909 | 150 | 77 → 83 |
| 7 | hzstream | — | 12375 | 7452 | 14490 | 13041 | 35718 | 26 → 36 |
| 8 | cd4 | C3classi, cd2, hzstream | 15228 | 5706 | 12645 | 11763 | 34710 | 28 → 37 |
| 9 | hzstream, cd4, C3classi | rshinld | 10413 | 18837 | 42957 | 40752 | 9213 | 39 → 71 |
| 11 | rshinld | C3classi, cd4, hzstream | 16182 | 9342 | 22455 | 20952 | 23946 | 34 → 51 |
| 12 | cd2, hzstream | cd4 | 2529 | 14805 | 29385 | 38079 | 30669 | 23 → 42 |
| 14 | hzbreach | cd2, hzstream | 1728 | 9063 | 19062 | 23994 | 41793 | 14 → 28 |
| 16 | hzbreach, wb3mlair | — | 2529 | 14454 | 31023 | 39789 | 29031 | 23 → 45 |
| 17 | hzstream | hzbreach | 8046 | 7452 | 14490 | 13041 | 40047 | 21 → 30 |
| 18 | Astpgmarch | hzstream | 6543 | 10962 | 52281 | 48789 | 3759 | 23 → 78 |
| 19 | Gaden, 3D-Galax | hzstream | 18234 | 9522 | 44163 | 43497 | 186 | 37 → 83 |
| 20 | wb3shop | 3D-Galax, Gaden, KSSMKEND | 13518 | 7353 | 22734 | 24984 | 26331 | 28 → 48 |
| 21 | KSSMKEND | — | 4797 | 2124 | 8082 | 7803 | 49704 | 9 → 17 |
| 26 | KSSMKEND, vswar | — | 15777 | 11709 | 46728 | 46260 | 78 | 37 → 83 |
| 28 | Lunar Pyramid | KSSMKEND, wb3shop | 7146 | 9531 | 30546 | 36684 | 24891 | 22 → 50 |
| 32 | dcbest | Lunar Pyramid | 12384 | 1809 | 13086 | 14481 | 37113 | 19 → 34 |
| 33 | dcbest | — | 5058 | 1809 | 13086 | 14481 | 44439 | 9 → 24 |
| 36 | golden axe-turtlev | hzstream | 0 | 1161 | 14319 | 15129 | 48264 | 2 → 19 |
| 52 | Fire Mustang Intro | — | 7587 | 4149 | 13752 | 15480 | 41244 | 16 → 28 |
| 70 | 11h035 | — | 0 | 6003 | 13581 | 22986 | 49002 | 8 → 18 |
| 73 | 11h035 | — | 0 | 6003 | 13581 | 22986 | 49002 | 8 → 18 |
| 74 | prepara | — | 7326 | 4896 | 20178 | 24984 | 35079 | 16 → 37 |
| 121 | T ProjectJustice D, bubstix, wb3town | — | 2529 | 15327 | 54873 | 58977 | 5181 | 24 → 76 |
| 133 | pn28year | — | 5922 | 1629 | 5886 | 7866 | 50775 | 10 → 16 |
| 255 | Tnt07 | — | 4797 | 1620 | 9891 | 11916 | 47895 | 9 → 20 |
| 261 | Deflector1 | — | 15840 | 7695 | 25119 | 31815 | 21624 | 31 → 54 |
| 269 | MML2 MotherZone | — | 4797 | 1485 | 12672 | 15039 | 45114 | 8 → 23 |
| 348 | T ProjectJustice D | — | 0 | 7614 | 26784 | 23571 | 35799 | 10 → 36 |
| pelea | T VGFighterMAX Mas | — | 14832 | 15642 | 42327 | 46557 | 5424 | 40 → 76 |
| titulo | Fantasia Of The Wi, hzstream | — | 0 | 11520 | 23400 | 27225 | 39183 | 15 → 31 |

(Los mapas 5, 6, 10, 13, 23, 29, 30 y 34 no tienen temas en el paquete y no
limitan a nadie; los de la segunda mitad de la tabla son los de prueba.)

Y lo que le toca a cada programa melódico. "Lo limita" es el paquete que lo
fijó en A ("4+Astpgmar" es el 4 con `Astpgmarch` sonando); "A+herencia" es A
con el tema heredado **y los efectos** en el presupuesto; B da el rango entre
las copias de los temas que lo usan. kHz:

| Programa | Muestra | Temas | Hoy | A | Lo limita | A+herencia | B |
|---|---|---:|---:|---:|---|---:|---:|
| 0 | PIANO64 | 6 | 4.5 | 14.7 | 4+Astpgmar | 17.4 | 13.2–22.1 |
| 1 | PIANO56 | 1 | 4.7 | 22.1 | — | 22.1 | 22.1–22.1 |
| 2 | PIANO56 | 3 | 4.7 | 22.1 | — | 22.1 | 14.9–22.1 |
| 7 | CLAVI60 | 3 | 21.1 | 21.1 | — | 21.1 | 21.1–21.1 |
| 8 | CELST77 | 2 | 22.5 | 18.2 | 3 | 18.2 | 18.2–22.5 |
| 10 | M_BOX82 | 2 | no está | 19.9 | 26 | 21.5 | 14.9–21.5 |
| 11 | VIBE_64A | 3 | 7.9 | 22.3 | — | 22.3 | 15.8–18.4 |
| 13 | XYLO_72 | 1 | 22.8 | 22.8 | — | 22.8 | 14.3–14.3 |
| 15 | SANTR74 | 1 | 22.5 | 22.5 | — | 22.5 | 22.5–22.5 |
| 16 | EORG173 | 1 | no está | 18.0 | 26 | 22.5 | 18.0–18.0 |
| 17 | EORG253 | 2 | 11.1 | 22.3 | — | 22.3 | 15.3–22.3 |
| 18 | EORG379 | 3 | no está | 19.5 | 19 | 20.9 | 14.9–16.6 |
| 20 | R_ORG53 | 1 | 22.1 | 22.1 | — | 22.1 | 22.1–22.1 |
| 24 | NYLON57A | 2 | 11.1 | 22.2 | — | 22.2 | 15.2–18.1 |
| 25 | STLGT57B | 1 | 9.4 | 22.2 | — | 22.2 | 17.6–17.6 |
| 26 | JAZGT59A | 1 | no está | 19.6 | 26 | 22.0 | 15.8–15.8 |
| 27 | CLNGT60 | 1 | no está | 22.0 | — | 22.0 | 14.7–14.7 |
| 30 | DSTGT64 | 3 | 21.3 | 21.3 | — | 21.3 | 16.0–21.3 |
| 32 | ACOBS60A | 2 | no está | 20.6 | — | 20.6 | 20.6–20.6 |
| 33 | MMBAS62 | 12 | 21.0 | 18.4 | 19 | 21.0 | 13.1–21.0 |
| 34 | PCKBS50A | 2 | 12.9 | 15.2 | 4+Astpgmar | 5.8 | 12.9–15.2 |
| 35 | FRTLS48A | 3 | 8.3 | 10.4 | 3 | 6.2 | 10.4–22.9 |
| 36 | SLPBS43 | 2 | no está | 22.1 | — | 22.1 | 22.1–22.1 |
| 37 | SLPMT52A | 2 | 22.3 | 11.1 | 3 | 5.9 | 9.8–15.7 |
| 38 | SYBS148A | 6 | 10.3 | 20.6 | 26 | 22.6 | 14.4–22.6 |
| 39 | SYBS248A | 2 | no está | 19.5 | 26 | 21.6 | 15.4–17.5 |
| 40 | VIOLN68 | 1 | no está | 23.3 | — | 23.3 | 16.7–16.7 |
| 42 | CELLH64 | 2 | 21.0 | 21.0 | — | 21.0 | 21.0–21.0 |
| 44 | STRNG71B | 2 | no está | 22.1 | — | 22.1 | 15.0–22.1 |
| 45 | PIZZ_71 | 3 | 19.7 | 22.4 | — | 22.4 | 17.9–22.4 |
| 46 | HARP_57A | 7 | 12.0 | 10.6 | 3 | 5.6 | 9.9–21.8 |
| 47 | TMPNI47 | 2 | 7.2 | 11.0 | 3 | 6.0 | 9.9–15.3 |
| 48 | STRNG71B | 10 | 4.1 | 10.8 | 3 | 5.9 | 9.6–22.1 |
| 49 | STRNG71B | 3 | no está | 19.5 | 19 | 20.9 | 15.8–22.1 |
| 50 | SSTR162A | 2 | no está | 22.0 | — | 22.0 | 14.9–22.0 |
| 52 | CHOIR65A | 4 | no está | 19.7 | 19 | 21.1 | 15.9–22.3 |
| 53 | POPVX64A | 1 | no está | 21.4 | — | 21.4 | 21.4–21.4 |
| 56 | TRMPT65 | 2 | no está | 19.3 | 26 | 22.1 | 16.6–19.3 |
| 58 | TRMBN62A | 2 | no está | 13.8 | 4+Astpgmar | 18.3 | 13.8–18.3 |
| 61 | BRASS64 | 1 | 5.4 | 21.7 | — | 21.7 | 16.3–16.3 |
| 63 | SBRS255 | 1 | no está | 21.9 | — | 21.9 | 21.9–21.9 |
| 68 | OBOE_61A | 3 | 21.9 | 8.8 | 3 | 4.4 | 8.8–21.9 |
| 69 | EHORN61A | 1 | no está | 17.5 | 19 | 21.9 | 17.5–17.5 |
| 71 | SYNCL64 | 1 | no está | 20.4 | 19 | 20.4 | 20.4–20.4 |
| 73 | FLUTE65A | 1 | 21.8 | 10.9 | 3 | 5.4 | 10.9–10.9 |
| 75 | PNFLT72 | 2 | 11.9 | 18.9 | 19 | 20.3 | 16.0–21.4 |
| 77 | SHAKU63 | 1 | 8.0 | 22.1 | — | 22.1 | 15.0–15.0 |
| 79 | OCARI72A | 2 | 16.1 | 16.1 | 4+Astpgmar | 16.1 | 16.1–24.1 |
| 80 | SQUAR60 | 6 | 6.2 | 14.7 | 4+Astpgmar | 5.8 | 13.1–22.0 |
| 81 | SAW0_60 | 4 | 4.6 | 14.7 | 4+Astpgmar | 11.7 | 13.1–22.0 |
| 82 | CALLI72 | 2 | 8.3 | 22.0 | — | 22.0 | 14.9–22.0 |
| 83 | CHFFR72A | 1 | no está | 25.3 | — | 25.3 | 25.3–25.3 |
| 87 | BS_LD48 | 3 | 14.6 | 20.8 | 2 | 6.2 | 16.7–22.9 |
| 88 | FANTA53 | 3 | 8.6 | 22.0 | — | 22.0 | 17.8–22.0 |
| 89 | WRMPD72A | 1 | no está | 22.0 | — | 22.0 | 22.0–22.0 |
| 90 | POLY_60A | 3 | 8.4 | 16.9 | 2 | 4.2 | 12.6–21.1 |
| 91 | SPACE79 | 3 | 7.2 | 19.1 | 2 | 5.9 | 15.0–22.1 |
| 92 | ELP1_56 | 1 | no está | 19.6 | 19 | 22.9 | 16.4–16.4 |
| 94 | CHOIR65A | 1 | no está | 19.7 | 19 | 21.1 | 16.7–16.7 |
| 96 | ICE__60A | 1 | no está | 22.1 | — | 22.1 | 18.1–18.1 |
| 99 | ATMOS60A | 3 | no está | 21.1 | — | 21.1 | 21.1–21.1 |
| 102 | CHOIR65A | 1 | no está | 22.3 | — | 22.3 | 18.2–18.2 |
| 107 | KOTO_57 | 1 | 24.4 | 24.4 | — | 24.4 | 16.3–16.3 |
| 112 | TNKBLA5 | 1 | no está | 22.4 | — | 22.4 | 22.4–22.4 |
| 116 | SURDO60 | 1 | 9.6 | 10.7 | 3 | 5.9 | 9.6–9.6 |
| 118 | SYNDR56 | 1 | no está | 20.8 | — | 20.8 | 20.8–20.8 |
| 127 | PISTL60 | 2 | 11.4 | 22.1 | — | 22.1 | 15.0–22.1 |

Lo que dice:

* **Los 19 temas que hoy no aportan pasan a aportar todos**: en A están
  todos los programas y todos los golpes del cartucho (116 muestras contra
  67). `3D-Galax`, por ejemplo, recupera el órgano, el piano eléctrico y el
  coro, que hoy no suenan.
* **La mediana de los programas pasa de 11,1 a 20,8 kHz**, y la de los golpes
  de 7 a 14,7 (hoy sólo 28 de los 49 golpes están en el banco). El piano pasa
  de 4,5 a 14,7, las cuerdas de 4,1 a 10,8, la sierra de 4,6 a 14,7, el
  bronce de 5,4 a 21,7.
* **Lo que manda son los efectos de los mapas 2 y 3**: 36,8 y 43 KB de sus
  64. Todo lo que tocan `evilrhys` y `lufsorr` en el 3 queda cerca de 10 kHz,
  y como la muestra es una por programa, queda así en todos los temas: el
  arpa, las cuerdas 48, los golpes de batería comunes. **Seis programas
  quedan peor que hoy**, porque hoy eran cortos y el banco les daba la tasa
  del SF2 —el oboe (21,9 → 8,8), la flauta (21,8 → 10,9), el slap (22,3 →
  11,1), la celesta, el arpa y el bajo sintético 33—, y el bombo y el charles
  de la batalla bajan de 19,4 y 14,9 a unos 10,7.
* **B** —una copia por tema— saca ese techo: cada tema queda limitado sólo
  por sus propios paquetes (`escape_newyork` todo a unos 21,5 kHz, la batalla
  a 16–22). Pero son **430 muestras** y el SRCN es un byte: hoy los 92 efectos
  ocupan su lugar en el mismo directorio, así que a la música le quedan 163.
  Ver el orden de implementación.

### La herencia: el tema que viene sonando, y los efectos

`paquete_cargar_ya` no mueve las muestras del tema que suena —la música sigue
durante el fundido—, y acomoda el paquete nuevo alrededor, en orden: sus
temas y después sus efectos. Lo que no entra, no sube. Medido en la ROM
(`herencia_rom.py`: el salto con el tema del mapa de origen marcado como el
que suena, que es lo único que mira `paquete_cargar_ya`):

* **Hoy ya pasa, en el juego**: del 2 al 3 la página del ascensor salta con el
  tema del 2 sonando —recién después vuelve a pedirlo— y al 3 le faltaban
  efectos, que no volvían en toda la escena aunque la página del 3 prendiera
  enseguida `evilrhys`. Es lo que arregla el paso 1.
* **Con A, sin nada más**, faltan muchos más, porque cada paquete ya llena la
  ARAM solo: del 1 al 2 con `escape_newyork` sonando faltan 6 efectos del 2,
  del 2 al 3 faltan 10, del 4 al 19 faltan 6, y del 4 al 1 con `hzstream`
  sonando falta **el trueno entero** (23,8 KB). Y con los saltos que no son del
  juego —el arnés salta de cualquier lado— faltan también un par de muestras
  de los temas, porque las muestras quietas dejan la ARAM partida en huecos.

Las dos maneras de pagarlo:

1. **Presupuestar la herencia entera** —cada paquete tiene que entrar con
   cualquiera de los temas que pueden venir sonando, efectos incluidos— es la
   columna "A+herencia": el polysynth de `escape_newyork` a 4,2 kHz, las
   cuerdas y la onda cuadrada a 5,8. Peor que hoy en los temas que importan.
2. **Que el tema que suena tenga prioridad y los efectos esperen**: el
   paquete se arma igual, lo que no entra queda anotado, y el primer
   `PlayBGM` —que arranca el tema de cero y calla el viejo— sube lo que
   faltaba. Es el paso 1, y cuesta un congelado del tamaño de lo que faltaba
   en ese `PlayBGM`: con A, del orden de 10 a 25 KB en esos saltos, o sea
   **15 a 35 cuadros**. Los efectos del mapa no suenan entre la llegada y ese
   `PlayBGM`; en el 2 y en el 3 del juego, la página prende su tema antes de
   usarlos. A es esto: los temas heredados cuentan en el presupuesto sólo
   como temas.

La 2 es la que hace que A valga la pena; la 1 no.

### Los efectos de sonido

Son lo último de cada paquete y van a 6 kHz, recortados a 0,75 s (el trueno
del mapa 1 entero, a 22 kHz). En el presupuesto por paquete son un costo fijo
que se resta antes de repartir: por eso los mapas 2 y 3 son los que limitan.
Con el paso 1 sobreviven a la herencia; al cambio de paquete ya sobrevivían,
porque son del paquete. Si alguna vez hace falta más lugar, los del 3 son el
lugar donde buscarlo: son veinte, casi todos de la secuencia del final del
mapa, y el trueno a 6 kHz está dos veces (en el 3 y entero en el 1).

### Una muestra por zona

Hoy cada programa lleva la muestra de la zona del do central. **El 34% del
tiempo-nota melódico de los 32 temas suena a 12 semitonos o más de la raíz de
esa muestra, en teclas para las que el SF2 tiene otra.** Y es muy concentrado:
32 pares (tema, programa) tocan más de un cuarto de sus notas en otra zona, y
muchos **todas** —el bajo sintético 33 en doce temas toca `MMBAS40` y no la
del 62; la sierra de `escape_newyork` y de `hzstream`, `SAW0_48`—.

* **La zona más usada** (variante 3): cada programa lleva la muestra de la
  zona que más tiempo-nota suma en el cartucho, en vez de la del do central.
  **No cuesta ARAM** —sigue siendo una por programa— y es lo que más cerca
  dejó a `3D-Galax` de la referencia (agudos: 11,8 dB de diferencia hoy, 7,3
  por paquete, 3,4 con la zona más usada, 3,8 el techo). Lo que pierde: un
  programa que dos temas tocan en registros distintos queda bien para uno
  solo.
* **Dos zonas** (variante 4, las que tienen al menos el 15% del programa):
  **149 muestras en vez de 116**, cada una a menos tasa (mediana de 14,7 a
  12,6 kHz en los temas grabados). En la cuenta del espectro sale peor que una
  sola, porque la cuenta mide agudos y no timbre; es para escuchar en los
  graves.
* **Tres zonas** serían 151: casi nadie usa una tercera con más del 15%.

### Cuánto cuesta en cuadros, y dónde se paga

La tabla de arriba tiene la subida de cada paquete. Dónde cae:

* **El cambio de mapa**: en el fundido, que no se ve. El peor pasa de 77 a 83
  cuadros (1,4 s); los mapas 2, 3, 19 y 26 quedan todos ahí.
* **La pelea**: hoy congela unos 40 cuadros al entrar y otros tantos al
  salir; con A, unos 76 (1,3 s) cada vez. Es lo único que se vería seguido.
* **El título**: 15 → 31 cuadros, al aparecer.
* **Un `PlayBGM` a mitad de escena**: ninguno cambia de paquete —los temas
  que prende cada página ya están en el paquete de su mapa, y los eventos
  comunes no tienen `PlayBGM`—, salvo el completado del paso 1, que es lo que
  faltaba y nada más.
* **El arranque**: 10 → 19 cuadros de trabajo, adentro de los 112 que ya
  espera.

### Cartucho, banco 0 y la tanda

* **El `release` pasa de 3.246.058 a 3.518.487 B usados** con A (77,4% a
  83,9% de los 4 MB): 166 KB de muestras más —cada programa a lo que da su
  peor paquete, 116 muestras— y 106 KB de stream, que es lo que los 19 temas
  que no aportaban tenían sin muestra.
* **El banco 0 no se mueve con A**: es todo del conversor. Con el paso 1 pasó
  de 1.168 a 1.144 B libres en `release`.
* **Lo que se rompe** al implementar A: `test_un_tema_pierde_sus_muestras_pero_nunca_su_numero`
  y `test_un_tema_que_no_aporta_pierde_notas_y_la_ROM_lo_dice` prueban el
  recorte de aportantes, que se va; la huella de los 32 temas en
  `techos.toml`, que hay que volver a medir con `just techos`.

### Decisiones que habría que tomar o reescribir

* **`decisiones/un-solo-banco-de-muestras.md` no se revierte con A: se
  reescribe su porqué.** Sigue habiendo un banco, una muestra por programa,
  subido en paquetes por mapa. Lo que se va es la regla de `build_varios` de
  que el banco **entero** tiene que entrar en la ARAM, y con ella el recorte
  de aportantes y `--banco-entero`. Con B sí se revierte: cada tema tiene sus
  copias.
* **Una nueva: cuando el tema que viene sonando y el paquete no entran
  juntos, gana el tema y los efectos esperan al próximo `PlayBGM`.** Es la
  del paso 1, y la que hace posible A.
* **`decisiones/el-arranque-esta-dimensionado-para-el-techo-de-aram.md`**:
  su "lo que lo compraría" quedó viejo —el cargador de varios puertos ya
  existe—. Lo que queda por decidir es si se achica `BOOT_CUADROS` al paquete
  de arranque (con A, 19 cuadros de trabajo más 9 de mapa: se podría bajar a
  unos 48 con margen y ganar un segundo al encender) con una aserción en el
  conversor de que el paquete del mapa de arranque entra en ese tiempo.
* **La pelea a 1,3 s de congelado en cada punta**, en vez de 0,7: la memoria
  de taro dice que la calidad del audio vale unos cuadros de carga; esto es
  medio segundo más, en cada pelea.
* **`wishlist/velocidad-presupuesto-percusion.md` se va con A**: el lazo que
  baja la percusión de a 10% es el de `Banco`, que A reemplaza.
* **`wishlist/musica-del-lado-del-spc700.md`**: si algún día el secuenciador
  va al SPC700, necesita un buffer en la ARAM, y con A cada paquete la llena.
  Habría que reservarlo en el presupuesto (es cambiar el margen).

### El orden de implementación, en commits verificables

1. **Hecho: el paquete que no entró se completa en el próximo `PlayBGM`**
   (commit "Audio: el paquete que no entró con otro tema sonando se completa
   en el próximo PlayBGM"). `PAQ_INCOMPLETO` y el rearmado en
   `tema_asegurar`. Arregla ya el paso del 2 al 3. Lo cobra
   `test_el_paquete_que_no_entro_con_otro_tema_sonando_se_completa` con el
   caso `paquete-incompleto`, que exige que el paquete haya quedado
   incompleto al llegar —si no, no prueba nada— y da rojo sin el arreglo.
2. **El presupuesto por paquete (A), en el conversor.** Las listas de los
   paquetes se arman antes de `build_varios` —los temas y los nombres de los
   efectos ya se saben; los tamaños de los efectos salen de `build_efectos`,
   que es determinista— y se le pasan; `Banco` reemplaza los 40 KB y el lazo
   de la percusión por el llenado progresivo; el recorte de aportantes se va.
   El conversor calcula también la herencia realista (los `Teleport` y los
   `PlayBGM` de cada mapa, lo de `herencia.py`) y **se corta** si un paquete
   no entra solo, o si con un tema heredado no entran los temas. Imprime la
   tasa de cada muestra y qué paquete la limitó. Verificación: la ROM entera
   con `SIN_CACHE=1` igual a la de con caché, `just techos`, `just pruebas`
   con las dos pruebas del recorte reemplazadas por una que pida que cada
   paquete entre y que todos los temas tengan todas sus muestras, y
   `test_cores.py` dos veces. Para escuchar: la variante 2.
3. **La zona más usada** (variante 3), si taro la prefiere escuchando: la
   tecla con que se pide la muestra de cada programa pasa de 60 a la raíz de
   su zona más usada, y la altura de cada nota sale de esa raíz. No cambia la
   ARAM. `just techos`.
4. **El remuestreo con filtro**, aparte: `snes_samples.resample` interpola
   lineal sin filtrar, y a 10 kHz desde 22 eso repliega. Sólo cambia bytes de
   muestras; se mide con la cuenta del espectro y se escucha. `just techos`.
5. **Si hace falta más**, en este orden: bajar `BOOT_CUADROS` (decisión de
   arriba); darle a los efectos su propio lugar en el directorio —unos veinte
   por paquete en vez de los 92 del cartucho— para que entre **B** para los
   programas que limita un paquete ajeno (el oboe, la flauta, las cuerdas 48,
   la batería); y una segunda zona sólo donde se oiga.

# Qué medir en los otros temas

Con los scripts de `tools/audio/proto/` en la rama del prototipo:

* **La batería que vuelve**: medido en el 0, con la tabla; volver a medirlo
  con las envolventes puestas antes de fijar el aire.
* **Polifonía contra 8 voces y tiempo-nota perdido**: medido en el 5, y lo
  imprime el conversor por tema. El peor es `pn28year` (51%, con un piso de
  50%), después la batalla (49%, piso 35%).
* **Qué temas usan CC7, CC10, CC11 y pitch bend**, y cuánto stream sumarían.
* **Golpes recortados sin fundido**: `_build_drum` corta en 0,5 s sin
  fundido, y el platillo, el ride y el charles abierto del SF2 duran más y
  hasta traen loop; eso es un corte en seco en cada platillo. En
  `escape_newyork` no pasa —sus cuatro golpes duran menos de 0,2 s—.
* **Notas lejos del do central**, que suenan con la zona equivocada.
* El de batalla, `T_VGFighterMAX_Masako`, que es el más pesado y el que más
  se oye.

**El rango de pitch bend de 3D-Galax (95 semitonos)**: taro decidió dejarlo como pide el MIDI, que es como lo toca fluidsynth y como suena la versión de Amiga (la última nota de la frase cae varias octavas). En Windows con un sintetizador GS se habría topado en 24. Respetarlo no cuesta nada: el bend ya se escribe igual, sólo cambia el valor de la altura. 2026-09-26.
