---
name: "La carrera y lo que sigue"
description: "Plan: la persecución en auto (49 a 54) y el 64 en release, el fin de la demo detrás de la carrera, y la regla de mapas por id"
type: feature
---

# Qué

Lo que sigue a `lashe-city-hasta-la-carrera.md`. Lo pidió taro el
2026-09-27: si entra, **la carrera** (49 a 54, y el 55 si hace falta) **y el
64**; después, si sigue habiendo lugar, **el 83 y el 84**, para que la regla de
qué mapas lleva `release` deje de ser la lista de `MAPAS_DEL_JUEGO` en
`tools/ensamblado/cartuchos.py` y pase a ser "los mapas con id menor a X" más
un `--exclude-maps` corto. El fin de la demo, que hoy está en el fork del 36
(`parches/manual/mapas/Map0036.json`), se muda a después de la carrera.

Esto es el plan; los hitos de abajo se vuelven tareas propias al lanzarlos.

Todo lo medido acá es del 2026-09-27 sobre `91a84c4` (el merge del hito 4 de
Lashe City), con variantes de `release` armadas aparte —`release` ni
`cartuchos.py` se tocaron—. Los scripts quedaron en `/extras/scratch/carrera-plan/`:
`armar.py` arma una variante (`release` con mapas de más o de menos),
`medir.py` saca el espacio con el método de `AGENTS.md` (un `.res N, $00` en el
segmento y el mensaje de `ld65`; el banco 1, hasta el último byte distinto de
cero), `far.py` mide el banco 1 aunque ya no entre, `culpables.py` es el
`medir.py` del plan anterior (qué comando frena cada página),
`perdidos.py`/`seguir.py`/`foto.py`/`intro.py`/`volante.py` corren la carrera
en el emulador, y `arreglos-temporales.diff` son los dos arreglos del
conversor que hicieron falta para armar la variante de X = 85 (ver el hito 4).

# El recorrido

    36  "We've got to get out of here" ......... Teleport [49, 1, 26]  (hoy: fin de la demo, fork)
    49  primera vuelta. RaceControllerZERO: cuatro mensajes, pantalla negra,
        el cartel de los controles (ShowPicture 'EscapeInst') y un
        KeyInputProc que espera cualquier tecla; prende 171
        RaceController1 (auto): tema, saca a todos del grupo y mete a CarRED
        (19) o CarBLUE (20) según el 130/131, PanScreen, prende 170
        RaceController2 (paralela, 170): empuja al héroe a la derecha cada
        cuadro y lo cambia de carril con arriba/abajo (KeyInputProc sin espera)
        eventos 4 a 37 (paralelas): los autos. Cada uno lee su celda
        (ControlVars clase 6) y la compara con la del héroe; si coinciden,
        cambia el gráfico del auto, anima el choque, prende 172 y salta al 50
        eventos 38 a 43 (paralelas), x = 255: la meta, salta al 52
    50  ResetRace: cuenta los choques (var 38); con cinco o más el compañero se
        ofrece a manejar (ShowChoice) y salta al 51; si no, vuelve a la vuelta
        que estaba (49, 52 o 54, por los switches 174 y 178)
    52  segunda vuelta: lo mismo, sin la intro. Meta -> 54
    54  tercera vuelta. Meta -> 51
    51  el puente: 12 páginas paralelas en la columna 75, el salto (una ruta
        forzada con sonidos adentro) -> 53
    53  RaceFinished (auto): el premio según los choques —oro e ítems— -> 64
    64  Leaving Lashe City Scene (auto): la escena con el compañero; termina en
        Teleport [66, 71, 29], el mapa del mundo, que no entra en la VRAM

El 55 es la carpeta de la carrera: nadie salta ahí, y no hace falta.

**El 83 y el 84 no se alcanzan**: al 83 se llega desde el 82 y el 84 sale al
66, y los dos cuelgan del mundo (el 66), que no entra. Meterlos es sólo para la
regla.

# Espacio

Medido con `medir.py`. "Banco 0" es lo que queda en `TABLAS`+`CODE`; `BSS` y
`ZEROPAGE` no se mueven en ninguna variante (109 y 4 bytes) y se omiten.

    variante                                cartucho  banco 0  banco 1
    release hoy                              70,9%     211     10.266
    (a) + 49 50 51 53 54                     72,3%     205     10.266
        + el 55                              72,3%     205     10.266
    (b) + 64                                 71,1%     211     10.266
    (c) + 83 84                              71,1%     211     10.266
    (a)+(b)+(c)                              72,6%     205     10.266
    la carrera + 64 (lo del hito 1)          72,5%     205     10.266
    (d) X = 65, todos                        73,9%     201     10.266
        X = 65 sin 15 22 46 55 58            72,5%     205     10.266
    (d) X = 85 sin 66 67 69 (*)              82,3%     129     10.033
        X = 85 sin 15 22 46 55 58 66 67 69   81,0%     133     10.033

    (*) sólo arma con los dos arreglos del conversor del hito 4

