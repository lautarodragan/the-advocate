.segment "CODE"

; --- volcado del mapa a la VRAM --------------------------------------------
; Todo por DMA y con la pantalla apagada, que es cuando se puede escribir la
; VRAM sin pelearle al PPU.
; Carga entero el mapa cuyo índice viene en A **de dieciséis bits**: sus datos
; a la VRAM y a CGRAM,
; sus tablas a donde la ROM las busca, la cámara donde arranca el héroe y la
; ventana del tilemap llena. Es todo lo que hay que hacer para cambiar de mapa.
;
; Con la pantalla encendida esto no se puede llamar: escribe VRAM y CGRAM por
; DMA, que fuera del vblank el PPU no deja.
.proc cargar_mapa_sin_eventos
.a16
.i16
    sta mapa_actual             ; para saber si el próximo salto cambia de mapa
    sep #$20
.a8
    jsr giro_limpiar            ; las filas van a ser otras
    jsr animacion_limpiar       ; y la animación de batalla no sigue
    rep #$20
.a16
    stz sub_n                   ; y las sustituciones de tiles se pierden al
    stz sub_refresco            ; cargar un mapa, como en RM2k: ver `sub_n`
    sep #$20
.a8
    lda #0                      ; y el cartel se borra: es el
    sta f:CARTEL_ACTIVA         ; `erase_on_map_change` de Game_Pictures, y
    sta f:CARTEL_LISTO          ; además sus tiles son de un solo mapa
    jsr paquete_cargar          ; el audio del mapa, en el fundido
    rep #$20
.a16
    lda mapa_actual
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; por MAPA_STRIDE, que es 128
    sta mapa_ofs
    tax

    ; El reparto de la animación de batalla en este mapa: en qué tile cae su
    ; caja y con qué paleta, o que acá no se dibuja. Necesita `mapa_actual` y
    ; `mapa_ofs`, que acaban de quedar puestos.
    phx
    sep #$20
.a8
    jsr animacion_dibujo_mapa   ; entra y sale con el acumulador en ocho
    jsl f:encuentro_mapa        ; y cada cuántos pasos hay un encuentro acá
    rep #$20
.a16
    plx

    ; Lo que se mira seguido se copia; lo que se usa una vez se lee en el lugar.
    lda f:mapa_tabla + M_MAP_BW, x
    sta mapa_ancho
    asl a
    sta mapa_cw                 ; el ancho en celdas de 8x8 es el doble
    lda f:mapa_tabla + M_MAP_BH, x
    sta mapa_alto
    asl a
    sta mapa_ch
    lda f:mapa_tabla + M_CAM_MAX_X, x
    sta cam_max_x
    lda f:mapa_tabla + M_CAM_MAX_Y, x
    sta cam_max_y
    lda f:mapa_tabla + M_EV_COUNT, x
    ; Todo lo que barre eventos va hasta acá y no hasta `EV_MAX`: con los
    ; ciento veinte, un mapa de cuatro eventos barría ciento dieciséis de más y
    ; eso alcanzaba para perder el cuadro.
    sta ev_total
    lda f:mapa_tabla + M_NPC_COUNT, x
    asl a
    asl a
    asl a
    asl a                       ; por dieciséis: NPC_STRIDE
.assert NPC_STRIDE = 16, error, "la cuenta de arriba multiplica por dieciséis a mano"
    sta npc_total

    ; Los punteros a las dos tablas que se leen desde la ROM. El segundo apunta
    ; ocho bytes más adelante, que es donde cada bloque guarda su capa de
    ; encima; sumar ocho no puede desbordar el banco porque el acomodo de
    ; `tools/ensamblado/bancos.py` garantiza que la tabla entera entra en uno.
    lda f:mapa_tabla + M_PTR_NPC_POSES, x
    sta poses_ptr
    lda f:mapa_tabla + M_PTR_MAP_BLOQUES, x
    sta bloques_ptr
    clc
    adc #8
    sta bloques8_ptr
    lda f:mapa_tabla + M_PTR_BLOQUE_PASS, x
    sta pass_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_MAP_BLOQUES + 2, x
    sta bloques_ptr + 2
    sta bloques8_ptr + 2
    lda f:mapa_tabla + M_PTR_BLOQUE_PASS + 2, x
    sta pass_ptr + 2
    lda f:mapa_tabla + M_PTR_NPC_POSES + 2, x
    sta poses_ptr + 2

    ; Dónde arranca el héroe: donde diga el registro, salvo que quien llamó haya
    ; dejado una entrada puesta, que es lo que hace una puerta. La cámara se
    ; acomoda antes de llenar la ventana, porque la ventana se llena alrededor
    ; de ella.
    rep #$20
