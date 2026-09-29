.segment "ZEROPAGE"
source:     .res 3      ; puntero al bloque que estamos subiendo
music:      .res 3      ; puntero dentro del stream de música
camara_x:   .res 2      ; dónde está mirando la cámara, en pixeles
camara_y:   .res 2
scroll_y:   .res 2      ; lo mismo menos uno, que es lo que el PPU quiere
pad:        .res 1      ; lo que el control tenía apretado este cuadro
pad_a:      .res 1      ; y A, que vive en el otro byte del control
pad_a_ant:  .res 1      ; cómo estaba el cuadro pasado, para ver el flanco
; La elección abierta, si hay una: es `ShowChoice`. Mientras `eleg_activo` esté
; puesto hay una ventana de mensaje en pantalla con las opciones y la página
; está bloqueada, igual que con un mensaje común.
;
; El cursor no es un sprite ni un dibujo: el conversor emitió **un cuadro de
; texto por opción**, iguales salvo por dónde está el ">", así que moverlo es
; recomponer la ventana con otro desplazamiento. Por eso acá no hay más estado
; que cuál está marcada.
eleg_activo: .res 1
eleg_n:      .res 1     ; cuántas opciones
eleg_sel:    .res 1     ; cuál está marcada, desde cero
eleg_cancel: .res 1     ; qué opción elige el botón B, más uno; 0 es "no se
                        ; puede cancelar". Es el `choice_cancel_type` de RM2k
                        ; tal cual, que easyrpg usa como `type - 1`.
eleg_tabla:  .res 2     ; dónde empieza la tabla de la elección, dentro de la
                        ; página: por cada opción, el cuadro y el destino
eleg_flancos: .res 1    ; los botones que se acaban de apretar este cuadro. No
                        ; usa `temp` porque `eventos_tick` lo tiene ocupado.
; El menú de la pantalla de título. Son dos bytes propios y no los de `eleg_`
; aunque el movimiento del cursor sea el mismo: la elección del intérprete vive
; adentro de una página de evento y ésta corre antes de que haya mapa, así que
; compartirlos ataría dos cosas que no se tocan nunca.
; 1 si el arranque —o el menú del título— cargó una partida de la SRAM. Lo mira
; `music_boot`: una partida trae su propio tema y no el del mapa inicial.
; En qué ranura se está trabajando, de 0 a SRAM_RANURAS - 1, o **$FF si no hay
; ninguna partida cargada**. Ese centinela hace de las dos cosas —qué ranura y
; si se cargó— porque la RAM del banco 0 está llena y guardar el dato aparte no
; entraba.
;
; Vive en la **página directa** a propósito, y no por lugar sino por el banco:
; las rutinas que trabajan con la SRAM tienen el banco de datos en $70, y una
; variable de la BSS leída con direccionamiento absoluto les daría la SRAM. La
; página directa apunta siempre al banco 0, así que desde ahí se lee bien esté
; el banco donde esté.
ranura: .res 1
titulo_sel:     .res 1  ; qué opción está elegida, desde cero
titulo_flancos: .res 1  ; y los botones que se acaban de apretar
; 1 mientras la pantalla de ranuras está a la vista. La ROM no lo lee: es para
; el arnés, como `cuadros_perdidos`. `vueltas` no avanza mientras la pantalla
; se ve, así que una prueba que espera por ticks se colgaría; con esto
; `consola.py` sabe cuándo apretar. Ver `Partida.guardar_en`.
menu_abierto:   .res 1
pad_ant:     .res 1     ; JOY1H del cuadro pasado, para mirar flancos de las
                        ; direcciones y de B como ya se hacía con A

