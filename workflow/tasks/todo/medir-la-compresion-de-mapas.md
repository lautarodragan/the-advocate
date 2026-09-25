---
name: "Medir la compresión de mapas"
description: "Cuánto se ahorra con trozos de bloques y capas separadas, y cuánto cuesta al caminar"
type: refactor
---

Idea de taro, el 2026-09-25. Hoy un mapa es un diccionario de bloques de
16×16 —cada uno con sus dos capas y su pasabilidad, ver `docs/port/maps.md`—
y una grilla con un índice por celda, sin comprimir. Muchos mapas usan un 30%
de su superficie y el resto es el mismo bloque repetido; la capa de objetos
es casi toda vacía y el piso es un tile repetido.

Medir, sobre todos los mapas del juego, cuatro variantes:

1. como hoy;
2. como hoy con un segundo nivel: trozos de N×N bloques deduplicados (4×4,
   8×8, 16×16), que es lo que hacen los juegos de SNES y Mega Drive, y que
   mantiene el acceso directo que pide el streaming al caminar y panear;
3. capas separadas, un diccionario por capa, con trozos;
4. capas separadas con trozos y una grilla aparte de pasabilidad (en RM2k la
   capa de encima cambia la pasabilidad de la de abajo: hoy viaja resuelta en
   el bloque).

De cada una: bytes en la ROM, cantidad de bloques distintos (el tope de hoy es
512) y ciclos por fila o columna nueva al caminar, contra el presupuesto del
cuadro. **Ojo con el orden de magnitud**: la radiografía de
`juntar-release-y-test-main.md` pone la música (`tema_stream`, 789 KB), las
animaciones de batalla (561 KB), los tiles de los mapas (470 KB) y las poses
(375 KB) arriba de todo; lo primero es medir cuánto pesan hoy las grillas y los
diccionarios, para saber si esto es el 5% o el 30% del problema. Y esto ahorra
ROM, no VRAM: no arregla el mapa 38.
