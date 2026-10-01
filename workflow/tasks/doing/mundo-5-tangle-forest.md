---
name: "Mundo 5: Tangle Forest"
description: "Los mapas 310 a 313 en release, hasta el túnel a Paradise: medido que entran, el EraseEvent después de un salto, el cronómetro en ramas y en condiciones de página, el cancelar fuera de las opciones, y el fin de la demo en el Continue onward del 66 ev18"
type: feature
assignee: Tacuarita
---

De taro, el 2026-10-01: "¿podemos agregar más mapas?". El plan es
`todo/el-mundo-y-lo-que-sigue.md`, hitos 1 a 4 hechos. La demo terminaba al
entrar a Tangle Forest (66 ev19), y Tangle **no es opcional**: el túnel a
Paradise está del otro lado del bosque, y se cruza por 310, 311, 313 y 312.

# Entra

Medido con `just espacio release`, como dice `AGENTS.md`. "Bancos" son los
de datos, de `$02` a `$7D`.

    release                         bancos     libres  hueco     banco 0  textos
    la base (37ea12fc)              120 de 124   4     19.744 B  320 B    143.114 B
    + 310 a 313, sin tocar código   124 de 124   0     23.873 B  278 B    144.758 B
    + todo lo de esta tarea         124 de 124   0      7.438 B  247 B    145.792 B

Banco 1 4.233 B y ZEROPAGE 4 B en las tres; BSS 129 B, y 128 con
`timer_watch`. O sea que **entra justo**: no queda ningún banco libre, y lo
que sigue de la ROM tiene que salir de ese hueco de 7,4 KB o del `.msu`
(ver el estudio de Lechuza). Lo que pesaba lo dijo el plan el 2026-09-27
—poses, tiles de fondo y música—; no hizo falta bajar la calidad de nada.

Lo que los 16 KB de diferencia entre la segunda y la tercera fila se comieron
son las páginas que pasaron a compilar —el claro del 311, la salida y el
fuego del 312, el 18 del 66 y la tienda del 348— y las doce poses del dueño
de la tienda, que ahora gira hacia el héroe (ver "Goldens").

# Qué faltaba, contado

Con el compilador instrumentado (un `eprintln` en el `scan`, en un `target/`
del scratchpad, no commiteado), sobre el request que arma `release` con los
cuatro mapas: **en Tangle no compilaban dos páginas**, no las cinco del plan.

* **311 ev4**, las latas de fuego: `EraseEvent`. Va **después** de un
  `Teleport` al 312, y en easyrpg el salto pone en 0 el evento de cada cuadro
  de la pila (`Game_Interpreter_Map::OnMapChange`) y `CommandEraseEvent` con 0
  no hace nada. Así que compila a nada cuando la página ya saltó
  (`MapEvents::jumped`); antes del salto sigue sin compilar. El único otro
  del juego es el del mapa 150.
* **312 ev10**, la salida del bosque en llamas: `ConditionalBranch` por el
  cronómetro. `OP_IF` con el tipo 2 (`COND_TIMER`), que es la pregunta del oro
  —`>=` o `<=` según la polaridad— con `timer_sec` en vez del oro:
  `op_if` comparte ahora la comparación. Pide `>= 0`, que vale siempre.

Y una que el plan contaba y no se veía como página que no compila:

* **312 ev81**, el fuego: tiene una página con **condición de cronómetro**
  (`timer <= 1`, el Game Over), y un evento así quedaba **entero** afuera de
  la tabla. Pero su página 2 es la que pelea con la nave y saca al mundo:
  sin esto, el bosque era un callejón. La condición viaja en el lugar de la
  de variable del registro de página, con la ranura `$FE` (`TIMER_SLOT`), y
  `conditions_ok` lee `timer_sec` y compara `<=`. Un evento con una página
  que pida las dos sigue quedando afuera (no hay ninguno). Y el cambio de
  segundo pide el refresco, como `Game_Party::UpdateTimers`, **sólo en un
  mapa donde alguna página preguntó** (`timer_watch`, un byte de BSS que la
  carga del mapa apaga y `conditions_ok` prende); `SetTimer` también.
* **348 ev1 p2**, la tienda del mundo: `ShowChoice` con `cancel_type` 4 y dos
  opciones. En RM2k cancelar no corre ninguna y la página sigue después del
  `ShowChoiceEnd`. `OP_CHOICE` lleva una entrada más, al final, que salta al
  fin de la elección, y el byte de cancelar en `$FF` (`CANCEL_PAST`) le dice a
  `op_choice` que esa entrada es sólo del cancelar: el cursor no llega. El
  largo la cuenta, porque es lo que recorre el código por encima de la
  tabla —la primera versión no la contaba y `instruction_size` se pasaba de
  largo—.

En el 66 no compilan tres: el 9, el 11 y el 18 original, cuyos destinos (67,
68, 105) no están. Las dos al 312 de antes ya compilan.

# El fin de la demo

