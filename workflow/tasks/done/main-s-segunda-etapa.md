---
name: "La segunda etapa de partir main.s"
description: "Mudanzas, interprete.s partido (B) y el despacho por tabla (C): hecha"
type: refactor
---

El corte del 2026-09-25 (`391930c`, ver `done/partir-main.s.md`) partió
`rom/src/main.s` en tramos contiguos **sin reordenar**, porque partir no
cambia la ROM y mover sí. Así que quedaron rutinas en un archivo que no es el
suyo. Eso ya está hecho (ver "Las mudanzas"). Después vino `interprete.s`:
taro eligió **B, y C después** entre las particiones de "interprete.s". B está
hecha (ver "B, hecha"), y C también (ver "C, hecha", al final).

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
2026-09-25, igual que todo lo de abajo—. Esto es lo medido y la propuesta
de antes de elegir; lo que se hizo está en "B, hecha".

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

## B, hecha

El 2026-09-25, en cuatro commits: cada manejador a su propio `.proc` en el
mismo archivo; el corte en archivos (sólo la salida de un script descartable
modelado sobre `partir_main.py`); el `.segment` y los anchos al principio de
cada archivo nuevo; y la prosa. Los tres primeros con las tres ROMs byte por
byte iguales a las de antes y `just pruebas` en verde; ver los mensajes.

Dos correcciones a lo medido arriba. Las referencias que cruzan de un
manejador a otro son **46, no 42**: los 45 `jmp otro` —todos los del
intérprete— y el `bra lugar_plantar`. El `bne op_route_event` no cruza:
`op_route_event` es una etiqueta de `op_route`, no un manejador. Y los
manejadores son 46 porque `op_battle_destination` —al que `op_battle` salta
con `jmp`— queda en su propio `.proc`, pero el despacho compara **45**
opcodes: los de `events.toml` menos `OP_DONE`.

**No quedó un archivo por familia**, porque las familias están intercaladas
en el orden de la ROM y juntarlas es mover código: las escenas caen en cinco
tramos y pantalla en cuatro. Quedó un archivo por tramo contiguo con un
tema, `interprete_*.s`, y cuando un tema sigue en otro archivo el encabezado
lo dice. La lista es la de `main.s`; el porqué de cada agrupación está en el
mensaje del commit del corte.

`blame -C --diff-algorithm=histogram` cruza el corte: sobre las 2399
líneas, cada una da el mismo commit que en el `interprete.s` de antes salvo
el blanco final de doce archivos, que culpa al corte de `main.s`. Ninguna
culpa al corte de `interprete.s`.

## C, antes de hacerla

**Un despacho por tabla**: `jmp (tabla, x)` con una `.addr` por opcode, en
lugar de la cadena de `cmp`/`bne`/`jmp`. Cambia la ROM. Es lo que de verdad
saca el punto donde chocan dos ramas que agregan un opcode cada una —con B,
la cadena de `interprete.s` sigue siendo el único lugar que todas tocan—.

Lo que se sabe, de la propuesta de antes (cuentas de la tabla de ciclos del
65816, no medidas): la cadena cuesta `5k + 7` ciclos al opcode en la
posición k, de 7 (`OP_MESSAGE`) a 227 (`OP_GAME_OVER`, el 45º), y la tabla
unos 23 para todos; en bytes del banco 0, la cadena son 45 × 7 = 315 y la
tabla 46 × 2 = 92 más unos 15 de código, **unos 200 bytes libres en el banco
más apretado**. Si la tabla la emite `tools/protocol/` desde `events.toml`
—el manejador de `OP_X` se llama `op_x`, por convención—, agregar un opcode
deja de tocar el despacho. Darle a `tools/protocol/` esa salida nueva es una
decisión de ese proyecto (que está en inglés y no sabe de este juego: el
nombre del manejador tendría que salir de una regla, no de un campo).

Lo que se aprendió haciendo B y cambia o afina C:

* **Los números ya son contiguos**: `events.toml` va de `0x00` a `0x2D` sin
  huecos, y los 45 que no son `OP_DONE` tienen su `op_x` con ese nombre
  exacto. La tabla no tiene que rellenar nada; `OP_DONE` (y cualquier número
  de más, con un `cmp` contra la cantidad y un `bcs`) va al `stz ev_activo`
  / `rts` de hoy.
* **Ningún manejador lee X antes de escribirlo**, en el orden del texto y
  sin seguir saltos ni `jsr` (un script descartable sobre los 45). El
  despacho de hoy no toca X, así que pisarlo sería nuevo, pero ninguno lo
  espera.
