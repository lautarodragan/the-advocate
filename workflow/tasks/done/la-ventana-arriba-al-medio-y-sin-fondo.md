---
name: "La ventana de mensajes arriba, al medio y sin fondo"
description: "MessageOptions de RM2k: la posición de la ventana (arriba, medio, abajo), sin fondo, correrse si tapa al héroe y los eventos que siguen durante el mensaje; hoy el compilador lo ignora y todo sale abajo con fondo"
type: feature
assignee: taro
---

De taro, el 2026-10-04: "podés hacer que el texto se pueda mostrar en el
medio o arriba de la pantalla, como en el rpg maker 2000 original? … puede
que también haya una opción para mostrarlo sin fondo".

Es `MessageOptions` (10120), que `compile.rs` tiene en `IGNORABLE` desde
`c64e4d96`: "where and how the message window is drawn, which without
messages is drawn nowhere". ABL lo usa 1110 veces en 202 mapas (contado el
2026-10-04 sobre el volcado); los parámetros más comunes, en el orden
[sin fondo, posición, correrse si tapa al héroe, eventos durante el
mensaje], con la posición 0 arriba, 1 medio, 2 abajo:

    (0,2,0,0) 284   (0,0,0,0) 223   (1,1,0,0) 175   (1,0,0,0) 134
    (0,1,0,0)  89   (1,2,0,0)  74   (0,2,1,0)  72   (0,0,1,0)  46

## Hecho (Quirquincho)

Worktree de las herramientas desde `cc502f93`; ABL en el clon
`/extras/scratch/quirquincho/abl` desde `e65a7b5`, rama
`ventana-de-mensajes`.

### Las cuatro opciones

* **La posición**: arriba en la línea 0, al medio en la 72 —centrada en las
  224— y abajo en la 144, como siempre. La elección y los dígitos van en la
  misma ventana, así que la siguen solos.
* **Sin fondo**: el texto con su sombra sobre el mapa. Con dos límites,
  escritos en `workflow/divergencias/la-ventana-sin-fondo-no-tapa-a-los-personajes.md`:
  los personajes pasan por encima del texto, y la capa de encima del mapa no
  se ve en la franja mientras dura el mensaje. Los dos salen de que la
  ventana es BG2, la misma capa que la de encima, y el modo 3 no tiene otra.
* **Correrse si tapa al héroe**: `GetRealPosition`, al abrir cada ventana,
  con los umbrales de RM2k medidos desde la ventana y no desde el borde de
  la pantalla, que acá mide 16 líneas menos (`DODGE_*` en
  `message_place.s`). Prendido por omisión, como en liblcf: por eso varias
  goldens se corren arriba sin que el juego lo pida. La prueba cubre abajo
  que se corre arriba; arriba y al medio que se corren, no.
* **Los eventos se mueven durante el mensaje**: las rutas propias de las
  páginas siguen leyendo órdenes con una página corriendo. Era una
  condición más en `event_routes.s`. **No lo cubre ninguna prueba**: ABL lo
  usa 3 veces.

Y una que no estaba pedida: con la ventana arriba, el cronómetro baja al pie
de la pantalla, como `Sprite_Timer` —RM2k lo dibuja encima de la ventana y
acá la máscara de los objetos lo escondía—.

### Cómo se mueve

Ni scroll de la capa ni reescribir el tilemap: **el HDMA**. Ya cambiaba
BG2SC y el scroll de BG2 en la línea 144; ahora las tablas tienen tres
tramos, que alcanzan para las tres posiciones, y las escribe
`msg_hdma_build` en el vblank en que la ventana aparece. Sin fondo tampoco
escribe VRAM: el tilemap de la ventana es de 32x32 y el marco usaba diez
filas, así que debajo va el mismo plano sin marco y el scroll elige.

### Lo que usa

* Opcode `0x41`, `OP_MESSAGE_OPTIONS (options: byte)`.
* RAM: `FAR_MSG_OPTIONS` en `$7E25FB`, en la partida; `MSG_PLACE`,
  `MSG_SC`, `MSG_ENTRY` y `MSG_VOFS` en `$7E25F6`-`$7E25F9`, fuera de ella.
  El hueco `$2580`-`$25EF` está lleno: la primera versión puso la máscara
  en `$25C4` y pisaba el estado del MSU-1 y de la música.
* VRAM: nada nuevo. El segundo plano va en las filas 10 a 19 del tilemap de
  la ventana, que estaban sin usar en los seis repartos y en las imágenes
  grandes.
* ROM: las máscaras de los objetos pasaron a cuatro tablas en `$C0`.

### Verificado

* La tanda de ABL con `cartridge`, `events`, `mapdata` y `convert` de este
  árbol: verde, con la prueba nueva y 22 goldens movidas. Se repitió hasta
  que no apareció ninguna roja nueva: cinco vueltas.
* El rojo de antes: la prueba nueva con las herramientas globales da 9 de
  10 en rojo —pasa `ventana-abajo`, que es lo de siempre—.
* `cargo test` de `events` y `mapdata`, y `just -f tools/justfile test`.
* Contra el original con Wine: la misma página de los casos puesta en una
  copia del juego. Las posiciones y el texto sin fondo caen igual.

## Para taro

Jugar una cinemática con texto sin fondo y una con la ventana arriba —la
corrida al trabajo, con el cronómetro—. Las goldens lado a lado, el
original al lado y un LEEME, en `/shared/capturas/2026-10-04-ventana-de-mensajes/`.

Al mergear, reinstalar `cartridge` —trae el runtime—, `events`, `mapdata` y
`convert`. `bytecode` cambió pero es biblioteca, adentro de ésos.
