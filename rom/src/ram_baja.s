.segment "BSS"
; Cuántas vueltas del lazo pasaron con el mundo congelado por un fundido. Las
; animaciones del mapa —la del ChipSet y la de los que animan quietos— cuentan
; `vueltas` **menos** éstas, así que no avanzan mientras la pantalla funde, y
; es lo que hace easyrpg-player: en una transición `Player::Update(false)` no
; llama a `IncFrame`, y el `GetFrameCounter` que mira `tilemap_layer.cpp:288`
; se queda quieto. `vueltas` no se puede frenar ahí: es el reloj del fundido
; mismo y el del arnés. Contándolas, el agua salía de un teletransporte con
; setenta ticks de fase de más.
vueltas_congeladas: .res 2


; Dos bits por evento, en vez de una cola. `FLAG_AUTO` dice si la página activa
; del evento es una automática que compiló —lo rehace el refresco— y
; `FLAG_ESPERA` es el `waiting_execution` de EasyRPG: quién tiene una página
; esperando turno, la haya puesto el barrido de las automáticas, la tecla de
; acción o un contacto.
;
; Reemplazan a una cola de ocho punteros que se llenaba y descartaba. Un bit
; por evento no puede desbordar ni marcar dos veces al mismo, que es justamente
; lo que hace posible remarcar en cada cuadro. Los dos bits van en la misma
; tabla y no en dos: 128 bytes más no entraban en los 7680 de RAM.
ev_flags:     .res EV_MAX
esperando_n:  .res 1     ; cuántos esperan, para no barrer 128 bytes por gusto
ev_corriendo: .res 2     ; de qué evento es la página que corre, o $FFFF
solo_auto:    .res 1     ; la pasada corta de `elegir_automaticas`
auto_n:       .res 1     ; cuántos eventos tienen una automática activa
refresco_cuadro: .res 1  ; un refresco a mitad de comando dejó la pasada larga
rp_ev_ant:    .res 2     ; el evento de la página anterior, en el refresco
arranques:    .res 1     ; presupuesto de páginas por cuadro; ver ARRANQUES_MAX
port0: .res 1

; Lo que `flush_video` le escribe a INIDISP al final del vblank: el brillo
; maestro de 0 a BRILLO_MAX. Nadie más lo escribe, y el porqué está en
; `prender`. Va en la BSS y no en la página directa porque se toca una vez por
; cuadro, en ningún lazo cerrado —y la página cero está llena—.
brillo:      .res 1

; El `FadeOutBGM`: si hay uno corriendo, cuánto le queda al volumen —de 65535 a
; cero— y cuánto baja por cuadro. El paso lo emite el conversor; ver
; `eventos.paso_de_fundido`.
bgm_fundido: .res 1
bgm_nivel:   .res 2
bgm_paso:    .res 2
dsp_valor:   .res 1     ; el byte que `escribir_dsp` le manda al SPC700

; La cámara corrida sin el héroe: `PanScreen`. Dónde está y adónde va, las dos
; en 1/16 de pixel y con signo, y cuánto corre por cuadro. `pan_px` y `pan_py`
; son lo mismo ya bajado a pixeles enteros, que es lo que suma `follow_camera`:
; se calcula una vez por cuadro en `pan_tick` y no en cada uso.
pan_x:      .res 2
pan_y:      .res 2
pan_dest_x: .res 2
pan_dest_y: .res 2
pan_paso:   .res 2
pan_px:     .res 2
pan_py:     .res 2

; El fundido de un teletransporte. Ver `fundido_tick`.
fundido:      .res 1    ; si hay uno corriendo
fundido_base: .res 1    ; el byte bajo de `vueltas` cuando arrancó
fundido_que:  .res 1    ; qué hay que hacer en el cuadro negro, y ya no
fundido_mapa: .res 2    ; a qué mapa, para los dos casos que cargan
FUNDIDO_NADA   = 0      ; ya se hizo
; `FUNDIDO_PUERTA` es el único que **ninguna ruta de la ROM pide**: lo escribe
; el arnés desde afuera —`Partida.ir_al_mapa`— para plantar la partida en un
; mapa cualquiera, y por eso quiere `cargar_mapa` entero, con el presupuesto
; de saltos repuesto, y no el camino de un salto encadenado. Se llama así
; porque era lo que pedía una puerta cuando las puertas tenían tabla propia;
; hoy cruzan por el intérprete y piden `FUNDIDO_SALTO` como cualquier otro
; teletransporte. Borrarlo es sacarle a las pruebas la manera de arrancar en
; un mapa que no es el del cartucho.
FUNDIDO_PUERTA = 1      ; el del arnés: `cargar_mapa`, con su tope de saltos
FUNDIDO_SALTO  = 2      ; un Teleport a otro mapa
FUNDIDO_MISMO  = 3      ; un Teleport al mismo: sólo mover al héroe

