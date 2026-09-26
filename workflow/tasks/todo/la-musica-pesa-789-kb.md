---
name: "La música pesa 789 KB"
description: "El stream de cada tema son escrituras crudas al DSP; un formato por nota lo baja a un tercio sin cambiar ni una escritura"
type: refactor
---

La radiografía de `juntar-release-y-test-main.md` pone a `tema_stream` arriba
de todo: 789 KB en el cartucho unido, el 21%. Esto es **por qué pesa eso y qué
se ganaría**, medido el 2026-09-25 sobre `6f1dc4a`. No hay nada implementado.

Todo lo medido sale de los `musicdata.inc` que `just cartuchos` dejó armados
ese día: **`test-main`, 31 temas, 768.863 B de stream**. El unido son esos
31 más el del título, `Fantasia_Of_The_Wind` —18.387 B en `release`—, y de ahí
salen los 789 KB. Los scripts que midieron fueron descartables, así que antes
de implementar hay que volver a medir: los números de abajo son del día.

# De qué está hecho

**El stream no son notas: son escrituras crudas al DSP.** Tiene tres opcodes
(`tools/protocol/music.toml`): `OP_DSP registro valor` (3 B), `OP_WAIT cuadros`
(2 B) y `OP_END`. Cada nota es la preparación entera de una voz —volumen
izquierdo y derecho, altura en dos bytes, muestra, ADSR1, ADSR2— y después un
`KON`; soltarla es apagar el ADSR1 y escribir el GAIN. `pack` saltea lo que no
cambió, y ésa es toda la compresión que tiene.

| Qué | Bytes | % | Escrituras por nota |
|---|---:|---:|---:|
| Altura (`PITCH_L` + `PITCH_H`) | 272.061 | 35,4 | 1,00 + 0,85 |
| ADSR1: prenderlo en cada nota y apagarlo en cada release | 182.532 | 23,7 | 0,62 + 0,62 |
| `KON` y el `KON=0` que lo baja en el cuadro siguiente | 131.949 | 17,2 | 0,45 + 0,45 |
| Volumen (`VOL_L` + `VOL_R`, siempre iguales) | 65.334 | 8,5 | 0,22 + 0,22 |
| Esperas | 63.016 | 8,2 | 0,64 |
| Muestra (`SRCN`) | 51.909 | 6,8 | 0,35 |
| ADSR2, GAIN, KOF, arranque, fin | 2.062 | 0,3 | — |
| **Total** | **768.863** | | **15,7 B por nota** |

49.063 notas que suenan, 3.529 segundos de música: 218 B por segundo.

Lo que **no** hay, y que la pregunta suponía:

* **Ni un byte de eventos de control.** `midi.py` tira los CC, el pitch bend y
  el aftertouch al leer; el stream no tiene volumen de canal, paneo ni bends.
  Los MIDI sí los traen —4.427 CC11, 3.851 CC7, 1.532 CC10 y 1.058 bends entre
  los 32—: sumarlos algún día **agrega** bytes, no los saca.
* **Ni loops desenrollados.** Ningún MIDI trae CC111, el punto de loop que
  respeta RM2k, así que el stream es el MIDI una vez y al terminar vuelve a
  empezar (`music_frame`). Lo que sí hay es **música que se repite adentro del
  MIDI** —los compases escritos dos veces—, y eso se mide abajo.
* **Ni canales duplicados.** Pero hay algo parecido y peor: **116.805 B, el
  15%, son notas que nunca suenan.** Cuando un canal pide más notas a la vez que
  voces tiene, `build_events` le roba la voz a la que termina antes, y si las
  dos arrancan en el mismo cuadro la segunda pisa la preparación de la primera
  antes del `KON`. Son 12.881 preparaciones enteras escritas para nada.

Por tema, los más pesados:

| Tema | Bytes | Notas | Segundos | B/s |
|---|---:|---:|---:|---:|
| `T_VGFighterMAX_Masako` (batalla) | 156.520 | 8.467 | 226 | 692 |
| `3D-Galax` | 60.346 | 4.322 | 267 | 226 |
| `cd4` | 50.849 | 3.127 | 149 | 341 |
| `Lunar_Pyramid` | 37.205 | 2.401 | 183 | 203 |
| `bubstix` | 37.137 | 2.631 | 195 | 191 |
| `evilrhys` | 36.461 | 2.385 | 120 | 304 |

