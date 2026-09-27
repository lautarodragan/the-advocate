---
name: "El directorio de los efectos"
description: "Los efectos comparten lugares del directorio del SPC700, y con las entradas que liberan las copias le devuelven a la música lo que se puede sin bajarle a nadie"
type: refactor
---

# Qué

El directorio de muestras del SPC700 tiene 255 entradas —el SRCN es de un
byte— y estaba lleno: las muestras de la música, las copias de
`snes_music.copias` y una entrada por cada efecto del cartucho. Sin entradas
no había más copias, así que cuando un paquete lleno se comía la ARAM —los
efectos enteros de la pelea y del mapa 3, que van enteros cueste lo que
cueste— el instrumento bajaba en **todos** los temas que compartían la
muestra, no sólo en el del paquete. Con los efectos enteros bajaban 175 pares
(tema, instrumento) sin MSU-1: la tabla está en
`efectos-de-sonido-sin-recortes.md`. taro lo aceptó, y el pedido era
liberar el directorio para devolverlo.

# Status

2026-09-26, en `testing/`: hecho, en la rama del agente. Lo que queda para
taro: escuchar `/shared/audio/2026-09-26-directorio/` (tiene su
`LEEME.txt`).

# Lo que se midió antes de elegir

Todo sobre el reparto de `release` en 868259d (main con todas las pistas de
MSU-1), con los argumentos que el conversor le pasa a `build_varios`
capturados y el reparto rearmado con cada variante. "Bajan" es perder más de
0,5 kHz, como en la tabla de los 175.

**Cuántos lugares necesitan los efectos.** El paquete más cargado trae 20 (el
mapa 3; después el 2 con 18, el 19 con 11), y colorear el grafo "dos
efectos se tocan si comparten paquete" con DSATUR da **20 lugares**, el
mínimo posible. Así que de las 92 entradas de los efectos se liberan 72.

**Cuántas copias querría `copias` sin tope**: 146 (262 muestras de música);
con 20 lugares para los efectos le entran 119. O sea que el directorio
deja de ser el límite casi del todo con sólo darles a los efectos sus lugares.

**Pero hacer más copias como se hacían le baja la tasa a otros.** Con las
entradas libres y la regla de siempre —la peor primero, sin mirar a nadie—:
de los 175 pares quedan 103, pero **56 pares bajan respecto de hoy** (el koto
de `rshinld` 27,7 → 13,9, platillos de 22 a 17). Es lo de siempre de las
copias: la muestra que se libera sube y compite en los otros grupos donde
está. Así que la segunda tanda de copias sólo acepta las que no le bajan a
ningún par, y de ésas la que más suma: **de los 175 quedan 117, y 0 bajan**.
Probando sólo la peor primero con esa condición quedaban 161: la mayoría de
las buenas no son "la peor".

**Lo que ningún directorio devuelve**: de los 117 que siguen bajando, 64 son
de temas que **limita su propio paquete** —el de batalla (la pelea, 20),
`evilrhys` (el mapa 3, 13), `3D-Galax` y `Gaden` (el 19, 13 y 6),
`TF3_1_awe` (el 2, 11)—. Una copia separa a los temas de afuera del paquete
que limita; a los de adentro no los saca de ahí nada que no sea achicar ese
paquete. Los tres que más pierden son justamente ésos.

**Las otras formas, medidas**:

* **Un directorio que se reescribe con cada paquete**, sólo con lo suyo. Lo
  único que agrega a lo hecho es ARAM: el directorio de un paquete serían
  unas 30 entradas en vez de 241, unos 850 B más para muestras. Rearmando el
  reparto con 850 B más en cada paquete (una cota por arriba): `evilrhys`
  +0,3 kHz de media, el de batalla +0,4, `TF3_1_awe` +0,7. Y el costo es
  grande: el SRCN está escrito en el stream de cada tema, así que habría que
  traducirlo en `music_frame` para cada nota, o rehacer el stream por
  paquete; y el tema que viene sonando al cargar un paquete toca con sus
  SRCN de antes. No vale.
* **Renumerar las muestras de la música por paquete**: lo mismo que lo
  anterior sin el ahorro de ARAM; las copias ya no las limita el directorio.
* **Reasignar el lugar de cada efecto al cargar** (el N-ésimo del paquete en
  el lugar N): los mismos 20 lugares que colorear, pero `sonido_tocar`
  tendría que buscar el lugar del efecto en la lista del paquete o en una
  tabla de 92 bytes de RAM. Colorearlo en el conversor deja el lugar escrito
  en `sonido_tabla`, como antes.

# Lo hecho