; La ruta forzada del héroe, hasta RUTA_MAX órdenes. Vivía en la página cero y
; se mudó acá cuando el compositor de texto necesitó lugar: `paso_de_ruta` la
; lee una vez por cuadro, así que el ciclo de más por acceso no se nota.
ruta:        .res 32
; La frecuencia de la ruta puesta sobre el héroe, y la que trae el OP_ROUTE que
; se está leyendo. Es el contador de parada de RM2k: ver `ruta_tras_paso`.
ruta_frec:    .res 1
ruta_frec_op: .res 1

; La ventana de mensaje. `msg_abierto` es si hay una en pantalla, y los otros
; dos son pedidos que el lazo principal atiende al final del cuadro, con la
; pantalla apagada: no se puede escribir el tilemap con el PPU dibujando.
;
; Van acá y no en la página cero porque no se tocan en ningún lazo cerrado, y
; la página cero la necesita el compositor de texto.
msg_abierto: .res 1

; De quién es el mensaje que está en pantalla: el evento del paralelo que lo
; abrió, o $FF si lo abrió el primer plano —o si no hay ninguno—. Es el
; `_state.show_message` de easyrpg, que allá es un campo por intérprete y acá
; alcanza con uno solo porque hay un mensaje a la vez. Lo escribe `op_message`
; copiando `par_ev`, que vale $FF fuera del lazo de paralelos.
msg_duenio:  .res 1

; El estado del compositor. Un mensaje no aparece en el cuadro en que se lo
; pide: se compone de a MSG_CHARS caracteres por vuelta del lazo, renglón por
; renglón, y recién cuando está entero se prende el HDMA.
;
; El presupuesto por vuelta no es una optimización sino lo que mantiene honesta
; la comparación: si una vuelta se pasara del cuadro, `wait_vblank` agarraría el
; siguiente y el héroe caminaría la mitad de rápido que en la referencia.
msg_estado:  .res 1     ; 0 quieto, 1 componiendo, 2 listo
msg_linea:   .res 1     ; qué renglón se está armando
msg_lineas:  .res 1     ; cuántos trae el mensaje
msg_col:     .res 1     ; por qué caracter va
msg_largo:   .res 1     ; cuántos tiene el renglón
msg_cebada:  .res 1     ; si el buffer ya tiene el fondo del renglón
msg_subir:   .res 1     ; si hay un renglón listo para subir a la VRAM

; El renglón que se está componiendo: dos filas de celda por 30 columnas, en el
; formato de tiles de la consola. Los 48 bytes de más son para que la máscara
; del último caracter pueda escribir su segunda columna sin salirse: ahí siempre
; escribe cero, pero leer y escribir fuera del buffer sería pisarle a otro.
texto_buf:   .res (VENTANA_TEXTO_COLS * 2 * 32 + 48)

; Las dos tablas del HDMA de la ventana. Viven en RAM porque las dos primeras
; entradas llevan la cámara de este cuadro; la última, que es la de la ventana,
; no cambia nunca.
;
;   hdma_sc    [127][BG2SC mapa] [17][BG2SC mapa] [80][BG2SC ventana] [0]
;   hdma_ofs   [127][hofs][vofs] [17][hofs][vofs] [80][0][VENTANA_VOFS] [0]
;
; Los 144 scanlines de arriba van en dos tramos porque el contador de líneas de
; una entrada es de 7 bits y no llega a 144.
hdma_sc:  .res 7
hdma_ofs: .res 16

; OAM se arma en RAM y se manda entero por DMA cada cuadro. Es más simple que
; escribir entradas sueltas, y es lo que va a hacer falta cuando haya NPCs.
; Son 128 objetos de cuatro bytes más una tabla chica de dos bits por objeto.
oam:      .res 512
oam_high: .res 32

