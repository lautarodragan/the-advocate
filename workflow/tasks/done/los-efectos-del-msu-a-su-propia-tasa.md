---
name: "Los efectos del .msu, cada uno a su tasa y sólo los que conviven"
description: "Con MSU-1 todos los efectos de un paquete van a una sola tasa, la que entra con todos juntos en la ARAM: uno largo baja a los demás"
type: feature
assignee: taro
---

De taro, el 2026-09-28, al meter el `Thunder9` del despegue en la pelea: con
MSU-1, los efectos de calidad de la pelea bajaron de 14000 a 12000 Hz, todos,
por un solo trueno de dos segundos. No urge, porque 12000 Hz con MSU-1 sigue
sonando bien. El 2026-09-30 pidió que se haga.

# Por qué pasa

`rates_per_package` (`tools/rm2k-snes/rm2k-snes-audio/src/effects.rs`, antes
`tools/audio/efectos_msu.py`) elegía **una tasa por paquete**: la más alta de
`RATES` a la que entran **todos** los efectos del paquete, enteros, en lo que
la música deja libre de la ARAM. La ROM los sube todos al cargar el paquete
(`se_msu_prepare` y `se_msu_upload`, en `tools/runtime/msu_effects.s`). El
`.msu` no tiene tope: el límite son los 64 KB de ARAM.

# Dos ideas, de menos a más

1. **Una tasa por efecto dentro del paquete.** Es del conversor; hay que
   mirar si el runtime supone una tasa común en algún lado.
2. **Que en la ARAM esté sólo lo que puede sonar junto**: subir un efecto
   cuando se pide, o por grupos que salen de un análisis estático de las
   páginas.

# Lo medido (2026-09-30, Zorzal, sobre `f7e53b3a`)

Todo sobre `release`. Cada paquete tiene 62.395 B para efectos (63.419 de
muestras menos el margen de 1 KB; con MSU-1 la música de todos los paquetes
tiene pista y no ocupa nada). Los scripts, en `<scratchpad>/zorzal/`.

**Con qué se mide "cuánto pierde"**: la parte de lo que se oye de cada WAV
—su espectro ponderado con la curva A— que queda arriba de lo que deja pasar
el remuestreo a esa tasa (0,9 de la mitad). Sin la ponderación, el retumbo
de un trueno, que lleva casi toda la energía, dice que no se pierde nada
cuando se va el chasquido.

**El runtime no supone una tasa común**: la altura de cada sonido sale de
`se_msu_pitch`, que el conversor arma por paquete con la tasa de la versión
de cada efecto. La idea 1 es sólo del conversor.

## Tres criterios para la idea 1

Sobre los catorce paquetes que no entran enteros a 22050 Hz:

* **tasa única** (lo de antes);
* **baja primero el más pesado**, lo que proponía esta tarea;
* **baja primero el que menos pierde de lo audible por byte que libera**, y
  a igual pérdida el más pesado; al final lo que sobra vuelve al que más
  recupera por byte, sólo si recupera algo.

"El más pesado primero" dejaba **al peor efecto del paquete peor que la tasa
única en cinco paquetes**: el 1 (`Rain1` 12→33%), el 11 (`Glass` 37→79%), el
19 (`Glass` 56→84%), el 39 (`Sand Storm` 7→48%) y el 99 (`misslesnd`
3→48%). Los efectos largos son muchas veces los agudos —un vidrio, una
tormenta de arena—, y bajarlos por pesados es lo contrario de lo que se
quería. "El que menos pierde" **no empeora al peor de ningún paquete** y
mejora la media en todos. Se implementó ése; el porqué está en el comentario
de `fit`, en `effects.rs`.

## Antes y después, por paquete

Pierde: peor efecto del paquete / media. Bytes: lo que se sube al cargarlo.

| paquete | antes | después | bytes antes → después |
|---|---|---|---|
| pelea | 57,5% / 9,1% | 5,4% / 1,0% | 62.010 → 62.280 |
| 2 | 68,9% / 18,3% | 41,6% / 10,0% | 59.121 → 62.316 |
| 3 | 90,4% / 35,4% | 90,4% / 27,8% | 61.992 → 62.370 |
| 7 | 14,5% / 3,2% | 5,8% / 1,6% | 58.563 → 62.037 |
| 11 | 36,7% / 7,7% | 7,0% / 2,1% | 62.235 → 62.370 |
| 19 | 56,0% / 7,6% | 2,8% / 0,7% | 57.312 → 62.316 |
| 26 | 2,2% / 0,4% | 0,2% / 0,0% | 62.190 → 62.361 |
| 32 | 1,2% / 0,7% | 0,1% / 0,0% | 58.572 → 61.542 |
| 39 | 18,4% / 8,9% | 14,5% / 5,7% | 61.479 → 62.208 |
| 99 | 6,1% / 2,0% | 0,7% / 0,3% | 53.901 → 62.028 |
| 261 | 1,2% / 0,3% | 0,0% / 0,0% | 58.806 → 61.902 |
| 9, 20, 49 | 0% | 0% | +45, +2.430, +1.629 |
| 1 | 12,4% / 6,8% | igual: `Rain1` y el trueno quedan a 16000 | igual |

