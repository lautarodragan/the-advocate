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
arriba y para el reparto** → reparto y rampa → muestras por mapa.


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

## 0. El arreglo de `dsp_musica`, ya

Es un bug y vuelve la batería de todos los temas. **Ciclos**: tres
instrucciones más por escritura a las voces 6 y 7. **Stream, ARAM**: nada.
Lo que tiene que venir con él es la prueba que faltó: grabar el audio de un
tema con sólo percusión y exigir que no sea silencio, o algo equivalente que
mire las voces 6 y 7. Hoy ninguna prueba ejecuta ese camino con valores
distintos de cero, y por eso sobrevivió dos semanas.

## 1. Las notas que se sueltan antes de tiempo

Ya es `notas-que-se-sueltan-antes-de-tiempo.md`. Se oye poco —son 329 notas,
casi todas del bajo de 6 cuadros—, pero **achica el stream un 11%** en el
cartucho, porque ya no se escriben releases que no hacen nada. Python, unas
líneas. Va en su propio commit, antes o después del formato nuevo, no junto.

## 2. Envolventes del SoundFont, con aire

Amplía `ataque-y-decaimiento-desde-el-soundfont.md` en dos cosas que la
grabación mostró:

* **La velocidad del release sí sale del SF2.** El mecanismo sigue siendo el
  de hoy —apagar el ADSR y pedir GAIN—; lo que cambia es con qué velocidad.
  Con la de hoy el bajo arrastra 2,4 s de cola donde el SF2 pide 30 ms. Los
  releases de menos de 100 ms van con GAIN **lineal**: el exponencial más
  rápido tarda 25 ms en llegar a cero y no alcanza.
* **La caída exponencial del DSP no es exponencial hasta el final**: por
  debajo de 1/8 resta de a uno y llega a cero en unos 790 pasos. Hacerla
  coincidir en pendiente con el SF2 la apaga antes de tiempo —el piano se
  callaba a los 1,4 s en vez de seguir a -26 dB—; el prototipo la hace llegar
  a cero donde el SF2 anda por -40 dB.

Hay que leer los generadores 33 a 40 del SF2 (retardo, ataque, hold,
decaimiento, sostenido, release y el escalado por tecla). El prototipo trae
un lector de Python descartable; lo de verdad es que **`gunter sf2 --extract
--json` los devuelva**, que es del formato y no del juego.

**Costo**: +1,8% de stream en el formato de hoy (el piano cambia de ADSR2 por
tecla); nada de ARAM ni de ciclos. El aire va en el mismo cambio, porque sin
él el 04 satura.

## 3. Curva de velocidad y controladores

La velocidad al cuadrado y CC7, CC11 y CC10 sobre las notas que suenan.
**Costo**: +4% de stream en el formato de hoy —en otros temas hay 4.427
CC11, 3.851 CC7 y 1.532 CC10—; nada de ARAM ni de ciclos. El pitch bend no se
prototipó porque este tema no tiene: hay 1.058 entre los 32 MIDI, y cuesta
una escritura de altura por paso del bend.

## 4. El formato por nota

`la-musica-pesa-789-kb.md`, idea 1. Va **acá, antes del reparto**, por los
bytes: el reparto del 5 suma **+74% de stream** en el formato de hoy —las
voces cambian de instrumento y de volumen seguido, y cada cambio son tres
bytes por registro—; en el formato por nota es un índice de instrumento de un
byte cuando cambia. Lo que este estudio le pide al formato, para diseñarlo
una sola vez:

* el instrumento como índice a (SRCN, ADSR1, ADSR2), y el ADSR2 puede variar
  por tecla dentro de un programa;
* volumen izquierdo y derecho distintos cuando hay paneo;
* el GAIN del release por instrumento, no uno por tema;
* un evento de "rampa" de un byte para el punto 5, o que el decodificador la
  deduzca;
* cambios de volumen de un canal que suena, por CC7/CC11.

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

* **La batería que vuelve**: con el 0, todos los temas suenan más fuerte y
  pueden saturar; mirar el recorte tema por tema antes de fijar el aire.
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