**Los efectos comparten lugares** (`lugares_de_efectos` en
`tools/audio/snes_music.py`): cada efecto tiene su número —el que llevan las
listas de los paquetes—, su fila de `muestra_tabla` detrás de las de la
música y un lugar del directorio desde `SE_PRIMERA`, que es el SRCN de sus
filas de `sonido_tabla`. La ROM anota en `FAR_EFECTO_EN` ($7E78D0, un byte
por lugar) qué efecto subió a cada lugar: `anotar_efecto` en
`rom/src/paquete_de_audio.s` olvida al que estaba si el paquete trae otro,
`fila_de_muestra` lee la fila del anotado, y `sonido_tocar` no toca un
efecto si el anotado en su lugar es otro (el de un evento común, que no es de
ningún paquete). Los efectos con MSU-1 siguen igual: se suben en orden de
lugar, y `escribir_msu` los pone en el `.msu` en ese orden.

**Las copias en dos tandas** (`copias`): primero las de siempre, la peor
primero hasta llenar el directorio como era cuando cada efecto tenía su
entrada —son las que taro escuchó—; después, con las entradas liberadas,
sólo las que no le bajan la tasa a ningún par respecto de ésas, la que más
suma primero. Esa tanda reparte con lo que los efectos ocupan **de verdad**:
los `SE_ENTEROS` gratis van en lo que la música deja libre, y sin eso las
copias del 26 y del 261 se lo comían y el conversor se cortaba. Y reparte
con el directorio lleno, así que ninguna copia le cobra a nadie sus cuatro
bytes; el directorio quedó en 241.

**`repartir` lleva la cuenta al día** en vez de volver a sumar cada
restricción en cada vuelta: da los mismos presupuestos (comparado sobre el
reparto de `release`) y la segunda tanda son miles de repartos. Con eso y
probando las copias en el orden de lo que sumaban la vez anterior —da las
mismas copias que probarlas todas en cada vuelta, comparado en `release`—,
`build_varios` tarda menos de un segundo más que antes; probándolas todas
eran más de diez.

**El título se calla antes de cargar el mapa** (`titulo_lazo`), y no
después con `music_boot`. Al cargar una partida, `tema_actual` ya es el de la
partida, y las muestras suyas que el título había subido quedaban fijas
—"las del tema que suena no se mueven"— partiendo la ARAM: el paquete del
mapa 1, ahora más lleno, no entraba, y el `PlayBGM` del mapa lo volvía a subir
entero. Cargar en el mapa 1 pasaba de 76 a 153 cuadros; así son 99.

# Cuánto le devuelve a la música

Sin MSU-1, `release`. "Bajaban" es contra el reparto sin los efectos enteros
pagados (el de la tabla de los 175); "bajan", lo mismo después; "suben"
es contra hoy, más de 0,5 kHz.

| Tema | Bajaban | Bajan | Suben | Lo que más sube (sin enteros → hoy → después) |
|---|---:|---:|---:|---|
| `T_VGFighterMAX_Masako` | 20 | 20 | 0 | (lo limita la pelea) |
| `3D-Galax` | 13 | 13 | 0 | (lo limita el 19) |
| `evilrhys` | 13 | 13 | 0 | (lo limita el 3) |
| `TF3_1_awe` | 12 | 11 | 1 | bajo 16,7 → 14,6 → 16,7 |
| `Lunar_Pyramid` | 11 | 6 | 6 | bombo 16,0 → 14,1 → 22,0 |
| `T_ProjectJustice_DiscLoad` | 9 | 9 | 0 | |
| `vswar` | 9 | 1 | 8 | polysynth 21,1 → 12,6 → 21,1 |
| `cd2` | 7 | 0 | 9 | bajo 16,7 → 13,3 → 23,3 |
| `escape_newyork` | 7 | 5 | 3 | polysynth 21,1 → 12,6 → 21,1 |
| `rshinld` | 7 | 7 | 0 | |
| `wb3shop` | 7 | 1 | 7 | bajo 16,7 → 13,3 → 23,3 |
| `Gaden` | 6 | 6 | 0 | (lo limita el 19) |
| `cd4` | 6 | 6 | 0 | |
| `wb3town` | 6 | 6 | 0 | |
| `wb3mlair` | 5 | 0 | 5 | bajo 16,7 → 13,3 → 23,3 |
| `11h035` | 4 | 0 | 6 | golpe 51 16,4 → 13,9 → 22,0 |
| `C3classi` | 4 | 4 | 0 | |
| `Deflector1` | 4 | 3 | 2 | bombo 16,0 → 14,1 → 22,0 |
| `Fire_Mustang_…` | 4 | 0 | 5 | guitarra 19,9 → 13,6 → 22,0 |
| `KSSMKEND` | 4 | 4 | 0 | |
| `hzbreach` | 4 | 0 | 7 | guitarra 19,9 → 13,6 → 22,0 |
| `Tnt07` | 3 | 0 | 3 | bajo 16,7 → 13,3 → 23,3 |
| `bubstix` | 2 | 2 | 0 | |
| `dcbest` | 2 | 0 | 2 | bajo 16,7 → 13,3 → 23,3 |
| `golden_axe-turtlevillage2` | 2 | 0 | 3 | golpe 42 16,0 → 14,1 → 22,1 |
| `prepara` | 2 | 0 | 3 | programa 88 19,9 → 13,8 → 22,1 |
| `Fantasia_Of_The_Wind` | 1 | 0 | 2 | cuerdas 16,4 → 14,1 → 22,1 |
| `lufsorr` | 1 | 0 | 2 | golpe 35 16,2 → 13,9 → 21,8 |
| `MML2_MotherZone`, `pn28year` | 0 | 0 | 3 | |
| **total** | **175** | **117** | **77** | |

