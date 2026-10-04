---
name: "El menú de la pelea como el de RM2k"
description: "Todo el menú y el texto de la pelea en la franja de abajo, sobre negro, como RM2k: los comandos a la izquierda, el grupo a la derecha, la lista de enemigos, ítems y habilidades abajo y la descripción arriba; sin el menú Engage/Automatic/Escape, con Escape como quinta opción"
type: feature
assignee: taro
---

De taro, el 2026-10-04: "el menú de las peleas. Hoy es muy distinto al
original. En el original, todos los menús y texto aparece abajo de la
pantalla". Sus decisiones:

* Nada de texto sobre el fondo ni sobre los enemigos: los nombres de los
  enemigos van en una lista sobre negro, abajo. La franja de abajo puede
  ser de otro modo (HDMA) mientras arriba sigue el 3.
* Sin el menú inicial Engage / Automatic / Escape. Los comandos de cada
  personaje: Attack, Special, Defend, Use Item, y **Escape como quinta**
  (elegido por taro el 2026-10-04), sólo en las peleas de las que se puede
  huir: un agregado de RPG Maker 2000 PLUS.
* El estado del grupo, una línea por personaje: `Talan  Normal  HP 49 / 49
  SP 46`.
* Use Item y Special: la lista en esa franja y la descripción arriba.
  Attack: la lista de enemigos a la izquierda, sin movimiento.
* El deslizamiento horizontal del original es opcional: si se complica, una
  primera versión sin él.

## Cardón, 2026-10-04

Worktree de las herramientas desde `d06a5779`; ABL en el clon
`/extras/scratch/cardon/abl`, rama `menu-de-la-pelea`, desde `5b29ba9`.

### El original, mirado

Con Wine, en la prueba de pelea del runtime de 2015 (`RPG_RT_2015.exe
BattleTest ShowTitle Window <tropa>`, sin jugar hasta un encuentro), tropas
82 y 87. La franja de abajo son 80 de 240 líneas, sobre negro; arriba, la
escena sin nada encima. Lo que se ve, de izquierda a derecha:

* **elegir la orden**: el grupo a la izquierda (`Talan  Normal  HP 49/ 49
  SP 49`, una línea por actor, la del que elige resaltada) y las órdenes a
  la derecha, cuatro renglones;
* **Attack**: la lista de enemigos tapa el nombre y el estado del grupo;
  se ven los HP y SP;
* **Use Item / Special**: la lista en dos columnas de cuatro renglones
  (`Potion   : 99`, `Memorize   -  5`) ocupa toda la franja, y la
  descripción va en una ventana de 32 líneas arriba de todo, tapando la
  escena;
* **los mensajes** ("attacks the enemy" / "health lost." / "collapses!")
  y la **victoria** van en una ventana del ancho entero, de arriba hacia
  abajo, y no se ve nada más.

Las capturas, en `/shared/capturas/2026-10-04-menu-de-la-pelea/original/`.

### El plan

* La franja de abajo **sigue en modo 3**: el texto ya es BG2 de 4bpp sobre
  el negro que deja la escena de 128 líneas, y los 447 pares alcanzan. Sin
  deslizamiento no hace falta otra capa; un cambio de modo por HDMA pediría
  otro tilemap y otros tiles para nada.
* Los renglones de la franja, en las filas **impares** 17 a 25: cinco de 16
  líneas, con 10 de aire arriba y 8 abajo.
* La descripción, en una franja de 32 líneas arriba: las cuatro primeras
  filas de tiles del tilemap de la escena pasan al tile transparente
  mientras está abierta una lista, y vuelven al cerrarla.
* Escape, quinta, sólo si la pelea deja huir: `escape_mode` distinto de 0
  en `EnemyEncounter`, siempre en un encuentro al azar
  (`args.allow_escape` de easyrpg). Viaja en el destino de huida de
  `OP_BATTLE`, que con `escape_mode` 0 no se usa nunca.
* Huir es del grupo, como en RM2k: el que la elige lo intenta; si falla,
  se olvidan las órdenes del turno, sale el mensaje y los enemigos actúan
  (`ProcessSceneActionEscape`, `eFailure`).

### Hecho

Herramientas, rama `worktree-agent-a299fc4e75fe398cc`:

* `Compilador: una pelea de la que no se puede huir lo dice en OP_BATTLE`
  —`BATTLE_NO_ESCAPE`, $FFFE, en el destino de huida con `escape_mode` 0—.
* `Pelea: las ventanas en la franja de abajo, como RM2k, y Escape del
  grupo` —el runtime, la geometría de `rm2k-snes-battle` y el conversor—.
  Va en un solo commit lo que se pidió separar (las ventanas, las órdenes y
  Escape, el modelo en Rust): comparten `ba_compose`, `battle_run.s`,
  `far_ram.s` y `model.rs`, y por separado la ROM no armaba. No hubo
  cambio de modo.

ABL, rama `menu-de-la-pelea` del clon `/extras/scratch/cardon/abl`: las
pruebas en un commit y las goldens en otro.

Lo que quedó:

* La franja **sigue en modo 3**; el **deslizamiento no se hizo**.
* El cursor sigue siendo ">": la barra de Tijereta (`window_bar`, y
  `rm2k_render::system::cursor_over` del lado del conversor) se compone en
  los tiles de la ventana de mensajes, y el texto de la pelea es BG2 sin
  fondo encima de la escena de 8bpp, sin una capa libre debajo. Para la
  barra haría falta la franja en otro modo por HDMA —el modo 1 deja BG1 y
  BG2 de 4bpp y BG3—, que es el siguiente paso si se quiere.