; La cola de subidas a VRAM: lo que hay que subir en el vblank que viene y no
; se puede subir ahora. Cada entrada son tres bytes de origen en el cartucho y
; dos de destino en palabras de VRAM, y lo que se sube es siempre una pose:
; 512 bytes en cuatro filas de 128, porque un objeto de 32x32 son cuatro filas
; de la grilla de nombres. Hasta VQ_POR_CUADRO por vblank; lo que sobra espera
; al siguiente, y quien lo encoló se entera de que no entró y lo vuelve a
; pedir. Ver `vram_encolar` y `vram_drenar`.
VQ_MAX = 8
VQ_POR_CUADRO = 5
VQ_STRIDE = 5
vq_n:      .res 1
vq:        .res VQ_MAX * VQ_STRIDE
vq_src:    .res 3
vq_dest:   .res 2
vq_hechas: .res 1
vq_filas:  .res 1
; La pose del héroe que hay en VRAM, o $FF si hay que subir la que toque.
hero_pose_vram: .res 1
pose_heroe:     .res 1

; Las tiras del mapa se arman acá fuera del vblank y se suben desde acá cuando
; empieza el siguiente, igual que OAM. Armarlas dentro del vblank no entraría, y
; escribirlas a la VRAM fuera de él las mostraría a medio hacer.
;
; Una columna son las 32 celdas de la ventana; una fila, las 64. Se indexan por
; la ranura, no por la celda del mapa: así el orden del buffer es exactamente el
; orden en que la VRAM las quiere y cada tira sale de un DMA.
; Las cuatro seguidas y en este orden: `limpiar_tilemaps` las borra de corrido,
; y `push_una_fila` y `push_una_columna` llegan a la de la capa de encima
; sumándole el largo de la otra, en vez de llevar dos punteros.
tira_col:   .res WINDOW_ROWS * 2
tira_col2:  .res WINDOW_ROWS * 2
tira_row:   .res WINDOW_COLS * 2
tira_row2:  .res WINDOW_COLS * 2

; La tira que `push_strips` está subiendo, mientras dura: de dónde sale y a
; dónde va. Existen porque son **dos** por eje y no una —ver `stream_map`— y
; escribir el bloque de DMA cuatro veces con las direcciones distintas era
; cuatro copias del mismo código.
tira_vram:  .res 2      ; la palabra de la VRAM donde arranca
tira_de:    .res 2      ; y de dónde sale, los dieciséis bits bajos
tira_banco: .res 1      ; en qué banco: 0 la de esta vuelta, $7E la de repuesto
; Y dónde van las de repuesto, que es lo mismo que `col_addr` y `row_addr` para
; las otras. En la BSS y no en la página directa como sus gemelas porque ahí
; quedan tres bytes, medidos con un `.res` en el segmento.
col_addr_b: .res 2
row_addr_b: .res 2

; La tabla de `TileSubstitution`: qué bloque se dibuja en lugar de cuál. Es lo
; único del mapa que se puede cambiar corriendo —la grilla vive en el cartucho—
; y por eso la sustitución no se escribe en ningún lado sino que se consulta al
; leer cada celda: ver `celda_sustituida`.
;
; **Vive lo que vive el mapa cargado, no lo que vive la ventana del tilemap.**
; Se limpia al cargar un mapa y no al rellenar la ventana. Así queda igual a lo
; que hace RM2k —la sustitución se aplica al spriteset de la escena, o sea que
; se pierde al recargar el mapa— y además correcta al volver de una pelea, que
; rellena la ventana sin cargar nada.
;
; `SUB_MAX` está escrito también en `tools/port/snes_convert.py`, que es quien
; puede negarse a emitir un mapa que no entre. `test_sustitucion.py` compara
; los dos: acá no hay forma de avisar que se pasó.
SUB_MAX = 8
sub_n:      .res 2      ; cuántos pares hay puestos, **en bytes**
sub_clave:  .res SUB_MAX * 2
sub_valor:  .res SUB_MAX * 2
; Lo que `op_tile_sub` necesita mientras aplica una instrucción. No va en
; `temp`, que mide cuatro bytes y ya lo usa medio intérprete.
sub_quedan: .res 1      ; pares que faltan de esta instrucción
sub_de:     .res 2      ; el bloque que sale y el que entra, del par en curso
sub_a:      .res 2
sub_hay:    .res 2      ; si alguna clave ya era el que sale
; Cuántas columnas de la ventana faltan rehacer después de una sustitución.
;
; Hace falta porque **el tilemap de la VRAM no se reescribe solo**: `stream_map`
; sólo arma la columna y la fila que la cámara destapa, así que una sustitución
; con la cámara quieta no se vería hasta caminar. Se rehace **una columna por
; cuadro**, y sólo en los cuadros en que la cámara no se llevó la suya: dos
; columnas por cuadro no entran, porque `push_strips` sube una sola y el resto
; del vblank ya está vendido. O sea que la ventana entera tarda `WINDOW_COLS`
; cuadros en ponerse al día, contra el "en el acto" de RM2k —que redibuja el
; spriteset—; el tramo que se ve son las de la pantalla, y las del margen van
; detrás. Está medido en `test_sustitucion.py`.
sub_refresco: .res 2

