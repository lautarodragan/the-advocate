---
name: "La segunda etapa de partir main.s"
description: "Las mudanzas están hechas; falta que taro elija cómo partir interprete.s"
type: refactor
assignee: taro
---

El corte del 2026-09-25 (`391930c`, ver `done/partir-main.s.md`) partió
`rom/src/main.s` en tramos contiguos **sin reordenar**, porque partir no
cambia la ROM y mover sí. Así que quedaron rutinas en un archivo que no es el
suyo. Eso ya está hecho (ver "Las mudanzas"). Lo que queda es
`interprete.s`, y es una decisión de taro: ver "interprete.s", al final.

## Las mudanzas

Hechas el 2026-09-25, sobre `d99694d` y con `main` mergeado en el medio
(`4147242`). Una por commit y sin tocar el texto movido:

| commit | qué | de → a |
|---|---|---|
| `d63130b` | `poner_switch` | `ruta_del_heroe.s` → `variables.s`, detrás de `var_escribir` |
| `14c71e5` | `volver_al_mapa`, `volver_de_batalla` | `items.s` → `cargar_mapa.s`, detrás de `cargar_mapa` |
| `4811091` | `poses_npc_olvidar` | `items.s` → `npcs.s`, detrás de `subir_pose_npc` |
| `be42124` | `sonido_de_codigo`, `sonido_tocar` | `quietos_que_animan.s` → `efectos_de_sonido.s`, al final |
| `14eb259` | `destello_de_codigo` | `quietos_que_animan.s` → **`destello_de_pantalla.s`**, detrás de `destello_tick` |
| `0164143` | `pan_cuadros` | `destello_de_pantalla.s` → `camara.s`, detrás de `pan_tick` |
| `6e49fc5` | `exp_sumar`, `aprender_del_nivel` | `batalla_lazo.s` → `nivel.s`, al final |
| `1874a93` | `menu_hp_escribir` | `equipo_desde_eventos.s` → `nivel.s`, detrás de `texto_maximo` |
| `c2df013` | `actor_nivel_de` | `banco1.s` → `nivel.s`, delante de `nivel_param` |
| `70f1716` | `hp_inicial_poner` | `banco1.s` → `nivel.s`, delante de `curar` |
| `5f395e0` | `ba_mensaje` | `batalla_habilidades.s` → `batalla.s`, debajo de su comentario |
| `3efad4e` | el comentario de `titulo_subir_menu` | `titulo.s` → `banco1.s`, pegado a la rutina |

Lo que cambió respecto de la lista de antes, medida sobre `43bd1aa`:

* `destello_de_codigo` iba a `destello_de_personaje.s`, pero arma
  `destello_rgb`/`destello_nivel`/`destello_resta`, que es el destello de
  **pantalla**.
* `menu_hp_escribir` sí tenía casa en el banco 1: `nivel.s` es lo que el
  menú escribe de cada actor y no sale del cartucho.
* Dos que no estaban en la lista: `pan_cuadros` (GetPanWait, al final del
  tramo del destello) y `ba_mensaje`, que era la dueña del "comentario huérfano
  antes de usar un ítem en la pelea": nacieron juntos en `9527063` y `72109da`
  metió los ítems entre los dos.

**Lo que no se mudó, y por qué**: `titulo_subir_menu` (su casa, `titulo.s`, es
del banco 0: volver a subirla cambia el `jsl` de sus tres llamadores; sólo se
le juntó su comentario). Por lo mismo `hp_inicial_poner` queda lejos de
`equipo_inicial_poner` (`variables.s`, banco 0) y `menu_hp_escribir` de
`menu.s`. Los finales de `ram_baja.s` y `ventana_del_mapa.s` terminan en
comentario, pero hablan de su propio archivo: no son huérfanos.

**Cómo se verificó cada una.** `just cartuchos` y `just pruebas` en verde
(con `test_cores.py` adentro) después de cada commit, sin ninguna golden
cambiada ni ninguna prueba tocada. La ROM cambia en cada una (la primera, 2352
bytes de `abl.sfc`). Que ninguna rutina quedara ensamblada con otro ancho lo
comprobó un script descartable que arma `ca65 -l` del árbol de antes y del de
después, contra los mismos generados de los tres cartuchos, y compara rutina
por rutina los bytes listados —con `rr` donde el linker reubica— y el texto:
en las once, 0 bloques distintos de 2015/2257/1378. Probado al revés: cambiar
el `.a8` de `hay_rutas` por `.a16` lo marca. El commit del comentario salió
con las tres ROMs byte por byte iguales.

**`git blame -C --diff-algorithm=histogram`** las sigue: en siete de las once
da para cada línea movida el mismo commit que daba en el origen. En las otras
cuatro se equivoca en unas pocas líneas genéricas que el diff aparea con las
vecinas del destino: 2 de 89 (`volver_*`), 4 de 56 (`pan_cuadros`: `sep`,
`.a8`, `rts`, `.endproc`), 6 de 187 (el final de `aprender_del_nivel`, igual
al de `curar_actor`, que era el final de `nivel.s`) y 10 de 28
(`actor_nivel_de`, los `rep`/`.a16`/`and #$00FF` iguales a los de
`nivel_param`).

## interprete.s

Un solo `.proc correr_codigo` con los 46 manejadores adentro —medido el
2026-09-25, igual que todo lo de abajo—. **No se hizo nada**; esto es lo
medido y la propuesta.

### Cuánto se toca cada parte

