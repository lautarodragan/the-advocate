---
name: "Todos los fondos de release en la ROM"
description: "Cada fondo que pide una pelea del cartucho va en la ROM, a 128x64 con 16 colores y agrandado por la consola; el reemplazo queda para lo que no se puede saber al convertir"
type: feature
---

De taro, el 2026-09-27, después de probar sacar dos de los tres fondos de la
ROM (ahorraba 32 KB, del 75,8 % al 75,0 %, y le pareció poca diferencia): **lo
contrario, meter en la ROM todos los fondos que usan los mapas de `release`,
con la calidad tan baja como haga falta**, y que el reemplazo quede sólo para
lo que no entre. Con MSU-1 no cambia nada. Sigue a
`testing/todos-los-fondos-en-el-msu-1.md`.

Todo lo medido acá es del 2026-09-27, sobre `91b5a37d` (antes) y esta rama
(después), con scripts descartables.

# 1. Qué fondos puede pedir una pelea de release

Con el conversor de `release` corriendo en proceso: las tropas que nombra un
`EnemyEncounter` compilado, el fondo del mapa de cada mapa con encuentros al
azar (subiendo el árbol), y si el mapa no nombra ninguno, el de cada terreno
de sus bloques.

De los mapas del juego, **trece**:

    SJBackdropABL04   ev del 2 (el droide)
    ABLBackdropSJ02   ev del 32
    ABLBackdropSJ03   al azar en 20, 28, 59; ev del 9 (Back Alleys, Sector 27)
    ABLBackdropSJ08   al azar en 21 y 26; ev del 21 y del 26 (Rat Tracks)
    SJBackdropABL01   al azar en 32, 60, 61, 62 (el Warehouse)
    mroad4            al azar en 76; ev del 76 (Sorbe Mountain)
    el 66, por terreno de celda (celdas del mapa entre paréntesis):
      forest5 (2.946)  river5 (1.738)  mroad2 (970)  plains5 (823)
      desert1 (464)    plains6 (361)   Galaxy (198)

De los mapas de prueba que `release` también lleva, tres más: `underbridgeback`
(el 255, que es del camino principal), `Castle` (133) y `SurlBattleBack` (269).

Ningún `EnemyEncounter` de un mapa del juego pide "el del lugar"; sólo los
casos `pelea-113`, `pelea-222` y `tropa-talan-aura`. Con eso, en todos los
mapas sin encuentros el fondo sale del terreno bajo el héroe, y ahí aparecen
`LasheBat`, `Forest1`, `Sea`, `SeaBeach` y `Galaxy`: los pide sólo una página
de prueba que pelee en esos mapas, y no se sabe al convertir en cuál.

# 2. Espacio

Con el método de `AGENTS.md` (un `.res` linkeado al `.o` de la receta) y el
banco 1 relinkeado sin el `.align`:

    release                 cartucho  último banco  banco 0  banco 1  BSS  ZP
    antes (91b5a37d)          81,8 %   $71 (19 KB)     189    7.863   138   4
    después (esta rama)       82,2 %   $72 (1,4 KB)    189    7.761   138   4

Antes quedaban doce bancos enteros ($72 a $7D) y 19 KB en el $71. Después,
once enteros ($73 a $7D) y unos 41 KB en huecos del $70 al $72: los bytes que
crecieron son 17 KB, medio banco, y el otro medio es el acomodo secuencial de
`bancos.py`, que deja un bloque que no entra para el banco siguiente.

**El camino principal que falta** (Tasgarde, Eisen, 259 y 255) son unos diez
bancos según `todo/el-mundo-y-lo-que-sigue.md` (`m2` 112 contra `m4` 122,
medidos con los tres fondos de antes). Con esto le queda **uno** en vez de
dos, más los fondos de sus propios mapas, a 4 KB cada uno. El hito 3 de ese
plan (first-fit decreasing) daba ocho más.

# 3. Cuánto pesa cada variante

Pesos **medidos**: cada fondo convertido de verdad y comprimido con `lz2`.
"LZ2 8bpp" es el flujo que descomprimiría directo a la WRAM, con los planos
fijos incluidos. En bytes, colores incluidos (el índice de 2 B por tile, en
las deduplicadas):

    los 13 del juego              crudo   dedup  dedup+espejo    LZ2  LZ2 8bpp
    256x128 16c 4bpp (antes)    213.408 200.224    199.520   139.269  149.550
    256x128 8c 4bpp             213.200 181.360    180.432    95.281  101.383
    256x128 4c 2bpp             106.600  71.272     70.168    37.265   43.983
    128x64 16c 4bpp (elegido)    53.664  53.472     53.216    39.782   42.659
    128x64 4c 2bpp               26.728  21.224     21.096    11.521   13.588

    los 16 que pide el cartucho
    256x128 16c 4bpp (antes)    262.656 245.056    244.256   166.285  178.736
    256x128 8c 4bpp             262.400 217.408    216.224   111.867  119.082
    256x128 4c 2bpp             131.200  86.864     85.408    44.070   52.100
    128x64 16c 4bpp (elegido)    66.048  65.728     65.472    47.396   50.856
    128x64 4c 2bpp               32.896  26.160     25.952    13.945   16.464

Deduplicar no sirve: una foto no repite tiles, y el espejo casi no suma. Lo
que antes pesaban los tres de la ROM eran 49.248 B.