Al "Yes - Continue onward" del **66 ev18**, el túnel a Paradise, que es la
meta del plan: el fork del 66 cambia el `Teleport` al 105 por el cartel ("END
OF THE DEMO / Paradise is not in the / cartridge yet. Thanks for
playing!") y la vuelta al título. El 19 volvió a ser el original. Del otro
lado del túnel está el 105, el capítulo siguiente: no se midió.

# Pruebas

Ningún caso nuevo: **la tabla de páginas de prueba de `release` está llena**.
El número de página es un byte (`+2` del registro, que la ROM no lee) y hay
256; un caso más rompe el ensamblado (`Range error (256 not in [0..255])`).
Así que las pruebas usan las páginas del juego, que es lo que importa que
compile:

* `rpgmaker/test_borrar_evento.py`: la automática del 311 entera, del 840 al
  cronómetro en el 312.
* `rpgmaker/test_cronometro_condiciones.py`: la salida del 312 (la rama) y
  la página del fuego, que no corre con 2 segundos y corre con 1.
* `rpgmaker/test_elegir.py`, `test_cancelar_a_una_opcion_que_no_esta_no_corre_ninguna`:
  el dueño de la tienda, B, y la página termina sin abrir nada.
* `rpgmaker/test_cores.py`, `test_el_fuego_del_cronometro`: la página del
  fuego en snes9x y en bsnes.
* `abl/test_tangle.py`: el 310 y el 311 recién llegados, con golden.
* `abl/test_recorrido_tangle_golden.py`: del 310 al título, por el tram, las
  latas, el bosque en llamas contra el cronómetro, la nave y el túnel. Con el
  grupo en el nivel 20: en el de arranque los golpes no les sacan nada a los
  Para Guard y la pelea no termina. Sus capturas no están bendecidas.
* `abl/test_recorrido_capitulo_golden.py` termina ahora al llegar al 310.
* Las tres del compilador en `compile.rs`, y la de `maps`.

**Las cuatro de la ROM se vieron en rojo** con las herramientas globales y
Tangle en `release`: el claro no salta, la salida no prende el 845, el fuego
no corre, la elección del dueño no se abre. Contra easyrpg se confirmó
leyendo el fuente (no está compilado acá): `CommandEraseEvent` y
`OnMapChange`, `CommandConditionalBranch` caso 2, `AreConditionsMet` con
`GetTimerSeconds`, `UpdateTimers` con `SetNeedRefresh`, y `InputChoice` con
`CommandOptionGeneric`.

Las dos de `python.rs` (eventos y mapas) usaban el cronómetro como "la
condición que la ROM no evalúa": ahora esa página pide cronómetro **y**
variable, que sigue sin evaluarse, y los hashes del Python no se tocaron.

`just pruebas`: todo verde salvo `test_musica_techos.py` (los dos casos, ver
abajo). `just -f tools/justfile test` en verde. `NO_CACHE=1 just cartuchos`
da las mismas huellas que con caché.

# Goldens

* **Nuevas**: `tangle-310-llegada` y `tangle-311-llegada`, en su commit.
* **Movidas**: las cinco de `test_heroe` del 348 y `ventana-348`, 16 pixeles
  del héroe —tres tonos: la piel, el pelo y la ropa—. Es la tienda: su página 2
  ahora compila, el dueño gira hacia el héroe, pide sus doce poses y una
  ranura más (`9 with their twelve poses` contra 8), y la paleta que comparte
  el héroe pierde esos tres colores. Antes y después en
  `/shared/capturas/2026-10-01-tangle/`. **El merge espera a taro.**

# Lo que no está hecho

* **`test_musica_techos.py` falla**: el tema nuevo es
  `T_AVGFighter_KyaraSelect` (el claro y el tram), y `golden_axe-turtlevillage2`
  recorta. No se corrió `just techos`.
* **La música de antes baja**: comparando las tasas del `conversor.log`
  contra el de la base, bajan 48 pares (tema, muestra) y suben 21. Casi
  todos son las copias de los golpes de batería —KICK264, SOLKK60A, FATSD60A,
  CHH__60A, OHH__60B, SYBS133, SAW0_60…— que caen de ~22 a ~10,6 kHz en
  Lunar_Pyramid, Tnt07, wb3shop, Story, cd4, escape_newyork y otros; y cuatro
  muestras base "limited by 311" (VIBE_76A, EORG173, SYBS233, ATMOS60A, de
  22 a 17-19 kHz). Es lo mismo que pasó en el hito 4: el paquete del 311 lleva
  el tema nuevo con Lunar_Pyramid y le quedan 1.265 B. **No se cambió nada ni
  se grabó**; las opciones son las de siempre (`apart_themes` para el tema del
  claro, que suena también en el tram; tocar cómo elige `copias`). Lo decide
  taro escuchando.
* **Las peleas del claro y de la nave** se juegan con el grupo en el nivel 20.
  No se midió si se ganan con el de una partida jugada.
* La duración de los `TintScreen` se sigue descartando: el fuego y la vuelta
  al mundo cambian de golpe.
* El 348 sigue en `[maps] test`, aunque ahora el mundo lleva a una tienda
  que anda.

# Lo que no cubre `just pruebas`

* El Game Over del fuego al llegar a cero (la prueba mira que la página
  corra, no el Game Over).
* La otra rama de las latas: con Saldra (56) o AG7 (150) en el grupo, los
  mensajes son otros.
* La rama falsa y el `<=` del cronómetro en `OP_IF`: el juego no los usa; la
  comparación es la del oro, que `test_oro.py` cobra en los dos sentidos.
* Los cofres del 310 y el save point.

# Al mergear

Instalar `events`, `maps` y `cartridge` (`just -f tools/justfile install
events maps cartridge`). Los `.py` sólo cambiaron de contenido.

# Qué tiene que probar taro

* Desde el puente: entrar al bosque, el norte, el claro, la pelea, el tram,
  las latas y **el bosque en llamas contra el cronómetro**: ¿alcanzan los dos
  minutos para llegar a la salida? Y dejarlo llegar a cero: el Game Over.
* La nave, la salida al mundo, y el túnel: "Not yet" y "Continue onward".
* La tienda del 348: comprar, descansar y cancelar.
* Escuchar los temas que bajan (ver arriba).
