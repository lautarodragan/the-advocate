.segment "CODE"

; Si la celda de al lado en la dirección que trae A existe, o sea si no se cae
; del mapa. Devuelve A distinto de cero si existe.
;
; Está separado de `puede_celda` por una razón de alcance y no de diseño: junto,
; el `beq` del primer control quedaba a 130 bytes de la salida y el ensamblador
; cortaba. `sep`/`rep` no tocan Z ni C, así que el resultado de la comparación
; de dieciséis bits sobrevive al cambio de ancho.
.proc celda_vecina_existe
.a8
.i16
    cmp #DIR_UP
    bne prueba_abajo
    rep #$20
.a16
    lda celda_y
    sep #$20
.a8
    beq no                      ; ya está en la fila de arriba
    bra si
prueba_abajo:
    cmp #DIR_DOWN
    bne prueba_izquierda
    rep #$20
.a16
    lda celda_y
    inc a
    cmp mapa_alto
    sep #$20
.a8
    bcs no
    bra si
prueba_izquierda:
    cmp #DIR_LEFT
    bne prueba_derecha
    rep #$20
.a16
    lda celda_x
    sep #$20
.a8
    beq no
    bra si
prueba_derecha:
    rep #$20
.a16
    lda celda_x
    inc a
    cmp mapa_ancho
    sep #$20
.a8
    bcs no
si:
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Si desde (celda_x, celda_y) se puede dar un paso en la dirección que trae A.
; Devuelve A distinto de cero si se puede.
;
; Es la misma regla que la del héroe —se consultan las dos caras, la que se deja
; y la que se entra— pero desde una celda cualquiera, y sin mirar quién está
; parado dónde, que es lo que hace también la ruta forzada del héroe.
;
; Un movimiento bloqueado se saltea. En las 26 rutas de eventos que este juego
; compila eso pasa **una sola vez**, en el mapa 117, y por esa sola vez hay que
; modelarlo: sin eso, esa ruta duraría ocho cuadros de más.
.proc puede_celda
.a8
.i16
    sta celda_dir
    stz celda_dir + 1
    jsr celda_vecina_existe
    bne :+
    jmp no                      ; queda lejos para un salto corto
:
    ; Atravesando paredes las dos caras dan que sí, pero la celda tiene que
    ; existir: es el `if (self.GetThrough()) return true;` de
    ; `Game_Map::CheckOrMakeWayEx`, que va después del `IsValid`.
    lda atravesando
    beq con_colision
    lda #1
    rts
con_colision:

    ; La cara que se deja.
    jsr ptr_de_celda
    rep #$20
.a16
    lda celda_x                 ; la celda que se deja, para lo que un evento
    sta pasa_x                  ; de tile le imponga
    lda celda_y
    sta pasa_y
    jsr pass_del_ptr
    jsr pasa_con_evento
    sep #$20
.a8
    ldx celda_dir
    and f:pass_salir, x
    bne :+
    jmp no                      ; queda lejos para un salto corto
:

    ; Y la cara del destino, que es la celda de al lado.
    lda celda_dir
    cmp #DIR_UP
    bne baja
    rep #$20
.a16
    lda tira_paso_col
    jsr ptr_menos
    bra entra
    ; Las tres etiquetas que siguen se alcanzan con el acumulador **en ocho
    ; bits**, aunque lo último que el ensamblador leyó fue un `.a16`: el `bra`
    ; de arriba se saltea el cambio de ancho. Sin este `.a8` el `cmp` se emite
    ; con un inmediato de dos bytes, la CPU lee sólo uno, y el segundo —un
    ; $00— se ejecuta como BRK.
baja:
.a8
    cmp #DIR_DOWN
    bne izquierda
    rep #$20
.a16
    lda tira_paso_col
    jsr ptr_mas
    bra entra
izquierda:
.a8
    cmp #DIR_LEFT
    bne derecha
    rep #$20
.a16
    lda #2
    jsr ptr_menos
    bra entra
derecha:
.a8
    rep #$20
.a16
    lda #2
    jsr ptr_mas
entra:
.a16
    lda celda_x                 ; y la celda a la que se entra
    sta pasa_x
    lda celda_y
    sta pasa_y
    sep #$20
.a8
    ldx celda_dir
    lda f:paso_dx, x
    jsr sumar_a_pasa_x
    lda f:paso_dy, x
    jsr sumar_a_pasa_y
    rep #$20
.a16
    jsr pass_del_ptr
    jsr pasa_con_evento
    sep #$20
.a8
    ldx celda_dir
    and f:pass_entrar, x
    bne :+
    jmp no
:
    ; Y que no haya nadie parado en la celda de al lado. Con `atravesando`
    ; no se llega acá: es el `GetThrough()` de arriba.
    rep #$20
.a16
    lda celda_x
    sta dest_x
    lda celda_y
    sta dest_y
    sep #$20
