---
name: "La ventana con más de 15 colores"
description: "Un System cuya ventana (fondo, marco, flecha, cursor, letra y sombra) pasa de los colores que caben corta hoy el juego entero; que Adeleine la reduzca en vez de cortar, para cualquier juego"
type: feature
agents: [Tijereta]
assignee: taro
---

Del relevamiento de Aguará (`docs/research/2026-10-05-otros-juegos.md`): le
pasa a 5 de los 7 juegos, que hoy arman sólo con el System reducido a mano
en una copia del juego. taro, el 2026-10-05, eligió esto como el primero,
de a uno por el límite de uso: sin maquetas previas, con capturas antes y
después.

## Cómo quedó (Tijereta, 2026-10-05)

`message_window::draw`, en `rm2k-snes-screens`, ya no corta cuando la
ventana pasa de quince colores: se los pasa a `adeleine::merge_least_visible`
y repinta todo —fondo, marco, flecha, cursor, filas de la letra y sombra—
con lo que quedó. El peso de cada color es lo que cubre en la ventana vacía,
la flecha y el cursor, y la letra y la sombra pesan una fila entera del área
de texto por línea, para que no sean lo primero en irse. Un System que entra
no pasa por ahí.

Lo perdido viaja en la respuesta de `window` (`brought`, `merges`, `system`)
y el conversor lo escribe en los parches como un tipo nuevo,
`parches/auto/ventanas/<System>.toml`, sólo si hubo fusiones.

Con el System original, `rm2k-snes-screens window` contesta:

    dooms2          18 -> 15
    frozen-world    16 -> 15
    book-of-three   23 -> 15 (pero el marco estirado no entra en el banco de tiles)
    desert          15, entra (lo que cortaba era End Game, otro límite)
    el-dorado, sunset: entran
    vampires-dawn   su System no está en el juego copiado

Lo mismo en las ventanas de 8bpp de las pantallas de texto (`borders.rs`:
ítems, equipo, tienda, elección de actor), que tenían su propio "the
windows use N colours and from 128 there is room for 16": el System de
Dooms 2 traía 26 y el de Frozen World 17. Ahí **lo fusionado todavía no se
escribe en los parches**: es lo que falta de esta tarea.

**Ningún juego arranca todavía con el System original.** Detrás de los
colores aparece el banco de tiles: un fondo en degradé estirado es un tile
por tono, y con 15 colores la ventana de mensajes de Frozen World pide 266
tiles de 256 (Book of Three 267), y la elección de actor de Dooms 2 se pasa
de `$4800`. Se probó seguir fusionando hasta que entren los tiles
(`merge_until`): Frozen quedaba en 4 colores y Book of Three en 2, que
destruye la ventana. No es la herramienta; va aparte (wishlist
`la-ventana-en-el-banco-de-tiles`). Desert corta en End Game y Dooms 2
además en sus BMP.

Capturas: `/shared/capturas/2026-10-05-ventana-con-mas-colores/`, la ventana
de Dooms 2 decodificada de lo que arma el cartucho, antes (System reducido a
mano) y después (Adeleine): la letra conserva el degradé.

Verificado: las pruebas de `screens`, `patches` y `convert`; la tanda de ABL
con estas herramientas, 1136, y `abl.sfc` igual, 27e94e67…, con la primera
versión y con la final. Las dos pruebas nuevas de `screens`
(`window_colors.rs`) se vieron en rojo antes del arreglo. Lo que ninguna
prueba corre: una ROM con una ventana reducida, porque ningún juego arma.

Al mergear se reinstalan `screens`, `patches` y `convert`.
