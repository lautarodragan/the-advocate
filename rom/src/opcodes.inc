; Los opcodes del bytecode de eventos.
;
; Generado por protocol/generate.py desde protocol/events.toml.
; **No editar a mano.** Hasta el 2026-09-14 estos equates salían
; adentro de mapdata.inc: el compilador le declaraba al intérprete
; los números que el intérprete implementa, y se los mandaba dentro
; de los datos de un mapa.

OP_DONE          = $00
OP_SWITCH        = $01
OP_TELEPORT      = $02
OP_DELAY         = $03
OP_TINT          = $04
OP_PARTY         = $05
OP_ROUTE         = $06
OP_MESSAGE       = $07
OP_WAIT_ROUTES   = $08
OP_FLASH         = $09
OP_TIMER         = $0A
OP_BGM           = $0B
OP_PLACE         = $0C
OP_SWAP          = $0D
OP_SHAKE         = $0E
OP_FLASH_SCREEN  = $0F
OP_FADE_BGM      = $10
OP_PAN           = $11
OP_IF            = $12
OP_GOTO          = $13
OP_CHOICE        = $14
OP_GOLD          = $15
OP_SAVE          = $16
OP_VAR           = $17
OP_IF_VAR        = $18
OP_ITEM          = $19
OP_ACCESS        = $1A
OP_SHOP          = $1B
OP_WEATHER       = $1C
OP_SOUND         = $1D
OP_ANIMATION     = $1E
OP_PICTURE       = $1F
OP_PICTURE_MOVE  = $20
OP_PICTURE_ERASE = $21
OP_BATTLE        = $22
OP_STOP_ROUTES   = $23
OP_IF_ACTOR      = $24
OP_ACTOR_SPRITE  = $25
OP_KEY           = $26
OP_PLACE_VAR     = $27
