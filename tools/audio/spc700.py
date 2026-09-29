"""Minimal assembler for the SPC700, the Super Nintendo's audio processor.

There is no SPC700 assembler packaged in Debian and we are not going to build
one from unreviewed sources, so this one it is. It covers only the
instructions the driver needs, which are few: the 65816 sends it DSP
(register, value) pairs through the ports and the SPC700 copies them. All the
music is handled by the 65816.

The opcodes come from the SPC700 manual. Each one is annotated with its
encoding so it can be checked without running anything.

The memory map that matters:
  $F1        control: resets the ports
  $F2/$F3    DSP address and data
  $F4-$F7    the four ports to the 65816 (there they are $2140-$2143)
"""

# (mnemonic, operands) -> (opcode, how many operand bytes)
#
# The operands are: dp = direct page, imm = immediate, rel = relative branch,
# abs = a sixteen-bit address, emitted in little endian.
OPCODES = {
    ("mov", "a,dp"):    (0xE4, 1),   # A <- (dp)
    ("mov", "a,imm"):   (0xE8, 1),   # A <- immediate
    ("mov", "dp,a"):    (0xC4, 1),   # (dp) <- A
    ("mov", "x,dp"):    (0xF8, 1),   # X <- (dp)
    ("mov", "x,imm"):   (0xCD, 1),   # X <- immediate
    ("mov", "dp,x"):    (0xD8, 1),   # (dp) <- X
    ("mov", "y,imm"):   (0x8D, 1),   # Y <- immediate
    ("mov", "[dp]+y,a"): (0xD7, 1),  # (word at dp + Y) <- A
    ("incw", "dp"):     (0x3A, 1),   # the word at dp, plus one
    ("decw", "dp"):     (0x1A, 1),   # minus one; Z if it reached zero
    ("dec", "dp"):      (0x8B, 1),   # the byte at dp, minus one
    ("inc", "y"):       (0xFC, 0),   # Y plus one
    ("cmp", "x,dp"):    (0x3E, 1),   # compares X with (dp)
    ("cmp", "a,imm"):   (0x68, 1),   # compares A with immediate
    ("beq", "rel"):     (0xF0, 1),   # branches if equal
    ("bne", "rel"):     (0xD0, 1),   # branches if not equal
    ("bra", "rel"):     (0x2F, 1),   # unconditional branch
    ("jmp", "abs"):     (0x5F, 2),   # long jump, to any address
    ("nop", ""):        (0x00, 0),
}


class Assembler:
    """Assembles in two passes: the first resolves the labels."""

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
                # The only two-byte one, and it goes in little endian like
                # everything else on the SPC700.
                return bytes([opcode, value & 0xFF, (value >> 8) & 0xFF])
            if shape == "rel":
                # Branches are relative to the end of the instruction.
                offset = value - (address + 2)
                if not -128 <= offset <= 127:
                    raise ValueError("branch out of range: %s %s"
                                     % (mnemonic, operand))
                return bytes([opcode, offset & 0xFF])
            return bytes([opcode, value & 0xFF])
        raise ValueError("cannot assemble: %s %s" % (mnemonic, operand))

    def _match(self, shape, operand):
        """If the operand matches the expected shape, returns its value."""
        if shape == "":
            return 0 if operand == "" else None

        if shape == "rel":
            return self.labels.get(operand, self.origin)

        if shape == "y":                    # the Y register
            return 0 if operand == "y" else None
        if shape == "abs":                  # a full address: !$FFC0
            return self._number(operand, "!")
        if shape == "dp":                   # a single direct-page operand
            return self._number(operand, "$")
        if shape == "[dp]+y,a":             # indirect indexed
            if not (operand.startswith("[") and operand.endswith("]+y,a")):
                return None
            return self._number(operand[1:-len("]+y,a")], "$")

        target, _, source = shape.partition(",")
        if source:                          # two-operand shapes
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
        """An operand like $F4 or #$10. None if it lacks the expected prefix."""
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