El resto baja de 35 KB a menos de 1 KB. El de batalla es la quinta parte de
todo el stream solo, y es el más repetitivo de todos: ver abajo.

# Por qué es así

Ninguna razón de tiempo real ni de ciclos. Es la forma más simple que funciona,
y el tamaño no importaba cuando se eligió:

* **El PoC** (`cd11930`, 2026-09-01): "la lógica en Python y en la consola un
  intérprete de un stream". Un opcode genérico hace que el lado del 65816 sea
  leer dos bytes y pasarlos por los puertos; cualquier cosa que el DSP sepa
  hacer se puede pedir sin tocar la ROM.
* **El caché de registros** (`d8c0689`): el stream de `11h035` pesaba 35 KB,
  "más que la ROM entera", y saltear lo que no cambia lo bajó a 19 KB. Es la
  única compresión que se le hizo, y su argumento de por qué es seguro con el
  loop sigue en el docstring de `pack`.
* **El release por GAIN** (`baf4bbd`) **es a propósito y es calidad**: el
  release del ADSR no se configura y con `KOF` la nota se corta en 8 ms.
  Soltar apagando el bit del ADSR1 y pidiéndole una caída a GAIN es lo que hace
  que el piano se apague en vez de cortarse. Cuesta el 24% del stream —el ADSR1
  va y viene en cada nota— y **no hay que tocarlo**: lo que se puede tocar es
  cuántos bytes cuesta pedirlo, no las escrituras.
* **El `KON` nunca se cachea**, también a propósito: es un disparador y no un
  cerrojo, y hay que bajarlo a mano. Otro 17%.
* **"Del cartucho sobra"**: lo dice el docstring de `build_varios` —"un índice
  no cuesta ARAM: cuesta su stream, que vive en el cartucho, y de ése sobra"— y
  el de `Banco`. Era cierto con tres temas. Con el cartucho unido en 89,6% ya
  no, y `el-cartucho-se-queda-en-4-mb.md` dice que se revisa al 85-90%.

Lo que se compró con la forma de hoy y hay que conservar: el `irq_musica` es
corto, no necesita RAM propia más allá del puntero, y la sombra de los efectos
de sonido (`dsp_musica`, `SE_SOMBRA`) recibe escritura por escritura. Todo lo
de abajo mantiene esas escrituras idénticas.

# Qué se podría ganar

Ordenado por bytes contra riesgo. Los tamaños son sobre los 768.863 B de
`test-main`.

## 1. Un formato por nota, que el 65816 expande a las mismas escrituras

**De 768.863 a 258.639 B (−66%). Con un diccionario de alturas por tema, a
219.794 (−71%): 549 KB menos.** Riesgo musical: ninguno, **y está medido**:
el prototipo re-codificó los 31 temas de `test-main` y los 22 de `release`, los
decodificó, y la secuencia de escrituras al DSP salió idéntica a la de hoy,
cuadro por cuadro, en todos.

Lo que se codificó:

* **Una nota**: un byte de cabecera —voz, "es nota", y tres banderas: cambia el
  volumen, cambia la parte alta de la altura, cambia el instrumento—, la parte
  baja de la altura, y detrás sólo lo que la cabecera dice que cambió. El
  volumen va una vez, porque izquierda y derecha son siempre iguales. El
  instrumento es un índice a una tabla por tema de ternas `(SRCN, ADSR1,
  ADSR2)`: ningún tema pasa de 18. El decodificador lleva la sombra de los
  registros de cada voz y hace el mismo "saltear lo que no cambió" que hoy hace
  `pack`, así que el ADSR1 que apaga el release vuelve solo en la nota
  siguiente, sin gastar un byte.
* **Un release**: un byte —voz y "suelta"—; el GAIN sólo si cambió, que es
  115 veces en todo el cartucho.
* **El `KON` sale implícito**: el decodificador junta las voces que recibieron
  nota en el cuadro, escribe `KON` al cerrarlo y `KON=0` al abrir el
  siguiente. Es exactamente la regla de hoy, y se lleva el 17% sin cambiar una
  escritura.
* **La espera es el cierre del cuadro**: un byte, hasta 64 cuadros; dos para
  más.
* Las escrituras del arranque y el `KOF` final van con un escape crudo.

