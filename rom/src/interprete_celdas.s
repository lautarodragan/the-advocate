.segment "FAR"
.a8
.i16

; --- OP_CELL_TEST: "¿está este personaje en la celda de las variables?" -------
;
; Es el patrón con que las páginas paralelas de RM2k miran si dos personajes se
; tocan: dos `ControlVars` de clase 6 que copian la celda de uno a dos
; variables, y dos `ConditionalBranch` anidados que las comparan con otras dos.
; El conversor funde los cuatro en uno —ver `fundir_celdas` en eventos.py— y
; hace **exactamente lo mismo**: las dos escrituras, con su refresco, y las dos
; comparaciones, cada una con su destino.
;
; Existe por el costo, no por la semántica. Cada vuelta de la carrera (49, 52 y
; 54) tiene cuarenta páginas así corriendo en cada cuadro, y por los cuatro
; opcodes el intérprete se llevaba casi cinco líneas por página: la vuelta
; entera no entraba en un cuadro. Medido en
; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
;
; Vive en el banco 1 porque en el banco 0 no hay lugar: `op_cell_test`, el
; manejador del despacho, es un `jsl` hasta acá. Por eso todo va con
; direccionamiento largo: el banco de datos es el del bytecode.
;
; Entra con Y en el primer operando y vuelve con Y en el opcode que sigue o en
; el destino de la condición que falló.
; Una de las dos escrituras: la variable, como desplazamiento, con la
; coordenada y el refresco en los dos bits de arriba. `temp` es la x del
; personaje y `temp + 2` su y. Entra y sale con A de dieciséis bits.
.macro CELDA_ESCRIBIR
.local refrescar, ya, es_y, poner
    lda [cod_ptr], y
    iny
    iny
    bmi refrescar               ; CELDA_REFRESCO, el bit 15
ya:
    bit #CELDA_Y
    bne es_y
    and #CELDA_VARIABLE
    tax
    lda temp
    bra poner
refrescar:
    pha
    sep #$20
    lda #1
    sta f:refresco
    rep #$20
    pla
    bra ya
es_y:
    and #CELDA_VARIABLE
    tax
    lda temp + 2
poner:
    sta f:FAR_LARGO + FAR_VARIABLES, x
.endmacro

; Una de las dos comparaciones: dos variables, como desplazamientos, y el
; destino si no son iguales. Si falla, deja Y en el destino y salta a `fin`.
.macro CELDA_PROBAR fin
.local falla
    lda [cod_ptr], y            ; la de la izquierda
    tax
    lda f:FAR_LARGO + FAR_VARIABLES, x
    sta temp                    ; la celda del personaje ya no hace falta
    iny
    iny
    lda [cod_ptr], y            ; y la de la derecha
    tax
    lda f:FAR_LARGO + FAR_VARIABLES, x
    cmp temp
    bne falla
    iny                         ; se cumple: saltea la derecha y el destino
    iny
    iny
    iny
    bra :+
falla:
    iny
    iny
    lda [cod_ptr], y            ; el destino, absoluto adentro de la página
    tay
    bra fin
:
.endmacro

; Lo que queda de una escritura sin los dos bits de arriba: el desplazamiento
; de la variable, que con 256 ranuras llega a 510.
CELDA_VARIABLE = $01FF
.assert CELDA_Y = $4000 && CELDA_REFRESCO = $8000, error, "celda_probar lee el refresco con el bit N y la coordenada con el 14"

.proc celda_probar
.a8
.i16
    jsr celda_probar_cerca
    rtl
.endproc

; Lo mismo, para quien está en el banco 1: vuelve con `rts`.
.proc celda_probar_cerca
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; el blanco: 0 el héroe, o el evento más uno
    iny
    and #$00FF
    asl a
    asl a                       ; por EV_STRIDE
    tax
    beq heroe
    ; La celda viva, igual que la clase 6 de `op_var`.
    lda f:ev_pos_buf - EV_STRIDE + 0, x
    sta temp
    lda f:ev_pos_buf - EV_STRIDE + 2, x
    sta temp + 2
    bra escribir