.a16
    lda entrada_x
    cmp #$FFFF
    bne desde_puerta
    lda f:mapa_tabla + M_HERO_START_X, x
    sta hero_x
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_x
    lda f:mapa_tabla + M_HERO_START_Y, x
    sta hero_y
    lsr a
    lsr a
    lsr a
    lsr a
    sta tile_y
    bra puesto

desde_puerta:
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; la celda mide 16 pixeles
    sta hero_x
    lda entrada_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entrada_x               ; consumida: la próxima carga vuelve al registro

puesto:
    sep #$20
.a8
    lda f:mapa_tabla + M_BG12NBA_VALUE, x
    sta BG12NBA
    ; Y el tilemap del fondo, que también sale del reparto: casi siempre en
    ; $5800, pero no en todos. Se copia a la RAM porque lo suman `build_column`
    ; y `build_row`, que tienen la X ocupada y no pueden leer la tabla.
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_MAP, x
    sta f:FAR_VRAM_MAPA
    sep #$20
.a8
    xba
    ora #MAP_LAYOUT
    sta BG1SC

    ; La cámara corrida vuelve a cero al cambiar de mapa, y de golpe: es lo que
    ; hace `Game_Player::PerformTeleport` con `map_changed`, que le devuelve a
    ; `pan_current` y a `pan_finish` el valor por omisión. Un salto al mismo
    ; mapa no pasa por acá y no la toca, que es también lo que hace RM2k.
    rep #$20
.a16
    stz pan_x
    stz pan_y
    stz pan_dest_x
    stz pan_dest_y
    stz pan_px
    stz pan_py
    sep #$20
.a8

    ; La grilla, a la WRAM, antes que nadie pregunte por una celda: viene
    ; comprimida. Ver `GRILLA`.
    jsl f:lz2_grilla + RAPIDO
    jsr follow_camera
    jsr load_map
    jsr load_above
    jsr load_sprite
    jsr load_npcs
    jsr load_ruta_graficos
    jsr load_ev_pos             ; y dónde arranca cada evento, con o sin gráfico
    stz refresco
    ; Antes del refresco, no después: las marcas del mapa anterior no valen
    ; nada acá —sus índices de evento apuntarían a otros eventos— y el refresco
    ; es el que vuelve a prender el `FLAG_AUTO` de los que corresponda.
    jsr limpiar_esperas
    jsr limpiar_paralelos
    jsr rutas_de_pagina         ; y las rutas propias de las páginas activas
    ; La tabla de actores es de este mapa, así que dónde caen las poses del
    ; líder cambia al cambiar de mapa aunque el grupo sea el mismo.
    jsr elegir_grafico_heroe
    jsr limpiar_tilemaps        ; lo que `fill_window` no pisa, del mapa de antes
    jsr fill_window             ; deja listo tira_paso_col, que el otro usa
    jsr load_ventana            ; tiles, paleta, tilemap propio y tablas de HDMA
    jsr init_hero_ptr

    ; El tinte es estado del juego, no del mapa: sobrevive al teletransporte.
    ; Las paletas que se acaban de subir son las del cartucho, sin teñir, así
    ; que se vuelven a teñir acá. Con el tinte neutro la cuenta es i*100/100 y
    ; deja los colores donde estaban, así que no hace falta preguntar si hay
    ; tinte: el camino es siempre el mismo.
    jsr aplicar_tinte
    stz destello_listo          ; lo que hubiera en `pal_buf` ya no
                                ; es de este mapa; el cuadro que viene lo
                                ; vuelve a armar si el destello sigue
    jsr subir_tinte             ; la pantalla está apagada: va ya
    rts
.endproc

