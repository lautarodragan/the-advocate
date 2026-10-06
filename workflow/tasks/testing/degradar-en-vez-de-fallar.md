---
name: "Degradar en vez de fallar"
description: "Los límites que hoy cortan el juego o el mapa entero pierden sólo lo que no entra, con un aviso: EraseScreen/ShowScreen, más de 256 variables, más de 8 gráficos de ruta por mapa, los nombres que no entran en el menú, el título que no entra en la VRAM"
type: feature
agents: [Carpintero]
assignee: taro
---

De taro, el 2026-10-06: atajos baratos para destrabar los otros juegos, en
la misma línea que las muestras que sobran. Del relevamiento
(`docs/research/2026-10-05-otros-juegos.md`) y del análisis breve de los
cuatro juegos.

## Hecho (Carpintero, 2026-10-06)

Cada punto en su commit. Ninguno tiene prueba de punta a punta fuera de los
juegos (no hay un juego de pruebas con esos límites): los cubre el rearmado.
Al mergear hay que reinstalar `events` y `convert`.

1. **EraseScreen / ShowScreen**: aceptados sin hacer nada, en
   `ACCEPTED_UNDONE` (el runtime no tiene un "pantalla a negro" que no pise
   un tinte). Deuda: el mapa queda visible donde el original queda en
   negro; en Desert, el menú de inicio sale sobre un fondo de basura de
   VRAM. Prueba unitaria.
2. **Más de 256 variables**: las que quedan sin slot salen de la lista con
   un WARNING; la página que usa una ya quedaba afuera; el *evento* cuya
   condición de página usa una queda afuera con WARNING (era un error
   fatal); y un valor que no entra en un byte (`byte()`) deja afuera la
   página en vez de cortar la conversión (el 263 de una ruta). Vampires
   Dawn ya pasa esto (nombra 600 variables).
3. **ROUTE_GFX_MAX**: los gráficos de la orden 34 que no entran se ignoran
   con WARNING (`Graphics::index_capped`, con prueba unitaria); las
   asociaciones de sprite pasadas del tope se descartan igual. El Dorado y
   Sunset arman sin exclusiones.
5. **El título que no entra**: el conversor lo chequea contra los límites
   que `title.s` afirma (544 tiles de imagen, 704 del menú) y arranca sin
   título con WARNING. Desert y Frozen arman sin `--no-title`.

## Sin hacer

4. **Los nombres que no entran en el banco del menú**: cuesta más que lo
   barato. Los nombres se componen en el runtime con tiles del banco, así
   que degradar es decidir qué se corta o qué se omite en `screens`, y
   probarlo en Dooms 2, cuya ROM es la de Mulita. Queda como estaba.
- **Vampires Dawn no arma todavía**, por límites que no son éstos: mapas
  con panorama que no entra, animaciones de batalla sin lugar en el banco
  de sprites (veinticinco excluidos y siguen apareciendo) y la ventana de
  mensajes, que pide 262 tiles contra 256. Cada uno es otro "degradar en
  vez de fallar" por mapa.
- Las exclusiones de Desert Nightmare quedan: no se probó cuáles dependían
  de EraseScreen.