La pelea, efecto por efecto:

| efecto | dura | antes | después | pierde antes → después |
|---|---|---|---|---|
| `Attack2` | 0,70 s | 12000 | 22050 | 57,5% → 5,4% |
| `Escape` | 0,46 s | 12000 | 20000 | 11,6% → 0,0% |
| `Thunder9` | 1,92 s | 12000 | 14000 | 1,8% → 1,6% |
| `Item2` | 1,14 s | 12000 | 14000 | 1,0% → 0,3% |
| `Bite` | 1,00 s | 12000 | 14000 | 0,4% → 0,1% |
| `Damage1` | 0,61 s | 12000 | 12000 | 0,3% |
| `Evasion1` | 0,38 s | 12000 | 11025 | 0,0% |
| `Monster1` | 2,99 s | 12000 | 6000 | 0,0% → 0,5% |

El 5,4% del `Attack2` es lo que pierde a 22050 Hz también: es el tope.

**Lo que empeora**: la regla minimiza lo que pierde el paquete sumado, así
que en los muy cargados algunos bajan para que otros suban mucho. En el 2
(18 efectos) `Explosion3` va de 6500 a 4000 (5% → 23%) y `Holy3` de 6500 a
16000 (69% → 10%); en el 3 (20 efectos) `Flash3` de 4000 a 3000 (64% →
77%) y `Key` de 6000 a 16000 (47% → 8%). En el resto, lo que baja pierde
menos de un punto.

**Lo que cuesta**: más bytes que subir en las cargas donde la tasa única
dejaba lugar sin usar, a 1,5–1,65 cuadros por KB (abajo): el 99 unos 13
cuadros más, el 19 unos 8, el 2, el 7, el 32 y el 261 unos 5, la pelea
menos de uno. Un paquete que entra entero a 22050 no cambia. Es "calidad de
audio antes que carga"; si pesa, `fit` no sube lo que no recupera nada, y
lo que se podría tocar es no llenar hasta arriba los paquetes que ya
quedaron bien.

## La idea 2: cuánto ganaría y cuánto costaría

**Subir un efecto por el puerto del MSU-1** cuesta lo mismo que subirlo de
la ROM —el mismo comando 3 del driver, de a tres bytes, con la CPU
dedicada— más tres lecturas de `MSU_DATA` por trío. De la tabla de cargas
de `efectos-de-calidad-con-msu-1.md` (snes9x, `.msu` del cartucho contra
efectos de la ROM) y los bytes de cada lado: **1,64 cuadros por KB** en el 8,
**1,51** en el 10 y **1,58** en la pelea; de la ROM, 1,45 (`emit.rs`). Más
una búsqueda por paquete, uno o dos cuadros en Mednafen. Que suene la
música no cambia nada: con MSU-1 la música es del MSU-1 y no pasa por el
puerto.

Así que **subir al pedir no sirve**: el `Thunder9` a 22050 son 23,8 KB,
unos 38 cuadros —más de medio segundo— con el juego congelado antes de que
suene, y un golpe de la pelea tiene que sonar en el cuadro en que pega.
Subirlo de a pedazos por cuadro sin congelar lo atrasaría más todavía.
Lo único que tendría sentido son **grupos subidos en un borde** —al empezar
una escena, al abrir la pelea—, que es otra carga de paquete: ~100 cuadros
por grupo lleno.

**Cuánto ganaría**: el techo es que cada efecto suene a 22050 Hz, y con la
idea 1 ya se está a menos de un punto de eso (media) en todos los paquetes
salvo cuatro:

| paquete | a 22050 pesa | idea 1: peor / media | techo: peor / media |
|---|---|---|---|
| 3 | 291 KB | 90,4% / 27,8% | 2,8% / 0,3% |
| 2 | 201 KB | 41,6% / 10,0% | 1,5% / 0,2% |
| 39 | 90 KB | 14,5% / 5,7% | 5,8% / 0,8% |
| 1 | 86 KB | 12,4% / 6,8% | 1,3% / 0,7% |

