---
name: "Mundo 7: el camino a Paradise"
description: "105 Mountain Path, 106 y 107 en release, huir con escape_mode 1, el fin de la demo en el túnel del 107; el 108 no entra en la VRAM y sus opciones, medidas, esperan a taro"
type: feature
assignee: taro
---

De taro, el 2026-10-01: "sumemos mapas primero". La demo termina hoy en el
"Continue onward" del túnel a Paradise (66 ev18). Del otro lado: 105
Mountain Path, 106 y 108 Distant Paradise, que es otro capítulo (padre 0 en
el árbol). El 108 es uno de los cinco mapas que no entran en la VRAM
(`docs/research/2026-10-01-los-mapas-por-el-msu-1.md`): 462 tiles de fondo y
696 de sprite, y no queda lugar para la ventana de mensaje.

# El 108 no entra, y arreglarlo es una decisión para taro

Medido el 2026-10-01 sobre `2de10ea4`, con una variante de `release` más el
105, el 106 y el 108, armada aparte (un `rm2k-snes.toml` copiado al
scratchpad; ni `release` ni el conversor se tocaron). Con el código de hoy el
conversor dice:

    Map 108 'Distant Paradise': 120x120 cells of 8x8 px
      462 unique tiles
      sprites: 24 characters, 42 slots, 731 tiles in VRAM, 8 palettes;
               22 with their twelve poses in the cartridge
      83 NPCs with a CharSet out of 114 events

(731 y no los 696 del estudio de Lechuza: no se siguió de dónde salen los 35
de diferencia; las cuentas de abajo son sobre los 731.)

**Qué lo come: las poses quietas, no los que caminan.** De las 42 ranuras de
16 tiles, 1 es el héroe, 3 son eventos que caminan (los `*Running`), 1 es la
del giro y **37 son poses quietas distintas**: hoy un quieto comparte ranura
con los que muestran **el mismo** (CharSet, índice, pose), y el pueblo tiene
15 personajes mirando para tres o cuatro lados. Por personaje:

    Chara1:2   1 4 7 10     Crown3:1   1 4 7 10     People3:2  1 4 7 10
    People1:3  4 7 10       People3:1  4 7 10       People3:3  4 7 10
    People4:2  1 4 10       Chara1:3   1 4          Chara4:1   1 7
    Crown1:2   1 7          emily:4    4 10         y cinco de una pose

**Por qué no entra en ningún reparto**: con 462 de fondo sirven los que dan
480 o 544 —"+fondo", "+ambos" y "+techo"—, que dejan a lo sumo 384 tiles de
sprite, o sea 24 ranuras menos el cronómetro (8 tiles). Hacen falta 42. Y
bajando el fondo a 384 o menos —que Adeleine no puede sin cambiar pixeles—
el techo de sprites es 512, 32 ranuras: tampoco. No es un reparto nuevo: el
hardware no tiene uno que alcance.

**Lo que sí alcanza es lo que se ve a la vez.** Contando, para cada lugar de
la cámara, cuántas ranuras distintas pide lo que cae en la pantalla de 16x14
celdas con un margen alrededor:

    margen (celdas)               0    1    2    4
    ranuras distintas a la vez   12   14   16   19

O sea que el problema del 108 es que la ROM sube **todo el pueblo** a la VRAM
al entrar, y en pantalla nunca hay más de la mitad.

## Las opciones, con números

**A. Ranuras compartidas por distancia** (recomendada). El conversor reparte
las poses quietas como un coloreo: dos eventos quietos comparten ranura si
muestran la misma pose **o** si nunca pueden estar los dos en pantalla —sus
celdas están más lejos que la pantalla más un margen—. La ROM sube la pose
que toca cuando el evento entra en pantalla, por la misma cola de `vram_queue`
que ya usan las poses en caliente. Para el 108, contando como candidatos sólo
los quietos con **un solo gráfico** en todas sus páginas (78 de 83; los otros
y los que mueve un `ChangeEventLocation` quedan como hoy):

    margen   ranuras compartidas (con más de una pose)   total   tiles
      0        12 (11)                                     20     320
      1        14 (14)                                     22     352
      2        16 (14)                                     24     384
      4        19 (17)                                     27     432

Con margen 1 —que es lo que la ROM ya descarta como "fuera de pantalla" en
`build_oam`— son **22 ranuras, 352 tiles más los 8 del cronómetro: entra en
"+ambos"** (384 de sprite, 480 de fondo) con 24 de margen.

