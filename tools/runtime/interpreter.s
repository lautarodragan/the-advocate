.segment "CODE"

; --- the event interpreter: the loop and the dispatch ------------------------
;
; `run_code` reads one opcode per pass and jumps to its handler. Each
; handler is its own `.proc op_*` and lives in one of the `interpreter_*.s`
; files that main.s includes after this one, one per family. Since the dispatch
; goes through a table, the code does not care where each one is, with one
; condition: it has to stay in `run_code`'s bank, because `jmp (tabla, x)`
; jumps within the program bank. As long as they are all in `CODE` that holds,
; and `test_la_entrada_k_de_la_tabla_salta_al_manejador_del_opcode_k` guards it.
;
; A new opcode touches two places: its number in tools/snes/protocol/events.toml
; —which, when regenerated with `just protocolo`, yields its entry in the
; dispatch table— and its `.proc op_x` in whichever file it belongs to, named
; after the opcode in lowercase. The dispatch is not touched: if the handler is
; missing, the table does not assemble.

; The interpreter loop: one opcode per pass until the DONE.
;
; Y is the bytecode cursor and has to survive the whole loop, so every `jsr`
; that leaves from here saves it before going. The routines it calls use X and
; Y for their own purposes —set_switch indexes the switch bitmap,
; apply_tint walks three palettes— and none of them has any reason to know
; they mean something else here. Without this, the first OP_SWITCH left Y
; holding the switch number divided by eight, and what got read as the next
; opcode was some byte from the middle of the page: the loop stopped there and
; the rest did not run.
.proc run_code
.a8
.i16
    ldy ev_cur                  ; where the previous frame left off
other:
    lda [code_ptr], y
    iny
    ; A number that is not an opcode ends the page, just like OP_DONE and just
    ; like the chain of `cmp` that was the dispatch until 2026-09-25 did, which
    ; ended in the `stz`. It
    ; should never happen —the converter emits the bytecode with the same
    ; numbers—, but it happens as soon as a handler miscounts its operands and
    ; Y ends up in the middle of an instruction; without the cap, that byte
    ; would index past the table and jump anywhere.
    cmp #EVENT_OPCODE_COUNT
    bcs op_done
    ; `tax` with sixteen-bit indexes copies all sixteen bits of C even when A
    ; is eight-bit, so the high byte has to be zero: it holds whatever the
    ; previous handler left. `xba` / `lda #0` / `xba` clears it without
    ; touching the widths, one cycle and three bytes less than `rep` /
    ; `and #$00FF` / `sep`. The `asl` goes first, in eight bits: the cap above
    ; keeps the opcode below 128 and nothing is lost.
    ;
    ; X reaches each handler clobbered —it holds the opcode times two— and so
    ; does A, with B at zero; none of them reads them before writing them. The
    ; chain did not touch them, and that was checked by following branches and
    ; `jsr`s from each handler and from the three callers of `run_code`
    ; on return.
    asl a
    xba
    lda #0
    xba
    tax
    ; `jmp (abs, x)` reads the table from the program bank, which is where it
    ; is: the data bank is the bytecode's (see `op_shop`) and an
    ; `lda tabla, x` would read something else.
    jmp (opcode_handlers, x)
.endproc

.assert EVENT_OPCODE_COUNT <= 128, error, "run_code's asl is done in 8 bits"

; OP_DONE, and any number that is not an opcode: the page ends.
.proc op_done
.a8
.i16
    stz ev_active
    rts
.endproc

; Entry k is the handler for opcode k. tools/snes/protocol/ emits it from
; events.toml, so a new opcode does not touch this: the handler for `OP_X`
; has to be called `op_x`, and if it is missing it does not assemble. It has to
; be in `run_code`'s bank, which is where the `jmp` reads it from, and so
; does each handler: an `.addr` is sixteen bits.
opcode_handlers:
    EVENT_HANDLERS