temp:       .res 4      ; cuentas intermedias
hero_x:     .res 2      ; dónde está el héroe en el mapa, en pixeles
hero_y:     .res 2
hero_dir:   .res 1      ; hacia dónde mira
tile_x:     .res 2      ; y en qué celda de 16x16 está. Dos bytes: hay mapas de
tile_y:     .res 2      ; 500 celdas de ancho y en uno no entrarían
celdas:     .res 3      ; puntero a la fila de bloques donde arranca la ventana
celdas_ptr: .res 3      ; el mismo, mientras se recorre para armar una tira
; La ruta forzada del evento que se está caminando, mientras dura la vuelta.
; Vive en la página directa y no en la ranura porque `lda [ptr], y` **sólo**
; direcciona la página directa: con el puntero en BSS el ensamblador emitiría el
; byte bajo y la ROM leería de otro lado. Ya pasó una vez, con `msg_ptr`.
ruta_ptr:   .res 3
; La tabla de poses de los NPCs que caminan, del mapa cargado.
poses_ptr:  .res 3
win_col:    .res 2      ; la celda de 8x8 que quedó en el borde de la ventana
win_row:    .res 2      ; el cuadro pasado, para saber si la cámara la cruzó
win_block:  .res 2      ; y la fila de bloques a la que apunta `celdas`
col_addr:   .res 2      ; dónde va en la VRAM la columna recién armada
row_addr:   .res 2      ; ídem la fila; $0000 en las dos si no hay nada
tira_ofs:   .res 2      ; desplazamiento dentro del bloque, mientras se arma
tira_paso_col: .res 2   ; lo que mide una fila de bloques, en bytes
tira_resta: .res 2      ; cuántas celdas faltan por armar
hero_ptr:   .res 3      ; y en qué celda de la grilla, como puntero: se mueve
                        ; con él en vez de recalcularse
step_left:  .res 1      ; lo que falta del paso en curso, en medias unidades
                        ; de RM2k —128 por celda—, 0 si no hay
step_dx:    .res 2      ; el sentido del paso en x: -1, 0 o 1
step_dy:    .res 2
anim_step:  .res 1      ; en qué punto del ciclo de caminata va
anim_timer: .res 1      ; cuántos cuadros lleva el frame de la caminata:
                        ; `anim_count`, que sube y se compara con la velocidad
moving:     .res 1      ; si se movió este cuadro
oam_slot:   .res 2      ; en qué objeto de OAM vamos
npc_ofs:    .res 2      ; desplazamiento dentro de la tabla de NPCs
hero_key:   .res 2      ; la clave de orden del héroe
hero_drawn: .res 1      ; si ya se lo intercaló
high_acc:   .res 1      ; los bits de la tabla chica que se van juntando
high_ptr:   .res 2      ; y en qué byte de ella van. Dos bytes porque se usa
                        ; como índice, y `ldx` con X de 16 bits lee dos: con uno
                        ; solo tomaría de basura el byte alto.
obj_x:      .res 2      ; posición en pantalla del objeto que se está armando
obj_y:      .res 2
obj_tile:   .res 1
obj_attr:   .res 1
token:      .res 1      ; testigo del handshake con el SPC700
es_pal:     .res 1      ; 1 si la consola corre a 50 cuadros por segundo
pal_tick:   .res 1      ; para meter el cuadro de música que falta
reinicio:   .res 1      ; si el stream ya volvió al principio en este cuadro

; El mapa que está cargado. Todo esto salía de constantes del .inc cuando había
; un mapa solo; ahora sale de su registro en `mapa_tabla` —que vive en RODATA y
; se lee con `lda f:`— y queda acá mientras
; dure. Lo que se usa una sola vez —los tamaños de los DMA, las bases de VRAM—
; no se copia: se lee del registro en el momento.
mapa_ofs:    .res 2     ; el desplazamiento del registro del mapa actual
; Y su índice, para saber si un salto cambia de mapa. Dos bytes desde que el
; destino de OP_TELEPORT es un word: el juego tiene 328 mapas y en un byte
; entran 256. El techo que queda es MAPA_STRIDE: `mapa_ofs` es de dieciséis
; bits, así que son 512 mapas.
mapa_actual: .res 2
mapa_ancho:  .res 2     ; su ancho en celdas de 16x16
mapa_alto:   .res 2
mapa_cw:     .res 2     ; y en celdas de 8x8, que es el doble. Se guarda hecho
mapa_ch:     .res 2     ; porque el redibujado lo mira en cada columna y fila
npc_total:   .res 2     ; cuántos bytes ocupa la tabla de NPCs de este mapa
cam_max_x:   .res 2     ; hasta dónde puede llegar la cámara sin salirse
cam_max_y:   .res 2
bloques_ptr: .res 3     ; la tabla de bloques, que ya no entra en el banco 0
bloques8_ptr: .res 3    ; la misma corrida ocho bytes, que es donde arranca la
                        ; capa de encima dentro del bloque. Dos punteros salen
                        ; más baratos que ocho `iny` en el lazo más caliente.