El 1 difícilmente se arregle con grupos: son dos efectos, `Rain1` (5 s) y
un trueno, la lluvia y el trueno de una misma tormenta (no lo verifiqué en
las páginas). En
el 3 el único momento medido con tres a la vez —`Glass`, `Flash3` y `Earth4`
en la escena de `evilrhys`, `test_msu_efectos.py`— pesa 77 KB a 22050 Hz:
ese solo grupo ya no entra. La idea 2 serviría de verdad en los mapas 2 y 3
y en ningún otro, y costaría: un análisis de páginas que diga qué
`PlaySound` conviven, una tabla de grupos en la ROM, una carga de ~100
cuadros en cada borde de grupo, y el caso de los efectos del sistema.

**Los efectos del sistema**: hoy la ROM no toca ninguno fuera de la pelea
—el menú no suena— y los de la pelea (`BATTLE_AUDIO_SE`) ya están en su
paquete. Cuando el menú los toque, `Cursor1`, `Key`, `Cansel1` y `Fog1` a
22050 son 16,2 KB que tienen que estar **en todos los paquetes**, con
cualquiera de las dos ideas; con la 2, además, en todos los grupos.

**La idea 2 no se implementó**, como pedía el encargo. Mi lectura: no hace
falta salvo para los mapas 2 y 3, y ahí el costo es alto.

## La música de la radio (lo de Yarará)

Esto no la destraba ni la traba. Con MSU-1 un tema con pista no ocupa ARAM,
así que meter la radio en el paquete de la pelea no les cambia la tasa a los
efectos; lo que baja es la música **sin** MSU-1, que es el reparto del banco
y no esto. Si el tema de la radio no tuviera pista, le quitaría lugar a los
efectos de la pelea, y ahora bajarían primero `Monster1` y los que menos
pierden en vez de todos juntos.

# Lo hecho

| commit | qué |
|---|---|
| `19272b9d` | `rates_per_package` con una tasa por efecto; `audible.rs`, lo que pierde cada WAV a cada tasa |
| `85631dc0` | la prosa del runtime y de `docs/port/` que decía "la tasa del paquete" |

La prueba del crate contra lo que escribía el Python (`tests/python.rs`)
cambió a propósito su hash de los efectos de MSU-1, con el cambio escrito al
lado: sólo las tasas del paquete 3 del juego de prueba, y el `Rumble` del 1
—un WAV a 11025 Hz— anotado a esa tasa en vez de 22050, con los mismos
bytes.

**Mueve la ROM y el `.msu`**: la ROM sólo por las alturas de `se_msu_pitch`.
No mueve goldens: la tanda corre sin MSU-1.

# Cómo se verificó

* `NO_CACHE=1 just cartuchos` en la base: los sha256 del encargo
  (`abl.sfc` `e20182d1…`, `abl.msu` `905decd2…`, `special` `6784ab8f…`,
  `encounter-every-step` `5dc9114c…`).
* Después, dos veces igual: `abl.sfc` `0d43de3c…`, `abl.msu` `e53bc400…`,
  `special` `ea444940…`, `encounter-every-step` `54ef5505…`. El
  `conversor.log` cambia sólo en las líneas de las tasas y en el tamaño y la
  firma del `.msu`.
* `just pruebas` 893, `just -f tools/justfile test` 46, `cargo test -p
  rm2k-snes-audio` con `SOUNDFONT` en verde. `test_musica_techos.py` pasa.
* **Lo que ninguna prueba mira**: que suene mejor. Para eso, lo de abajo.

# Para escuchar

`/shared/audio/2026-09-30-efectos-msu/`, con un `LEEME.txt`: los efectos de
la pelea que cambian, antes y después, y los que más cambian en otros mapas,
sacados del `.msu` y decodificados a su tasa (sin la interpolación del DSP),
con el nombre y la tasa en el archivo; y los WAV originales de cuatro.

Lo que hay que escuchar sobre todo: si `Monster1` a 6000 Hz se nota, y si
`Attack2` y `Glass` ganan lo que dicen los números.

# Al mergear

* Instalar en el global **`rm2k-snes-audio`**: `just -f tools/justfile
  install rm2k-snes-audio`. Sin él, el `.msu` sale con la tasa única de
  antes.
* No agrega ni renombra scripts de Python.
* Toca un comentario de `tools/runtime/msu_effects.s`: la ROM no cambia por
  eso.
