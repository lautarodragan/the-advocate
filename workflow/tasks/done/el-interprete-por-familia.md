---
name: "El intérprete por familia"
description: "Los manejadores de opcode juntados por familia, y eventos_tick fuera de cargar_mapa.s: hecha"
type: refactor
---

El despacho es por tabla desde el 2026-09-25 (la parte C de
`done/main-s-segunda-etapa.md`), así que ya se puede hacer. Ojo: la prueba
`test_la_entrada_k_de_la_tabla_salta_al_manejador_del_opcode_k` exige que
cada manejador siga en el banco de `correr_codigo`.

Desde la parte B cada manejador de opcode es su propio `.proc`, repartidos en
`rom/src/interprete_*.s` por tramo contiguo con un tema, no por familia: las
familias están intercaladas en el orden de la ROM (las escenas caen en cinco
tramos) y juntarlas era mover código. Con el despacho por tabla, dónde vive
cada manejador deja de importar, así que juntar cada familia en su archivo es
mover `.proc` enteros **dentro del mismo segmento**, igual que las once
mudanzas de la segunda etapa.

Se verifica igual que ellas: `just pruebas` sin ninguna golden cambiada, y el
listado de `ca65` comparado rutina por rutina para que ningún manejador quede
con otro ancho (el script de esa comparación estaba en el scratchpad de la
segunda etapa: rehacerlo si se perdió). Una familia por commit, sin tocar el
texto movido, para que `git blame -C --diff-algorithm=histogram` la siga.

Decidido con taro el 2026-09-25: el intérprete sí, y **no** reordenar todo
`rom/src/` —el banco 0 va justo, hay código sensible al tiempo, choca con
cada rama abierta, y para depurar en un emulador alcanza con los símbolos del
`.dbg`—.

**De paso, otra mudanza del mismo tipo**, vista depurando en Mesen2:
`eventos_tick` —con `espera_boton` adentro, lo que corre las páginas cada
cuadro— vive en `rom/src/cargar_mapa.s`, junto con `entrar_en_panico`,
`empezar_fundido` y `fundido_tick`. Quedaron ahí porque el corte cortó por
tramos y ése empezaba con `cargar_mapa`. Mirar si tienen un archivo mejor
(mismo segmento) y moverlas con las mismas verificaciones.

## Hecha

El 2026-09-26, sobre `b581d4e` y con `main` mergeado dos veces en el medio
(`7d7528a`, antes de tocar los archivos de los otros agentes, y al final).
Una mudanza por commit, cada `.proc` entero con su comentario y sin tocar el
texto:

| commit | qué | de → a |
|---|---|---|
| `f043c13` | `op_choice` | permisos/saltos/switches → `interprete_mensaje.s`, al final |
| `bfd27c8` | `op_if_var`, `op_goto` | variables y permisos → `interprete_condiciones.s` (`op_if_var` detrás de `op_if`) |
| `d4aa17a` | `op_switch` | permisos → `interprete_variables.s`, al final |
| `d8ebb29` | `pelea_arrancar` | teletransporte → `interprete_tienda_y_pelea.s`, al final |
| `4b441c9` | el archivo del teletransporte, renombrado | `interprete_teletransporte_y_pelea.s` → `interprete_teletransporte.s` |
| `e7cac13` | `eventos_de_mapa`, `eventos_tick` | `cargar_mapa.s` → `paginas_de_eventos.s`, delante de los paralelos |
| `52a788a` | `tinte_de_evento` | `cargar_mapa.s` → `tinte.s`, detrás de `aplicar_tinte` |
| `40873aa` | `entrar_en_panico` | `cargar_mapa.s` → `arranque.s`, detrás de `contar_perdidos` |
| `a0510b4` | `op_wait_routes`, `op_stop_routes` | `interprete_esperar_rutas.s` (se va) → `interprete_movimiento.s` |
| `33a29df` | `op_sound` | efectos → `interprete_musica.s`, al final |
| `7bdb733` | `op_access` | permisos (se va) → `interprete_guardar.s`, al final |
| `2ef02b8` | los encabezados | sólo comentarios |