pass_ptr:    .res 3     ; la pasabilidad, un byte por bloque
npc_ptr:     .res 3     ; y la de NPCs, sólo mientras se la copia a la RAM
entrada_x:   .res 2    ; por dónde entrar al mapa que se está por cargar, en
entrada_y:   .res 2     ; celdas. $FFFF quiere decir "donde diga el registro"

; El intérprete de eventos.
pag_ptr:     .res 3     ; la tabla de páginas del mapa cargado
cod_ptr:     .res 3     ; el código de la página que se está ejecutando
elegida:     .res 3     ; el código de la página que ganó, mientras se decide
elegida_hay: .res 1     ; si alguna página del evento en curso ganó
elegida_trigger: .res 1 ; y qué la dispara, para correr sólo las automáticas
; Y en qué capa está, que es lo que decide cuál de las dos celdas la dispara
; con la tecla de acción: la de adelante pide la capa del héroe y la propia
; pide cualquier otra. Ver `probar_accion`.
elegida_capa: .res 1
; Cuál de las dos se está mirando: 1 la del héroe, 0 la de adelante.
accion_propia: .res 1
; `ev_actual` vivía acá y no lo leía nadie: sus dos bytes son los que pagan
; el índice de mapa de dieciséis bits, que si no no entraba —la ZP estaba en
; 256 de 256—.
salto_mapa:  .res 2     ; un Teleport pedido por un evento: a qué mapa
salto_x:     .res 2     ; y a qué celda. salto_hay dice si hay uno pendiente
salto_y:     .res 2
salto_hay:   .res 1
saltos_restantes: .res 1 ; cuántas cadenas de teletransporte quedan permitidas
; Y cuántas son. Lo que cuenta el tope son los teletransportes **encadenados**,
; o sea los que ocurren sin que el jugador recupere el control: dos mapas que se
; apuntan entre sí se colgarían para siempre. No cuenta los de una partida, que
; son todos los que quieran ser. Ver dónde se repone, en `eventos_tick`.
;
; Fue 8 hasta el 2026-09-27, y la guarida de Boss Wick lo desmintió: de la
; puerta del vecino en el 37 hasta volver ahí son doce saltos entre mapas sin
; que el jugador toque el pad —el 41, el 40, los vidcasts, el video, el 40 otra
; vez, el 43, el 42, el favor, el 41 y el 37—, y con 8 la ROM entraba en pánico
; a mitad del segundo paso por el 43. 32 deja margen para otra escena así y
; sigue cortando un par de mapas que se apuntan entre sí, sólo que medio
; minuto más tarde.
SALTOS_MAX = 32
; Y qué pasa cuando se acaba. **No se descarta el salto**: se para todo y se
; avisa. Descartarlo en silencio fue lo que escondió el bug de arriba durante
; semanas —la partida seguía andando, sólo que en el mapa equivocado— y es
; exactamente la falla que el CLAUDE.md llama "un camino que ninguna prueba
; ejecuta". Un tope que se alcanza es un error nuestro o del juego: o el tope
; quedó corto para una escena de verdad —como pasó con la de Wick—, o dos
; mapas se apuntan entre sí, y eso en RM2k cuelga el juego.
;
; `panico` es el código de lo que pasó, cero mientras no pase nada. Lo lee la
; prueba de estado; en la consola lo que se ve es la pantalla parpadeando, que
; no se confunde con nada del juego.
panico:      .res 1
PANICO_SALTOS = 1       ; se acabó el presupuesto de teletransportes
; El intérprete corre de a un cuadro, no de una sola pasada. Antes `cargar_mapa`
; ejecutaba todas las páginas del tirón con la pantalla apagada y las esperas se
; salteaban: eso colapsaba el tiempo, y todo lo que en RM2k pasa *durante* una
; página no existía. Ahora las páginas elegidas se encolan al cargar el mapa y
; el lazo principal las va comiendo.
; Cuántas páginas se pueden arrancar en un mismo cuadro, encadenadas. En RM2k
; el tope no es de páginas sino de comandos —`loop_limit = 10000` en
; `game_interpreter.h`— y se reparte entre todas las que arranquen en el
; cuadro. Acá se cuenta por página, que es más grueso: sólo se nota con una
; página que termine sin hacer nada y vuelva a activarse, o sea la que en RM2k
; cuelga el juego. Ahí ésta no cuelga: gasta el cuadro y sigue.
ARRANQUES_MAX = 8