* Lo que no es igual al original está en
  `workflow/divergencias/lo-que-el-menu-de-la-pelea-no-modela.md`, y Escape
  en `workflow/divergencias/escape-es-la-quinta-orden.md`.
* La victoria parte su término por letras (31) y no por pixeles: "The
  combat has resulted in victory!" va en dos renglones.
* Con la fuente de ABL y +1, el conversor avisa que se cortan tres nombres
  de actor (DummyHero, Gang Member, MobilizedCar: ninguno es del grupo),
  siete habilidades y cuatro ítems —"Pungent Elixir-LIFE", "Jumper
  Cable-LIFE", "HerbSproutSalad-HP", "Healing Draught-HP"—: dos columnas de
  doce celdas, que es lo que RM2k también deja.

RAM: `$7E3CB3`-`$7E3CB7` (`FAR_BATTLE + 691` a `+ 695`). VRAM: nada nuevo
—la franja de la descripción es el tilemap de la escena apuntado al tile
transparente—. Opcodes: ninguno.

### Verificado

* La tanda de ABL con `battle`, `events`, `mapdata`, `convert` y
  `cartridge` de este árbol: cambian **dieciocho goldens**, todas de la
  pelea, miradas lado a lado; repetida hasta que no apareció ninguna roja
  nueva (las dos `msu-*-msu` aparecieron en la segunda vuelta, porque su
  prueba cortaba en la primera golden): **1072 en verde**.
* Dos pruebas nuevas: `test_huir_es_del_grupo` y
  `test_sin_huida_no_hay_escape`.
* `cargo test` de `rm2k-snes-battle`, `-events`, `-mapdata` y `-convert`;
  `just -f tools/justfile test`: 27.
* Lo que la tanda no cubre: el desplazamiento de la lista de enemigos
  —ninguna tropa de prueba pasa de cinco— y el ítem que vuelve al
  inventario con la huida fallida.

## Para taro

Una pelea de la que se puede huir y una de las que no; las listas de ítems y
habilidades con el cursor recorriéndolas; Attack con varios enemigos;
Escape, y que si falla actúen sólo los enemigos. Las capturas, con el
original con Wine al lado, en `/shared/capturas/2026-10-04-menu-de-la-pelea/`.

La segunda vuelta, abajo, reemplaza lo que hay que reinstalar.

## Cardón, segunda vuelta, 2026-10-04

Lo que pidió el coordinador después de comparar con el original: el grupo a
la izquierda y las órdenes a la derecha; las ventanas del System con su
borde y la barra del cursor; la victoria partida por pixeles.

### Lo que se hizo

* **Las ventanas van en BG1, la capa de la escena, en modo 3**, en las filas
  del tilemap que la escena no usa. Se pidió modo 1 por HDMA en la franja;
  no se hizo porque en modo 1 BG1 necesita una paleta entre la 0 y la 7, y
  en la pelea están todas tomadas (texto y los 96 colores del fondo). En
  8bpp las ventanas usan la última paleta de los battlers: una tropa queda
  en siete battlers distintos (ABL usa tres a lo sumo; el conversor se
  niega con ocho). Sí va por HDMA (canal 5) el desplazamiento horizontal de
  BG1 por franja, para que el temblor no mueva las ventanas: mirado a mano
  en la pelea de los agentes.
* **VRAM**: el texto, de 447 pares a 255 (palabras 0 a $1FFF; la lista más
  ancha de ABL pide 170); las ventanas, en $2000-$37FF: ABL usa 34 tiles de
  192 y 4 colores. Ver `docs/port/vram.md`.
* La barra: `Skin::cursor` de `rm2k-snes-screens`, que es el `cursor_over`
  de Tijereta en rm2k-render; las ventanas se dibujan en el conversor
  (`battle.rs`) y la ROM las pone en el vblank cuando el texto ya está.
* La victoria se parte con la fuente del juego: "The combat has resulted in
  victory!" en un renglón.
* La descripción va en un renglón; la de los ítems, entera (`ba_item_desc`).
* Mientras corre una página sin mensaje, la ventana de mensajes vacía: antes
  se veían las órdenes con basura en la de habilidad.

RAM: `$7E3CB6`-`$7E3CC8` (`FAR_BATTLE + 694` a `+ 712`), además de los tres
de la primera vuelta (`+ 691` a `+ 693`). Opcodes: ninguno. No se tocaron
`text_layer.s` ni el menú de pausa.

### Verificado

La tanda de ABL con `battle`, `screens`, `mapdata`, `convert`, `events` y
`cartridge` de este árbol: las mismas dieciocho goldens, miradas lado a lado
con el original; **1072 en verde**, tres vueltas sin rojas nuevas. cargo
test de los crates tocados y `just -f tools/justfile test`: 27. Sin cubrir:
el temblor con las ventanas (mirado a mano), una pelea sin escena y el
desplazamiento de la lista de enemigos.

Capturas: `/shared/capturas/2026-10-04-menu-de-la-pelea-2/`.

Al mergear, reinstalar `battle`, `events`, `screens`, `mapdata` y `convert`.