Con el diccionario de alturas —un índice por tema a las alturas que usa, que no
pasan de 103— el stream pasa de 15,7 B por nota a 4,4, contando todo. De qué
queda hecho:
cabeceras de nota 28,6%, índices de altura 28,6%, cierres de cuadro 14,4%,
releases 14,1%, instrumento 8%, volumen 5%.

**Lo que cuesta**, estimado y no medido:

* **Ciclos del 65816**: por nota, comparar siete registros contra la sombra y
  mirar dos tablas; unos cientos de ciclos. Las escrituras por cuadro siguen
  siendo las mismas —la mediana 5, el 99% de los cuadros hasta 32, el peor
  56—, y lo que domina hoy es la espera del testigo del SPC700 en cada una, que
  no cambia. `musica-del-lado-del-spc700.md` pone el costo de hoy en hasta
  veinte líneas por cuadro; esto le sumaría del orden de unas pocas.
* **RAM**: la sombra de las ocho voces —64 B— más volumen, altura alta,
  instrumento y GAIN corrientes por voz, unos 100 B. La `BSS` tiene 108 libres
  y la página cero 3, así que va a `ram_lejana` con direccionamiento largo,
  como ya hace `SE_SOMBRA`.
* **Código**: el decodificador reemplaza a `music_frame`; `music_tick` vive en
  el banco 0, al que en el unido le quedan ~1,9 KB.
* **ARAM: nada.** Se decodifica del lado del 65816 y el driver del SPC700 no
  cambia. Decodificar en el SPC700 ahorraría viajes por los puertos pero
  crecería el driver, y la ARAM es lo más apretado que tiene el audio.

**Qué lo cobraría si sale mal**: casi nada de la tanda, y eso es lo primero a
resolver. No hay goldens de audio. `test_musica_paquete.py` usa
`muestras_del_stream`, que habría que reescribir para el formato nuevo —se
rompería fuerte, bien—; `test_tema_del_mapa.py` mira que el puntero avance, y
sigue valiendo. `test_msu.py` compara la misma ROM con y sin pista, así que no
ve el formato. Hacen falta dos redes:

* **en Python, codificar y decodificar da las escrituras de `pack`**, para todos
  los temas del cartucho: es lo que hizo el prototipo, y es barato;
* **y el decodificador del 65816 contra ése**, que ninguna prueba de Python
  cubre. Lo más directo es grabar el audio de la ROM vieja y la nueva con el
  mismo tema y compararlo. Las escrituras son las mismas en el mismo cuadro,
  pero el decodificador tarda distinto adentro de la IRQ, así que un `KON`
  puede caer una o dos muestras del DSP más tarde: **hay que medir si sale
  idéntico byte por byte** antes de proponerlo como prueba. Si no sale, la
  alternativa es leer desde el core los registros del DSP al final de cada
  cuadro.

## 2. Saltar a lo que ya se tocó: compases repetidos, sin RAM

**Sobre el formato 1 con diccionario: de 216.290 a 121.018 B (−95 KB más).**
Un opcode "tocar N bytes desde tal lugar del mismo tema y volver", de un solo
nivel: la fuente tiene que ser bytes que se emitieron tal cual, no otro salto.
Al decodificador le cuesta un puntero de vuelta y una cuenta —5 B de RAM— y
nada de ciclos. Riesgo musical: ninguno, porque lo que se expande son los
mismos bytes.

Por qué gana tanto: las repeticiones exactas de 64 B o más cubren el 37% del
formato 1. El de batalla tiene una de 2.638 B y 143 en total; `evilrhys`, una
de 2.822; `C3classi`, una de 2.319. Sobre el formato de hoy rinde menos, porque
el caché de registros hace que la segunda vuelta de un compás no escriba lo
mismo que la primera.

## 3. Descomprimir con ventana en la RAM

**Sobre el formato 1 con diccionario: LZSS con ventana de 4 KB, 64.948 B;
de 32 KB y coincidencias de hasta 258, 60.422.** O sea 704 KB menos que hoy.
La cota —zlib— es 43.414 sobre el formato 1 con diccionario, y 71.778 sobre el
de hoy.

