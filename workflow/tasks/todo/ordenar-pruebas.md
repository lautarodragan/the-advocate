---
name: "Ordenar pruebas/"
description: "Los bugs de las pruebas, los helpers a arnes/ y una pasada de prosa, en tres trabajos"
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

## 2. Los helpers a `arnes/` (mecánico, lo verifica `just pruebas`)

- Pruebas que sirven de biblioteca: `test_menu.abrir/tocar`,
  `test_batalla.Pelea`, `test_game_over.sin_hp/pagina_de`,
  `test_curar.maximos/palabra_de`, `test_piedras.hablarle_a_la_reja`,
  `test_recorrido.UN_ANO_DESPUES`, `conftest.LINKAGE`. A `arnes/menu.py`,
  `arnes/batalla.py`, `arnes/lcf.py`.
- La comparación contra un dibujo de Python, copiada en `test_menu`,
  `test_equipo`, `test_tienda`, `test_items_pantalla`, `test_curar_menu`,
  `test_hp_de_batalla`, `test_titulo`, `test_experiencia`, `test_escena`: una
  `comparar_pantalla` y una fixture de sesión con la base de datos y el skin.
- Los `sys.path.insert` repetidos: `pythonpath` en `pytest.ini`.
- Constantes copiadas que el `.sym` tiene: `test_batalla.py:49`,
  `test_tropa.py:51`, `test_piedras.py:245`, los offsets de `pelea.hp`, el
  `b"ABLS"` en lugar de `SRAM_MAGIA`.
- Duplicados: `EMPEZAR` (seis definiciones), el reset + `BOOT_CUADROS`,
  `celda`, `DEMO`, `heroe`, la traducción LoROM de `tanda.py:191`,
  `coherente`, las tres maneras de calcular la ranura de una variable, y
  `tocar` con tres relojes distintos.
- La fixture `mundo` redefinida en `abl/test_guardar_save_point.py:52-57`.
- Las capturas de un rojo en tres lugares: falta mudar `rom/build/cores/`
  (`test_cores.py:103-104`).
- `herramientas/test_teleport.py` es la prueba de opcodes: va con
  `test_protocolo.py`.
- Código muerto: `tanda.correr_ticks`, `ABRE_LA_DE_RANURAS`, el campo `mapa`
  de `SACUDIDAS`, `REJA`, casos que corren lo mismo que otro.

## 3. La pasada de prosa (su propio commit)

Guiada por el diff de las dos anteriores y por esto:

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
  `test_teleport.py:5`, `test_recorrido.py:9-11`, `tanda.py:18`,
  `test_parches.py:17`.
- Lápidas: `test_tanda_pantallas.py:360-376`, `test_titulo.py:252-257` y
  `:145-156`, `test_tanda.py` (varias), `test_tanda_escenas.py:19-32`,
  `UNTESTED.md` sobre `plx`/`ply`.

**Se quedan aunque cuenten historia**, porque protegen una línea:
`test_titulo.py:102-105`, `test_game_over.py:88-92`, `consola.py:659-661`,
`recorrido.py:567-573`.
