---
name: "La tienda como el original"
description: "Las ventanas del System y la barra roja de cursor, como ya tienen ítems y equipo, llevadas a la tienda"
type: feature
assignee: taro
---

Nació el 2026-09-28, cuando taro aprobó la pantalla de equipo, para dejar
escrito lo de la VRAM que está más abajo. Es lo que sigue después de ítems y
equipo. taro la pidió el 2026-09-28: "vamos con la tienda". Hoy la tienda sigue sobre negro y con el ">" (`EQ_CURSOR`
sigue existiendo por ella). La pantalla es `rom/src/tienda.s`, y la
referencia es `pantallas.pantalla_tienda`.

Lo hecho hasta ahora, que es de donde sale el mecanismo:
`testing/la-pantalla-de-items-como-el-original.md` (Jacarandá) y
`testing/la-pantalla-de-equipo-como-el-original.md` (Ñandú). Las dos arman
las ventanas en BG1 detrás del texto de BG2, comparten tiles y colores
(`titulo.marcos`), y cada una sube su tilemap. Falta capturar el original
de la tienda con Wine, como se hizo para las otras dos.

## Los tiles de las ventanas ya no entran donde están

Los de ítems y equipo, que son 24 de 8bpp, van en la misma base que la
fuente (BG1 y BG2 arrancan en `$2000`) y detrás de ella. Con la fuente de
336 tiles de 4bpp llegan **justo** a `$3800`, donde empieza el tilemap de
BG1: no queda ni un tile libre. Unas ventanas para la tienda no van a entrar
ahí salvo que compartan todos los tiles con las de las otras dos
pantallas. El conversor lo controla en `_controlar_marco_de_items`.

No es un problema de que vivan en VRAM todo el tiempo, porque no viven ahí:
se suben al abrir la pantalla, y al cerrar `volver_al_mapa` repone el mapa
con `load_map`. La regla es que el menú sólo escriba en el banco de BG1 que
`load_map` repone (`_controlar_ranuras`). Así, cerrar el menú no cuesta
nada más que eso. Si el menú escribiera afuera de ese banco, al cerrar
habría que reponer lo que pisó, y eso sí se sentiría como un lag.

La salida que se charló con taro, **sin medir**: darle a BG1 una base de
tiles propia (`BG12NBA` deja una por capa, de a 4096 palabras), por ejemplo
`$4000`, y llevar las ventanas ahí. Según los comentarios de `RANURA_VRAM` en
`snes_convert.py`, en todos los repartos el banco de BG1 cubre al menos
`$2000..$4C00`, y el menú usa hasta `$3C00` (el tilemap de las ranuras). Si
es así, en `$4000..$4C00` entran unos 96 tiles de 8bpp sin tocar la fuente
y sin nada que reponer al cerrar. Primero hay que medirlo contra los
repartos de verdad, que es lo que hace el conversor, y no contra el
comentario.

## Medido el 2026-09-28, con la elección de actor

La elección de actor (`testing/la-eleccion-de-actor-como-el-original.md`)
ya usa esa salida: BG1 con base en `$4000`, 60 tiles de 8bpp y su tilemap
en `$4800`. Medido contra los repartos (`_controlar_objetivo`): el banco de
BG1 más chico es el de `VENTANA_FONDO`, `$1000..$4C00`; todos los demás
llegan por lo menos a `$5000`. O sea que `$4000..$4C00` está siempre
adentro. Para la tienda:

- Con el tilemap de BG1 donde lo tienen ítems y equipo (`$3800`), toda la
  zona de `$4000..$4C00` queda para tiles: **96 de 8bpp**.
- Con el tilemap ahí mismo, como la elección, **64**.
- Las dos pantallas no se abren a la vez que la elección, así que pueden
  pisarse. Las ventanas de ítems y equipo (24 tiles) también podrían mudarse
  ahí, y eso devolvería los 24 a la fuente.

## Qué hace el original

Capturado el 2026-09-28 con el RPG_RT de 2015 y Wine, a 320x240, sobre una
copia del juego cuyo mapa 4 arranca con Kersh y Core, ítems, mil de oro y un
`OpenShop` de tipo 0 con armas, armaduras, un casco, medicinas y un material.
Las capturas están en `/shared/capturas/2026-09-28-tienda/original-*.png`, y
se contrastaron con `Scene_Shop` y `Window_Shop*` de easyrpg.

- **La principal**: la ayuda arriba (32 de alto) vacía, el medio (128) una
  ventana vacía, y abajo la del mensaje (80) con el saludo y debajo las tres
  órdenes, 16 pixeles más adentro. La barra cruza la ventana (x = 11 a 308).
