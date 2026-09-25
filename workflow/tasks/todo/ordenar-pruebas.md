---
name: "Ordenar pruebas/"
description: "Los bugs de las pruebas, los helpers a arnes/ y una pasada de prosa, en tres trabajos"
---

**Lo que encontró una revisión de `pruebas/` el 2026-09-25, contra `43bd1aa`.**
Decidido con taro: se hace **después de que se mergee el cambio de MSU-1**
—que toca `tools/emulador/retro.py` y el arnés—, y en tres trabajos
separados, en este orden. Los números de línea son de ese commit: verificar
antes de tocar.

## 1. Los bugs (primero, solos)

Confirmados:

- **`ev41` no ejercita nada** (`abl/test_tanda_escenas.py:79-84`). El
  EV0041 nunca corre —héroe quieto en (52,24), `ev_activo=0`— y las tres
  goldens (60/120/200) tienen el mismo md5. Su "verificado" era contra la
  referencia de Python.
- **`varios-18-down` no camina** (`rpgmaker/test_tanda.py:98`): su golden es
  byte por byte la de `varios-18-none`; hay una página corriendo desde el tick
  0. Nació en `6cfce1e`; en `571fc59` las dos todavía diferían. Igual
  `plan-73`, `plan-17` y `plan-8` (`down 0 9`, goldens iguales a `*-none`).
- **La cobertura de `test_los_largos_de_opcode_cuadran_en_todo_el_juego`
  depende del orden**: `paginas_del_juego` (`herramientas/test_teleport.py:45`)
  sólo llama a `indexar_variables`, y los dicts globales de `eventos` quedan
  llenos o vacíos según qué corrió antes en el worker. `test_paginas.py:110`
  limpia `VARIABLE_SLOT` y no lo repone.
- **`test_parches` nunca mira `release`**: `_armados`
  (`herramientas/test_parches.py:39-44`) lista sólo `cartuchos.DESTINO`.
  `UNTESTED.md:43-53` dice algo que dejó de ser cierto.
- **El `skipif` está en el test equivocado** (`test_teleport.py:66`): el que
  lee el juego es el otro.
- **`GAME_DIR` y `ABL_GAME_DIR`**: `test_timer_paleta.py:29` y
  `test_destello_paleta.py:36` leen la primera; todo lo demás, la segunda.
- **El mapa 6 es una grilla periódica**: en `ruta-vel` y `ruta-vel-lenta`
  la mayoría de los ticks son idénticos a `6-none`, así que no distinguen si
  la ruta corrió.

Arreglar las goldens de `ev41` y `varios-18-down` es re-congelarlas:
**se le muestran a taro lado a lado antes del merge.** Y sumar un chequeo
barato que avise cuando todas las capturas de un caso son idénticas.

Sospechosos, para mirar en la misma pasada: `Partida.reiniciar` no repone
`llegada` ni `hardware` (`arnes/consola.py:377-400`); las pruebas de "viaja en
la partida" dependen de que el arranque reinicialice la WRAM; `test_piedras`
lee el `.lmu` original y no el fork de `parches/manual/`; las fotos del
recorrido sin golden pasan siempre y se buscan por número de orden
(`arnes/recorrido.py:501-503`); siete goldens son la misma pantalla negra.

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