.a8
    lda f:paso_dx, x
    jsr sumar_a_dest_x
    lda f:paso_dy, x
    jsr sumar_a_dest_y
    jsr celda_bloqueada
    bne no
    lda #1
    rts
no:
    lda #0
    rts
.endproc

; Si desde (celda_x, celda_y) se puede dar el paso diagonal que trae A, 4 a 7.
; Devuelve A distinto de cero si se puede, y deja la celda donde la encontró.
;
; RM2k **no mira la celda diagonal**: es `Game_Character::Move`, que prueba las
; dos eles. Primero la vertical y después la horizontal desde el codo, y si esa
; no sale, la horizontal y después la vertical; alcanza con que una de las dos
; esté libre entera. Por eso no se cruza el vértice de dos paredes en diagonal,
; y sí se pasa si hay por dónde rodear.
;
; Cada pata es una llamada a `puede_celda`, o sea las mismas dos caras y el
; mismo chequeo de quién está parado dónde que un paso derecho.
.proc puede_celda_diag
.a8
.i16
    sec
    sbc #4
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:diag_vert, x
    sta diag_v
    lda f:diag_horiz, x
    sta diag_h
    rep #$20
.a16
    lda celda_x                 ; de dónde sale, para volver entre ele y ele
    sta diag_x
    lda celda_y
    sta diag_y
    sep #$20
.a8

    lda diag_v                  ; la ele vertical: arriba y después al costado
    jsr puede_celda
    beq otra_ele
    lda diag_v
    jsr celda_al_codo
    lda diag_h
    jsr puede_celda
    bne si
otra_ele:
    jsr celda_al_origen         ; la ele horizontal: al costado y después arriba
    lda diag_h
    jsr puede_celda
    beq no
    lda diag_h
    jsr celda_al_codo
    lda diag_v
    jsr puede_celda
    bne si
no:
    jsr celda_al_origen
    lda #0
    rts
si:
    jsr celda_al_origen
    lda #1
    rts
.endproc

; La celda pasa a ser la de origen más el paso de la dirección que trae A: el
; codo de la ele, de donde arranca la segunda pata.
.proc celda_al_codo
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    lda diag_x
    sta celda_x
    lda diag_y
    sta celda_y
    sep #$20
.a8
    lda f:paso_dx, x
    beq sin_x
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc mas_x
    ora #$FF00
mas_x:
    clc
    adc celda_x
    sta celda_x
    sep #$20
.a8
sin_x:
    lda f:paso_dy, x
    beq sin_y
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc mas_y
    ora #$FF00
mas_y:
    clc
    adc celda_y
    sta celda_y
    sep #$20
.a8
sin_y:
    rts
.endproc

; Y la celda vuelve a ser la de origen.
.proc celda_al_origen
.a8
.i16
    rep #$20
.a16
    lda diag_x
    sta celda_x
    lda diag_y
    sta celda_y
    sep #$20
.a8
    rts
.endproc

; Hacia dónde queda mirando el evento de la ranura X después de un paso en la
; diagonal de `ruta_dir`. La pose nueva sale en A.
;
; Es `Game_Character::UpdateFacing`, y la respuesta no es "hacia la diagonal":
; el charset tiene cuatro poses y ninguna apunta a un rincón. Se conserva la
; que ya tenía si es una de las dos componentes del paso, y si no se da vuelta
; 180°.
;
; Lo primero es de dónde sale el giro, y no es sólo leer +8: veinte de las
; veintiséis rutas con diagonales de este juego arrancan **con** la diagonal,
; sin girar antes, así que ahí todavía está RUTA_EV_SIN_MIRAR y la pose de
; verdad es la de su página, que vive en la fila del NPC.
.proc encarar_diagonal
.a8
.i16
    lda ruta_ev + 8, x
    cmp #RUTA_EV_SIN_MIRAR
    bne con_pose
    phx
    lda ruta_ev + 0, x
    jsr npc_de_evento
    plx
    cpy #$FFFF
    beq sin_fila
    lda npc_buf + 10, y
    bra con_pose
sin_fila:
    lda #DIR_DOWN               ; sin gráfico: no se le ve la pose a nadie
con_pose:
    sta diag_mira
    lda ruta_dir
    sec
    sbc #4
    phx
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:diag_vert, x
    sta diag_v
    lda f:diag_horiz, x
    plx
    cmp diag_mira
    beq queda
    lda diag_v
    cmp diag_mira
    beq queda
    lda diag_mira               ; ninguna de las dos: 180°
    clc
    adc #2
    and #$03
    rts
queda:
    lda diag_mira
    rts
.endproc

; Le suman a dest_x / dest_y el byte con signo que trae A.
.proc sumar_a_dest_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positivo
    ora #$FF00
positivo:
    clc
    adc dest_x
    sta dest_x
    sep #$20
.a8
    rts
.endproc

.proc sumar_a_dest_y
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positivo
    ora #$FF00
positivo:
    clc
    adc dest_y
    sta dest_y
    sep #$20
.a8
    rts
.endproc