- **Comprar**: la ayuda con la descripción de lo que marca el cursor; a la
  izquierda la lista (184 de ancho, siete filas) con el nombre y el precio, en
  gris lo que no alcanza; a la derecha, una encima de la otra, el grupo (48),
  "Owned Items" y "Equipped Items" en rojo con sus cuentas (48), y el oro con
  la moneda en rojo (32); abajo el mensaje, de un renglón.
- **El grupo** son los charsets de cada uno, de frente: caminando y en color
  si puede equiparlo, quietos y en gris (`Tone(128,128,128)`) si no, y al
  lado una flecha del System —azul si sube, roja si baja, un punto si queda
  igual, una "E" si ya lo tiene puesto—. Con una medicina, en color y sin
  flecha.
- **La cantidad**: la ventana de la lista se vuelve una con el ítem, "x" y la
  cantidad —con una barra chiquita sobre las cifras— y el total con la moneda
  en rojo debajo. El grupo, la cuenta y el oro siguen.
- **Los "listo"** ("Done", "Thanks."): la ventana de la lista vacía, lo demás
  igual.
- **Vender**: la lista a lo ancho, en dos columnas, sin la columna de la
  derecha; la cantidad de vender es como la de comprar, con el grupo.

## Qué difería en la ROM

Todo sobre negro, el ">" como cursor, el mensaje arriba donde RM2k pone la
ayuda —sin descripción—, el oro, la cuenta y la lista en una sola columna, y
los términos en blanco.

## Qué se hizo

- **Tres distribuciones** (`pantallas.TI_CAPAS`), que comparten la ayuda
  de arriba (48, dos renglones, como en ítems):
  - la principal: el medio vacío (80) y abajo el mensaje (96) con el saludo
    y las órdenes pegadas debajo, como RM2k;
  - la de comprar, que usan también las dos cantidades y los dos "listo": la
    lista (96, cinco filas) o la cantidad; debajo, lado a lado, "Owned
    Items" y "Equipped Items" en rojo con sus cuentas (152 de ancho) y el oro
    con la moneda en rojo (104), que es la columna de la derecha de RM2k
    bajada; y el mensaje de un renglón (32);
  - la de vender: la lista (144, ocho filas) y el mensaje.
- **La ayuda muestra la descripción** de lo que marca el cursor, y el
  mensaje del tendero bajó a su ventana, como en RM2k. Antes el mensaje iba
  arriba y la descripción no estaba.
- **Los "listo" dejan la ventana del medio vacía**, como RM2k: antes
  mostraban la lista.
- **La barra** en lugar del ">": sobre la orden —de x = 12 hasta donde las
  otras—, sobre la fila de la lista —la del equipo, de x = 4 a 244— y sobre
  las dos cifras de la cantidad, como la barrita de RM2k.
