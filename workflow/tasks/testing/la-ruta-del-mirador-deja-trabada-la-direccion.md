---
name: "La ruta del mirador deja trabada la dirección del héroe"
description: "A velocidad 3, la escena del sueño en el mirador (mapa 109) corta la ruta del héroe antes de que destrabe la dirección, y Talan queda sin poder girar"
type: bug
agents: [Hurón]
assignee: taro
---

Lo encontró Hurón el 2026-10-04 (`workflow/tasks/*/dos-puertas-mas-en-el-mapa-de-debug.md`,
en ABL). La ruta del héroe del 109, evento 6, traba la dirección y la
destraba al final; a velocidad 3 —la del juego desde la carrera— la ruta se
corta antes del destrabe, la traba queda y la velocidad termina en 4. Con
la dirección trabada Talan no puede girar hacia Emily en su casa. A
velocidad 4 la ruta termina, y por eso el recorrido del primer día, que
corre a 4, no lo ve. La prueba de la puerta de Paradise destraba a mano,
con un comentario para sacarlo cuando esto se arregle. Falta ver qué hace
RM2k: si la ruta se corta en el original también, o es nuestra.

## Qué hace RM2k: lo mismo

**La traba es de RM2k, medido en el original.** Una copia del juego,
armada con `ditto`, arranca en el 109 debajo del evento 6 y corre su
página sin los mensajes —los que hay antes de la ruta del héroe no la
tocan—; la del 122 espera el movimiento y abre la pantalla de guardar
apenas termina su ruta del héroe. Del `.lsd`, la `party_location`:

| runtime            | velocidad al llegar | `lock_facing` | velocidad | celda  |
|--------------------|---------------------|---------------|-----------|--------|
| RPG_RT de 2015     | 3                   | 1             | 4         | (4, 8) |
| RPG_RT de 2015     | 4                   | 0             | 4         | (4, 6) |
| RPG_RT de 2000     | 3                   | 1             | 4         | (4, 8) |

Lo mismo que la ROM: la ruta del 109 no se cancela con el teletransporte,
sigue en el 122, y la ruta del héroe del 122 la reemplaza antes de su 27.
A velocidad 3 son 80 cuadros hasta el 26 y la página salta a los 90; los
nueve pasos a velocidad 4 no llegan.

**Y la velocidad 3 es del juego**: la pone el 64, evento 2, con un `[29]`
dentro de una rama sobre el switch 164, y el comentario del autor dice
"I need to adjust Talan's walking speed based on whether he's been healed".

Una cosa más que salió midiendo: con la traba puesta, un `face_left` de una
ruta **sí** lo gira en el RPG_RT de 2000 (`facing` 3 con `lock_facing` 1),
como ya hacía la ROM.

## Lo que era nuestro: hablar trabado

RM2k guarda dos direcciones del héroe, `direction` y `facing`. `Move`
cambia siempre la primera y, trabado, no la segunda; `CheckActionEvent`
mira la celda de `GetDirection`. Así que trabado, apretar contra Emily no
lo gira **pero la A le habla**. La ROM tenía una sola, `hero_dir`, y
trabado la A miraba hacia donde se dibuja: el comentario de `try_toward`
lo declaraba, con "ningún caso del juego lo aprieta trabado". Éste lo
aprieta.

Arreglado con `hero_heading` (BSS, en `low_ram.s` al lado de
`hero_lock`): el `direction` de RM2k, que se lee sólo trabado. Lo escriben
`try_toward`, los `face_*` y el salto, y el 26 lo arranca desde
`hero_dir`. Prueba: `test_el_heroe_trabado_habla_hacia_donde_intento_ir`
en `pruebas/rpgmaker/test_direccion_trabada.py` de ABL, caso
`traba-heroe-habla` (el pandillero del mapa 9): roja con `main`, verde con
el arreglo.

**Y la partida no guardaba la traba**: cargar destrababa, con la cuenta de
que la única traba que pasaba de su ruta era la del auto de la carrera, y
entre el 49 y el 64 no hay save point. La del mirador dura todo Distant
Paradise, que sí tiene. Ahora `hero_lock` y `hero_heading` van en
`save_table` —`SAVE_BYTES` crece dos y las partidas viejas dejan de
cargar—. Prueba: `test_la_direccion_trabada_vuelve` en `test_guardar.py`,
roja con el primer commit y verde con el segundo. `test_titulo_dibujo.py`
resta desde el final de la partida para encontrar la música, y aprendió
los dos bytes.

