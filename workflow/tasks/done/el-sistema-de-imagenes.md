---
name: "Plan: el sistema de imágenes y la portable console"
description: "Qué usa la portable console de ABL (ShowPicture, MovePicture, eventos comunes automáticos y paralelos, la entrada del control), cuántas imágenes y de qué tamaño, cómo dibujarlas en modo 3 y qué se congela mientras se muestran; para sacar de ahí las tareas"
type: research
assignee: taro
---

De taro, el 2026-10-01: le interesa `ShowPicture` y "todo el sistema de la
portable console" —el menú propio de ABL, hecho con eventos comunes e
imágenes—, porque sirve para sistemas custom de muchos juegos. Dijo que es
aceptable usar el MSU-1; con 46 bancos libres de 64 KB y las imágenes del
juego estimadas en ~430 KB con LZ2, Hornero cree que entran en la ROM sin
romper `decisiones/el-juego-se-juega-sin-msu-1.md`.

La idea de taro para dibujarlas en modo 3, que tiene dos capas: "en la
práctica la mayoría de los ShowPicture impiden moverse mientras se muestran.
No sé si congelan otras cosas, como movimientos de eventos o tiles
animados, pero no descartaría la posibilidad de hornear en runtime la
imagen o capas del mapa, o no mostrar eventos mientras se muestra una
imagen. No es algo que sirva siempre, pero creo que en muchos casos sí".

El menú custom propio, con modo 5 y fuente, quedó en el wishlist:
`wishlist/un-menu-custom-propio.md`. Esto es antes: las imágenes como las
usa RM2k.

## El estudio (Jilguero, 2026-10-01)

Está en `docs/research/2026-10-01-el-sistema-de-imagenes.md`, medido sobre
`76d98bed`. Lo que taro tiene que mirar para decidir:

* **La portable console no hace falta para jugar**: lo que escribe no lo lee
  nadie fuera de ella. La abre el ítem 81. El menú viejo (comunes 11 a 20 y
  34) está muerto: nadie lo abre.
* **Lo que pide además de las imágenes**: comunes automáticos (no los
  paralelos), `Label`/`JumpToLabel`, un `CallEvent` compartido —pegado en
  el lugar, el menú son 140.193 comandos— y `\V[n]` en tres mensajes.
* **Dibujo**: dos planos. Objetos para lo chico sobre el mapa —con los
  eventos ocultos cuando el mapa no deja lugar—, y BG1 en modo 1 para lo
  grande con el mapa oculto, sin VRAM extra. Cubren 20 de las 21
  situaciones de las escenas y toda la consola, con un marco negro en sus
  páginas de texto. Deudas: el montaje translúcido del 217, el humo y la
  sombra opacos, el zoom de las cuatro fotos *Diff* como fundido.
* **Espacio**: ~330 KB con LZ2, 5 o 6 de los 46 bancos.
* **Orden**: primero las escenas (fases 1 a 3 del estudio), después la
  consola (4 a 6), después el menú propio del wishlist.

Las tareas que salen están en la sección 5 del estudio, con su orden; no se
abrieron en `todo/` para que taro elija el plano antes.

No cambió código: no hay nada que instalar al mergear. `just pruebas` no se
corrió —sólo cambian un `.md` de `docs/research/` y esta tarea—. No se
sacaron capturas con el RPG_RT bajo Wine: las imágenes del juego alcanzaron
para medir.