; Los dos bits de `ev_flags`, uno por evento.
FLAG_ESPERA = $01
FLAG_AUTO   = $02
ev_cur:      .res 2     ; el cursor dentro de la página que corre
; Los intérpretes paralelos. La lista de eventos y el estado de cada uno viven
; en la RAM del banco 1; acá queda sólo lo que el lazo necesita en la mano.
par_n:       .res 1     ; cuántos eventos con página paralela tiene el mapa
par_i:       .res 1     ; por cuál va el lazo
par_dir:     .res 2     ; dónde cae su estado, que hay que apuntar dos veces
par_ev:      .res 1     ; de qué evento es, para moverlo detrás del intérprete
; Cuántas vueltas dio el lazo principal, o sea **el tiempo del juego**. Un tick
; es un paso de lógica de RM2k —el `while (Game_Clock::NextGameTimeStep())` de
; easyrpg, `player.cpp:245`—, que allá también está separado del cuadro que se
; dibuja: la lógica va a DEFAULT_FPS y el dibujo a lo que la máquina aguante.
; Acá normalmente coinciden, y se separan cuando una vuelta se pasa del cuadro.
;
; Lo leen las pruebas por la WRAM para saber **qué tick** están mirando —ver
; `Partida` en rom/pruebas/arnes/consola.py—, así que con esto deja de importar si
; la ROM llegó tarde. Lo tarde que llega lo dice
; `cuadros_perdidos`, que es otra pregunta.
vueltas:     .res 2
; Lo único que la animación del ChipSet guarda: qué hay que subir en el vblank
; que viene, tres bits por familia —cero es nada, y si no el dibujo más uno—.
;
; Que la **decisión** viva acá y no adentro del vblank no es gusto: el vblank
; del mapa 8 no tiene un ciclo de sobra. Veinte `nop` puestos ahí a propósito le
; cuestan 61 pixeles —la cola de poses se le va del vblank y las últimas
; escrituras caen con la pantalla ya encendida— así que las dos divisiones van
; en el cuerpo del lazo, donde sí sobra tiempo, y en el vblank queda un `lda` y
; un `beq`. Es el último byte libre de la página directa.
anim_pend:   .res 1
ev_activo:   .res 1     ; si hay una página a medio correr
ev_esperando: .res 2    ; cuántos cuadros faltan de la espera en curso
; La ruta forzada del héroe. En RM2k `ForceMoveRoute` es asincrónico: la página
; sigue corriendo y quien camina es el personaje, así que esto no vive en el
; intérprete sino acá, y lo come `move_hero` en vez del pad. Las órdenes
; están en el bytecode: ver `ruta_heroe`.
ruta_n:      .res 1
ruta_i:      .res 1
; Si el paso que el héroe tiene en curso lo arrancó la ruta forzada y no el pad.
; Hace falta para `hay_rutas`: el último paso de una ruta sigue contando como
; ruta pendiente aunque ya no queden órdenes, y un paso del pad no cuenta nunca.
; Sin esto, `ProceedWithMovement` dejaría de esperar ocho cuadros antes de
; tiempo, o esperaría de más porque el jugador se puso a caminar.
ruta_paso:   .res 1
ruta_espera: .res 1     ; los cuadros que faltan de un `wait` de la ruta
; El blanco y el largo de la ruta que se está leyendo del bytecode. El largo va
; en dos bytes con el alto siempre en cero: se le suma a Y, que es de dieciséis.
ruta_blanco: .res 1
ruta_cuantas: .res 2
; Un tinte pedido por un evento, para aplicarlo en el vblank siguiente.
tinte_pendiente: .res 1
; El grupo, en orden. El gráfico del héroe es el del primero —RM2k lo decide
; así, y `AddActor`/`RemoveActor` llaman los dos a `ResetGraphic`—, o sea que
; esto no es contabilidad: se ve en la pantalla. `hero_poses` apunta a las doce
; palabras de la tabla de actores del mapa que dicen qué tile es cada pose, y
; `hero_pal` a con qué paleta se dibuja.
grupo:       .res 4
grupo_n:     .res 2
hero_poses:  .res 3
hero_pal:    .res 1
; Y dónde están sus quince colores, adentro de la tabla de actores del mapa.
;
; Los líderes posibles **comparten una ranura de CGRAM**: lidera uno a la vez,
; así que darle una paleta a cada uno es tenerla ocupada por alguien que no está
; en pantalla. `aplicar_tinte` sube los del que lidera encima de esa ranura,
; teñidos como el resto. En cero, no hay líder con gráfico y no se sube nada.
hero_cgram:  .res 3
; La página que se está mirando, ya leída de la tabla. Se copia en vez de
; leerse en el lugar porque Y hace de cursor de la tabla, y usarlo además para
; indexar el bitmap de switches vuelve el código imposible de seguir.
pag_ofs:     .res 2
pag_restan:  .res 2
pg_evento:   .res 2
pg_trigger:  .res 1
pg_sa:       .res 2
pg_sb:       .res 2
pg_cod:      .res 3
pg_actor:    .res 1     ; el actor que pide en el grupo, o 0
act_ptr:     .res 3     ; cursor de la tabla de actores del mapa
tinte_r:     .res 1     ; el tinte de pantalla, de 0 a 200 con 100 neutro
tinte_g:     .res 1
tinte_b:     .res 1
tin_ptr:     .res 3     ; la paleta que se está tiñendo, en la ROM
tin_count:   .res 2     ; cuántos colores tiene
tin_cgadd:   .res 1     ; y en qué entrada de CGRAM va
tin_fin:     .res 2     ; cuántos bytes mide, que es el tope del lazo

; --- el compositor de texto ------------------------------------------------
; Todo esto se toca en el lazo más interno del repo —doce filas por caracter,
; cuatro escrituras de dieciséis bits por fila— así que va en la página cero.
msg_ptr:     .res 3     ; puntero al caracter que sigue, dentro de `mensajes`. Va
                        ; acá y no con el resto del estado porque `[dp],y` sólo
                        ; direcciona la página directa.
comp_glifo:  .res 3     ; puntero a las doce filas del caracter, en la ROM
comp_char:   .res 2     ; qué caracter, ya como índice en la fuente
comp_col:    .res 2     ; en qué columna del renglón va
comp_fase:   .res 2     ; y en qué pixel de la celda cae, o sea x mod 8
comp_base:   .res 2     ; el byte del buffer donde arranca su columna de celda
comp_mask:   .res 2     ; la fila del glifo ya corrida a su fase
comp_color:  .res 1     ; con qué índice de paleta se pinta
comp_fila:   .res 1     ; en qué fila del buffer, de 0 a 15
comp_dup:    .res 4     ; la máscara duplicada a los dos planos de cada par
comp_and:    .res 4     ; y las tres combinaciones que salen de ella
comp_or01:   .res 4
comp_or23:   .res 4