- **Un saludo de dos renglones baja las órdenes uno.** El resaludo de los
  juegos de mensajes 1 y 2 mide 31 y 32 letras ("Are you going to buy
  something?", "I dont have all day you know!!!!") y en un renglón entran
  30; la ventana de abajo tiene lugar para ese caso, y con un saludo de un
  renglón las órdenes suben, pegadas al mensaje como en RM2k. Los demás
  mensajes miden 26 a lo sumo, y el conversor comprueba que entren en uno.
- **Las ventanas en BG1 con su propia base, `$4000`**, y el tilemap en
  `$3800`, donde el de ítems y equipo. Son **39 tiles** de 8bpp de los 96
  que entran, y **4 colores**, en la CGRAM 64..67 —donde los de ítems—.
  `_controlar_tienda` comprueba contra los repartos que caigan en lo que
  `load_map` repone; `tienda-120` y `tienda-200`, que miran el mapa después
  de cerrar la tienda, no cambiaron.
- **Lo que se guarda es poco** (`pantallas.tienda_compacta`): las tres capas
  como tramos de filas, sin repetir un tramo que ya está guardado —16 filas
  de tilemap para las tres, 1024 bytes—, y cada barra sólo en el rectángulo
  que cambia, sin repetir los iguales: 628 bytes para las 18 posiciones.
- **Cada cuadro se repone todo**, como en el equipo (`ti_ventanas`): las
  filas de la capa del modo debajo de la ayuda, 1408 bytes, y encima la
  barra. Con los 1792 del texto son unos 3,3 KB por vblank; calculado, unas
  veintisiete de sus treinta y siete líneas. En bsnes, que no deja escribir
  la VRAM fuera del vblank, las veintidós pantallas de las pruebas salieron
  pixel por pixel iguales a la referencia.
- `items_ppu_prender` sigue de largo en `pantalla_ppu_prender`, que recibe
  `BG12NBA` en A: la tienda le pasa la base propia de BG1.
- El código nuevo va en el banco 1 (`tienda.s`); el banco 0 no cambió.
- `EQ_CURSOR` y `PANT_NOMBRE` se fueron en su propio commit: el ">" y la
  columna de los nombres de ítems en esta pantalla quedaban sólo por la
  tienda. Las ROMs salieron byte por byte iguales.

## Qué no entra

- **La lista y la columna de la derecha, lado a lado**: con letras de 8
  pixeles un nombre de veinte letras con su precio son 26 celdas y "Equipped
  Items" con su cuenta 17; con los cuatro de marco son 47, y la pantalla tiene
  32. La columna baja, entre la lista y el mensaje.
- **La lista de siete filas**: debajo de la ayuda (48), la cuenta y el oro
  (48) y el mensaje (32), quedan 96: cinco filas. La de vender, que no tiene
  la cuenta, tiene ocho. Las dos columnas de vender, por lo mismo que en
  ítems: una.
- **El grupo, con sus sprites y sus flechas**: no tiene dónde ir en esta
  distribución sin sacarle filas a la lista —la ventana de RM2k mide 136 por
  48—, y es un trabajo aparte de las ventanas: los charsets de cada uno del
  grupo como sprites, de frente, caminando en tres cuadros, una versión en
  gris de cada uno para el que no puede equiparlo, y las cuatro flechas del
  System —de 8x8, en cuatro cuadros— con la cuenta de `CmpEquip`. Queda como
  divergencia declarada; si taro lo quiere, es una tarea propia.
- **Las flechitas de la lista** que dicen que hay más arriba o abajo: la de
  ítems tampoco las tiene.
- **La ayuda de un renglón** y la fuente a 6 pixeles: como en ítems y
  equipo, ya declarado.
- **El mensaje del juego 0 arranca un espacio más adentro** en RM2k ("
  What do you want to buy?"): partir los renglones se come el espacio, como
  ya era.

## Pruebas

- `test_tienda_dibujo.py` compara cada modo contra `pantalla_tienda`, que
  ahora dibuja las ventanas y la barra (`Texto.ventanas`). Con dos pruebas
  nuevas, entre las tres la barra pasa por cada lugar con un parche distinto
  —la última fila de cada lista y la última orden, que cruzan la franja del
  fondo—:
  - el de armas (EV0021), como estaba: cada modo una vez;
  - nueva, el de armaduras (EV0023, juego 1): el resaludo de dos renglones con
    la barra en Leave, vender con diez ítems y la lista corrida, la cantidad
    de vender y "vendido";
  - nueva, el de repuestos (EV0025 con el switch 150): once ítems, la barra
    en la quinta fila y la lista corrida.
- **Goldens nuevas**, diez, de la ROM en esos mismos estados:
  `tienda-principal`, `tienda-comprar-2`, `tienda-cuantos-2`,
  `tienda-comprado`, `tienda-vender`, `tienda-armaduras-resaludo-salir`,
  `tienda-armaduras-vender-corrida`, `tienda-armaduras-cuantos-venta`,
  `tienda-armaduras-vendido` y `tienda-repuestos-corrida`. Hasta ahora la
  tienda no tenía golden de su pantalla, sólo del mapa alrededor, y ésas no
  cambiaron.
- Antes, ahora y el original, lado a lado, en
  `/shared/capturas/2026-09-28-tienda/`, con las goldens del último commit.
- Verificado con `just cartuchos` y `just pruebas` sobre esta rama, con
  `main` mergeado —no se había movido—: todo en verde. Ningún tema de música
  pasó a recortar, así que no hay commit de techos.
- **Lo que `just pruebas` no corre**: la tienda en bsnes. Se corrió a mano,
  con las tres pruebas de la tienda apuntadas a bsnes, y las veintidós
  pantallas salieron iguales a la referencia; es lo que dice que el DMA de
  cada cuadro entra en el vblank. Tampoco corre una tienda de sólo comprar o
  de sólo vender (`OpenShop` tipo 1 o 2), que entra derecho a la lista: su
  camino no cambió, pero la capa sale de la misma tabla.
- `just espacio`, antes (`main` en `24dc8b6e`) y después: en `release` los
  huecos de datos pasaron de 13.910 a 9.432 B, el banco 1 de 3.739 a 3.333
  y el banco 0 quedó en 224; en `test-special`, de 23.213 a 18.735, de 6.243
  a 5.837 y 1.117. Ningún cartucho usa un banco de datos más.

## Qué tiene que mirar taro

- Un tendero: la principal con el saludo abajo y las órdenes debajo, la
  barra cruzando la ventana; el de armaduras de Lashe City Interiors, que
  saluda de nuevo en dos renglones al volver con B.
- Comprar: la descripción arriba, la barra en la lista, "Owned Items",
  "Equipped Items" y la moneda en rojo; con más de cinco cosas, que la lista
  se corra con la barra.
- La cantidad: la barrita sobre las cifras, y "Done" con el medio vacío.
- Vender, con muchas cosas en el inventario, y "Thanks.".
- Salir, y el mapa como siempre (BG1 tiene otra base en la tienda y el mapa
  la repone).