; La tabla de NPCs del mapa cargado. Es la única de las tablas del mapa que se
; copia a RAM en vez de leerse con un puntero, y por una razón concreta:
; build_oam la recorre con un índice y en cinco desplazamientos distintos, así
; que con `lda tabla, x` sale una instrucción por campo y con un puntero salen
; tres. Copiarla cuesta un DMA por carga de mapa y entra de sobra: el mapa con
; más NPCs de todo el juego tiene 89, y acá entran 127, que es el tope que
; impone OAM.
npc_buf:  .res NPC_MAX * NPC_STRIDE
; Los gráficos a los que las rutas de este mapa cambian con la orden 34: dos
; bytes por gráfico, la entrada en `npc_poses` y la paleta. Se copia acá al
; cargar el mapa, como la tabla de NPCs, y por lo mismo: se lee con un índice
; —`lda ruta_graf_buf, x`— y eso direcciona el banco de datos.
;
; Copiarla y no leerla del cartucho con un puntero largo es lo que la hace
; barata: un `lda [ptr], y` pide el puntero en la página directa, y la página
; directa está llena. Cabe de sobra: el mapa que más pide de todo el juego
; pide seis. Ver RUTA_GRAF_MAX en snes_convert.py.
ruta_graf_buf: .res RUTA_GRAF_MAX * 2

; Dónde está cada evento del mapa, en celdas, por índice de la tabla. Se copia
; de la ROM al cargar el mapa, igual que la de NPCs, y por una razón que no es
; comodidad: **una ruta forzada la cambia**, y la siguiente ruta sobre el mismo
; evento arranca de donde quedó. Hay una página de este juego que manda a
; caminar nueve veces al mismo evento.
;
; Va todo el mapa y no sólo los eventos con gráfico: la mitad de las rutas de
; este juego caen sobre eventos invisibles, que no se dibujan pero sí tardan, y
; lo que tardan es lo que espera `ProceedWithMovement`.
ev_pos_buf: .res EV_MAX * EV_STRIDE

; Las rutas forzadas que están corriendo sobre eventos. Una ranura por ruta y no
; por evento: son pocas a la vez —la página que más manda a caminar mueve
; cuatro— y así la tabla no depende de cuántos eventos tenga el mapa.
;
;   +0  evento     el índice del evento, o $FF si la ranura está libre
;   +1  ptr        puntero de 24 bits a la primera orden, en el bytecode
;   +4  n          cuántas órdenes trae
;   +5  i          en cuál va
;   +6  movio      si este cuadro fue parte de un paso, que es lo que hace
;                  avanzar el ciclo de caminata
;   +7  cuadros    cuántos cuadros le faltan al paso en curso
;   +8  mirando    hacia dónde mira, o $FF si la ruta todavía no lo giró: ahí
;                  vale la dirección que trae su página
;   +9  espera     los cuadros que faltan de un `wait`
;   +12 banderas   bit 0 atraviesa paredes, bit 1 animación parada
;   +13 salto      lo que le queda al salto en curso, 0 si no hay
;   +14 salto_dx   y de dónde salió, en celdas y con signo
;   +15 salto_dy
;   +10 paso       en qué punto del ciclo de caminata va
;   +11 timer      cuántos cuadros faltan para el frame siguiente
;
; El paso es de 16 y no de 9 para que la ranura se indexe con cuatro
; corrimientos en vez de con una multiplicación.
; Los campos de la ranura: +0 el evento, +1..+3 el puntero a las órdenes, +4
; cuántas, +5 en cuál va, +6 si se movió en este cuadro, +7 lo que le falta al
; paso, +8 hacia dónde mira, +9 la espera, +10 y +11 la animación, +12 las
; banderas, +13 lo que le falta al salto y +14/+15 de dónde salió, +16 la
; frecuencia. El paso es potencia de dos por costumbre; sobra lugar.
RUTA_EV_STRIDE = 32
RUTA_EV_LIBRE = $FF
RUTA_EV_SIN_MIRAR = $FF     ; en +8: la ruta todavía no lo giró
ruta_ev:  .res RUTA_EV_MAX * RUTA_EV_STRIDE
; Cuántas de las doce vale la pena mirar: la más alta que se llegó a usar desde
; que se cargó el mapa, más una. **No baja** al liberarse una, y no hace falta
; que baje: una ranura que nunca se tomó tiene $FF en +0, así que buscar más
; allá no puede encontrar nada.
;
; Existe por `ranura_del_evento`, que corre **una vez por evento paralelo y por
; cuadro** y recorría las doce siempre. En el HQ de los Lazer Teeth hay once
; eventos con página paralela y **una sola ranura usada**: eran once recorridas
; de doce para encontrar una, y con eso el lazo se pasaba del cuadro. Es un byte
; porque en la BSS del banco 0 quedaba exactamente uno.
ruta_ev_tope: .res 1

