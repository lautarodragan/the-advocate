---
name: "ROM de prueba: el menú en modo 5, en la SNES"
description: "Una ROM mínima que muestra la maqueta del menú en modo 5 (×1,5) como imagen fija, para que taro vea en la SNES con el FX Pak si la alta resolución se lee por su salida de video"
type: research
assignee: taro
---

De taro, el 2026-09-30, después de la maqueta
(`testing/maqueta-del-menu-en-alta-resolucion.md`, Ñacurutú). El modo 5 con
la fuente ×1,5 por glifo es lo que mejor se lee en la maqueta, pero hay un
riesgo que sólo se ve en la consola: las columnas de un pixel de alta
resolución están en el límite del ancho de banda de NTSC y pueden verse
borrosas por compuesto o RF. Esta ROM lo contesta antes de invertir en el
texto de ancho variable.

taro, sobre la fuente: si hace falta, se puede hacer una a mano, con el ×1,5
pensado letra por letra —la L y la I, por ejemplo, tratadas aparte—.

No es el juego: no pasa por el conversor ni por `cartuchos`.

## Qué se armó (Carancho, 2026-09-30)

La ROM está en `rom/experimentos/menu-modo-5/` y se arma con `just
menu-modo-5`, que después la corre en snes9x, bsnes y mesen-s y compara cada
pantalla con su maqueta a 15 bits. Va en `rom/justfile` y no en el de
`tools/` porque lo que muestra es el menú de ABL. La entrega, con un
`LEEME.txt` de qué mirar, está en `/shared/experimentos/2026-09-30-menu-modo-5/`.

Tres pantallas: 1 la ×1,5 (modo 5), 2 la ×1,6 por posición (modo 5), 3 el
menú de hoy (modo 3). Derecha o A pasa a la siguiente, izquierda a la
anterior, B esconde el número de la esquina.

**Iguales a la maqueta en los tres emuladores**, pixel por pixel, sin el
número. La comparación cobra lo que importa del modo: con BG1 fuera de la
subpantalla da catorce mil pixeles distintos por pantalla (probado a mano,
no queda como caso).

Lo que se aprendió de paso, para el menú de verdad:

* **Las caras no entran en el fondo**: una celda de 16x8 que cruza una cara
  lleva hasta 19 colores. Como sprites entran enteras, sin que Adeleine
  pierda nada, cortando cada cara en bandas de filas de hasta 15 colores
  con una paleta cada una.
* **El resto entra en las ocho paletas de BG1** sin perder un color, así
  que no hizo falta Adeleine; la agrupación la hace el script.
* **Voodoo no sabe de las celdas de 16x8 del modo 5**: numera los tiles de
  a uno y los reusa espejados, y en modo 5 una entrada del tilemap nombra
  un par consecutivo. Para esta prueba lo resuelve el script; el menú de
  verdad, si hornea algo en modo 5, le va a pedir ese modo a Voodoo.
* En modo 5 la subpantalla vacía muestra COLDATA, así que va en negro.
* **La lectura del control tiene que esperar que la automática empiece**, y
  no sólo que termine: al entrar al vblank todavía no empezó, y leer JOY1L
  mientras se llena hacía que bsnes perdiera un toque o contara dos.

Al mergear no hay nada que instalar: no toca Rust ni agrega scripts al
PATH.

**Falta**: que taro la mire en la SNES con el FX Pak, por su salida de
video, y diga si las columnas de un pixel se leen y si ×1,5 gana a ×1,6.
