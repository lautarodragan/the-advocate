---
name: "La flecha de seguir y la barra de la elección"
description: "Lo que le falta a la ventana de mensajes para verse como la de RM2k: la flecha que dice que hay más texto, y la elección con la barra resaltada del System en vez de '>'"
type: feature
assignee: taro
---

De taro, el 2026-10-04: "Dale", a seguir con las dos diferencias que
Quirquincho encontró comparando contra el original con Wine
(`workflow/tasks/testing/la-ventana-arriba-al-medio-y-sin-fondo.md`; las
capturas en `/shared/capturas/2026-10-04-ventana-de-mensajes/original/`).

## Hecho (Tijereta)

Worktree de las herramientas desde `69289619`; ABL en el clon
`/extras/scratch/tijereta/abl` desde `5b29ba9`, rama `flecha-y-barra`.

### Lo medido en el original (Wine, runtime de 2015)

* **La flecha** es el trozo 16x8 del System en (40,16), abajo al centro y
  sobre el borde de la ventana —`Window::Draw` de easyrpg—. Titila: unos 20
  cuadros prendida y 20 apagada, y arranca prendida al terminar la página
  (`SetPause` pone el contador en cero). Sale también sin fondo.
* **La barra** es el cursor del System —el trozo de (64,0)—, de 16 de alto
  y del ancho del texto menos 4, corrida 2 a la derecha
  (`UpdateCursorRect`); el texto de cada opción va 12 pixeles más adentro.
  Medido: barra en x 11..308 e y 89..102 de 320x240 —el System de ABL deja
  el primer pixel transparente—, "Yes" empieza en x 20. Sin fondo también.
* **La barra de ABL no titila**: sus dos dibujos del System, (64,0) y
  (96,0), son iguales pixel por pixel —un rojo oscuro, (83,0,0)—, y 40
  capturas seguidas del título y de la elección dan el mismo color. En un
  System con dos dibujos distintos RM2k los alterna cada 10 cuadros.

### La flecha

El conversor la dibuja sobre la ventana vacía y sobre nada, y la corta en
dos tiles más del banco de la ventana: en 256 de ancho el trozo cae justo
en las celdas 15 y 16 de la fila de abajo. La consola la prende y la apaga
escribiendo esas dos celdas del tilemap de la ventana, en el plano que se
ve —con marco o sin fondo—, desde el vblank y sólo cuando cambia
(`msg_arrow`, en `message_arrow.s`). El HDMA ya pone la ventana arriba, al
medio o abajo, así que la flecha la sigue sola. Sale cuando RM2k pondría
`pause`: página compuesta, sin elección ni dígitos, sin `\^`, con los `\|`
ya esperados.

### La barra

Compuesta en la ventana como el texto: `prime_line` ceba la línea de
`pick_sel` con `window_bar` —el fondo con el cursor— en vez del fondo
pelado, y la letra va encima, que es el orden de RM2k. Las opciones van
doce pixeles más adentro. El compilador dejó de poner el ">": las cajas de
las opciones son una sola, y la tabla de `OP_CHOICE` no cambió.

El cursor del System sobre un rectángulo, para otras pantallas:
`rm2k_render::system::cursor_over`.

### Lo que no cambió, y en RM2k es distinto

* **`InputNumber`** sigue con ">": en RM2k el cursor es un recuadro
  alrededor del dígito, y la barra precompuesta es de una línea entera.
  Haría falta otra pieza —un recuadro del ancho de un dígito sobre la
  línea de los dígitos—; no es caro, pero es otro dibujo.
* **El menú de pausa y las ranuras de guardar y cargar** siguen con ">":
  sus filas son de otro mecanismo (`tl_strip` y las filas por cursor de
  `slots.rs`). Ítems, equipo, tienda y la pelea ya tenían la barra.
* **La barra no alterna los dos dibujos del cursor**: ver
  `workflow/divergencias/la-barra-de-la-eleccion-no-alterna-sus-dos-dibujos.md`.
  En ABL son iguales.

### Lo que usa

* **CGRAM: cinco colores más en la paleta de la ventana**, trece en vez de
  ocho, que salen del fondo de todos los mapas. Once mapas de ABL fusionan
  entre uno y cinco colores. Es lo que más hay que mirar:
  `workflow/divergencias/la-ventana-se-lleva-trece-colores-de-cada-fondo.md`.
* VRAM: cuatro tiles más en el banco de la ventana —con el System de ABL
  quedan 256 justos—. Tilemap, sprites, OAM: nada.
* RAM: `MSG_ARROW_T`, `MSG_ARROW_WAY` (dos bytes) y `MSG_ARROW_UP`, en
  `$7E3620`-`$7E3623`, después de la animación de batalla.
* ROM: `window_bar` (7,5 KB) y `window_bar_bare` (1,9 KB) en datos;
  `msg_arrow` y `msg_bar_source` en el banco lejano; en el banco 0, unas
  comparaciones.
* Cuadros perdidos: sobre el mapa 6 con la cámara andando, componiendo y
  con el mensaje arriba, ninguno más que antes. Uno más en la llegada al
  mapa, con la pantalla apagada.

### Verificado

* La tanda de ABL con `screens`, `wally`, `mapdata`, `events`, `convert` y
  el runtime de este árbol: verde dos veces seguidas, con la prueba nueva,
  56 goldens movidas y 7 nuevas.
* El rojo de antes: la prueba nueva con las herramientas globales, 5 de 6.
* `cargo test` de los crates tocados y `just -f tools/justfile test`.
* Contra el original con Wine: la flecha titila 20 y 20 y sale también sin
  fondo; la barra cae donde la de RM2k, con el texto en el mismo x.

## Para taro

Jugar una elección —el Insta-Shave de Talan, o la de quedarse en Lashe— y
mirar un mensaje esperando la tecla. Mirar sobre todo los once mapas que
pierden colores (Lashe Area y los interiores de Paradise): si se nota, la
alternativa es la de la divergencia. Lado a lado, con el original y LEEME,
en `/shared/capturas/2026-10-04-flecha-y-barra/`.

Al mergear, reinstalar `cartridge` —trae el runtime—, `screens`, `wally`,
`mapdata`, `events` y `convert`. `rules` y `rm2k-render` cambiaron pero son
bibliotecas, adentro de ésos. Y en ABL, la rama `flecha-y-barra`: trae la
prueba, los parches y las goldens.
