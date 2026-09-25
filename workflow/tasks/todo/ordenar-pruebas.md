---
name: "Ordenar pruebas/"
description: "Los bugs de las pruebas, los helpers a arnes/, la organización y una pasada de prosa, en cuatro trabajos"
---

**Lo que encontró una revisión de `pruebas/` el 2026-09-25, contra `43bd1aa`.**
Decidido con taro: se hace **después de que se mergee el cambio de MSU-1**
—que toca `tools/emulador/retro.py` y el arnés—, y en tres trabajos
separados, en este orden. Los números de línea son de ese commit: verificar
antes de tocar.

## 1. Los bugs — hecho el 2026-09-25

Lo que era cada uno y qué se hizo. Las goldens que cambiaron están lado a lado
en `/shared/goldens/2026-09-25-pruebas-bugs/`, con su `LEEME.txt`.

- **`ev41` estaba mal armado, no la ROM.** El EV0041 es de la capa de abajo, y
  a esos se les habla **desde su celda** (`CheckEventTriggerHere`); de frente
  sólo los de la capa del héroe (`CheckEventTriggerThere` pide
  `Layers_same`, en easyrpg-player). El caso lo ponía en (52,24) mirando al
  (52,23): medido con un caso temporal, de frente la página no corre nunca,
  igual que en RM2k, y sus capturas son byte por byte las goldens viejas.
  Ahora arranca en (52,23), la página corre y la ruta termina en (55,18), que
  es la cuenta de su `MoveEvent`. Ticks 30/60/108/200: mensaje, subida,
  salto, llegada (el 120 salía igual que el 200 y se fue).
- **`varios-18-down` tampoco era la ROM**: `RunDirectorScene` del mapa 19 es
  automática y sin condiciones, y compila desde que sus mensajes compilan
  (`6cfce1e`); en RM2k el héroe no camina mientras corre. `down` usa ahora
  `grupo-11-en-19-sin-escena`, con el switch 90 que deja al mapa después de
  la escena, y camina las cinco celdas del plan. `none` queda igual.
- **`plan-73`, `plan-17` y `plan-8` para abajo son correctos**: el plan dice
  cero celdas y es verdad —pared en el 17 y el 8, la Receptionist en (15,7)
  del 73—; que la foto sea la de parado es lo que prueba la colisión.
- **Las caminatas ahora miran la RAM**: `test_heroe` y `test_varios` exigen
  que el héroe haya caminado las celdas del plan (`tanda.celdas_del_plan`,
  `Partida.heroe`). Salvo cuando cambia de mapa —el 8 a la derecha pisa la
  puerta al 16, que la referencia no modelaba—.
- **`ruta-vel` / `ruta-vel-lenta`**: además de la golden, `BAJO_EN_EL_TICK`
  pide la celda y la velocidad del héroe en los ticks que son byte por byte
  `6-none`. No se movieron de mapa: habría cambiado trece goldens.
- **El chequeo de capturas iguales**: `conftest._capturas_distintas` falla si
  todas las goldens de una prueba son la misma pantalla. Las que lo eran
  a propósito y están en `MISMA_PANTALLA` con su porqué.
- **`test_los_largos_de_opcode_cuadran_en_todo_el_juego`**: `paginas_del_juego`
  llena todos los índices que llena el conversor, no sólo el de variables.
  El `skipif` del juego pasó a esa prueba, que es la que lo lee.
- **`test_paginas`** repone `VARIABLE_SLOT` aunque la aserción falle.
- **`test_parches` mira `release`**, y exige que esté armado. Se fue la
  sección de `UNTESTED.md` que decía que no.
- **`ABL_GAME_DIR`** en `test_timer_paleta` y `test_destello_paleta`, vía
  `render_map.GAME_DIR`.

Los sospechosos:

- **`Partida.reiniciar` no reponía `llegada` ni `hardware`: confirmado.** Un
  `correr(10)` después de un reset corría 81 ticks en `guardar-198`. Los tres
  resets pasan ahora por `_resetear`, que los pone en cero.
- **"Viaja en la partida" dependía de la WRAM: confirmado a medias.** El
  reset de snes9x deja la WRAM como estaba y la ROM no la limpia entera, así
  que un valor que la carga no repusiera seguía ahí. `_resetear` la pisa con
  `$55` antes. Con eso las pruebas que resetean siguen en verde: hoy no
  había ninguna pasando por eso.