; Y esto es lo que hay que llamar: carga el mapa y le corre los eventos
; automáticos.
;
; Si un evento pide un teletransporte, el ciclo se repite acá y no adentro del
; intérprete. Llamar a cargar_mapa desde el intérprete sería recursión, y dos
; mapas que se apuntan entre sí la harían infinita: la pila se va al fondo y la
; consola hace cualquier cosa. El tope de vueltas está por la misma razón, para
; el caso en que se apunten con un ciclo más largo.
.proc cargar_mapa
.a16
.i16
    pha                         ; el índice del mapa, que lo de abajo pisaría
    sep #$20
.a8
    lda #SALTOS_MAX
    sta saltos_restantes        ; con stx serían dos bytes y pisaría el de al lado
    rep #$20
.a16
    pla
    jsr cargar_mapa_sin_eventos
    rts
.endproc

; Repone lo que la pantalla de ranuras le pisó al mapa, y nada más. Es para el
; save point, que la abre con el juego andando; el título no la necesita porque
; al salir carga el mapa entero.
;
; Qué pisó, en palabras de VRAM: los tiles en RANURA_VRAM y el tilemap en
; RANURA_MAP, que están elegidos para caer adentro del banco de tiles de BG1
; **en los cuatro repartos** de `vram_layout` —el conversor lo comprueba—. Los
; sprites, la capa de encima, la ventana y los dos tilemaps del mapa quedan
; afuera. No era así con las direcciones del menú del título: en el reparto
; ancho los sprites arrancan en $4000 y el tilemap en $4400 les caía encima,
; que se vio como 267 pixeles en el héroe del mapa 73 con el grupo 11 —el del
; bloque 0 se salvaba—. Y en CGRAM, la paleta 0: el color de fondo y la ventana
; de mensaje, más los primeros colores del mapa. Los registros: BG2SC,
; BG12NBA, TM y el scroll de BG2.
;
; Así que se vuelve a subir el banco de tiles con `load_map` —que además trae
; la CGRAM de abajo y la del mapa, y el dibujo de la animación que toca—, se
; tiñe de nuevo porque lo que subió viene sin teñir, y los registros los pone
; `ppu_init` más el BG12NBA y el BG1SC del mapa. Es un subconjunto de
; `cargar_mapa_sin_eventos`, elegido a mano: lo que falta de ahí es estado
; —eventos, rutas, poses, la cola de VRAM— y reponerlo reiniciaría el juego.
;
; La pantalla se apaga a mano y **no se vuelve a prender acá**: `flush_video`
; escribe `brillo` en el vblank que viene, y así el mapa aparece en un cuadro
; entero y no a mitad de uno. Se llega apenas empezado un vblank —la pantalla
; de ranuras sale justo después de su `read_pad`—, así que el apagado también
; cae en un borde de cuadro. Medido: se ven **dos** cuadros negros y después el
; mapa, porque los 30 KB de `load_map` no entran en un vblank y ese tick dura
; dos cuadros —`cuadros_perdidos` cuenta uno—. En RM2k cerrar la escena lleva
; una transición, así que no desentona.
.proc volver_al_mapa
.a8
.i16
    lda #$80
    sta INIDISP
    jsr ppu_init
    ldx mapa_ofs
    lda f:mapa_tabla + M_BG12NBA_VALUE, x
    sta BG12NBA
    lda f:mapa_tabla + M_VRAM_MAP + 1, x
    ora #MAP_LAYOUT
    sta BG1SC                   ; la pelea lo deja apuntando a su escena
    jsr load_map
    ; Y la capa de encima, por su paleta: las caras de la pantalla usan hasta
    ; ocho paletas de BG2, o sea las entradas 16 a 127, y `load_map` repone
    ; sólo las del fondo. Las de encima empiezan en ABOVE_FIRST, que puede
    ; caer ahí adentro.
    jsr load_above
    jsr aplicar_tinte
    stz destello_listo          ; `pal_buf` era de antes; si el destello sigue,
                                ; el cuadro que viene lo vuelve a armar
    jsr subir_tinte
    rts
.endproc

