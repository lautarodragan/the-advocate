"""Los opcodes del bytecode de eventos: su número y su layout.

Generado por protocol/generate.py desde protocol/events.toml.
**No editar a mano**: el cambio se hace allá y se regenera. La prueba
`test_protocolo.py` exige que regenerar no cambie nada.
"""

OP_FIN           = 0x00
OP_SWITCH        = 0x01
OP_TELEPORT      = 0x02
OP_ESPERAR       = 0x03
OP_TINTE         = 0x04
OP_GRUPO         = 0x05
OP_RUTA          = 0x06
OP_MENSAJE       = 0x07
OP_RUTAS         = 0x08
OP_FLASH         = 0x09
OP_TIMER         = 0x0A
OP_BGM           = 0x0B
OP_LUGAR         = 0x0C
OP_TRUEQUE       = 0x0D
OP_SACUDIR       = 0x0E
OP_DESTELLO      = 0x0F
OP_FUNDIR_BGM    = 0x10
OP_PAN           = 0x11
OP_SI            = 0x12
OP_IR            = 0x13
OP_ELEGIR        = 0x14
OP_ORO           = 0x15
OP_GUARDAR       = 0x16
OP_VAR           = 0x17
OP_SI_VAR        = 0x18
OP_ITEM          = 0x19
OP_ACCESO        = 0x1A
OP_TIENDA        = 0x1B
OP_CLIMA         = 0x1C
OP_SONIDO        = 0x1D
OP_ANIMACION     = 0x1E
OP_IMAGEN        = 0x1F
OP_IMAGEN_MOVER  = 0x20
OP_IMAGEN_BORRAR = 0x21
OP_BATALLA       = 0x22
OP_PARAR_RUTAS   = 0x23
OP_SI_ACTOR      = 0x24
OP_ACTOR_GRAF    = 0x25
OP_TECLA         = 0x26
OP_LUGAR_VAR     = 0x27


# Cuántos bytes ocupa cada instrucción de largo fijo, contando el opcode.
# Se deriva de los argumentos declarados, no se escribe.
LARGO_DE_OPCODE = {
    OP_FIN: 1,
    OP_SWITCH: 4,
    OP_TELEPORT: 7,
    OP_ESPERAR: 3,
    OP_TINTE: 5,
    OP_GRUPO: 3,
    OP_MENSAJE: 3,
    OP_RUTAS: 1,
    OP_FLASH: 7,
    OP_TIMER: 5,
    OP_BGM: 2,
    OP_LUGAR: 6,
    OP_TRUEQUE: 3,
    OP_SACUDIR: 5,
    OP_DESTELLO: 6,
    OP_FUNDIR_BGM: 3,
    OP_PAN: 8,
    OP_SI: 7,
    OP_IR: 3,
    OP_ORO: 5,
    OP_GUARDAR: 1,
    OP_VAR: 8,
    OP_SI_VAR: 8,
    OP_ITEM: 4,
    OP_ACCESO: 3,
    OP_CLIMA: 3,
    OP_SONIDO: 3,
    OP_IMAGEN: 5,
    OP_IMAGEN_MOVER: 6,
    OP_IMAGEN_BORRAR: 1,
    OP_BATALLA: 9,
    OP_PARAR_RUTAS: 1,
    OP_SI_ACTOR: 7,
    OP_ACTOR_GRAF: 3,
    OP_TECLA: 3,
    OP_LUGAR_VAR: 4,
}

# Las de largo variable, como (base, dónde está la cuenta, cuánto mide
# cada entrada): el largo es base + cuenta * entrada.
LARGO_VARIABLE = {
    OP_RUTA: (4, 3, 1),
    OP_ELEGIR: (3, 1, 4),
    OP_TIENDA: (4, 3, 2),
    OP_ANIMACION: (4, 3, 8),
}