; Los destellos corriendo. Una ranura por destello:
;
;   +0 blanco   0 el héroe, o el índice del evento más uno; $FF libre
;   +1 r, +2 g, +3 b   el color, de 0 a 31
;   +4 potencia, +5 cuadros, +6 k
;   +7 la entrada de CGRAM de su paleta si está esperando el vblank en
;      FAR_FLASH_PAL, o 0. Nunca es cero de otra forma: las paletas de
;      sprite arrancan en la 128
;
; El paso es ocho para que la ranura se indexe con tres corrimientos.
FLASH_STRIDE = 8
FLASH_LIBRE = $FF
flash_ev:  .res FLASH_MAX * FLASH_STRIDE
; Lo que `paleta_con_destello` necesita mientras arma las tablas.
flash_dest: .res 1
flash_alfa: .res 1
flash_slot: .res 2
flash_ranura: .res 2
flash_parcial: .res 2

; La celda que se está consultando, para `ptr_de_celda` y `puede_celda`. Va acá
; y no en la página directa porque se lee con direccionamiento absoluto, que
; alcanza: en la página directa sólo tiene que estar lo que se use como puntero
; con `[dp], y`, y ahí quedan doce bytes contados.
celda_x:  .res 2
celda_y:  .res 2
; Cuántos eventos tiene el mapa —para buscarlos por celda— y cuál se está
; mirando. Van acá y no en la página directa porque se leen con
; direccionamiento absoluto.
ev_total:   .res 2
ev_buscado: .res 2
; Qué disparo se está buscando: la tecla de acción o el contacto. Los dos usan
; la misma búsqueda —el evento de una celda y su página activa— y sólo cambia
; con qué trigger tiene que coincidir.
trigger_buscado: .res 2
; La fila del NPC que se está refrescando, y dónde queda en pixeles.
npc_fila: .res 2
npc_px:   .res 2
npc_py:   .res 2
; Lo que `refrescar_npc` se copia de la ranura antes de usar X para otra cosa.
; Si en este cuadro alguna ranura de ruta hizo algo. Es lo que decide si hay que
; volver a ordenar la tabla de NPCs, que si no cuesta todos los cuadros.
rutas_movieron: .res 1
; Las dos filas que se están comparando o intercambiando.
cmp_a:    .res 2
cmp_b:    .res 2
slot_cuadros: .res 1
slot_mira:    .res 1
slot_paso:    .res 1
; Las dos direcciones en curso. Van en dos bytes con el alto en cero porque se
; usan como índice, y X e Y son de dieciséis: `ldx dir` de un byte se llevaría
; puesto el de al lado. `ruta_dir` es la de la orden que se está ejecutando y
; tiene que sobrevivir a la llamada que usa `celda_dir`.
ruta_dir:  .res 2
celda_dir: .res 2
; Lo que la orden 34 saca de la tabla del mapa: de qué personaje van a salir
; las poses —$FF es "esconder la fila"— y con qué paleta.
graf_k:   .res 1
graf_pal: .res 1
; Lo que un paso en diagonal necesita mientras prueba sus dos eles: las dos
; componentes, y la celda de la que sale, porque `puede_celda` trabaja sobre
; `celda_x`/`celda_y` y hay que correrla hasta el codo y devolverla.
diag_v: .res 1
diag_h: .res 1
; Y la pose de la que sale el giro de una diagonal, ya resuelta: +8 puede
; traer todavía RUTA_EV_SIN_MIRAR.
diag_mira: .res 1
diag_x: .res 2
diag_y: .res 2