**Ningún par baja respecto de hoy**, ni por poco: 189 de los 338 suben algo y
los otros quedan igual. La mediana de los 338 pasa de 14,1 a 18,9 kHz (sin
los enteros pagados era 16,2).

Los que siguen bajando y no son de su propio paquete —`rshinld`, `cd4`,
`wb3town`, `T_ProjectJustice_DiscLoad`, `C3classi`, `KSSMKEND`— comparten
muestra con el tema de batalla o con `3D-Galax`, y la copia que los
separaría le baja algo a otro tema: la regla la rechaza.

# Lo que costó

* **Cuadros de carga**, saltando desde el título por 1, 2, 3, 8, 11, 19, 20,
  23, 26, 32, 261, 17, 255, 13, 9, 18, 121, 2, 3, 19 (cuadros de hardware
  desde el pedido de salto hasta el fin del fundido), contra 868259d: el 1
  +15, el 20 +6, el 2, el 32, el 255 y el 121 +4; el 9 −2 y el 18 −3; los
  demás igual. Los paquetes que no estaban llenos ahora llevan copias a más
  tasa. Cargar una partida en el mapa 1: de 76 a 99 cuadros (sin callar el
  título antes eran 153).
* **Ciclos**: `anotar_efecto` dos veces por efecto del paquete y la pregunta
  de `sonido_tocar`, unas decenas de ciclos cada una; nada al lado de subir
  las muestras.
* **Banco 0** en `release`: de 526 a 388 B libres (el código nuevo de
  `paquete_de_audio.s`, `efectos_de_sonido.s` y `titulo.s`).
* **RAM lejana**: $7E78D0 a $7E78FF para `FAR_EFECTO_EN`, uno por lugar;
  `SE_LUGARES_MAX` en snes_music.py es ese tamaño.
* **Cartucho**: las muestras de la música pasan de 295 KB a 461 KB (58
  copias más). Los efectos, sus 92 muestras y sus alturas, byte por byte
  iguales: cambió sólo su SRCN.

# Pruebas

`just techos` (la mezcla cambió), `just cartuchos` y `just pruebas` en verde,
`test_cores.py` dos veces y `test_musica_escrituras.py`. Nuevas, las dos en
`pruebas/rpgmaker/test_musica_paquete.py`:

* `test_los_efectos_comparten_lugares_y_a_las_copias_les_sobran_entradas`:
  del cartucho, que el directorio no esté lleno —las copias pararon porque
  ninguna sumaba—, que ningún paquete tenga dos efectos en un lugar y que los
  lugares sean los del paquete más cargado. Con main falla: 255 entradas.
* `test_un_efecto_no_suena_con_la_muestra_de_otro`: `Success2` en el mapa 10
  con otro efecto anotado en su lugar no suena, y sin tocar nada sí. Con la
  pregunta de `sonido_tocar` sacada, falla.

`test_la_partida_cargada_arranca_con_su_musica` miraba `music_apagada` tres
cuadros después de elegir, en medio de la carga del mapa; ahora espera un
tick, porque durante la carga el título está callado a propósito.

**Lo que no cubre `just pruebas`**: que la segunda tanda de copias no le baje
a nadie lo asegura `copias` al elegirlas, sobre el reparto, y se midió con el
reparto de verdad (`Banco`, con el redondeo a bloques) comparando cada par
contra 868259d: ninguno baja. Los cuadros de carga los midió un script
aparte. Y el camino de un efecto de evento común que no está en ningún
paquete —el que protege la pregunta de `sonido_tocar`— no existe en el juego
hoy: la prueba lo fuerza.

# Para escuchar

`/shared/audio/2026-09-26-directorio/`, con su `LEEME.txt`: los tres que más
pierden por los efectos enteros (que suenan igual: los limita su paquete) y
tres de los que recuperan, antes y después, sin MSU-1, a -16 LUFS.