Lo que cuesta: es extender `decisiones/las-poses-se-suben-en-caliente.md`
("los quietos siguen compartiendo ranura por (CharSet, índice, pose), porque
no cambian") a los quietos. En la ROM: una tabla por mapa de qué (personaje,
pose) quiere cada evento compartido, un byte por ranura compartida con lo que
tiene ahora (14 para el 108: cabe en los 16 de `$25A0`), el chequeo en
`place_npc` —que es el lazo caliente de `build_oam`—, olvidarlo en
`npc_poses_forget` al volver de la pelea, y no dibujar el cuadro en que la
cola está llena. En el conversor, el coloreo en `wally` y la tabla en
`rm2k-snes-mapdata`. Y `M_*` no tiene lugar: el registro del mapa está lleno
(128 de 128), así que la tabla va por otro lado —una tabla global por índice
de mapa, o detrás de `npc_poses`—. Banco 0 tiene 245 bytes libres; el código
nuevo va mejor en `FAR`.

**B. Una pose por personaje quieto.** Todos los quietos del mismo personaje
se dibujan mirando para el mismo lado —el más común— hasta que se les habla,
que giran como hoy. 42 → 21 ranuras, entra. Es sólo conversor, pero **cambia
lo que se ve**: un pueblo donde todos miran para abajo. Es de las de taro
mirando.

**C. Espejar izquierda y derecha** con el bit de la OAM, para los CharSets
cuyo lado izquierdo es el espejo exacto del derecho (siete de los nueve de
arriba lo son; People1:3 y People4:2 no). 42 → 36. **No alcanza solo**, pero
es casi gratis —el atributo ya viaja en la fila y en la página; `turn_apply`
tendría que limpiar el bit— y le daría margen a A.

**D. Una caché de ranuras de verdad**: cada evento, quieto o no, pide ranura
al entrar en pantalla y la suelta al salir. Es lo único que cubriría también
al 127 (ver abajo), y es la decisión grande.

## Los otros cuatro: A no los cubre

* **127 ParadiseFarmland**: 138 de fondo, 731 de sprite (medido con una
  variante de `release` más el 127). Ahí el problema son **los que caminan**:
  22 eventos con ruta —una escena de bandidos—, una ranura cada uno, más 18
  poses quietas. A no le sirve (no tiene candidatos: todos los quietos tienen
  más de un gráfico o caminan). En pantalla a la vez hay 30 ranuras distintas
  sin margen y 36 con 2: ni una caché (D) entraría holgada en las 32 de
  "+sprite".
* **148 y 250**: 614 y 621 tiles de fondo, por encima del techo de 544 con
  cualquier cantidad de sprites. Es el camino 2 del plan del mundo —tiles del
  fondo subidos en caliente—, no éste.
* **285**: la caja de 64 tiles de las animaciones de batalla.

# Lo que se hizo

Mientras taro decide lo del 108, el capítulo llega hasta su puerta.

## Qué mapas, siguiendo las puertas

    105 Mountain Path     padre 66   -> 106 (ev3, y ev7 al final de su escena)
    106 TalanGetsAmnesty  padre 108  -> 107 (ev2, ev3, y la automática ev7)
    107 TunnelToParadise  padre 108  -> 106 y 108 (la automática ev4; ev10 y ev11)
    108 Distant Paradise  padre 0    -> 109, 110, 112 a 120, 126, 127, 150...

El 106 y el 107 cuelgan del 108 en el árbol: son ya de Paradise, pero son el
camino hasta su puerta. Del 108 para adentro es otro capítulo entero —las
casas, el Consejo, la granja (127), la cantera (150), el área (158)—, que
sin el 108 no tiene sentido sumar.

**La regla**: `below = 108`. Los tres entran por id, y no hubo que excluir
ni agregar nada.

## Qué no compilaba

Con el compilador instrumentado (un `eprintln` en el `scan`, en un `target/`
del scratchpad, sin commitear), sobre el request de `release` con los tres:

* **105 ev5 p2 y p3, y ev7 p1**: `EnemyEncounter` con `escape_mode` 1, "huir
  termina el evento". Es `abort_on_escape` en `CommandEnemyEncounter` de
  easyrpg (`game_interpreter_map.cpp`), que al volver huyendo llama a
  `EndEventProcessing`. Se compila sin tocar la ROM: huir va a un `OP_DONE`
  justo después del opcode; con manejadores, a uno detrás de un `OP_GOTO`
  al final del bloque. Las del 105 son el guardia que persigue —pisarlo es
  pelear, y ganar lo vuelve a poner arriba— y la emboscada antes del túnel,
  que es la que salta al 106.
