---
name: "La elección de actor como el original"
description: "Al usar un ítem, la elección de actor con las ventanas, la barra roja, el nombre del ítem y Owned Items, como Scene_ActorTarget"
type: feature
assignee: taro
---

De taro, el 2026-09-28: "Ahora hagamos que la pantalla de selección de
personaje, dentro del use item, funcione también como RPG Maker. El ejemplo
más simple es: elegir Cold Sandwich. Nuestra pantalla actualmente mantiene
el indicador `>` en lugar del fondo rojo, y no muestra ni el nombre del item
ni el Owned Items a la izquierda."

## Qué hace el original

La captura con el RPG_RT y Wine, a 320x240:
`/shared/capturas/2026-09-28-items/original-eleccion-de-actor.png`, y
`Scene_ActorTarget` de easyrpg.

- **Tres ventanas**: a la izquierda, de 136 de ancho, la ayuda con el nombre
  del ítem (32 de alto) y debajo `Window_TargetStatus` con "Owned Items" en
  rojo —el color 1— y la cantidad a la derecha; a la derecha, a todo lo alto,
  el grupo.
- **La barra roja** del System sobre la fila marcada, **sobre el texto** del
  actor —las tres líneas—, no sobre el sprite.
- A usa el ítem y la pantalla se queda, con las dos ventanas al día; con la
  cantidad en cero suena el error y sigue ahí.
- Un ítem con `entire_party` marca a todo el grupo a la vez (índice -100).

## Qué difería en la ROM

La pantalla era el panel del grupo del menú sobre negro, con un ">" al
costado de la fila, y la columna de la izquierda vacía: el banco del menú no
tenía con qué escribir el nombre del ítem.

## Qué se hizo

- **Las ventanas en BG1, con su propia base de tiles** (`OBJETIVO_VRAM`,
  `$4000`) y su tilemap en `$4800`. En la base de BG2 no queda lugar: el
  banco del menú llega casi hasta su tilemap (`$3C00`). Medido contra los
  repartos de verdad (`_controlar_objetivo`): el banco de BG1 que `load_map`
  repone es, en el más chico —`VENTANA_FONDO`—, `$1000..$4C00`, y en los
  demás llega por lo menos a `$5000`. Así que `$4000..$4C00` está siempre
  adentro y fuera de lo que usa el menú: cerrar el menú no cuesta nada más.
  Ahí entran 64 tiles de 8bpp y el tilemap; las ventanas usan **60**.
- **Los colores de BG1 en 128..143**, los de la paleta 0 de los sprites: en
  esta pantalla no hay sprites, y `menu_exp_cerrar` los repone al cerrar el
  menú. En 0..127 no hay lugar: son las ocho paletas del banco del menú. Son
  **10** de 16.
- **La columna de la izquierda llega hasta x = 104** y no hasta 96, donde
  empieza la fila del grupo: las caras del banco miden 48 pero lo que se ve
  de ellas arranca en x = 108 (medido en las once). Así entran **once**
  letras de 8 pixeles por renglón, que es lo que pide "Sandwich-HP".
- **El nombre del ítem** en dos renglones de once, partido por palabras
  (`nombre_en_renglones`), con los glifos del banco del menú: el banco lleva
  ahora también las letras de las medicinas. Eran 391 tiles y son **411**; el
  techo es 448 (`$3C00`).
- **"Owned Items" horneado en BG1**, en rojo y a los seis pixeles de la
  fuente: a ocho, sus once letras llenaban la ventana y no quedaba lugar para
  la cantidad, y en BG2 no hay paleta libre para el rojo. La cantidad va con
  los glifos, en dos cifras, y se repinta después de usar el ítem.
- **La barra** sobre las tres líneas del actor, de x = 148 al borde, con el
  sprite afuera, como en RM2k. Moverla es copiar el rectángulo de BG1 donde
  cambia algo —6 filas por 14 columnas de celdas—, del juego de barras o del
  tilemap: un DMA de 28 bytes por fila de celdas.
- **Un solo tilemap y lo justo de barra y de nombres** (`d9645920`): el de
  elegir a quién equipar es el mismo con las 10 x 13 celdas de la izquierda
  borradas al subirlo, la barra se guarda sólo en su rectángulo, y los
  nombres sólo para las medicinas, con una tabla de un byte por ítem que dice
  cuál es. `objetivo_compacto` comprueba al convertir que las dos primeras
  cosas valgan.
