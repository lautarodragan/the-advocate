---
name: "La tienda como el original"
description: "Las ventanas del System y la barra roja de cursor, como ya tienen ítems y equipo, llevadas a la tienda"
type: feature
assignee: Aguaribay
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