`git log` sin merges sobre el `main.s` de antes del corte (`391930c^`, desde
el 2026-09-03, 214 commits) más `interprete.s` después, repartiendo cada línea
de cada hunk entre los manejadores según la versión de cada lado. Se sacan el
corte y los cuatro commits de `.git-blame-ignore-revs` (el renombre de
`ec94369` tocaba 70 manejadores), y los nombres viejos se cuentan con los
nuevos (`op_si` es `op_if`). Queda: **76 commits tocan `correr_codigo`**.

| familia | manejadores | commits | líneas cambiadas | tamaño hoy |
|---|---|---|---|---|
| flujo | despacho, if, if_var, if_actor, goto, delay, key | 41 | 935 | 599 líneas, 782 bytes |
| escenas | shop, battle, save, game_over, access, teleport | 23 | 376 | 238, 274 |
| pantalla | tint, flash, flash_screen, shake, pan, weather, picture×3, animation, tile_sub, terrain | 16 | 482 | 455, 679 |
| audio | bgm, fade_bgm, sound | 14 | 286 | 80, 68 |
| grupo | gold, item, party, actor_sprite, heal, equipment, skill | 12 | 235 | 203, 265 |
| variables | switch, var, timer | 12 | 340 | 308, 364 |
| movimiento | route, route_event, place, place_var, swap, wait/stop_routes | 12 | 296 | 261, 342 |
| mensajes | message, choice | 9 | 91 | 79, 87 |

Lo que importa está adentro de "flujo": **el despacho solo —la
cadena de `cmp`/`bne`/`jmp`— lo tocan 34 de los 76.** Ningún manejador pasa
de 9 (`op_message`), y casi todos tienen 2 a 4, contando el que los creó.
Cada opcode nuevo agrega su comparación al despacho y su cuerpo al final del
`.proc`: ésos son los dos lugares donde dos ramas chocan, y ninguna partición
por familia los separa. Desde el 2026-09-18 sólo 15 commits tocaron
`correr_codigo`: el ritmo ya bajó.

### Lo que se probó (en el scratchpad, sin commitear)

**Cada manejador puede ser su propio `.proc`, y sale byte por byte igual.**
Sólo se cierran los scopes: `.endproc` antes del comentario de cada manejador
y `.proc op_x` en vez de `op_x:`. Las referencias que cruzan de un manejador a
otro son 42 y nada más: los 40 `jmp otro` de vuelta al lazo (pasan a `jmp
correr_codigo::otro`, mismo `jmp` absoluto), el `bra lugar_plantar` de
`op_place_var` a `op_place` (`op_place::lugar_plantar`), y el `bne
op_route_event` de `op_route`, que ya es global. Armado contra los generados de
`release`, `tests/main` y `tests/special`: **las tres ROMs iguales**. Y
también iguales con un `.a8`/`.i16` explícito al principio de cada manejador,
o sea que ninguno está ensamblado con un ancho heredado del texto de arriba.
Lo único que cambia es el `.sym`: `correr_codigo::abrir` pasa a
`op_shop::abrir`; ninguna prueba ni herramienta lee los locales de
`correr_codigo` (grep de `correr_codigo::` y `op_*::` en `pruebas/` y
`tools/`).

### Las particiones posibles

**A. `.include` adentro del `.proc`, por familia** —lo que proponía el plan
del corte—. Byte por byte igual. Gana: el diff es sólo mover texto. Pierde:
ocho archivos que empiezan a mitad de un scope, con `jmp otro` a una etiqueta
de otro archivo y sin un `.proc` que diga dónde se está; `blame` y el
lector tienen que saber que el archivo no existe solo.

**B. Un `.proc` por manejador, y los archivos por familia**, en el mismo
orden de hoy. Byte por byte igual (probado arriba). Gana lo de A sin su
defecto: cada archivo empieza con un `.proc` y sus anchos, y un manejador es
una unidad que se encuentra con `grep '\.proc op_'`. Cuesta 42 líneas
mecánicas además del corte. No resuelve el despacho, que sigue en
`interprete.s` como el punto donde chocan dos opcodes nuevos. Se verifica
igual que el corte: las tres ROMs iguales y `just pruebas`.

**C. B más un despacho por tabla**: un `cmp` contra el número de opcodes, `bcs` y `jmp (tabla,
x)` con una `.addr` por opcode en el orden de su número. **Cambia la ROM.** Las
cuentas, de la tabla de ciclos del 65816 y no medidas: la cadena de hoy cuesta
`5k + 7` ciclos al opcode en la posición k, o sea de 7 (`OP_MESSAGE`) a 227
(`OP_GAME_OVER`, el 45º), y la tabla unos 23 para todos; en bytes del banco 0,
la cadena son 45 × 7 = 315 y la tabla 46 × 2 = 92 más unos 15 de código,
**unos 200 bytes libres en el banco más apretado**. Y si la tabla la emite
`tools/protocol/` desde `events.toml` —un nombre de manejador por
convención—, agregar un opcode deja de tocar el despacho: el número se sigue
eligiendo en un solo lugar. Pierde: pisa X en el despacho, que hoy no lo toca
(hay que revisar que ningún manejador lea X antes de escribirlo), obliga a
que los números sean contiguos o a llenar los huecos, y darle a
`tools/protocol/` una salida nueva es una decisión de ese proyecto.

Partir por **frecuencia de cambio** no tiene con qué: ningún manejador se
separa del resto, salvo el despacho, que es de lo que se ocupa C.

### La recomendación

**B, ya**, como commit mecánico solo y verificado igual que el corte —las tres
ROMs iguales—, con un archivo por familia de la tabla. **C después y aparte**,
si taro quiere los doscientos bytes o sacar el despacho del camino: cambia la
ROM, y es la que de verdad saca el punto donde chocan las ramas.