* El 106 y el 107 compilaban enteros. Del 107 no compilan el ev10 y el ev11,
  la vuelta al 108 desde el túnel, porque el 108 no está.

## El fin de la demo

Al final de la escena de Isabella en el túnel (107 ev4): el fork del 107
cambia el tinte a negro, el `Teleport` al 108 y la pregunta de guardar que
venía detrás por el cartel ("END OF THE DEMO / Paradise is not in the /
cartridge yet. Thanks for playing!") y la vuelta al título. El texto es el
mismo de antes: sigue siendo cierto. **El fork del 66 se borró**: era sólo
el fin de antes, y el 66 ev18 vuelve a llevar al 105.

## Pruebas

Mulita agrandó la tabla de páginas de prueba mientras esto corría, así que
hay un caso nuevo:

* `casos/huir-corta.json` y `rpgmaker/test_batalla.py`,
  `test_huir_con_escape_mode_1_termina_la_pagina`: pelea, huye (con
  `BA_ESCAPE` en 100) y el `ControlSwitches` de después no corre. **Se vio en
  rojo**: con las herramientas globales el conversor se negaba a armar ("a
  test page's EnemyEncounter does not compile"). Las dos del compilador
  miran los destinos con y sin manejadores.
* `abl/test_paradise.py`: el 105, el 106 y el 107 recién llegados, con
  golden; el 106 y el 107 con su escena ya vista (331 y 332).
* `abl/test_recorrido_paradise_golden.py`: del 105 al título, con Talan y
  Arden en el nivel 20: los vehículos, el guardia, la emboscada (gana la
  pelea con la tropa 184), Arden que se queda, la amnistía, Isabella y el
  cartel. Sus fotos no están bendecidas.
* `abl/test_recorrido_tangle_golden.py` termina ahora al llegar al 105.

`just pruebas`: todo verde salvo `test_musica_techos.py` (ver abajo).
`just -f tools/justfile test` en verde. `cargo test -p rm2k-snes-events` en
verde. `NO_CACHE=1 just cartuchos` da las mismas huellas que con caché.

## Goldens

**Nuevas**: `paradise-105-llegada`, `paradise-106-llegada` y
`paradise-107-llegada`, en su commit. **Ninguna existente se movió.** Las
tres y las fotos del recorrido están en `/shared/capturas/2026-10-01-paradise/`.
**El merge espera a taro.** El cielo del 105 sale negro: su panorama
(Evening1) no se dibuja, como en todos los mapas con panorama
(`wishlist/panorama-del-mapa-2.md`).

## Espacio

`just espacio release`, antes (`a0863e9e`) y después:

                   antes                 después
    bancos         58 de 128, 50 libres  59 de 128, 49 libres
    huecos         10.580 B              22.948 B
    banco 0        245 B                 239 B
    banco 1        3.828 B               3.828 B
    BSS, ZEROPAGE  128 B, 4 B            128 B, 4 B
    textos         94.417 B              96.945 B

# Lo que no está hecho

* **El 108**, y con él Paradise: esperan la decisión de arriba.
* **`test_musica_techos.py` falla**: el tema nuevo es `lf-st5`, la
  persecución del 105. No se corrió `just techos`.
* La música del 105 al 107 no se escuchó.
* Huir del guardia que persigue termina su página, así que vuelve a tocar al
  héroe enseguida: es lo que hace RM2k. La prueba del recorrido no huye.
* La rama de Saldra (switch 56) de la emboscada no la juega ninguna prueba:
  es la misma escena con el otro compañero.

# Lo que no cubre `just pruebas`

* Huir en una pelea con manejadores y `escape_mode` 1: el juego no la usa;
  la cobra sólo la prueba del compilador.
* La rama de AG7 en el túnel (switch 150): Isabella lo deja afuera.

# Al mergear

Instalar `events` (`just -f tools/justfile install events`). El `cartridge`
de mi `bin/` local era el de `main`: no se tocó. No hay Python nuevo en
`tools/`.

# Qué tiene que probar taro

* Desde el túnel del mundo, "Continue onward": Mountain Path, los vehículos,
  el guardia que persigue (pelear, y huir), la emboscada y la escena de
  Arden o Saldra, la amnistía, Isabella y el cartel.
* Elegir qué hacer con el 108: A, B, C o D de arriba.