El hito 4 de Lashe City ya está adentro de estos números: el banco 0 que dejó
es el de la primera fila. `test-special` no lleva ninguno de estos mapas.

**El cartucho sobra**: lo que cuesta cada mapa en ROM son decenas de KB y queda
casi un 30% libre. **Lo que aprieta es el banco 0**: la carrera se come 6
bytes, y cada arreglo de motor que pida la carrera cuesta del orden de diez
(ver "Qué le falta"). X = 85 se come 72 más.

El banco 1 está holgado desde el hito 4, que mudó `tropa_codigo` y
`mensajes_tropa` a RODATA. Antes de eso X = 85 no entraba: el 76 (Sorbe
Mountain) trae tropas nuevas y se pasaba por 2.314 bytes.

Sin MSU-1, la carrera y el 64 (dos temas nuevos, `Fire_Mustang_…` y `prepara`)
bajan seis pares (tema, instrumento) y suben dos; el peor es `wb3mlair`
programa 33, de 23,3 a 13,3 kHz. Va a `el-audio-despues-de-lashe-city.md`.

## Lo que no entra con X = 85

    66  Lashe Area: "no puede llevar ventana de mensaje: gasta 527 tiles de
        fondo y 222 de sprite" (la misma razón por la que está afuera hoy)
    67  Yun Town: "el cronómetro no entra: el mapa ya usa las 8 paletas de sprite"
    69  Sorbe Village: "con este reparto de VRAM, encima necesita 157 tiles y
        entran 128"

Y **dos errores latentes del conversor**, que esta variante destapó y que no
son de X = 85 sino de cualquier cartucho con otro acomodo:

* **La ruta propia de una página apunta al bloque de código equivocado** cuando
  el bloque está deduplicado: `tabla_de_paginas` en `snes_convert.py` arma el
  puntero de la ruta con `"evcodigo_%d" % numero` —el mismo error que su propio
  docstring cuenta que se arregló para el código— y el ensamblado se cae con
  "Symbol 'evcodigo_82' is undefined". El arreglo es usar la etiqueta
  `evcodigo` que ya recibe.
* **`actor_hpmax` y `actor_spmax` van a RODATA sin `.bloque`**
  (`words_asm(..., declarar=False)`), así que `bancos.py` las puede partir entre
  dos bancos. Con la variante de X = 85 el corte cayó en el medio de una
  palabra y `bancos.py` se negó; si cae entre dos palabras no se niega, y la
  ROM lee lo que hay en `$xx:0000` para los actores de la cola. Hay que mirar si
  hay más tablas así.

## Lo que sale de X

**Recomendado: X = 65**, o sea todo el capítulo de Lashe City. Convierten todos;
la lista de exclusión sería

    58  Aura Tutorial: de otro capítulo (cuelga de Tutorials, 161). Trae su
        propio tema y dos animaciones: 46,7 KB y 4 bytes de banco 0
    15 22 55   carpetas (Lashe City, The Rat Tracks, la de la carrera): negras,
        nadie salta ahí
    46  Security Footage 2: un respaldo inalcanzable
        (los cuatro juntos: 12,9 KB y nada de banco 0)

más el 164 (el tutorial de AG7) como agregado explícito, porque la regla por id
no lo alcanza, y los `MAPAS_DE_PRUEBA` como hoy (el 52 pasa a ser del juego).

X = 85 mete 18 mapas que no se alcanzan (el mundo no entra), cuesta 8,5% del
cartucho y 72 bytes de banco 0 más que X = 65, y su lista de exclusión arranca
con ocho ids. Tiene sentido el día que entre el 66.

# Qué le falta para funcionar

Contado con `culpables.py` sobre la variante con la carrera y el 64:

    mapa  compilan  lo que frena
    49    43 de 44  KeyInputProc sin espera (RaceController2)
    50     1 de 1
    51     8 de 9   KeyInputProc sin espera
    52    42 de 43  KeyInputProc sin espera
    53     1 de 1
    54    42 de 43  KeyInputProc sin espera
    64     3 de 4   Teleport -> 66
    83    58 de 58
    84     3 de 4   Teleport -> 66

Ningún evento de estos mapas llama a un común, y ningún común paralelo o
automático mira los switches de la carrera (el 37 de AG7 queda afuera: la
carrera saca a AG7 del grupo).

**Lo que ya se sabía, corregido:**

* **`ControlVars` de clase 6 no falta.** Las 268 de la carrera piden la x o la
  y (sub-operandos 1 y 2, 134 cada uno), que la ROM hace desde antes de este
  plan. El
  comentario de `MAPAS_DEL_JUEGO` que dice que la carrera queda afuera "por
  `ControlVars` de clase 6" está viejo.
