; Los opcodes del bytecode de eventos.
;
; Generado por protocol/generate.py desde protocol/events.toml.
; **No editar a mano.** Hasta el 2026-09-14 estos equates salían
; adentro de mapdata.inc: el compilador le declaraba al intérprete
; los números que el intérprete implementa, y se los mandaba dentro
; de los datos de un mapa.

OP_FIN           = $00
OP_SWITCH        = $01
OP_TELEPORT      = $02
OP_ESPERAR       = $03
OP_TINTE         = $04
OP_GRUPO         = $05
OP_RUTA          = $06
OP_MENSAJE       = $07
OP_RUTAS         = $08
OP_FLASH         = $09
OP_TIMER         = $0A
OP_BGM           = $0B
OP_LUGAR         = $0C
OP_TRUEQUE       = $0D
OP_SACUDIR       = $0E
OP_DESTELLO      = $0F
OP_FUNDIR_BGM    = $10
OP_PAN           = $11
OP_SI            = $12
OP_IR            = $13
OP_ELEGIR        = $14
OP_ORO           = $15
OP_GUARDAR       = $16
OP_VAR           = $17
OP_SI_VAR        = $18
OP_ITEM          = $19
OP_ACCESO        = $1A
OP_TIENDA        = $1B
OP_CLIMA         = $1C
OP_SONIDO        = $1D
OP_ANIMACION     = $1E
OP_IMAGEN        = $1F
OP_IMAGEN_MOVER  = $20
OP_IMAGEN_BORRAR = $21
OP_BATALLA       = $22
OP_PARAR_RUTAS   = $23
OP_SI_ACTOR      = $24
OP_ACTOR_GRAF    = $25
OP_TECLA         = $26
OP_LUGAR_VAR     = $27