; El cronómetro. Los cuadros no se guardan enteros sino partidos en segundos y
; el resto adentro del segundo, y eso no es una optimización: es lo que evita
; dividir por 60 en cada cuadro. Bajar uno es `sub - 1`, y cuando `sub` da la
; vuelta baja un segundo; que el cronómetro esté en cero es `timer_seg = 0`,
; que es lo mismo que `cuadros / 60 == 0` de `Game_Party::UpdateTimers`.
;
; Los dos puntos parpadean con `sub`, que es `cuadros % 60`.
timer_seg:  .res 2
timer_sub:  .res 1
timer_activo:  .res 1
timer_visible: .res 1
; Los cuatro dígitos ya separados, de los minutos a los segundos. Se recalculan
; cuando cambia el segundo y no en cada cuadro: dividir por 60 y por 10 sesenta
; veces por segundo sería trabajo para nada.
timer_dig:  .res 4
; Y lo que `timer_oam` va llevando mientras dibuja: cuál de los cinco glifos
; va, cuál de sus dos mitades, y qué glifo le tocó.
timer_i:     .res 1
timer_mitad: .res 1
timer_glifo: .res 1
; El tamaño con el que sale el próximo objeto, ya corrido a su lugar en la
; tabla chica de OAM: $02 son los 32x32 de los personajes y $00 los 8x8 de los
; dígitos. Es lo único que los dos tamaños de OBSEL necesitan distinguir.
obj_grande:  .res 1

; Un bit por switch de RM2k. El juego consulta hasta el 1003 en las condiciones
; de página, así que con 1024 alcanza. Se limpian una sola vez al arrancar: en
; RM2k una partida nueva empieza con todos apagados.
; El oro del grupo, de 24 bits porque el tope de RM2k son 999999. Todavía no se
; muestra en ningún lado —el menú no existe— pero la rama de oro de
; `ConditionalBranch` lo pregunta, y `ChangeGold` lo mueve.
oro:      .res 3
switches: .res SWITCH_BYTES