La prueba de la puerta de Paradise ya no destraba a mano: exige la traba
y camina trabada hasta la granja. El arnés (`recorrido.mirar_a`) gira
hacia un evento mirando lo que mira la A.

## Otras rutas que se cortan igual

Un script descartable recorre todas las páginas y, para cada ruta del
héroe que abre algo que cierra más adelante (26/27, 28/29), cuenta en qué
cuadro corre el cierre a velocidad 3 y a 4 contra lo que la página espera
antes de la ruta siguiente del héroe —o del teletransporte—. Es un modelo
(los pasos de easyrpg: 16 cuadros a velocidad 3, 8 a 4; el salto por
`jump_speed`; la espera de ruta, 20), no una medición. Las que salen:

* **Que siguen después de un teletransporte**: sólo la del 109, y la del
  165 al 166, que el autor destraba a mano en el 166 (`[27, 39, 14]`).
* **La espera del tram de Lashe City** (9, evento 25, "2 minutos" y "5
  minutos"): cada par de rutas `[28, 22 pasos, 29]` lo reemplaza el par
  siguiente a los 90 cuadros. A velocidad 3 no llega nunca al 29: cada
  par de más deja **un punto más de velocidad**. A velocidad 4 el modelo
  da 88 cuadros contra 90, y eso se decide por un cuadro: no está medido,
  ni en el original ni en la ROM. Lo intenté en el original y la copia se
  quedó quieta: no averigüé dónde se para de verdad el héroe para hablarle
  al oficial.
* **A velocidad 3, tres escenas lo dejan más lento para siempre**: 128
  evento 2 (cmd 154, `[29, 23, 23, 4 pasos, 13, 28]` contra 120 cuadros),
  132 evento 5 (cmd 8, `[29, 4 pasos, salto, 28]` contra 120) y 142
  evento 2 (cmd 250, `[29, 2 pasos, 28]` contra 48; y la del cmd 234 si
  los tres mensajes se pasan rápido). Bajan a 2 y no vuelven. Con el mismo
  mecanismo que el 109, así que RM2k tendría que hacer lo mismo, pero
  **no lo medí** en el original.
* La del 64 (`[26, 36, 28, 28, 8 pasos, …, 29, 29]` contra 30 cuadros) sale
  a velocidad 3 y 4, pero ahí el héroe va a 6 —el auto— y termina en 16.

Ninguna de ésas es un error de la ROM: hacen lo que RM2k. Si se quieren
arreglar, es un parche del juego, en ABL.

## Para mergear

* Herramientas: la rama de Hurón, dos commits del runtime. Reinstalar
  `cartridge` en el global —`rm2k-snes-cartridges` arma desde el
  `tools/runtime/` del checkout del que se instaló—.
* ABL: la rama `huron-direccion-trabada` del clon de Hurón. Sin goldens
  nuevas ni cambiadas.
* Las partidas guardadas antes dejan de cargar: `SAVE_BYTES` creció dos.

**Verificado**: la tanda de ABL entera, con `main` mergeado en las dos
ramas y las herramientas de la rama instaladas en local, en verde. Lo que
no cubre: que el héroe trabado se vea bien caminando por Paradise —eso es
lo de RM2k, y la tanda lo mira sólo hasta hablarle a Emily—, y nada de lo
de "Otras rutas", que es un modelo.

## La velocidad 3 no era del juego (2026-10-05)

Lo encontré con el tanque de Dalia (ABL, `el-tanque-de-dalia-se-vuelve-dalia.md`):
en RM2k Talan **no** llega a Paradise a 3. El Dr. Vago le cura el tobillo
(mapa 81, evento 6, página 1) con un `[28]` que corre durante un
`TintScreen` con espera, y la ROM tiraba esa espera: la ruta siguiente
reemplazaba al `[28]` sin leerlo. Arreglado en `rm2k-snes-events`; desde
ahí Talan llega a Paradise a 4, el mirador termina su ruta y sale
destrabado, como mide la fila "4" de la tabla de arriba. Lo de esta tarea
—hablar trabado y guardar la traba— sigue siendo de RM2k y sigue en pie,
pero el juego ya no lo ejercita en el mirador: lo cobran los casos de
`test_direccion_trabada.py` y `test_guardar.py`. La puerta 8 del mapa de
debug deja ahora la 4, y su prueba exige al héroe destrabado.

Y de "Otras rutas que se cortan igual": el modelo contaba sin los
`TintScreen`, que ahora esperan; los cortes de ahí hay que volver a mirarlos
con eso.