; Y volver de una **pelea**, que pisa mucho más que la pantalla de ranuras.
;
; `volver_al_mapa` alcanza para la tienda, el menú y las ranuras porque las tres
; escriben nada más que `RANURA_VRAM` y `RANURA_MAP`, elegidos para caer adentro
; del banco de tiles de BG1 en los cuatro repartos. La escena de la batalla no:
; `escena_subir` sube **32 KB**, o sea las palabras $4000 a $8000, más su
; tilemap en $3800 y 64 bytes en la palabra 0. En los repartos de
; `vram_layout` eso se lleva puesto, además del banco de BG1:
;
;   $5800  el tilemap del mapa          lo llena `fill_window`; en el reparto
;                                       que lo baja a $1800 no lo toca, y
;                                       `fill_window` lo rellena igual
;   $7800  el de la capa de encima      el mismo
;   $6800  los tiles de la ventana      `load_ventana`, con su tilemap y su HDMA
;   los sprites                         `load_sprite`: arrancan en 0, y la
;                                       palabra 0 se lleva los dos primeros
;                                       tiles del héroe
;
; Nada de eso lo repone `load_map`, así que hasta el 2026-09-13 el mapa volvía
; de la pelea con el fondo hecho basura. Lo que **no** va acá es `load_npcs` ni
; `load_ruta_graficos`: copian tablas del cartucho a RAM, la pelea no las toca,
; y reponerlas borraría lo que los eventos hayan movido antes de pelear.
;
; Va aparte de `volver_al_mapa` y no adentro para no cobrarle a la tienda, al
; menú y a las ranuras las 64 columnas de `fill_window`, que son el único
; momento en que se escribe tanto tilemap de una vez: ellas no lo necesitan, y
; un cuadro perdido de más se lo comerían los casos de la tanda que las miran.
.proc volver_de_batalla
.a8
.i16
    lda #$80
    sta INIDISP                 ; lo que sigue escribe VRAM por DMA
    jsl f:escena_cgram_reponer  ; las paletas que se llevaron los battlers
    jsr load_sprite             ; el banco de poses, la paleta de objetos y OBSEL
    jsr poses_npc_olvidar
    jsr load_ventana
    ; La grilla, que la escena pisó en la mitad del banco $7F —es
    ; `ESC_ESCENA`— si el mapa pasa de 32 KB de grilla. Se vuelve a
    ; descomprimir entera, que es más simple que llevar dónde empieza el
    ; segundo flujo y cuesta lo mismo que al entrar al mapa. Antes de
    ; `fill_window`, que la lee.
    jsl f:lz2_grilla + RAPIDO
    jsr fill_window
    jmp volver_al_mapa
.endproc

; Arranca un fundido de teletransporte. A trae qué hay que hacer cuando la
; pantalla llegue a negro; el mapa, si hace falta, ya está en `fundido_mapa`.
.proc empezar_fundido
.a8
.i16
    sta fundido_que
    lda #1
    sta fundido
    ; El reloj del fundido son **vueltas del lazo**, o sea ticks, y no cuadros
    ; de hardware: así el fundido dura FUNDIDO_TOTAL ticks tarde lo que tarde la
    ; carga del mapa adentro del negro.
    ;
    ; Estuvo contando `boot_cuadros` —cuadros de hardware— desde que la carga
    ; empezó a tardar seis o siete cuadros adentro de una sola vuelta: contando
    ; vueltas el fundido duraba eso de más **en cuadros**, y el arnés, que
    ; contaba cuadros, quedaba corrido. Desde el 2026-09-08 el arnés cuenta
    ; ticks —ver `vueltas`— así que el reloj vuelve a ser el mismo de los dos
    ; lados y el que absorbe el atraso es el reloj de pared.
    lda vueltas
    sta fundido_base
    rts
.endproc

; Un cuadro del fundido. Devuelve A distinto de cero mientras el juego tenga que
; quedarse quieto, que es todo lo que dura.
;
; RM2k congela la escena entera mientras la transición corre: `Scene::MainFunction`
; ve `IsAsyncPending()` y llama a `Player::Update(false)`, que no actualiza nada.
; Acá es lo mismo por omisión: el lazo principal se saltea el intérprete, al
; héroe, los eventos, el cronómetro y todo lo que mueva algo. Lo que sigue
; corriendo es la música, que en RM2k tampoco se corta.
.proc fundido_tick
.a8
.i16
    lda fundido
    beq no_hay
    lda vueltas                 ; el byte bajo alcanza: el fundido dura 70
    sec
    sbc fundido_base
    cmp #FUNDIDO_TOTAL
    bcs terminar
    cmp #FUNDIDO_CARGA
    bcc rampa                   ; todavía se está apagando
    pha
    jsr cargar_lo_pedido        ; una sola vez: se apaga solo
    pla