* **`tax` con A de 8 bits e índices de 16 copia los 16 bits de C**, o sea
  que el byte alto de A tiene que estar en cero antes: con el opcode leído en
  8 bits, B trae lo que haya quedado del manejador anterior. Hace falta un
  `rep #$20` / `and #$00FF` / `asl` / `tax` / `sep #$20`, o equivalente.
* **`jmp (tabla, x)` lee la tabla del banco del programa**, no del de datos,
  y eso importa acá: el intérprete corre con el banco de datos en el del
  bytecode (ver el comentario de `op_shop`). Una tabla leída con `lda
  tabla, x` leería otro banco.
* **Todos entran con `.a8`/`.i16`** y Y en el primer operando, y ninguno
  depende del ancho que le deja el anterior en el texto (el prototipo con los
  anchos explícitos lo mostró): el orden de los manejadores en la ROM no le
  importa al despacho.
* `op_battle_destination` no es un opcode: no va en la tabla.

## C, hecha

El 2026-09-25, sobre `73fc639`, en cuatro commits más la prosa:

| commit | qué |
|---|---|
| `a0b0358` | `protocol --jump-table`: `EVENT_OPCODE_COUNT` y la macro `EVENT_HANDLERS`, un `.addr op_x` por opcode en el orden del número |
| `40661ce` | la receta `protocolo` y `test_los_generados_estan_al_dia` lo piden; la ROM no cambia (las tres byte por byte iguales) |
| `79d765e` | el despacho: `cmp #EVENT_OPCODE_COUNT` / `bcs op_done` / `asl` / `xba` / `lda #0` / `xba` / `tax` / `jmp (manejadores_de_opcode, x)` |
| `97614f8` | `test_la_entrada_k_de_la_tabla_salta_al_manejador_del_opcode_k` |

Lo que se decidió en el camino:

* **El nombre sale de una regla**: el manejador de `OP_X` es `op_x`. Por eso
  `OP_DONE` pasó a tener su `.proc op_done` (el `stz ev_activo` / `rts` del
  final de la cadena), en vez de ser una excepción.
* **Es un flag y una macro**, no algo que el generador haga siempre: pide
  números contiguos, y `music.toml` termina en 0xFF. El `.inc` sigue en
  `rom/src/` porque es el mismo para todos los cartuchos y no tapa a nadie;
  la regla de los generados es por los de cartucho.
* **Un opcode fuera de rango corta la página**, como hacía la cadena. No
  debería llegar nunca —lo emite el conversor con los mismos números—, pero
  llega si un manejador cuenta mal sus operandos, y sin tope indexaría
  fuera de la tabla. Ninguna prueba ejecuta ese camino.
* **B se limpia con `xba` / `lda #0` / `xba`**, no con `rep` / `and` /
  `sep`: un ciclo y tres bytes menos.

**X, A y las banderas.** Cada manejador entra ahora con X = opcode × 2, A =
opcode × 2 con B en cero, C=0 y Z=0 (antes: X lo que dejó el anterior, A el
opcode con B basura, C=1 y Z=1). Cuatro scripts descartables que siguen
ramas, `jmp`, `jsr` y `jsl` —cortando en la vuelta a `correr_codigo::otro`—
no encuentran ningún camino que lea X, A, C o Z/N antes de fijarlos, ni
desde los 45 manejadores ni desde el `jsr correr_codigo` de los tres
llamadores (y los de ellos) al volver. Lo que cruzan de `phx`/`plx` con X
sin escribir es guardar-y-restaurar, o el truco de la dirección de vuelta de
`cerrar` en `ranuras.s`.

**Medido**: el banco 0 tiene 210 bytes más libres en los tres cartuchos
(`.res N, $00` en `TABLAS` contra el `.o` de cada uno): release 2139 → 2349,
tests/main 1769 → 1979, tests/special 2463 → 2673. **Calculado, no medido**:
22 ciclos de `cmp` a `jmp` para cualquier opcode, contra `5k + 7` de la
cadena; tres se encarecen (`OP_MESSAGE` 7 → 22, `OP_SWITCH` 12, `OP_ROUTE`
17). Pesado por cuántas veces aparece cada opcode en las páginas compiladas
del juego —estático, no por cuántas veces corre—, de 87 a 22 ciclos por
instrucción.

Verificado con `just cartuchos` y `just pruebas` tres veces sobre el
despacho, en verde, sin ninguna golden cambiada ni ninguna prueba tocada, y
`test_cores.py` tres veces más aparte.
