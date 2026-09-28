---
name: "La pantalla de equipo como el original"
description: "Las ventanas del System y la barra roja de cursor de la pantalla de ítems, llevadas a la de equipar"
type: feature
assignee: taro
---

De taro, el 2026-09-28: "Ahora quiero implementar las mejoras de UI que
hicimos en el menú de items para el menú de equipamiento".

Lo de ítems está en `testing/la-pantalla-de-items-como-el-original.md`
(Jacarandá, `f3b0cc90`): las ventanas del System en BG1 detrás del texto de
BG2, y la barra roja como cursor en lugar del ">". Su sección "Equipar y
habilidades" ya decía qué servía: el mecanismo, pero con su propio juego de
ventanas y su propio tilemap, y la barra hecha distinto, porque esta pantalla
compone el texto entero en `texto_buf` cada cuadro.

## Qué hace el original

Las capturas con el RPG_RT y Wine, a 320x240, en
`/shared/capturas/2026-09-28-el-menu/original-equipo*.png`.

- **Cuatro ventanas**: la ayuda arriba a lo ancho (32 de alto); a la
  izquierda el actor —el nombre y debajo los cuatro parámetros en una
  columna, con el valor que quedaría—; a la derecha las cinco ranuras; y
  abajo a lo ancho la lista de lo que se puede poner, en dos columnas.
- **Rojo (color 1)**: los términos de los parámetros, los de las ranuras, y
  la flecha entre el valor de ahora y el que quedaría (medido en la captura:
  la flecha es roja, no blanca).
- **La barra roja** ocupa la fila entera de la ranura —término y lo puesto,
  de borde a borde de la ventana—, y mientras se elige queda sobre la ranura
  y otra marca el candidato de la lista.
- El término y lo puesto van pegados: "Right HandModified Blaster-R".

## Qué difería en la ROM

Todo sobre negro, una columna, el ">" como cursor, los parámetros en dos
columnas de dos —"Attack 280> 95 Defense 147>147" llegaba al borde de la
pantalla— y los términos en blanco. Los colores de "sube" y de "baja" ya
estaban (Tero, `el-menu-como-rm2k.md`).

## Qué se hizo

- **Tres ventanas en BG1**, una debajo de la otra (`pantallas.EQ_VENTANAS`):
  la ayuda, igual que la de ítems (48, dos renglones); la del actor, de 80,
  con los cuatro parámetros en una columna como RM2k y el nombre a la
  derecha; y la de abajo, de 96, con las cinco ranuras o —eligiendo— la
  lista. El texto sigue en BG2 sin saber nada de ellas.
- **La barra**: sobre la ranura, a lo ancho de la fila como en el original,
  y sobre el candidato, la misma que la de ítems. Cada cuadro, detrás de los
  1792 bytes del texto, se suben las diez filas de celdas de la ventana de
  abajo sin cursor y encima las dos del cursor (`eq_barra`): 768 bytes, sin
  acordarse de dónde estaba. Las puntas de las dos barras caen en el mismo
  lugar de su tile que la de ítems, a propósito: son los mismos tiles.
- **Los términos y la flecha en rojo**: una cuarta variante de la fuente,
  `ITEM_ROJO`, la paleta 3. **Entera**: medido, la fuente en rojo son **diez
  tiles** más (326 a 336, bajo el tope de 384 que impone la pelea), porque
  los tiles se deduplican por índice y el degradé del rojo cae en los mismos
  índices que el del blanco. Sólo las letras de los términos eran treinta y
  cinco: con menos letras el orden de la paleta, que es por frecuencia, sale
  otro. `pant_glifo` suma una tabla por variante en vez de preguntar cuál.
- **Tiles y colores compartidos con ítems** (`titulo.marcos`): las dos
  pantallas no se abren a la vez y suben al mismo lugar, así que suben el
  mismo juego y cada una su tilemap. Los 17 tiles de ítems no alcanzaban:
  equipo suma cinco propios y el juego conjunto es de **22**, y con la fuente de 336 terminan en $37C0,
  a dos tiles de 8bpp del tilemap en $3800. `_controlar_marco_de_items`
  controla el conjunto. Los colores de las ventanas bajaron de la entrada 48
  a la 64 de la CGRAM, detrás de la paleta roja.
- Los parámetros con más aire: el valor en la columna 9 del bloque y la
  flecha en la 12, que en la ventana del actor sobra lugar.
- El código nuevo va en el banco 1 (`banco_de_la_pantalla.s`,
  `pantalla_de_equipo.s`).

## Qué no entra

- **El actor y las ranuras lado a lado**: con letras de 8 pixeles los
  parámetros con el valor nuevo son quince celdas y una ranura con lo puesto
  veintinueve; la pantalla tiene treinta y dos. Van una debajo de la otra.
- **Las ranuras y la lista a la vez**: debajo de la ventana del actor quedan
  seis filas de 16 pixeles y las ranuras usan cinco. La lista sigue
  **reemplazando** a las ranuras mientras se elige, como ya era.
- **La lista en dos columnas**: lo mismo que en ítems, dos nombres de veinte
  letras no entran en 256. Una columna, y ahora de **cinco** filas y no de
  ocho: es lo que deja la ventana de abajo. Se corre como antes cuando el
  cursor se sale.
- **La ayuda de un renglón**: va de dos, como en ítems.
- **La tienda**: usa la misma fuente y el mismo ">" (`EQ_CURSOR` se queda
  por ella); no se tocó.
- La fuente a 6 pixeles: ya estaba declarado.

## Pruebas

- Cambian `equipo`, `equipo-lista`, `equipo-sube-baja` y `equipo-sube`: las
  ventanas, la barra, los términos y la flecha en rojo, y la nueva
  distribución. Nueva `equipo-ranura`: la barra sobre la cabeza, que es una
  ranura que no es la primera y está vacía. `equipo-lista` ya cubría la barra
  sobre la lista, en su segunda fila.
- `pantallas.pantalla_equipo` dibuja las ventanas y la barra (`Texto.ventanas`),
  así que `test_menu_equipo_dibujo.py` compara también eso pixel por pixel.
- **Lo que ninguna prueba ejecuta**: la barra con la lista corrida —más de
  cinco candidatos—. La cuenta es la misma que la del texto (el cursor menos
  el primero que se ve), pero ningún caso tiene tantos.
- `rama-equipo*` no cambian: son capturas del mapa.
- Antes, ahora y el original, lado a lado, en
  `/shared/capturas/2026-09-28-equipo/`.
- Verificado con `just cartuchos` y `just pruebas` sobre esta rama: todo en
  verde. `just espacio`: en `release` el banco 0 pasó de 190 a 196 B libres
  y el banco 1 de 4.499 a 4.380; en `test-special`, de 1.083 a 1.089 y de
  7.003 a 6.884. Los datos nuevos —el tilemap del equipo, sus barras y la
  fuente roja— son unos 4 KB en los bancos de datos.

## Qué tiene que mirar taro

- Menú, Equipment, un actor: las tres ventanas, los términos en rojo, la
  barra a lo ancho de la ranura; moverla por las cinco.
- A sobre una ranura: la barra en la lista, los valores que quedarían con la
  flecha roja; con un arma o una armadura con varios candidatos, bajar y
  subir.
- Equipar y volver con B: las ranuras con lo nuevo; y B otra vez, el menú y
  el mapa como siempre (BG1 se prende en esta pantalla y el mapa lo repone).
- Una pelea después de haber equipado: la fuente creció diez tiles y la pelea
  la sube.
