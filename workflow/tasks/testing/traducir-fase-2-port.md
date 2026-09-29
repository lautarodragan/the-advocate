---
name: "Traducir las herramientas, fase 2: port/"
description: "Los nombres de código de tools/port/ (el conversor en Python) al inglés, con todos sus usos"
type: refactor
assignee: taro
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
9. `menus`: sus nombres al inglés (`pantalla_ranuras` → `slots_screen`,
   `render_objetivo` → `render_target`, las constantes `ITEM_*`, `MENU_*`,
   `OBJETIVO_*` → `TARGET_*`…), también por el alias local `T = menus_mod`
   de snes_convert.
10. `pantallas` → `screens`: equipo, tienda y pelea (`pantalla_tienda` →
    `shop_screen`, `Texto` → `TextGrid`, las constantes `BA_*`, `EQ_*`,
    `TI_*` con su prefijo), también por los alias locales `P` y `PM` de
    snes_convert.
11. Los flags del conversor: `--relleno-de-textos` → `--text-padding`,
    `--sin-titulo` → `--no-title`, `--aire-de-medida` →
    `--measure-headroom`, `--hp-de-enemigos` → `--enemy-hp`, `--sin-timer` →
    `--no-timer`, `--grafico-de-prueba` → `--test-graphic`,
    `--encuentros-de-prueba` → `--test-encounters`, `--heroe-encima` →
    `--hero-above`, `--grupo` → `--party`, `--comandos-de-prueba` →
    `--test-commands`, `--mapas` → `--maps`, `--inicial` → `--start-index`
    y el separador `--caso` → `--case`, con quien los pasa: `cartridges.py`,
    `ceilings.py` y los `flags` de `rom/rm2k-snes.toml`. La clave
    `aire_de_medida` de `techos.toml` es del TOML y queda.
12. `snes_convert`: sus ~750 nombres, las clases `Sustituciones` →
    `Substitutions` y `Materiales` → `Materials`, los atributos que le
    cuelga a `args` (`imagenes` → `pictures`, `casos` → `cases`…) y los
    alias de los módulos (`escena_mod` → `scene_mod`…). Lo que cobraron el
    build y la tanda, y que ningún renombre mecánico ve: un `dict(nombre=…)`
    cuya clave es un dato de los TOML de parches, y el atributo `mapa` de
    cada caso, que es una copia de `args` y que al llamarse `map_id` pisaba
    el `--map-id` del cartucho: se llama `run_map`.

13. Las citas que quedaron con los nombres viejos en comentarios, docstrings
    y mensajes de error de `tools/`.
14. Las rutas de `tools/port/` en los comentarios de `tools/runtime/*.s`.
    No cambia ningún `.sfc`, `.msu`, `.pcm` ni `.inc`; sí los dos
    `.sfc.dbg`, que anotan el tamaño de cada fuente.

## Lo que queda, a propósito

- **Lo que el conversor escribe al `.inc`**: los símbolos y los comentarios
  que cita (`; See tools/port/imagen.py.`, `; Temas: …`). Cambiarlos cambia
  el `.inc`: van con la última área, junto con el runtime.
- **Las constantes de Python y los símbolos del ensamblador ya no se llaman
  igual**: `events.GOLD_MAX` se escribe como `ORO_MAX`, `KEY_DECISION` como
  `TECLA_DECISION`. La última área puede tomar los de Python como guía.
- **Las claves de los diccionarios** que viajan entre módulos o a disco —las
  de `collect_npcs` (`evento`, `cambia`, `graficos`, `tile_pasa`…), las de
  `scene` (`clave`, `chico`, `alto_rm`), las de cada mapa convertido—, los
  TOML de `rom/parches/auto/` con sus comentarios (el
  `asignador.merge_least_visible` de los battlers lo escribe `patches.py`) y
  los nombres de archivo y de directorio que producen las herramientas
  (`rom/build/<cartucho>/asignador/`, `parches/auto/mapas/`).
- **Los nombres propios de las pruebas de ABL**: `rom/pruebas/` sigue en
  castellano, incluidos sus alias de los módulos de `tools/`
  (`from port import battle as modelo`).
- Alguna prosa describe tuplas o diccionarios con los nombres de sus
  campos en castellano (`(tiles, filas, fila0, paletas)`), que son datos.

## Para quien mergea

- `patches.py` cambió de nombre: el symlink global de `rm2k-snes-patches`
  queda apuntando a nada hasta que se corra `just -f tools/justfile
  install-scripts` en el checkout principal.
- Cualquier rama que todavía use un nombre viejo de `port/` —un `from
  port import eventos`, un flag `--sin-titulo` en `rom/rm2k-snes.toml`—
  mergea limpio y rompe al armar: hay que buscarla con grep.
