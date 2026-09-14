"""Ensamblador mínimo para el SPC700, el procesador de audio de la Super Nintendo.

No hay ensamblador de SPC700 empaquetado en Debian y no vamos a compilar uno de
fuentes sin revisar, así que va este. Cubre sólo las instrucciones que necesita
el driver, que son pocas: el 65816 le manda pares (registro, valor) del DSP por
los puertos y el SPC700 los copia. Toda la música la maneja el 65816.

Los opcodes salen del manual del SPC700. Cada uno está anotado con su
codificación para que se pueda verificar sin ejecutar nada.

El mapa de memoria que importa:
  $F1        control: reinicia los puertos
  $F2/$F3    dirección y dato del DSP
  $F4-$F7    los cuatro puertos hacia el 65816 (allá son $2140-$2143)
"""

# (mnemónico, operandos) -> (opcode, cuántos bytes de operando)
#
# Los operandos son: dp = página cero, imm = inmediato, rel = salto relativo,
# abs = una dirección de dieciséis bits, que se emite en little endian.
OPCODES = {
    ("mov", "a,dp"):    (0xE4, 1),   # A <- (dp)
    ("mov", "a,imm"):   (0xE8, 1),   # A <- inmediato
    ("mov", "dp,a"):    (0xC4, 1),   # (dp) <- A
    ("mov", "x,dp"):    (0xF8, 1),   # X <- (dp)
    ("mov", "x,imm"):   (0xCD, 1),   # X <- inmediato
    ("mov", "dp,x"):    (0xD8, 1),   # (dp) <- X
    ("mov", "y,imm"):   (0x8D, 1),   # Y <- inmediato
    ("mov", "[dp]+y,a"): (0xD7, 1),  # (palabra en dp + Y) <- A
    ("incw", "dp"):     (0x3A, 1),   # la palabra en dp, más uno
    ("decw", "dp"):     (0x1A, 1),   # menos uno; Z si llegó a cero
    ("dec", "dp"):      (0x8B, 1),   # el byte en dp, menos uno
    ("inc", "y"):       (0xFC, 0),   # Y más uno
    ("cmp", "x,dp"):    (0x3E, 1),   # compara X con (dp)
    ("cmp", "a,imm"):   (0x68, 1),   # compara A con inmediato
    ("beq", "rel"):     (0xF0, 1),   # salta si iguales
    ("bne", "rel"):     (0xD0, 1),   # salta si distintos
    ("bra", "rel"):     (0x2F, 1),   # salto incondicional
    ("jmp", "abs"):     (0x5F, 2),   # salto largo, a cualquier dirección
    ("nop", ""):        (0x00, 0),
}


class Assembler:
    """Ensambla en dos pasadas: la primera resuelve las etiquetas."""

    def __init__(self, origin):
        self.origin = origin
        self.labels = {}

    def assemble(self, source):
        for _ in range(2):
            code = self._pass(source)
        return code

    def _pass(self, source):
        code = bytearray()
        for line in source.splitlines():
            line = line.split(";")[0].strip()
            if not line:
                continue

            if line.endswith(":"):
                self.labels[line[:-1]] = self.origin + len(code)
                continue

            parts = line.split(None, 1)
            mnemonic = parts[0].lower()
            operand = parts[1].replace(" ", "").lower() if len(parts) > 1 else ""
            code += self._encode(mnemonic, operand, self.origin + len(code))
        return bytes(code)

    def _encode(self, mnemonic, operand, address):
        for (name, shape), (opcode, size) in OPCODES.items():
            if name != mnemonic:
                continue
            value = self._match(shape, operand)
            if value is None:
                continue
            if size == 0:
                return bytes([opcode])
            if shape == "abs":
                # La única de dos bytes, y va en little endian como todo lo
                # demás del SPC700.
                return bytes([opcode, value & 0xFF, (value >> 8) & 0xFF])
            if shape == "rel":
                # Los saltos son relativos al final de la instrucción.
                offset = value - (address + 2)
                if not -128 <= offset <= 127:
                    raise ValueError("salto fuera de rango: %s %s"
                                     % (mnemonic, operand))
                return bytes([opcode, offset & 0xFF])
            return bytes([opcode, value & 0xFF])
        raise ValueError("no sé ensamblar: %s %s" % (mnemonic, operand))

    def _match(self, shape, operand):
        """Si el operando encaja con la forma esperada, devuelve su valor."""
        if shape == "":
            return 0 if operand == "" else None

        if shape == "rel":
            return self.labels.get(operand, self.origin)

        if shape == "y":                    # el registro Y
            return 0 if operand == "y" else None
        if shape == "abs":                  # una dirección entera: !$FFC0
            return self._number(operand, "!")
        if shape == "dp":                   # un solo operando de página cero
            return self._number(operand, "$")
        if shape == "[dp]+y,a":             # el indirecto indexado
            if not (operand.startswith("[") and operand.endswith("]+y,a")):
                return None
            return self._number(operand[1:-len("]+y,a")], "$")

        target, _, source = shape.partition(",")
        if source:                          # formas de dos operandos
            left, _, right = operand.partition(",")
            if target in ("a", "x", "y") and left != target:
                return None
            if source in ("a", "x", "y") and right != source:
                return None
            slot = right if target in ("a", "x", "y") else left
            if source == "imm":
                return self._number(slot, "#")
            if source == "dp" or target == "dp":
                return self._number(slot, "$")
            return 0
        return None

    @staticmethod
    def _number(text, prefix):
        """Un operando como $F4 o #$10. None si no tiene el prefijo esperado."""
        if not text.startswith(prefix):
            return None
        text = text[len(prefix):]
        if text.startswith("$"):
            text = text[1:]
        try:
            return int(text, 16)
        except ValueError:
            return None


def assemble(source, origin):
    return Assembler(origin).assemble(source)