; El tinte de pantalla escala cada canal por el mismo factor para todos los
; colores, así que en vez de hacer la cuenta 256 veces se hace 32: una tabla por
; canal, indexada por el valor de 5 bits que tenía.
; La saturación del tinte, en las mismas unidades que los otros tres. Va en la
; BSS y no en la página directa —donde están `tinte_r`, `tinte_g` y `tinte_b`—
; porque ahí ya no entra: sólo tiene que estar lo que se use como puntero con
; `[dp], y`, y quedaban doce bytes contados.
; Lo que la ruta forzada del héroe lleva además del cursor. Va en la BSS y no
; en la página directa —donde están `ruta_i` y `ruta_n`— porque ahí ya no entra:
; sólo tiene que estar lo que se use como puntero con `[dp], y`.
ruta_atraviesa: .res 1  ; walk_everywhere: la ruta ignora la colisión
ruta_anim_para: .res 1  ; stop_animation: la pose se queda en la del medio
ruta_salto:  .res 1     ; lo que le queda al salto en curso, 0 si no hay
; `ruta_salto_dx` y `ruta_salto_dy` vivían acá y no los leía nadie; su byte
; de más es el que paga `fundido_mapa` de dieciséis bits.
; Prendida mientras se prueba un paso de una ruta que atraviesa paredes. La
; miran `can_leave` y `can_enter`, que también usa la caminata con el pad: por
; eso vive acá y no adentro de la ruta.
atravesando: .res 2
; Quién está probando un paso o un salto, para chocar con los demás: el índice
; del evento, o MOVIL_HEROE. Y la capa de su página activa, o $FF si no tiene
; ninguna, que es un evento que no está —`IsActive()`— y no choca con nadie.
; Los pone `preparar_movil` para un evento y `heroe_bloqueado` para el héroe,
; y `mover_eventos` los devuelve al héroe al terminar, así que fuera de una
; ruta de evento siempre dicen "el héroe".
movil:       .res 1
movil_capa:  .res 1
; En qué capa está la página que `leer_pagina` acaba de leer. Va acá y no con
; los otros `pg_*` porque la página directa está llena —257 bytes en 256 con
; éste adentro— y se lee con direccionamiento absoluto, que alcanza.
pg_capa:     .res 1
; Y su ruta propia, la que camina sola: las banderas —bit 0 la tiene, 1 se
; repite, 2 se saltea lo bloqueado, 3 mira siempre igual, 4 la animación sigue
; quieto—, la frecuencia y la velocidad, y dónde están sus órdenes y cuántas.
; La velocidad va en todas las páginas, con ruta o sin ella: es la que usa una
; ruta forzada sobre el evento, como en RM2k.
pg_flags:    .res 1
pg_tile:     .res 1     ; +20..+23: lo que dibuja la página, ver leer_pagina
pg_attr:     .res 1
pg_pose:     .res 1
pg_pasa:     .res 1
; La celda que `pasa_con_evento` mira, y lo que encontró.
pasa_x:      .res 2
pasa_y:      .res 2
pasa_hallada: .res 1
pg_frec:     .res 1
pg_vel:      .res 1
pg_ruta:     .res 3
pg_ruta_n:   .res 1
; +24..+27, la condición por variable, no se copia: `condiciones_ok` la lee
; de la tabla, que es la única que la mira. La BSS está llena.
; Que un switch o el grupo cambió y hay que volver a mirar qué página está
; activa en cada evento: `rutas_de_pagina`, al empezar el cuadro siguiente.
refresco:    .res 1
; Lo que `rutas_de_pagina` va juntando: la página activa de cada evento con
; rutas propias, por su desplazamiento en la tabla; $FFFF si el evento no tiene
; rutas y $FFFE si las tiene y ninguna página cumple.
eleg_por_ev: .res EV_MAX * 2
rp_ev:       .res 2
slot_px:     .res 2
slot_dir:    .res 1
MOVIL_HEROE = $FF
CAPA_HEROE  = 1
; La celda a la que se quiere entrar, y lo que `celda_bloqueada` va mirando.
dest_x:      .res 2
; Por dónde va `build_row`: la columna que arma, con signo, y cuántas le
; faltan de las 64.
fila_col:    .res 2
tira_total:  .res 2
dest_y:      .res 2
otro_ev:     .res 1
trueque_a:   .res 1
trueque_b:   .res 1
; La sacudida de pantalla: dónde está en pixeles, con signo; cuántos cuadros le
; quedan; y con qué fuerza y velocidad. Y `pantalla_x`, que es la cámara más la
; sacudida: es lo que ven el scroll, la tabla HDMA y la OAM, mientras que el
; streaming del tilemap sigue mirando `camara_x`, porque la sacudida es un
; corrimiento del dibujo y no de lo que hay que tener cargado.
; El tinte se arma acá durante el cuadro —las tres paletas del mapa, teñidas,
; en su lugar de CGRAM— y se sube por DMA en el vblank siguiente. Antes
; `tinte_de_evento` apagaba la pantalla a mitad del cuadro para escribir CGRAM
; directo, y eso es un cuadro teñido a medias en el emulador y una franja
; negra en el hardware; lo delató la sacudida, que compara cuadro por cuadro.
cgram_sombra: .res 512
tinte_listo:  .res 1
; Y el destello de pantalla: si hay uno armado en `pal_buf` para subir,
; de dónde sube `dma_sombra`, y el destello en sí.
destello_listo: .res 1
sombra_origen:  .res 2
destello_rgb:   .res 3
destello_nivel: .res 2  ; a escala 256: el byte alto es lo que se dibuja
destello_resta: .res 1
dest_tab_r:  .res 32    ; las tres tablas, de 32 bytes cada una
dest_tab_g:  .res 32
dest_tab_b:  .res 32
dest_nivel:  .res 1
dest_hacia:  .res 1
dest_v:      .res 1
dest_d:      .res 1
dest_fin:    .res 2
; Cuántas poses puede subir `vram_drenar` este vblank: VQ_POR_CUADRO, salvo
; que el tinte ya se haya llevado parte del presupuesto.
vq_tope:      .res 1
; Los cuadros que van del reset, contados por la NMI: el arranque espera a que
; sean BOOT_CUADROS, y después sigue contando para `contar_perdidos`.
boot_cuadros: .res 1
nmi_visto:        .res 1  ; lo que valía al final de la vuelta anterior
cuadros_perdidos: .res 1  ; los que el lazo principal dejó pasar, saturado