# Los argumentos de cada uno, en orden, como (nombre, bytes, con signo).
LAYOUT = {
    OP_FIN: (),
    OP_SWITCH: (("id", 2, False), ("value", 1, False)),
    OP_TELEPORT: (("map", 2, False), ("x", 2, False), ("y", 2, False)),
    OP_ESPERAR: (("frames", 2, False),),
    OP_TINTE: (("red", 1, False), ("green", 1, False), ("blue", 1, False), ("saturation", 1, False)),
    OP_GRUPO: (("operation", 1, False), ("actor", 1, False)),
    OP_RUTA: (("target", 1, False), ("frequency", 1, False), ("length", 1, False)),
    OP_MENSAJE: (("offset", 2, False),),
    OP_RUTAS: (),
    OP_FLASH: (("target", 1, False), ("red", 1, False), ("green", 1, False), ("blue", 1, False), ("power", 1, False), ("frames", 1, False)),
    OP_TIMER: (("operation", 1, False), ("seconds", 2, False), ("visible", 1, False)),
    OP_BGM: (("track", 1, False),),
    OP_LUGAR: (("target", 1, False), ("x", 2, False), ("y", 2, False)),
    OP_TRUEQUE: (("first", 1, False), ("second", 1, False)),
    OP_SACUDIR: (("power", 1, False), ("speed", 1, False), ("frames", 2, False)),
    OP_DESTELLO: (("red", 1, False), ("green", 1, False), ("blue", 1, False), ("power", 1, False), ("frames", 1, False)),
    OP_FUNDIR_BGM: (("step", 2, False),),
    OP_PAN: (("operation", 1, False), ("dx", 2, True), ("dy", 2, True), ("step", 1, False), ("wait", 1, False)),
    OP_SI: (("kind", 1, False), ("operand", 2, False), ("polarity", 1, False), ("destination", 2, False)),
    OP_IR: (("destination", 2, False),),
    OP_ELEGIR: (("length", 1, False), ("on_cancel", 1, False)),
    OP_ORO: (("sign", 1, False), ("amount", 3, False)),
    OP_GUARDAR: (),
    OP_VAR: (("slot", 1, False), ("operation", 1, False), ("kind", 1, False), ("a", 2, False), ("b", 2, False)),
    OP_SI_VAR: (("slot", 1, False), ("kind", 1, False), ("comparison", 1, False), ("value", 2, False), ("destination", 2, False)),
    OP_ITEM: (("item", 2, False), ("delta", 1, True)),
    OP_ACCESO: (("bit", 1, False), ("allowed", 1, False)),
    OP_TIENDA: (("kind", 1, False), ("layout", 1, False), ("length", 1, False)),
    OP_CLIMA: (("kind", 1, False), ("power", 1, False)),
    OP_SONIDO: (("index", 2, False),),
    OP_ANIMACION: (("animation", 1, False), ("target", 1, False), ("length", 1, False)),
    OP_IMAGEN: (("red", 1, False), ("green", 1, False), ("blue", 1, False), ("saturation", 1, False)),
    OP_IMAGEN_MOVER: (("red", 1, False), ("green", 1, False), ("blue", 1, False), ("saturation", 1, False), ("frames", 1, False)),
    OP_IMAGEN_BORRAR: (),
    OP_BATALLA: (("troop", 2, False), ("on_win", 2, False), ("on_escape", 2, False), ("on_lose", 2, False)),
    OP_PARAR_RUTAS: (),
    OP_SI_ACTOR: (("subkind", 1, False), ("actor", 1, False), ("data", 2, False), ("destination", 2, False)),
    OP_ACTOR_GRAF: (("actor", 1, False), ("graphic", 1, False)),
    OP_TECLA: (("slot", 1, False), ("flags", 1, False)),
    OP_LUGAR_VAR: (("target", 1, False), ("x_slot", 1, False), ("y_slot", 1, False)),
}


def largo_de_opcode(codigo, i):
    """Cuántos bytes ocupa el opcode que empieza en `codigo[i]`."""
    op = codigo[i]
    variable = LARGO_VARIABLE.get(op)
    if variable is not None:
        base, cuenta, entrada = variable
        return base + entrada * codigo[i + cuenta]
    largo = LARGO_DE_OPCODE.get(op)
    if largo is None:
        raise ValueError(f"opcode desconocido: 0x{op:02X}")
    return largo