rampa:
    ; El brillo de este cuadro. Bajando, la rampa se lee al revés.
    cmp #FUNDIDO_RAMPA
    bcs subiendo
    eor #$FF
    clc
    adc #FUNDIDO_RAMPA          ; FUNDIDO_RAMPA - 1 - t
    bra en_la_rampa
subiendo:
    sec
    sbc #(FUNDIDO_CUADROS + FUNDIDO_NEGRO)
    bcs en_la_rampa             ; pasada la carga: la rampa de vuelta
    lda #0                      ; el negro del medio
    sta brillo
    bra sigue
en_la_rampa:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda fundido_rampa, x
    sta brillo
sigue:
    lda #1                      ; el juego sigue congelado
    rts
terminar:
    stz fundido
    lda #BRILLO_MAX
    sta brillo
no_hay:
    lda #0
    rts
.endproc

; El tema que prende el mapa al que se entra, entre `mapa_tema_callar` y el
; final de la carga, o $FF si no hay que prender nada. En la RAM lejana porque
; la BSS del banco 0 está llena.
TEMA_DEL_MAPA = $7E6100

; Lo que el mapa al que se entra le hace a la música, que es el
; `Game_Map::PlayBgm` de easyrpg: su tema, si trae uno —`mapa_tema`, que ya
; resolvió la herencia del árbol—. Vuelve con A en el tema que hay que prender
; cuando el mapa esté cargado, o $FF si no hay que tocar nada, y en ese caso
; lo que sonaba sigue.
;
; No se toca nada en dos casos:
;
; * `mapa_tema` en $FF: el mapa no trae tema, o es el `music_type` 1, "lo
;   decide un evento". También un tema más allá de `TEMA_TOTAL`, igual que
;   hace `op_bgm`.
; * **el tema es el que ya está sonando**. `Game_System::BgmPlay` con el mismo
;   nombre no lo reinicia: pasar de un mapa de los Rat Tracks al otro no
;   vuelve `KSSMKEND` al principio. Con una salvedad, que es la suya también:
;   si se estaba apagando por un `FadeOutBGM` —su `music_stopping`— sí
;   arranca de cero.
;
; "Está sonando" no es sólo `music_apagada` en cero: con pista de MSU-1 el
; SPC700 está callado a propósito y `music_apagada` vale 1. Por eso se mira
; `MSU_SUENA` antes, que es lo mismo que hace `op_fade_bgm`.
;
; Si hay que cambiar, se calla acá, con la pantalla ya negra: el MSU-1 se para
; y el SPC700 suelta las voces, como en `batalla_bgm`.
.proc mapa_tema_callar
.a8
.i16
    ldx fundido_mapa
    lda f:mapa_tema, x
    cmp #TEMA_TOTAL
    bcs nada                    ; $FF, o uno que el cartucho no lleva
    pha
    lda bgm_fundido
    bne cambia                  ; se estaba apagando: vuelve a empezar
    lda f:MSU_SUENA
    bne suena
    lda music_apagada
    bne cambia
suena:
    lda tema_actual + 1
    bne cambia
    pla
    cmp tema_actual
    bne cambia_ya
nada:
    lda #$FF
    rts
cambia:
    pla
cambia_ya:
    pha
    jsr msu_parar
    lda #$FF
    jsr batalla_bgm             ; callar: las voces sueltan
    pla
    rts
.endproc

; Lo que el fundido tiene que hacer en su primer cuadro negro: cargar el mapa,
; o mover al héroe si el salto era al mismo. Se hace una vez y se apaga.
;
; La pantalla se pone en blanking forzado a mano en vez de esperar al vblank:
; `cargar_mapa` escribe VRAM y CGRAM por DMA y con el PPU dibujando esas
; escrituras se pierden. No se ve, porque el brillo ya viene en cero.
.proc cargar_lo_pedido
.a8
.i16
    lda fundido_que
    beq listo
    pha
    lda #$80
    sta INIDISP
    stz brillo                  ; y que el vblank que viene lo deje en negro
    pla
    cmp #FUNDIDO_MISMO
    bne carga
    jsr mover_heroe_a
    bra hecho