Lo que cuesta cada una, **contra los 16**:

    variante                  +ROM      deja al camino   código           cuadros de carga
    256 16c crudo            +208 KB   no entra         0                 como antes
    256 16c LZ2              +114 KB   no entra         ~150 B banco 1    ~+15 (modelo)
    256 8c LZ2                +61 KB   0 bancos         ~150 B banco 1    ~+15 (modelo)
    256 4c 2bpp crudo         +80 KB   0 bancos         ~10 B             como antes
    256 4c 2bpp LZ2            -5 KB   dos              ~150 B banco 1    ~+15 (modelo)
    128x64 16c crudo          +17 KB   uno              +102 B banco 1,   +4 (medido)
                                                        +512 B de tabla
    128x64 16c LZ2             -2 KB   dos              ~250 B banco 1    ~+5 (estimado)

"Deja al camino" es lo que queda después de los diez bancos del camino
principal, antes del hito 3. El código de las que no se implementaron es
estimado. **Ninguna toca el banco 0.**

Los cuadros de carga de la elegida son `ESC_CUADROS`, medidos sin MSU-1 en
snes9x y bsnes: la pelea del mundo pasa de 6-7 a 10-11, la de Sector 27 (tres
battlers) de 12 a 16; con MSU-1, 5 y 11-12, iguales que antes. Los de las
LZ2 no están medidos: salen de `LZ2_CICLOS_POR_COMANDO` y
`LZ2_CICLOS_POR_BYTE` de snes_convert.py, que es una cota alta, y 32 KB por
búfer más la copia del segundo. Las 2bpp crudas usarían el mismo camino de
DMA de antes, sin CPU.

**Cómo se ve cada una**: `/shared/capturas/2026-09-27-fondos-en-la-rom/variantes/`,
un PNG por fondo con la del `.msu` como referencia y cada variante al lado,
con su peso. A 128x64 con 16 colores se ve pixelado pero con todos los
tonos; con cuatro colores se pierden el cielo, el monitor del droide y los
carteles.

# 4. La recomendación, y lo que se hizo

**128x64 con 16 colores, sin comprimir, agrandado por la consola.** Es la
única que mete todos los fondos sin costarle más de medio banco al camino
principal y sin tirar los colores. LZ2 encima ahorraría otros 19 KB a cambio
de un cuadro más y un camino más; no hace falta hoy, y queda anotado.

* **El conversor** (`escena_de_la_rom`) mete en la ROM **todo lo que se
  pide**: tropas, mapas con encuentros y los terrenos de los mapas con
  encuentros que no nombran fondo. `escena.FONDOS` ya no existe. El
  reemplazo (`ABLBackdropSJ08`) entra sólo si alguna pelea puede caer en un
  fondo que no está: una tropa del lugar en un mapa sin encuentros.
* **El respaldo** (`escena.fondo_liviano`) es de 128x64, 16 colores fundidos
  por `merge_least_visible`; `respaldo_bytes` lo emite en el orden que
  `esc_doblar` lee sin cuentas, con medio byte de dos planos por byte.
* **La ROM**: `esc_llenar` deja en los dos búferes sólo los planos fijos (un
  DMA de 32 B por tile), y `esc_doblar` —nueva, en el banco 1, entrada por el
  espejo rápido— escribe la mitad de abajo de cada tile con la tabla
  `respaldo_doble`, en los dos búferes a la vez.

# Pruebas

* `test_msu_cada_camino_dibuja_su_fondo` y
  `test_msu_una_pelea_del_mundo_lee_su_terreno` (antes `…_o_el_reemplazo`):
  el fondo limpio de la WRAM contra el liviano **armado de sus índices
  duplicados**, sin pasar por `respaldo_bytes`: compara lo que hace la ROM
  contra la imagen, no contra el mismo orden de bytes. El del mundo ahora es
  plains6, no el reemplazo.
* `test_escena_una_pelea_del_lugar_usa_el_fondo_del_mapa`: el 60 ya tiene su
  fondo en la ROM.
* `test_escena_una_pelea_cuyo_fondo_no_esta_usa_el_reemplazo` (nueva, con el
  caso nuevo `pelea-113-en-7`): la tropa 113 del lugar en el 7, sin
  encuentros y de un solo terreno (`LasheBat`, que la ROM no lleva): el
  reemplazo, y de paso la rama de `M_TERRENO_PLANO` de `esc_terreno`, que
  hasta hoy no corría ninguna prueba.
* **Goldens que cambiaron, a propósito** (el fondo sin MSU-1 pasa a 128x64;
  en `msu-mundo-rom`, además, de la cueva de reemplazo a la pradera):
  `batalla`, `batalla-blanco`, `batalla-droide`, `batalla-hab`,
  `batalla-hab-blanco`, `batalla-hab-dos`, `batalla-item`,
  `batalla-item-blanco`, `batalla-textos-lejos`, `encuentro`,
  `msu-datos-rom`, `msu-mundo-rom`. Antes y después en
  `/shared/capturas/2026-09-27-fondos-en-la-rom/goldens/`.

# Qué tiene que mirar taro

* **Sin MSU-1 (Mednafen)**: las peleas de siempre con su fondo pixelado al
  doble, y **las del mundo con el terreno que pisa** (pradera en la llegada,
  bosque, montaña, desierto, río), no la cueva. Sorbe Mountain (76) con su
  camino de montaña. La entrada a la pelea tarda unos cuatro cuadros más.
* **Con MSU-1**: igual que antes, el de calidad.