* **Páginas paralelas: 41** en el 49, el 52 y el 54 (40 autos y metas, más el
  volante) y **13** en el 51. Entran en `PARALELO_MAX` (48).
* **`KeyInputProc` sin espera**: cuatro páginas, el volante de cada vuelta. El
  `raise` de `KEY_INPUT_PROC` en `eventos.py` lo frena por una razón que ya no
  existe —la referencia en Python se fue el 2026-09-16—, y la ROM lo tiene hecho.

**Lo que se midió corriendo la carrera** (variante con `TECLA_SIN_ESPERA=1`,
que acepta el volante), en orden de cuánto destraba:

1. **Un `Teleport` desde una página paralela no se atiende si no corre ninguna
   página de primer plano.** `op_teleport` prende `salto_hay`, y `eventos_tick`
   sólo lo mira después de correr una página de primer plano: con el primer
   plano quieto sale por `nada`. En el 49 el choque prende el 172 y el auto se
   queda en (104, 26) para siempre —400 ticks mirados—, sin saltar al 50. **Son
   126 páginas, todas las salidas de la carrera** —40 por vuelta más 6 del
   puente— y ningún mapa de `release` tiene hoy una: es un camino que nada
   ejecuta. General (es lo que hace RM2k con cualquier paralelo), del orden de
   diez bytes de banco 0 y nada de RAM.
2. **El volante no dobla.** `op_key` usa `tecla_valor`, que mira **flancos**
   (`pad eor pad_ant`) en las dos formas; easyrpg usa `Input::IsPressed` para la
   que no espera (`game_interpreter.cpp:3222`, `wait ? IsTriggered :
   IsPressed`), y el comentario de `KEY_INPUT_PROC` en `eventos.py` dice lo
   mismo. Sosteniendo arriba, la variable 33 queda en 0 y el auto cambia de
   carril una sola vez. General, unos diez bytes de banco 0. Arreglado eso, hay
   que ver que el cambio de carril sobreviva a que el volante le vuelva a
   poner la ruta hacia la derecha cada cuadro (el orden entre la ruta del héroe
   y los paralelos).
3. **La carrera corre a la mitad de la velocidad.** Con las 40 páginas de los
   autos, **cada tick cuesta dos cuadros**: 2,07 cuadros por tick en el 49 y
   2,02 en el 52, medido con `cuadros_perdidos` durante 300 ticks. El 51, con
   13 páginas de la misma forma, no pierde ninguno, y `release` en el 52 (con
   las páginas de los autos sin compilar) tampoco. Coincide con lo que estimaba
   `wishlist/chips-sa-1-y-s-dd1.md` (~9 líneas por página, ~370 líneas). Se
   juega, pero a 30 cuadros. Lo general es
   `wishlist/optimizar-los-eventos-paralelos-al-compilar.md`: las 40 páginas
   son el mismo patrón —leer la celda propia en dos variables y compararlas con
   otras dos— y un opcode fundido lo haría en código nativo. Un opcode, del
   orden de diez bytes de banco 0 para su entrada y cien de banco 1, más el
   reconocedor en el compilador. Sirve también para las luces del mapa 11.
4. **El cartel de los controles no se ve.** El `ShowPicture 'EscapeInst'` de
   la intro está aceptado sin hacer, y la ROM lleva un solo cartel, que es el de
   "One year previously". El jugador ve la pantalla negra y tiene que apretar
   una tecla sin que nada se lo diga. Es una imagen de 276x205 sobre negro con
   el texto "Use the UP and DOWN arrow keys to change lanes, and avoid the
   traffic! Fewer crashes means better rewards! Press any key to begin."
5. **Los sonidos del salto del puente** (orden 35 de ruta, seis rutas del 51)
   se tiran al compilar. Es `todo/los-sonidos-adentro-de-las-rutas.md`.
6. **El fin de la demo**: el 64 salta al 66, que no entra. Va un fork del 64
   con el mismo cartel y el `ReturntoTitleScreen` que hoy tiene el del 36, y el
   fork del 36 se borra.

Lo que anduvo, visto en el emulador: la intro con sus mensajes y la espera, el
171, el cambio de grupo al auto, el `PanScreen`, el empuje hacia la derecha,
los autos que se mueven solos y el choque (el gráfico que cambia y la
animación). No se llegó a ver el 50, el 52 por su entrada, el 51 por su
entrada, el 53 ni el 64: sin el punto 1 no se sale del 49.