heroe:
    lda tile_x
    sta temp
    lda tile_y
    sta temp + 2
escribir:
    ; Todo en línea y sin `jsr`: corre cuarenta veces por cuadro.
    CELDA_ESCRIBIR
    CELDA_ESCRIBIR
    CELDA_PROBAR listo
    CELDA_PROBAR listo
listo:
    sep #$20
.a8
    rts
.endproc

; --- los paralelos que no pasan de su `OP_CELL_TEST` -------------------------
;
; `paralelos_tick` corre la lista de paralelos de a uno, y cada uno paga
; buscar su estado, guardarlo y volver: casi una línea por página. Pero la
; mayoría de los de la carrera —cuarenta por vuelta— empiezan con
; `OP_CELL_TEST`, no están a mitad de nada, fallan la condición y terminan
; ahí. Ésos se corren acá de corrido, desde `par_i`, hasta el primero que no
; sea así; lo que hace cada uno es exactamente el atajo de `un_paralelo`: su
; condición, y como lo que sigue es el `OP_DONE`, nada más.
;
; Para, sin haber tocado nada de ése, en el primero que:
;   * no empiece con `OP_CELL_TEST`;
;   * tenga el estado de otra página, una espera o la página a medio correr;
;   * ande —tenga ranura de ruta—: su paso lo da `un_paralelo`;
; y antes de empezar si hay un mensaje o una elección en pantalla, porque
; entonces importa de quién es (ver `un_paralelo`). Vuelve con el acarreo en
; 0 y `par_i` en ése, o en `par_n` si llegó al final.
;
; Si la condición de uno se cumple —o lo que sigue no es el `OP_DONE`— ya
; corrió su primera instrucción, con lo que escribe: vuelve con el acarreo en
; 1, Y en la siguiente y `cod_ptr`, `pag_ofs`, `par_dir` y `par_ev` puestos,
; para que `un_paralelo_seguir` siga con su intérprete.
.proc paralelos_celda
.a8
.i16
    lda f:msg_abierto
    ora f:msg_estado
    ora eleg_activo
    bne no
otro:
    lda par_i
    cmp par_n
    bcs no
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a                       ; por PAR_LISTA_BYTES
    tax
    lda f:FAR_LARGO + FAR_PAR_LISTA + 1, x
    sta cod_ptr
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_PAR_LISTA + 3, x
    sta cod_ptr + 2
    lda [cod_ptr]               ; el primer opcode
    cmp #OP_CELL_TEST
    bne no
    rep #$20
.a16
    lda f:FAR_LARGO + FAR_PAR_LISTA + 4, x
    sta pag_ofs
    lda f:FAR_LARGO + FAR_PAR_LISTA + 0, x
    and #$00FF
    asl a
    asl a
    asl a                       ; por PAR_BYTES
    sta par_dir
    tax
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 5, x
    cmp pag_ofs
    bne no16                    ; el estado es de otra página
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 2, x
    bne no16                    ; esperando
    sep #$20
.a8
    lda f:FAR_LARGO + FAR_PAR_ESTADO + 4, x
    bne no                      ; a medio correr
    lda f:FAR_LARGO + FAR_PAR_ESTADO + PAR_RANURA, x
    bne no                      ; anda
    ldy #1
    jsr celda_probar_cerca
    lda [cod_ptr], y
    bne sigue                   ; no terminó en su `OP_DONE`
    inc par_i
    bra otro
sigue:
    rep #$20
.a16
    lda par_dir
    lsr a
    lsr a
    lsr a
    sep #$20
.a8
    sta par_ev
    sec
    rtl
.a16
no16:
    sep #$20
.a8
no:
    clc
    rtl
.endproc