Cuesta una ventana en la RAM lejana —4 KB a 32 KB—, del orden de cuarenta
ciclos por byte que sale —estimado—, y el formato 1 gasta en promedio un byte por cuadro, así que el
tiempo no es el problema; el problema es la complejidad y la RAM. Hay que
confirmar dónde: `ram_lejana.s` no nombra nada en el banco `$7F`, pero eso hay
que verificarlo con el mapa entero y no darlo por libre. Riesgo musical:
ninguno, mismo argumento.

**Descomprimir el tema entero al prenderlo**, en vez de en vivo, pediría 48 KB
de RAM para el de batalla ya en formato 1, y un `PlayBGM` pasa en medio de
un evento: frenaría el juego ahí, no en un fundido. No lo recomiendo.

## 4. No escribir las notas que nunca suenan

**116.805 B del formato de hoy; 32.233 sobre el formato 1.** Es cambiar
`build_events` para que la nota que pierde la voz en el mismo cuadro no emita
su preparación. Es lo más barato de hacer —unas líneas en Python, nada en la
ROM— pero **no deja las escrituras idénticas**: saca la preparación pisada, que
hoy le cambia la altura y el volumen a la voz durante los microsegundos que
tarda en llegar la siguiente. Eso no se oye, pero ya no hay comparación exacta
que lo demuestre. Conviene hacerlo **después** del 1 y en su propio commit.

## Resumen

| | Bytes | Ahorro | Riesgo |
|---|---:|---:|---|
| Hoy | 768.863 | | |
| 4 solo, sobre el formato de hoy | ~652.000 | −15% | las escrituras cambian; no se oye |
| 1, formato por nota | 258.639 | −66% | ninguno, verificado |
| 1 con diccionario de alturas | 219.794 | −71% | ninguno, verificado |
| 1 + 2, saltos de un nivel | ~124.500 | −84% | ninguno |
| 1 + 3, LZSS con ventana de 4 KB | ~68.500 | −91% | ninguno; RAM y complejidad |

Las tablas por tema —instrumentos y alturas, 3.504 B— están sumadas en las
filas de 1 + 2 y 1 + 3. En el cartucho unido, el 1 con diccionario son unos
565 KB menos: del 89,6% a algo como el 76%.

# `muestra`: 269 KB

**268.794 B, y el 79% son efectos de sonido, no música.**

* **Música: 58 muestras, 57.285 B.** Está topada por la ARAM —el banco entero
  tiene que entrar en los 64 KB del SPC700, `un-solo-banco-de-muestras.md`—,
  así que no crece con los temas: crecen los temas que se quedan afuera.
  **Cinco grupos son byte por byte iguales**, 6.453 B; no miré de qué
  programas o golpes salen. Eso
  cuesta ARAM además de cartucho cuando dos caen en el mismo paquete, y ahí sí
  importa: es resolución que se le podría devolver a otra muestra.
* **Efectos: 92, 211.509 B.** 50 están en el tope, 2.529 B —0,75 s a 6 kHz,
  `SE_MAX_SEGUNDOS` y `SE_TASA`—, y el trueno entero de la apertura son 23.760
  (`el-trueno-va-entero-a-22-khz.md`). Todos entran en el paquete de algún
  mapa, así que no hay ninguno muerto. `efectos-de-sonido-sin-recortes.md`
  quiere levantar esos topes, y eso lo va a hacer **crecer**.
* **Nada obvio que comprimir**: BRR ya es 9 bytes por cada 16 muestras, y zlib
  sobre todas las muestras da el 92%.

# El MSU-1, como contexto

22 temas tienen pista (`PISTAS_MSU`). Con MSU-1 la ROM calla el SPC700 y el
stream no corre, pero **sin MSU-1 es lo único que suena**, así que tiene que
estar igual: la pista no ahorra ni un byte de stream. El de batalla tiene
pista, y aun así es el que manda en todo lo de arriba.

# De paso, medido y no arreglado

* **686 notas se sueltan antes de tiempo** —10.308 cuadros en total, 329 notas
  en `escape_newyork`—. Cuando una nota le roba la voz a otra que termina
  antes, el release de la robada ya quedó agendado en su cuadro final y suelta
  a la que robó. No lo oí; es para una tarea aparte, de tipo `bug`, y taro
  diría si se nota.
* **Una nota cuyo programa no está en el banco ocupa la voz igual**:
  `busy[voice]` se anota antes del `continue` de `build_events`, así que la
  nota que no suena les quita la voz a las que sí.