Queda así —la lista y el orden en la ROM son los de `main.s`—:

| archivo | manejadores |
|---|---|
| `interprete_mensaje.s` | message, choice |
| `interprete_condiciones.s` | if, if_var, if_actor, goto |
| `interprete_oro_e_items.s` | gold, item |
| `interprete_tienda_y_pelea.s` | shop, battle, battle_destination, y `pelea_arrancar` |
| `interprete_efectos.s` | picture, picture_move, picture_erase, animation, weather |
| `interprete_movimiento.s` | route, place, place_var, swap, wait_routes, stop_routes |
| `interprete_destellos.s` | shake, flash_screen, flash |
| `interprete_cronometro.s` | timer |
| `interprete_musica.s` | bgm, fade_bgm, sound |
| `interprete_guardar.s` | save, access |
| `interprete_variables.s` | var, switch |
| `interprete_grupo.s` | party, actor_sprite, heal, equipment, skill |
| `interprete_game_over.s` | game_over |
| `interprete_mapa.s` | tile_sub, terrain |
| `interprete_teclas_y_esperas.s` | key, delay |
| `interprete_camara_y_tinte.s` | pan, tint |
| `interprete_teletransporte.s` | teleport |

Lo que se decidió en el camino:

* **Los archivos que ya tenían nombre de familia se quedaron con el suyo**,
  aunque la tabla de "Cuánto se toca cada parte" de la segunda etapa junte
  más (el oro con el grupo, el cronómetro con las variables, las escenas en
  una). Separarlos no cuesta nada y renombrar choca con cada rama abierta;
  se renombró sólo el que mentía (`..._y_pelea`).
* **`op_access` va con guardar**: los permisos son estado de la partida, y
  el primero es el de guardar. **`op_goto` con las condiciones**: es el
  salto que el conversor pone en el `else`.
* **`empezar_fundido` y `fundido_tick` se quedan en `cargar_mapa.s`**: son
  el fundido del teletransporte, y `fundido_tick` llama a
  `cargar_lo_pedido`, que está detrás en el mismo archivo con
  `mapa_tema_callar` y `mover_heroe_a`. `eventos_de_mapa`, que la tarea no
  nombraba, se fue con `eventos_tick` porque es su otra mitad, y
  `tinte_de_evento`, que tampoco, porque sin ellas quedaba sola entre la
  vuelta de la pelea y el fundido.

**Cómo se verificó.** Cada commit con `just cartuchos` y `just pruebas` en
verde (707 hasta el primer merge de `main`, 719 después), sin ninguna golden
cambiada ni ninguna prueba tocada. Que ningún manejador quedara ensamblado
con otro ancho, con el script de la segunda etapa —`ca65 -l` del árbol de
antes y del de después contra los mismos generados de release y
tests/special, rutina por rutina—: en cada mudanza, 0 bloques con bytes
distintos, y lo mismo entre `main` y el final de la rama (2955 y 1589
bloques). La única diferencia de texto es la lista de `.include`. Probado al
revés: un `.a16` al principio de `op_choice` lo marca. El renombre y los
encabezados salieron con las dos ROMs byte por byte iguales a las del
commit anterior. `test_cores.py` dos veces al final, en verde.

**`git blame -C --diff-algorithm=histogram`** sigue a las trece rutinas
movidas: de 683 líneas, 648 dan el mismo commit que en el origen. De las 35
que no, 30 van a los cortes de `main.s` (`391930c`) y de `interprete.s`
(`a1547b9`), que tienen el mismo texto en otro archivo —`jmp
correr_codigo::otro`, `.endproc`, `rts`, `phb`/`phk`/`plb`—, y 5 a la
mudanza misma, apareadas con las vecinas del destino: `si_var_sigue:` y dos
`iny` de `op_if_var`, un `rts` y `sin_espera:` de `eventos_tick`.