**Las pruebas del 52.** El 52 es mapa de prueba (`test_caminar_golden.py`,
`en-52`, `grupo-11-en-52`, `pelea-en-52`, `ev41`). Con el 50 y el 54 en el
cartucho compilan sus 40 páginas de autos, y con el volante aceptado el héroe
ahí es empujado a la derecha cada cuadro: el comentario de `KEY_INPUT_PROC`
ya avisa que `heroe 52` deja de terminar. Hay que elegir otro mapa grande para
`heroe`, y mirar las demás goldens del 52 antes de dar por bueno el hito.

# Hitos

**1. La carrera entra y se puede correr, a 30 cuadros.** 49 a 54 y el 64 en
`release`; el fin de la demo pasa al fork del 64 y el del 36 se borra; el
`Teleport` desde un paralelo (1) y el volante con `IsPressed` (2); el
`KeyInputProc` sin espera aceptado, sin el interruptor de medición. Las
pruebas: el 52 fuera de `heroe`, las goldens del 52 revisadas, el cierre del
36 que ahora entra al 49 (`test_recorrido_lashe_*` cambian: "irse termina la
demo" pasa a ser "irse lleva a la carrera") y un recorrido de la carrera
entera, que el arnés puede manejar sosteniendo teclas. Banco 0: 6 bytes de los
mapas más los dos arreglos, del orden de veinte.

   **Hecho el 2026-09-27**, con las preguntas 1, 3, 5 y 6 contestadas con la
   recomendación: ver `testing/carrera-1-entra-y-se-corre.md`.

**2. La carrera a 60 cuadros.** El opcode fundido (3), o lo que diga la
medición de `optimizar-los-eventos-paralelos-al-compilar.md`. Se da por hecho
con `cuadros_perdidos` en cero —o casi— en el 49, el 52 y el 54 manejando.
Independiente del 3 y del 4.

**3. Lo que se ve y se oye.** El cartel de los controles (4) y los sonidos del
salto (5), según lo que conteste taro.

   **Hecho el 2026-09-27**, con la opción (a) de la pregunta 4: ver
   `testing/carrera-3-lo-que-se-ve-y-se-oye.md`.

**4. La regla de los mapas por id.** `release` pasa a ser "los mapas con id
menor a X, sin los de `--exclude-maps`, más los agregados" —hoy el 164— y los
de prueba como hasta ahora. Primero los dos errores latentes del conversor
(la ruta propia deduplicada y las tablas de actores sin `.bloque`), cada uno en
su commit y con la ROM byte por byte igual donde no cambia nada. Después el
cambio de regla, que **no debe mover la ROM**: con X = 65 y la exclusión de
arriba, la lista resultante tiene que ser la misma que la de este hito 1, y
eso se compara. Puede ir antes, en paralelo o después del 2.

   **Hecho el 2026-09-27**: los errores en `9d6c0d3`, la regla en
   `done/la-regla-de-mapas-por-id.md`. La exclusión no es un flag del
   conversor sino un valor de `cartuchos.py`; el porqué está ahí.

**5. (Condicional) X = 85.** Sólo si taro lo quiere antes de que entre el
mundo: los 18 mapas inalcanzables, con 66, 67 y 69 en la exclusión.

Lo que hay que repartir si el 1 y el 2 van en paralelo: el opcode del 2, en
`tools/protocol/events.toml`; y `cartuchos.py`, que lo tocan el 1 y el 4.

# Preguntas para taro

1. **¿X = 65 u 85?** 65 es todo Lashe City y deja el 83 y el 84 afuera: no se
   alcanzan hasta que entre el mundo (el 66). 85 los mete junto con otros 16
   igual de inalcanzables, por 8,5% del cartucho y 72 bytes de banco 0.
   **Recomendado: 65.**
2. **La exclusión de X = 65**: ¿el 58 solo (el tutorial de otro capítulo, que
   es el que cuesta: 46,7 KB), o también las tres carpetas y el respaldo (15,
   22, 55, 46: 12,9 KB)? **Recomendado: los cinco**, así lo que entra es lo que
   se puede pisar.
3. **¿La carrera a 30 cuadros vale como paso intermedio** (hito 1 entregado
   antes que el 2), o no se entrega hasta que corra a 60?
4. **El cartel de los controles**: (a) un fork del 49 que cambie el
   `ShowPicture` por un `ShowMessage` con el mismo texto —barato, y la
   pantalla ya está negra—; (b) un segundo cartel por ROM
   (`wishlist/sistema-de-imagenes.md`); (c) deuda. **Recomendado: (a).**
5. **Dónde termina la demo**: ¿al final de la escena del 64, en vez del salto
   al mundo, o antes, al salir del 53 con el premio? **Recomendado: el 64**, que
   cierra la escena con el compañero.
6. **El mapa grande de `heroe`**: el 52 deja de servir (la carrera corre ahí).
   ¿Se reemplaza por otro de los grandes que ya están (el 8, el 11 y el 20 ya
   son de la lista), o alcanza con sacarlo?