- **`test_piedras` y el fork: descartado.** `lcf.Map` sobre `GAME_DIR` lee el
  volcado de `data/` con el fork encima (34 eventos, el original tiene 84).
- **Las fotos del recorrido por número de orden: confirmado y cubierto.** Una
  foto sin golden sigue sin fallar, a propósito; pero si su hito tiene golden
  con otro número, falla diciendo que se corrió la numeración.
- **Las siete goldens negras: descartado.** Las cuatro `puerta-*-40` y
  `manta-2800` están a mitad de un fundido (`fundido` = 1), `cartel-880` es
  la imagen ya borrada sobre el mapa 4, que es negro, y `saturar-120` es el
  tinte a negro que el caso pide.

Lo que quedó sin cubrir: las siete fotos del recorrido `vipers` no tienen
golden, así que pasan siempre hasta que taro las bendiga; y las goldens
nuevas de `ev41` y `varios-18-down` las tiene que mirar él.

## 2. Los helpers a `arnes/` — hecho el 2026-09-25

Un commit por tema, cada uno con `just pruebas` en verde; el detalle y lo
medido está en cada mensaje. Lo que quedó y dónde buscarlo:

- **Ninguna prueba importa de otra.** El arnés creció: `menu.py` (abrir y
  tocar el menú, `GRUPO`, `ORO`), `batalla.py` (`Pelea`, el droide, perder
  sin pelear, `sabe`), `datos.py` (lo que se lee del juego original: la base,
  el System, `maximos`, `pagina_de`, `DEMO` y los índices de variables y de
  habilidades del cartucho), `dibujo.py` (`comparar_pantalla` contra
  `titulo.render_*`) y `piedras.py`. `LINKAGE` está en `tanda.py`,
  `UN_ANO_DESPUES` en `recorrido.py`, `EMPEZAR` y `SEGUIR` en `consola.py`.
  La única excepción es `video.py`, que importa `test_recorrido` para correr
  sus jugadas, a propósito.
- **`arnes/lcf.py` se llama `datos.py`**: `import lcf` suelto tiene que
  fallar —`tools/README.md`, "Cómo se importa"— y un `lcf` en el arnés lo
  haría andar con otro módulo.
- **No hay fixture de sesión para la base y el skin**: son `datos.base()` y
  `datos.skin()`, con caché, porque casi todas las lecturas estaban adentro de
  funciones de ayuda que no pueden pedir fixtures.
- **Las ranuras de variable se contaban de cinco maneras** y no eran la misma
  cuenta; queda la del conversor. Antes de unificar se comparó número por
  número lo que pide cada prueba: daban lo mismo.
- **`Pelea.modo()` contesta el nombre** del modo (`"ORDEN"`, `"FIN"`), de la
  tabla de símbolos. La marca `b"ABLS"` se queda escrita, una vez
  (`consola.MAGIA`): la ROM no la tiene como símbolo.
- **`tocar` sigue teniendo tres relojes** —`Partida.tocar` en ticks,
  `menu.tocar` y `Pelea.tocar` en cuadros con distinto aire—: unificarlos
  cambia cuándo cae cada toque. El docstring de `menu.tocar` lo dice.
- **Nuevos métodos de `Partida`** para lo que estaba copiado: `evento`,
  `oro`/`poner_oro`, `equipo`, `hay_partida`/`magia`,
  `celdas_mal_dibujadas`.
- **Se borraron tres casos** que corrían lo mismo que otro —`batalla-segunda`,
  `tabla` y `ventana-7-y-269`, con sus goldens y el caso JSON del último—:
  las goldens eran byte por byte las del caso que queda.
- `test_teleport.py` vive ahora al final de `test_protocolo.py`; las capturas
  de `test_cores` van a `pruebas/snapshots/cores/`.

## 3. La pasada de prosa (su propio commit)

Guiada por el diff de las dos anteriores y por esto. Los números de línea son
de `43bd1aa`, y el trabajo 2 corrió muchos: buscar por el texto.

- Rutas que se mudaron: `test_luces.py:6`, `test_hover_tram.py:6`,
  `test_tanda_paginas.py:275`, `test_tanda_rutas.py:19`,
  `golden/tanda/LEEME.md:42`; el `xfail` que ya no existe
  (`test_guardar_save_point.py`, `recorrido.py:852-856`); `demo-apertura`,
  `cerrar`, `bsnes` como recetas.
