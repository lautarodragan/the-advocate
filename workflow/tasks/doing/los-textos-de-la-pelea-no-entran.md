---
name: "Los textos de la pelea"
description: "Mensajes de pelea cortados a 31 caracteres o pasados del borde"
type: bug
assignee: Cardenal
---

**Los textos de la pelea que no entran en el ancho de la pantalla.**

Dos casos, los dos de la pantalla de pelea:

- **Los mensajes de las páginas de tropa se cortan a los 31 caracteres.**
  Algunas líneas de `Absorb Aura` llegan a 40 ("RainDrop... GatheringWaves...") y
  pierden la segunda técnica.
- **El mensaje propio de la pelea se pasa del borde** en vez de cortarse:
  "Talan has absorbed the enemy aura!". Ya estaba así antes de las páginas de
  tropa.

Salen de `done/el-sistema-de-batalla-de-talan.md`.

**Otro caso, visto el 2026-09-26 al hacer el elixir en la pelea**: "Kersh
Pungent Elixir-LIFE  used." pasa de 32 columnas y el punto cae en la columna
0 del renglón de abajo, delante de "Core has revived!". Pasa con cualquier
ítem de nombre largo, y el nombre del LDB trae un espacio al final.

**Dos más, desde que corren las páginas por turno y por HP (2026-09-28)**: el
despegue de la pelea de los agentes sale "The Captain has taken off in th", y
el segundo llamado del Rat King pierde la "s" de "sounds". Ver
`tasks/*/eventos-de-tropa-de-release.md`.

# Lo que se hizo (Cardenal, 2026-10-02)

**Qué dijo el blame del tope de 31.** Nace en `a7cd387a` (2026-09-21), "Las
páginas de tropa se compilan", como `BA_PAG_MSG_ANCHO = 31`: es lo que entra
desde la columna 1 en una pantalla de 32 celdas, y el comentario ya decía
que los renglones de hasta cuarenta de los sistemas de Talan perdían su
segunda técnica, y que era deuda declarada. El bloque `messages_troop` se
armaba con la ventana del mapa —39 columnas— y la ROM cortaba al dibujar.
Fue una decisión consciente de dejarlo para después, no de cortar.

Los mensajes propios de la pelea se arman pegando pedazos desde la primera
versión (`9527063d`): nadie decidió que se pasaran, nunca se midió cuánto
miden. Medido sobre el LDB: 43 pares de actor y habilidad pasan de 31 en el
primer renglón, el más largo de 41, y 3 `using_message2` en el segundo, el
más largo de 50 (el de la habilidad 144, de Manta).

**Las páginas de tropa** (el primer commit): el compilador rehace las cajas
de las páginas para la ventana de la pelea —31 por 4— con el mismo `refit`
que las del mapa usan para la suya (`reflow` en `troops.rs`); el conversor
le pasa la ventana en el pedido, `troop_window`, con el ancho que contesta
`rm2k-snes-battle layout`. La ROM no cambia. "The Captain has taken off in
the ship!" sale en una caja de tres renglones con TALAN arriba.

Pruebas, en ABL: `test_el_despegue_se_lee_entero` lee la pantalla —no el
cartucho— y exige el texto entero del LDB; en rojo antes: "The Captain has
taken off in th". Las que comparaban el bloque contra el LDB
(`test_eventos_de_tropa.py`, `test_sistemas_de_tropa.py`) ahora comparan
contra las cajas rehechas (`screen_stage.refit`).

**Los mensajes propios de la pelea** (el segundo commit, en la ROM):
`ba_message` ya no escribe letra por letra en la pantalla. Arma los dos
renglones de RM2k en `BA_MBUF` —`ba_put`, `ba_put_text`, `ba_put_name`,
`ba_put_number`— y `ba_flow` los parte en los espacios en renglones de 31
(una palabra más larga, en el borde), y los dibuja desde abajo: con dos o
menos van donde iban siempre, y con más suben sobre los del grupo, que es lo
que tapa la ventana de mensajes de RM2k. Hasta cuatro.

- RAM: `$7E7B00`-`$7E7BFF`, en `far_ram.s` (`BA_MBUF` y compañía). Ningún
  símbolo de los tres cartuchos caía ahí —medido sobre `abl.sfc.sym`—, y no
  toca `FAR_PAIR_LIST` (`$7E2400`-`$7E257F`).
- Se fue `ba_number_exact`: lo usaba sólo `ba_message`.

Pruebas, en ABL (`test_batalla.py`): `test_el_mensaje_del_elixir_entra_en_la_pantalla`
y `test_el_mensaje_de_detect_aura_entra_en_la_pantalla` leen la pantalla y
exigen los renglones que da `envolver`, la regla escrita en la prueba.
En rojo antes: `'#Kersh Pungent Elixir-LIFE  used'` —el `#` es la celda que
pisó el punto— y `'####an has perceived the enemy a'`.

**Ninguna golden se movió**: ninguna muestra un mensaje que se pase. Las
capturas de los casos nuevos, antes y después, en
`/shared/capturas/2026-10-02-textos-de-la-pelea/`.

**Lo que queda**: el corte de `ba_page_message` sigue, para un renglón que
`refit` no pueda partir (una palabra de más de 31). Una página con `\V[n]`
que crezca al poner los dígitos también se corta en el borde, como en el
mapa.
