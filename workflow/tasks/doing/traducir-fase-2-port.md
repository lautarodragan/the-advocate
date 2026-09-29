---
name: "Traducir las herramientas, fase 2: port/"
description: "Los nombres de código de tools/port/ (el conversor en Python) al inglés, con todos sus usos"
type: refactor
assignee: Tatú
---

Fase 2 de la traducción de `tools/` al inglés, tercera área: `tools/port/`,
el conversor en Python —`snes_convert.py`, `eventos.py`, `batalla.py`,
`menus.py`, `pantallas.py`, `parches.py` y el resto—, con todos sus usos en
`tools/` y `rom/pruebas/`. Las constantes y los símbolos que el conversor
emite al ensamblador (lo que escribe en los `.inc`) **no** entran: son de la
última área, junto con el runtime.

## Cómo va

De a un módulo o un grupo chico por commit, de las hojas hacia
`snes_convert.py`. Cada commit: `SIN_CACHE=1 just cartuchos` con todo
`rom/build/` (menos `cache/`, `.o`, `sello.txt` y el mtime de los `.dbg`)
byte por byte igual al de `a6fd0d19`, `just pruebas` y
`just -f tools/justfile test` en verde, pyflakes sin avisos nuevos y los
ejecutables `rm2k-snes-*` andando desde `/tmp`.

1. `constantes` → `constants`, `formato_snes` → `snes_format`, `comprimir` →
   `compress`, `fuente` → `font`, `reglas` → `rules`, y los nombres de
   `color`.
2. `asignador` → `allocator`, `msu_datos` → `msu_data`, `paleta` →
   `palette`, `experiencia` → `experience`, y los nombres de `tiles_bin`.
3. `ventana` → `window`, `imagen` → `picture` (el cartel de `ShowPicture`),
   `pantalla_completa` → `fullscreen`, `titulo` → `title`, `fin_del_juego` →
   `end_game`.
4. `escena` → `scene`. `snes_convert` la usa también por un alias local
   (`E = escena_mod`), que ningún renombre por import ve: sólo lo cobró el
   build.
5. `parches` → `patches`, el de `rm2k-snes-patches`: su symlink en
   `tools/justfile`, y la namedtuple `Clase` → `Kind` con sus campos. Sus
   flags ya estaban en inglés. Los TOML que escribe no cambian: `just
   parches` los reescribe iguales.
6. `eventos` → `events`, el compilador de páginas: sus ~440 nombres, sus
   clases (`Temas` → `Songs`, `Eventos` → `MapEvents`, `Mensajes` →
   `Messages`, `Imagenes` → `Pictures`, `Tropas` → `Troops`,
   `PaginasDeTropa` → `TroopPages`, `Encuentros` → `Encounters`, `Estado` →
   `PartyState`, `NoSePuede` → `CannotCompile`, la namedtuple `Disparo` →
   `Trigger`) con sus atributos y métodos, renombrados sólo sobre las bases
   que los usan de verdad (`temas.`, `mensajes.`, `del_mapa.`…), porque
   `.mapa`, `.nombre` o `.paso` también son de otros objetos.

   Las constantes que tienen el mismo nombre que un símbolo del
   ensamblador (`ORO_MAX`, `TECLA_DECISION`, `TRIGGER_AUTOMATICO`…) también
   se tradujeron: el `.inc` las escribe con un string, que no cambia. El
   runtime las sigue llamando en castellano hasta la última área, que puede
   usar los nombres de Python como guía.
7. `animacion` → `animation` y `textos` → `texts`.
8. `batalla` → `battle`, el modelo de la pelea contra el que comparan las
   pruebas: `Batalla` → `Battle`, `Combatiente` → `Combatant`, `Azar` →
   `Rng`, con sus atributos y métodos también del lado de las pruebas de
   ABL (`esperado.jugar_turno` → `esperado.play_turn`). Tres cosas que
   ningún renombre por import ve y cobraron las tandas: el alias local `B =
   batalla_mod` de snes_convert, un `**extra` del arnés que le pasa
   `paginas=` a `Battle`, y un `getattr(enemigo, "botin_item")`.

Lo que el conversor escribe al `.inc` cita rutas de `tools/port/` en sus
comentarios (`; See tools/port/imagen.py.`): esas quedan con el nombre
viejo, porque cambiarlas cambia el `.inc`. Van con la última área.