- La "referencia de Python" citada como si existiera, en casi todos los
  `test_tanda*.py`, `consola.py`, `recorrido.py` y una docena más (`grep -rn
  referencia pruebas/`; no confundir con los dibujos de `titulo.render_*`).
- Prosa que contradice al código: `test_recorrido_vipers.py:241-246`,
  `recorrido.py:75-78` (`PASO_TOPE`), `test_guardar.py:130` ("8 KB"),
  `test_batalla.py:955`, `test_guardar_save_point.py:54-56`,
  `test_tanda.py:27-31`, `test_condicional.py:29-33`, `test_tanda_paginas.py:11`
  y `:490-491`, `pruebas/README.md`.
- Números del estado del trabajo: `golden/tanda/LEEME.md:3`,
  `test_teleport.py:5` (ahora en la sección "los largos, contra el juego"
  de `test_protocolo.py`), `test_recorrido.py:9-11`, `tanda.py:18`,
  `test_parches.py:17`.
- Lápidas: `test_tanda_pantallas.py:360-376`, `test_titulo.py:252-257` y
  `:145-156`, `test_tanda.py` (varias), `test_tanda_escenas.py:19-32`,
  `UNTESTED.md` sobre `plx`/`ply`.

**Se quedan aunque cuenten historia**, porque protegen una línea:
`test_titulo.py:102-105`, `test_game_over.py:88-92`, `consola.py:659-661`,
`recorrido.py:567-573`.

## 4. Organización — hecho el 2026-09-25

Cuatro propuestas que taro aprobó, cada una en su commit y con `just
pruebas` en verde; lo medido está en cada mensaje. Hecha **antes** que la 3,
así que la prosa tiene que tener en cuenta también esto.

- **HP y SP de la partida**: `Partida.hp` / `poner_hp` / `sp` / `poner_sp`,
  sobre `FAR_HP` y `FAR_SP`. Los de la pelea son otra cosa —la ranura
  `BA_UNO` por puesto de combatiente— y quedan en
  `Pelea.hp_del_combatiente` / `sp_del_combatiente`. Se fueron
  `palabra_de`, `hp_guardado`, `sp_guardado`, `hp_de` y los dos `poner_hp`
  de prueba.
- **El 370 de `apertura`** era byte por byte el de `cinematica`, de la misma
  corrida: se fue de `apertura`, con su golden. El porqué de cuál, en el
  commit.
- **El mapa 11** se lee en `piedras.mapa11()` / `eventos_del_11()`, de
  `GAME_DIR`: comparado campo por campo, es lo mismo que leían las dos.
- **Los nombres**: `test_<sistema>[_<detalle>][_golden|_dibujo].py`. El
  sufijo dice contra qué se compara la pantalla —las goldens de
  `pruebas/golden/`, o lo que dibuja `tools/port/`—; sin sufijo, la prueba
  mira estado o no corre ROM. Por qué sufijo y no prefijo ni carpeta, en el
  commit de los renombres. `test_tanda_pantallas` se partió en
  `test_batalla_golden`, `test_menu_golden`, `test_guardar_golden` y
  `test_titulo_golden`, y su `test_espera` pasó a `test_comandos_golden`.

Para la 3:

- **Las citas en prosa de los nombres viejos no se tocaron**: el commit de
  los renombres es sólo eso más el import de `video.py`. Se buscan con los
  nombres viejos —`test_tanda`, `test_tanda_*`, `test_menu`,
  `test_items_pantalla`, `test_equipo`, `test_curar_menu`,
  `test_hp_de_batalla`, `test_tienda`, `test_titulo`, `test_experiencia`,
  `test_escena`, `test_recorrido`, `test_recorrido_vipers`— como palabra
  entera; el glob `pruebas/*/test_tanda*.py` aparece en `AGENTS.md`, el
  `justfile` y varias cabeceras, y hoy es `pruebas/*/test_*_golden.py`.
- `pruebas/README.md` no tiene índice de pruebas; el inventario por tipo y
  por sistema que armó la 4 sirve para hacerlo.
- `herramientas/test_pila.py` corre la ROM, y el README dice que
  `herramientas/` son las que no. No se movió: es una decisión de carpeta,
  no de nombre.
- Dos cuentas de goldens quedaron viejas por el 370: "las diecisiete" de la
  lápida al final de `test_titulo_golden.py`, y "las seis de `apertura`" en
  `test_escenas_golden.py::test_cinematica`, que ahora son cinco.