- **El banco del menú lleva el bit de prioridad**, como los glifos de ítems:
  en modo 3, BG1 de prioridad 0 queda arriba de BG2 de prioridad 0 y la barra
  habría tapado la fila. En las otras pantallas del banco BG1 está apagado y
  no cambia un pixel: ninguna golden del menú ni de las ranuras cambió.
- **Para elegir a quién equipar**, la misma pantalla sin las dos ventanas de
  la izquierda: no hay ítem.
- El código nuevo va en el banco 1 (`eleccion_de_actor.s`); el banco 0
  **ganó** bytes, porque el ">" se escribía desde ahí.

## Qué no entra

- **La columna de la izquierda de 136**: en 256 de ancho, con la fila del
  grupo como está —la cara desde x = 96 y el texto desde x = 152—, entran 104.
  El nombre va en dos renglones y no en uno.
- **Un nombre de más de once letras sin espacios** se corta donde llega:
  "HerbSproutSalad-HP" sale "HerbSproutS" / "alad-HP". De las veintiséis
  medicinas del juego es la única.
- **La ayuda de un renglón**: son dos, 48 de alto en vez de 32.
- **SP y el estado en su lugar**: la fila es la del menú, con el nivel, el
  estado y los HP en tres líneas; RM2k pone los SP a la derecha. Ya estaba
  declarado en el menú.
- **`entire_party`**: la ROM no lo lee, y marca una fila sola. En el juego lo
  tiene una medicina, el Pocket Shelter (8).
- **A quién equipar, desde el menú principal**: en RM2k se elige en el menú
  mismo, con las órdenes a la izquierda y el cursor sobre el grupo. Acá es
  esta pantalla, con la mitad izquierda en negro (`equipo-a-quien`), como ya
  era antes con el ">". Queda para una tarea aparte.

## Pruebas

- Nueva `eleccion-sandwich`: el Cold Sandwich sobre la segunda fila, Arden
  en 10 HP, que es el caso de taro. Nueva `equipo-a-quien`: la elección para
  equipar, sin las ventanas del ítem.
- `render_objetivo` dibuja las ventanas, la barra, el nombre y la cantidad,
  así que `test_menu_curar_dibujo.py` y `test_menu_items_dibujo.py` los
  comparan pixel por pixel, también después de usar el sándwich (la cantidad
  baja de 2 a 1).
- No cambió ninguna golden del menú ni de las ranuras, con el bit de
  prioridad puesto en todo su banco.
- Antes, ahora y el original, lado a lado, en
  `/shared/capturas/2026-09-28-eleccion-de-actor/`.
- Verificado con `just cartuchos` y `just pruebas` sobre esta rama con
  `main` mergeado (la repetición de las flechas de Tala): todo en verde. La
  elección calcula los flancos con `pad` contra `pad_ant`, así que repite
  sin tocar nada. Antes del merge `dcbest` recortaba en
  `test_musica_techos.py`; con el merge la ROM se movió otra vez y dejó de
  recortar, así que no hizo falta `just techos` y **no hay commit de techos**,
  aunque el mensaje de `714dcef2` lo anuncia.
- `just espacio`, antes (`main` en `1475d9da`) y después de este cambio sin
  mergear: en `release` el banco 0 pasó de 196 a 254 B libres, el banco 1 de
  4.380 a 3.841, y los huecos de datos de 21.584 a 7.456 B (unos 14 KB: los
  tiles, los dos tilemaps, las barras y la tabla de nombres); en
  `test-special`, de 1.089 a 1.147, de 6.884 a 6.345, y de 30.545 a 18.777.
  Con `main` mergeado, `release` queda con 224 B en el banco 0 y 3.793 en el
  banco 1. Ningún cartucho usa un banco de datos más.
- Lo que sumaba, medido bloque por bloque contra `main`: 14.704 B, de los
  que 7.168 eran dos tilemaps y dos juegos de barras. Después de
  `d9645920`, en `release` los huecos pasan de 6.880 a 13.910 B y el banco 1
  de 3.793 a 3.739; en `test-special`, de 18.201 a 23.213 y de 6.297 a
  6.243. Las goldens salieron idénticas.

## Qué tiene que mirar taro

- Ítems, Cold Sandwich: el nombre en dos renglones, "Owned Items" en rojo y
  la cantidad; la barra roja sobre el texto del actor, y moverla.
- Usarlo sobre alguien herido: los HP y la cantidad cambian ahí mismo.
- B: la lista de ítems como estaba; y cerrar el menú: el mapa con sus colores
  y sus sprites de siempre (BG1 y los colores 128..143 los repone el cierre).
- Equipment: la elección de a quién, con la barra y sin la columna de la
  izquierda.