sacudida_pos:    .res 2
sacudida_resta:  .res 2
sacudida_fuerza: .res 1
sacudida_vel:    .res 1
pantalla_x:      .res 2
sac_amp:   .res 1
sac_seno:  .res 1
sac_nuevo: .res 2
sac_corte: .res 2
sac_lo:    .res 2
sac_hi:    .res 2
capa_ev:     .res 2
capa_hallada: .res 1
salto_orden:   .res 1  ; el índice del `begin_jump` que se está armando
salto_trabado: .res 1  ; 1 si el salto no arrancó porque la celda está ocupada
; Lo que `armar_salto` va juntando mientras recorre las órdenes de un salto:
; cuánto se desplaza en celdas —con signo— y hacia dónde queda apuntando.
salto_dx:  .res 1
salto_dy:  .res 1
; Y el valor absoluto con el que `direccion_del_salto` compara los dos ejes.
mirar_abs: .res 2


; 1 mientras no haya ningún tema sonando. Va en la BSS y no en la página directa
; —donde vive el resto del estado de la música— porque ahí ya no entra.
music_apagada: .res 1
; Qué tema está sonando, en dos bytes con el alto en cero porque se usa como
; índice de las tres tablas de punteros y X es de dieciséis.
tema_actual: .res 2
; El desplazamiento del salto con el signo ya extendido a dieciséis bits, que
; es como se suma a la celda.
salto_dx16: .res 2
salto_dy16: .res 2
; Y lo que `dibujo_del_salto` recibe y devuelve: la posición en pixeles de quien
; salta, cuánto le queda al salto, y cuánto hay que levantar el dibujo.
salto_px:  .res 2
salto_py:  .res 2
salto_resta: .res 1
salto_alto: .res 2
salto_val:  .res 2
salto_prod: .res 2
salto_signo: .res 2

tinte_s:  .res 1
; Lo que la saturación necesita mientras corre. Los tres canales van en
; palabras y no en bytes para poder hacer `ldx sat_r` derecho: los índices son
; de dieciséis bits, así que un `ldx` sobre un byte se llevaría el de al lado.
sat_r:    .res 2
sat_g:    .res 2
sat_b:    .res 2
sat_luz:  .res 1     ; el gris del color, de cinco bits
sat_ch:   .res 1     ; el canal que se está saturando
sat_sube_marca: .res 1  ; si al sobresaturar el canal se aleja hacia arriba
sat_acc:  .res 3     ; la suma de los tres pesos, de 24 bits
peso_lo:  .res 1
peso_hi:  .res 1
peso_ch:  .res 1
; Si la tabla que se está armando es la mitad de arriba del hard light, o sea
; la que aclara. Ver `tabla_canal`.
tinte_espejo: .res 1
; Donde se copia una tabla mientras se la espeja. Ver `tabla_canal`.
tinte_tmp: .res 32

tabla_r:  .res 32
tabla_g:  .res 32
tabla_b:  .res 32
; Y las tres del tinte solo, que es de donde salen las otras. Van en un solo
; arreglo —el rojo en 0, el verde en 32 y el azul en 64— para poder indexarlas
; con un desplazamiento; el llamador dice cuál.
puro:     .res 96
puro_ofs: .res 2

; Y la paleta teñida se arma acá antes de subirla. No se puede teñir en CGRAM
; leyéndola y volviéndola a escribir: un segundo tinte se compondría con el
; primero. Siempre se parte de la paleta original, que está en la ROM.
pal_buf:  .res 512
; La sombra con el destello de pantalla encima —lo que arma `destellar_rango`
; y sube `subir_destello`— vive en este mismo lugar: la paleta teñida se arma y
; se copia a la sombra en el mismo cuadro, antes de que `destello_tick` escriba
; acá, y lo que hay se sube en el vblank que sigue. La RAM del banco 0 no daba
; para otros 512 bytes.