carga:
    ; El tema del mapa nuevo se decide **antes** de cargarlo, porque si cambia
    ; hay que callar el que suena antes de que `paquete_cargar` arme el
    ; paquete: ése deja quietas las muestras del tema que dice estar sonando,
    ; y el que se va a prender las necesita en su lugar. Ver `mapa_tema_callar`.
    pha
    jsr mapa_tema_callar
    sta f:TEMA_DEL_MAPA
    pla
    cmp #FUNDIDO_PUERTA
    bne salto
    rep #$20
.a16
    lda fundido_mapa            ; el índice va en dieciséis bits
    jsr cargar_mapa             ; el del arnés: reinicia el tope de saltos
    sep #$20
.a8
    ; El héroe aparece quieto en la celda de entrada. Esto no le hace falta a
    ; ningún salto del juego —`advance_step` sólo dispara un teletransporte con
    ; el paso ya terminado, y `move_hero` recalcula `moving` en el primer cuadro
    ; vivo— pero acá la partida llega desde afuera, con la RAM en cualquier
    ; estado, y arrancar a mitad de un paso no es lo que la prueba pidió.
    stz step_left
    stz moving
    bra prender
salto:
    rep #$20
.a16
    lda fundido_mapa            ; el índice va en dieciséis bits
    jsr cargar_mapa_sin_eventos
    sep #$20
.a8
    ; Y los eventos automáticos del mapa nuevo, a la cola. La página que pidió
    ; el salto sigue corriendo —su código está en la ROM y el cursor quedó
    ; guardado— así que éstos arrancan recién cuando ella termine, que es el
    ; orden de RM2k: `Game_Interpreter_Map::OnMapChange` no toca la pila del
    ; intérprete, sólo los ids de evento.
    ;
    ; Antes no se marcaban nunca. El comentario decía que se encolaban "cuando
    ; ésta termine" y no lo hacía nadie: después de un teletransporte, los
    ; eventos del mapa de destino no corrían jamás. Nada lo veía porque la única
    ; prueba que teletransportaba miraba el tinte, que lo pone el mapa de origen.
    ; Hoy lo hace `cargar_mapa_sin_eventos`, adentro de su refresco.
prender:
    ; Y el tema del mapa, con el paquete ya subido: sus muestras vinieron en
    ; él. Va antes de que corra ninguna página del mapa nuevo, así que un
    ; `PlayBGM` de un evento automático le gana, que es el orden de RM2k:
    ; `Game_Map::PlayBgm` corre al armar el mapa, antes que sus eventos.
    lda f:TEMA_DEL_MAPA
    cmp #$FF
    beq hecho
    jsr music_start
hecho:
    stz fundido_que
    ; Y OAM, que si no se queda con la del mapa que se dejó. El lazo no la
    ; rearma mientras el fundido dura —`build_oam` es de las cosas que se
    ; saltea— así que la rampa de vuelta iría dibujando el mapa nuevo con los
    ; sprites viejos.
    jsr build_oam
listo:
    rts
.endproc

; Mueve al héroe a (entrada_x, entrada_y) sin tocar el mapa. Es lo que hace un
; teletransporte que no cambia de mapa: la tabla de eventos, sus posiciones, las
; rutas que estén corriendo y las páginas encoladas siguen como estaban.
.proc mover_heroe_a
.a8
.i16
    rep #$20
.a16
    lda entrada_x
    sta tile_x
    asl a
    asl a
    asl a
    asl a                       ; la celda mide 16 pixeles
    sta hero_x
    lda entrada_y
    sta tile_y
    asl a
    asl a
    asl a
    asl a
    sta hero_y
    lda #$FFFF
    sta entrada_x               ; consumida
    sep #$20
.a8
    stz step_left               ; un paso a mitad de camino se corta
    stz moving
    jsr menu_olvidar            ; y un pedido de menú también: `MoveTo`
    jsl f:encuentro_mover       ; y lo caminado, que es lo otro que borra
    jsr follow_camera
    jsr fill_window             ; la cámara saltó: el tilemap se llena de nuevo
    jsr init_hero_ptr
    rts
.endproc

