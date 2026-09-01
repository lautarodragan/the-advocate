#!/usr/bin/env python3
"""Ensamblador de 65816 que además arma la ROM, sin enlazador aparte.

Reemplaza a ca65 y ld65 para lo que este proyecto necesita. El motivo no es
técnico sino de superficie: cc65 no está en los repos de ninguna distro que
usemos con paquetes revisados, y clonarlo y compilarlo mete código sin auditar
adentro de la caja donde viven el repo y las credenciales. Doscientas líneas
propias y revisables salen más baratas que esa dependencia.

Es el mismo camino que tools/spc700.py, y por la misma razón. La diferencia es
que este se puede verificar contra el original: tools/w65_check.py ensambla el
mismo fuente con ca65 y compara los 32.768 bytes. Mientras eso dé idéntico, el
ensamblador es correcto para todo lo que el proyecto usa — comprobado, no
prometido.

No pretende ser un ca65 completo. Cubre el subconjunto que aparece en
snes/src/main.s y falla ruidosamente ante cualquier otra cosa, que para una
herramienta interna es la conducta correcta: es preferible un error a una ROM
sutilmente distinta.

Uso:
    python3 tools/w65.py snes/src/main.s -o snes/build/abl.sfc
"""

import argparse
import os
import re
import sys


# --- el mapa de memoria -----------------------------------------------------
# LoROM de 128 KB: cuatro bancos de 32 KB, cada uno mapeado en $8000-$FFFF del
# banco que le toca. La cabecera y los vectores van al final del primero.
#
# Lo cómodo de LoROM es que el archivo es lineal aunque las direcciones no lo
# sean: el byte que sigue a $007FFF en el archivo es $018000. Así que las piezas
# se ubican por desplazamiento dentro del archivo, que es contiguo, y la
# dirección se calcula después. Un bloque de datos grande puede cruzar de banco
# sin que haya que partirlo.
#
# Lo que sí paga el precio es el 65816: un puntero de 24 bits no avanza solo de
# $00FFFF a $018000, hay que ayudarlo. Está en `advance`, en main.s.
BANK_SIZE = 0x8000
ROM_BANKS = 4

AREAS = [
    ("ROM",  0x00000, 0x07FC0, ["CODE"]),
    ("HEAD", 0x07FC0, 0x00020, ["HEADER"]),
    ("VECT", 0x07FE0, 0x00020, ["VECTORS"]),
    ("DATA", 0x08000, 0x18000, ["RODATA"]),
]
# La RAM no sale en el archivo: se ubica por dirección, no por desplazamiento.
RAM_AREAS = [
    ("ZP",  0x0000, 0x0100, ["ZEROPAGE"]),
    ("RAM", 0x0100, 0x1F00, ["BSS"]),
]

SEGMENTS = ([n for _, _, _, names in AREAS for n in names]
            + [n for _, _, _, names in RAM_AREAS for n in names])
ZP_SEGMENT = "ZEROPAGE"


def lorom_address(offset):
    """La dirección que el 65816 ve para un byte del archivo."""
    return ((offset // BANK_SIZE) << 16) | 0x8000 | (offset % BANK_SIZE)


# --- los opcodes ------------------------------------------------------------
# Un mnemónico por línea, con el byte que le toca a cada modo de
# direccionamiento. Los modos son:
#
#   imp   implícito, sin operando          rts
#   acc   sobre el acumulador              inc a
#   imm   inmediato, 1 o 2 bytes según     lda #$8F
#         el ancho vigente de A o de X/Y
#   dp    página directa, 1 byte           lda $12
#   abs   absoluto, 2 bytes                lda $2140
#   dpil  indirecto largo por página       lda [$12]
#         directa, 1 byte
#   dpi   indirecto por página directa     lda ($12)
#   rel   relativo al PC, 1 byte con signo bne etiqueta

OPCODES = {
    "lda": {"imm": 0xA9, "dp": 0xA5, "abs": 0xAD, "dpil": 0xA7, "dpi": 0xB2},
    "sta": {"dp": 0x85, "abs": 0x8D, "dpil": 0x87, "dpi": 0x92},
    "ldx": {"imm": 0xA2, "dp": 0xA6, "abs": 0xAE},
    "stx": {"dp": 0x86, "abs": 0x8E},
    "ldy": {"imm": 0xA0, "dp": 0xA4, "abs": 0xAC},
    "sty": {"dp": 0x84, "abs": 0x8C},
    "cmp": {"imm": 0xC9, "dp": 0xC5, "abs": 0xCD},
    "cpx": {"imm": 0xE0, "dp": 0xE4, "abs": 0xEC},
    "cpy": {"imm": 0xC0, "dp": 0xC4, "abs": 0xCC},
    "inc": {"acc": 0x1A, "dp": 0xE6, "abs": 0xEE},
    "dec": {"acc": 0x3A, "dp": 0xC6, "abs": 0xCE},
    "stz": {"dp": 0x64, "abs": 0x9C},
    "and": {"imm": 0x29, "dp": 0x25, "abs": 0x2D},
    "ora": {"imm": 0x09, "dp": 0x05, "abs": 0x0D},
    "eor": {"imm": 0x49, "dp": 0x45, "abs": 0x4D},
    "adc": {"imm": 0x69, "dp": 0x65, "abs": 0x6D},
    "sbc": {"imm": 0xE9, "dp": 0xE5, "abs": 0xED},
    "bit": {"imm": 0x89, "dp": 0x24, "abs": 0x2C},
    "asl": {"acc": 0x0A, "dp": 0x06, "abs": 0x0E},
    "lsr": {"acc": 0x4A, "dp": 0x46, "abs": 0x4E},
    "rol": {"acc": 0x2A, "dp": 0x26, "abs": 0x2E},
    "ror": {"acc": 0x6A, "dp": 0x66, "abs": 0x6E},
    "jsr": {"abs": 0x20},
    "jmp": {"abs": 0x4C},
    # rep y sep llevan siempre un inmediato de un byte, sea cual sea el ancho
    # vigente: su operando son los bits del registro de estado, no un dato.
    "rep": {"imm8": 0xC2},
    "sep": {"imm8": 0xE2},
}

IMPLIED = {
    "sei": 0x78, "cli": 0x58, "clc": 0x18, "sec": 0x38, "cld": 0xD8,
    "xce": 0xFB, "xba": 0xEB, "nop": 0xEA,
    "txs": 0x9A, "tsx": 0xBA, "txa": 0x8A, "tax": 0xAA,
    "tay": 0xA8, "tya": 0x98, "txy": 0x9B, "tyx": 0xBB,
    "inx": 0xE8, "iny": 0xC8, "dex": 0xCA, "dey": 0x88,
    "pha": 0x48, "pla": 0x68, "php": 0x08, "plp": 0x28,
    "phx": 0xDA, "plx": 0xFA, "phy": 0x5A, "ply": 0x7A,
    "phb": 0x8B, "plb": 0xAB, "phd": 0x0B, "pld": 0x2B, "phk": 0x4B,
    "rts": 0x60, "rtl": 0x6B, "rti": 0x40,
}

BRANCHES = {
    "bpl": 0x10, "bmi": 0x30, "bvc": 0x50, "bvs": 0x70,
    "bcc": 0x90, "bcs": 0xB0, "bne": 0xD0, "beq": 0xF0, "bra": 0x80,
}

# Cuáles miran el ancho de A y cuáles el de X/Y para decidir si el inmediato
# ocupa uno o dos bytes.
INDEX_WIDTH = {"ldx", "ldy", "cpx", "cpy"}


class Error(Exception):
    pass


# --- expresiones ------------------------------------------------------------

TOKEN = re.compile(r"""
    \s*(?:
      (?P<hex>\$[0-9A-Fa-f]+)
    | (?P<bin>%[01]+)
    | (?P<dec>\d+)
    | (?P<func>\.[A-Za-z]+)
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<op>[-+*/()<>^~&|])
    )""", re.VERBOSE)


def tokenize(text):
    tokens, pos = [], 0
    while pos < len(text):
        match = TOKEN.match(text, pos)
        if not match:
            if text[pos:].strip():
                raise Error("no entiendo la expresión %r" % text)
            break
        pos = match.end()
        kind = match.lastgroup
        tokens.append((kind, match.group(kind)))
    return tokens


class Expression:
    """Una expresión sin evaluar, para poder resolverla cuando haya símbolos.

    Guarda los tokens y el texto original; el texto sólo se usa en los mensajes
    de error, que sin él serían imposibles de ubicar.
    """

    def __init__(self, text):
        self.text = text.strip()
        self.tokens = tokenize(self.text)

    def base_name(self):
        """El primer símbolo que aparece, que es el que define si es página
        directa. En `source + 2` el que manda es `source`."""
        for kind, value in self.tokens:
            if kind == "name":
                return value
        return None

    def value(self, symbols):
        result, pos = self._sum(symbols, 0)
        if pos != len(self.tokens):
            raise Error("sobra algo en la expresión %r" % self.text)
        return result

    def _sum(self, symbols, pos):
        value, pos = self._term(symbols, pos)
        while pos < len(self.tokens) and self.tokens[pos][1] in "+-":
            operator = self.tokens[pos][1]
            right, pos = self._term(symbols, pos + 1)
            value = value + right if operator == "+" else value - right
        return value, pos

    def _term(self, symbols, pos):
        if pos >= len(self.tokens):
            raise Error("expresión incompleta: %r" % self.text)
        kind, text = self.tokens[pos]

        if kind == "hex":
            return int(text[1:], 16), pos + 1
        if kind == "bin":
            return int(text[1:], 2), pos + 1
        if kind == "dec":
            return int(text), pos + 1
        if kind == "name":
            if text not in symbols:
                raise Error("símbolo desconocido: %s" % text)
            return symbols[text], pos + 1

        if kind == "func":
            name = text.lower()
            if self.tokens[pos + 1][1] != "(":
                raise Error("%s necesita paréntesis" % text)
            inner, pos = self._sum(symbols, pos + 2)
            if self.tokens[pos][1] != ")":
                raise Error("falta cerrar el paréntesis en %r" % self.text)
            pos += 1
            if name == ".loword":
                return inner & 0xFFFF, pos
            if name == ".hiword":
                return (inner >> 16) & 0xFFFF, pos
            if name == ".bankbyte":
                return (inner >> 16) & 0xFF, pos
            if name == ".lobyte":
                return inner & 0xFF, pos
            if name == ".hibyte":
                return (inner >> 8) & 0xFF, pos
            raise Error("no conozco la función %s" % text)

        if text == "(":
            inner, pos = self._sum(symbols, pos + 1)
            if self.tokens[pos][1] != ")":
                raise Error("falta cerrar el paréntesis en %r" % self.text)
            return inner, pos + 1
        if text in "<>^":
            # Los tres prefijos de ca65: byte bajo, byte alto y banco.
            inner, pos = self._term(symbols, pos + 1)
            shift = {"<": 0, ">": 8, "^": 16}[text]
            return (inner >> shift) & 0xFF, pos
        if text == "-":
            inner, pos = self._term(symbols, pos + 1)
            return -inner, pos

        raise Error("no esperaba %r en %r" % (text, self.text))


# --- las piezas que se van acumulando ---------------------------------------

class Data:
    """Bytes literales, o expresiones de uno o dos bytes ya ubicadas."""

    def __init__(self, parts):
        self.parts = parts      # cada una: bytes, o (Expression, ancho)
        self.size = sum(len(p) if isinstance(p, bytes) else p[1]
                        for p in parts)

    def emit(self, symbols, address):
        out = bytearray()
        for part in self.parts:
            if isinstance(part, bytes):
                out += part
            else:
                expression, width = part
                out += (expression.value(symbols) & ((1 << 8 * width) - 1)
                        ).to_bytes(width, "little")
        return bytes(out)


class Instruction:
    def __init__(self, opcode, expression, width, relative=False):
        self.opcode = opcode
        self.expression = expression
        self.width = width
        self.relative = relative
        self.size = 1 + width

    def emit(self, symbols, address):
        if self.width == 0:
            return bytes([self.opcode])

        value = self.expression.value(symbols)
        if self.relative:
            # El salto se cuenta desde el byte siguiente a la instrucción.
            value -= address + self.size
            if not -128 <= value <= 127:
                raise Error("salto demasiado lejos: %d bytes" % value)
            value &= 0xFF

        return bytes([self.opcode]) + (value & ((1 << 8 * self.width) - 1)
                                       ).to_bytes(self.width, "little")


class Reserve:
    """Espacio reservado en RAM: ocupa lugar pero no se escribe a la ROM."""

    def __init__(self, size):
        self.size = size

    def emit(self, symbols, address):
        return b"\x00" * self.size


# --- el ensamblador ---------------------------------------------------------

OPERAND = re.compile(r"^(?P<mnemonic>[A-Za-z]+)(?:\s+(?P<operand>.*))?$")


class Assembler:

    def __init__(self, checksum=True):
        self.checksum = checksum
        self.items = {name: [] for name in SEGMENTS}
        self.segment = "CODE"
        self.symbols = {}
        self.pending = []       # (segmento, índice del item, nombre) de etiquetas
        self.zeropage = set()   # nombres que viven en la página directa
        self.scope = ""         # el .proc en curso, para las etiquetas locales
        self.anonymous = []     # (segmento, índice) de cada `:`
        self.anon_refs = []     # referencias `:+` / `:-` a resolver
        self.a16 = False        # ancho vigente del acumulador
        self.i16 = False        # ancho vigente de X e Y

    # --- pasada 1: leer el fuente y ubicar cada pieza ---

    def assemble(self, path):
        self.read(path)
        self.place()
        return self.emit()

    def read(self, path):
        directory = os.path.dirname(os.path.abspath(path))
        for raw in open(path, encoding="utf-8"):
            line = raw.split(";")[0].strip()
            if not line:
                continue
            try:
                self.line(line, directory)
            except Error as error:
                raise Error("%s: %s\n  en: %s" % (path, error, line.strip()))

    def line(self, line, directory):
        # Etiquetas: pueden venir solas o con una instrucción atrás.
        while True:
            match = re.match(r"^([A-Za-z_@][A-Za-z0-9_]*):\s*(.*)$", line)
            if match:
                self.label(match.group(1))
                line = match.group(2).strip()
                continue
            if line.startswith(":"):
                self.anonymous.append((self.segment, len(self.items[self.segment])))
                line = line[1:].strip()
                continue
            break
        if not line:
            return

        if line.startswith("."):
            self.directive(line, directory)
            return

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", line)
        if match:
            self.symbols[match.group(1)] = Expression(match.group(2)).value(
                self.symbols)
            return

        self.instruction(line)

    def label(self, name):
        full = self.scope + name if self.scope else name
        self.pending.append((self.segment, len(self.items[self.segment]), full))
        if self.segment == ZP_SEGMENT:
            self.zeropage.add(full)

    def directive(self, line, directory):
        parts = line.split(None, 1)
        name = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if name in (".p816", ".smart", ".endproc", ".setcpu", ".feature"):
            if name == ".endproc":
                self.scope = ""
            return
        if name == ".a8":
            self.a16 = False
            return
        if name == ".a16":
            self.a16 = True
            return
        if name == ".i8":
            self.i16 = False
            return
        if name == ".i16":
            self.i16 = True
            return
        if name == ".segment":
            segment = rest.strip('"')
            if segment not in self.items:
                raise Error("segmento desconocido: %s" % segment)
            self.segment = segment
            return
        if name == ".proc":
            self.label(rest)
            self.scope = rest + "::"
            return
        if name == ".include":
            self.read(os.path.join(directory, rest.strip('"')))
            return
        if name == ".res":
            self.items[self.segment].append(
                Reserve(Expression(rest).value(self.symbols)))
            return
        if name in (".byte", ".word", ".addr", ".dword"):
            width = {".byte": 1, ".word": 2, ".addr": 2, ".dword": 4}[name]
            self.items[self.segment].append(Data(self.data(rest, width)))
            return
        raise Error("no conozco la directiva %s" % name)

    def data(self, rest, width):
        parts = []
        for piece in split_commas(rest):
            piece = piece.strip()
            if piece.startswith('"'):
                parts.append(piece[1:-1].encode("latin-1"))
            else:
                parts.append((Expression(piece), width))
        return parts

    def instruction(self, line):
        match = OPERAND.match(line)
        if not match:
            raise Error("no entiendo la instrucción")
        mnemonic = match.group("mnemonic").lower()
        operand = (match.group("operand") or "").strip()

        if mnemonic in IMPLIED:
            if operand:
                raise Error("%s no lleva operando" % mnemonic)
            self.add(Instruction(IMPLIED[mnemonic], None, 0))
            return

        if mnemonic in BRANCHES:
            self.add(Instruction(BRANCHES[mnemonic], self.target(operand), 1,
                                 relative=True))
            return

        modes = OPCODES.get(mnemonic)
        if modes is None:
            raise Error("no conozco la instrucción %s" % mnemonic)
        mode, expression = self.decode(mnemonic, operand, modes)
        if mode not in modes:
            raise Error("%s no acepta el modo %s" % (mnemonic, mode))
        width = {"imp": 0, "acc": 0, "dp": 1, "dpil": 1, "dpi": 1,
                 "imm8": 1, "abs": 2}.get(mode)
        if mode == "imm":
            wide = self.i16 if mnemonic in INDEX_WIDTH else self.a16
            width = 2 if wide else 1
        self.add(Instruction(modes[mode], expression, width))

    def decode(self, mnemonic, operand, modes):
        """Qué modo de direccionamiento pide este operando."""
        if not operand or operand.lower() == "a":
            return "acc", None
        if operand.startswith("#"):
            return ("imm8" if "imm8" in modes else "imm",
                    Expression(operand[1:]))
        if operand.startswith("[") and operand.endswith("]"):
            return "dpil", self.target(operand[1:-1])
        if operand.startswith("(") and operand.endswith(")"):
            return "dpi", self.target(operand[1:-1])

        expression = self.target(operand)
        # Página directa en dos casos: el símbolo vive en el segmento ZEROPAGE,
        # o la expresión ya se puede calcular y entra en un byte. Es la regla de
        # ca65. Una etiqueta todavía sin definir no se puede juzgar, así que va
        # como absoluta, que es lo que hace ca65 con una referencia hacia
        # adelante.
        base = expression.base_name()
        if base is not None and base in self.zeropage:
            direct = True
        else:
            try:
                direct = expression.value(self.symbols) < 0x100
            except Error:
                direct = False
        return ("dp" if direct and "dp" in modes else "abs"), expression

    def target(self, text):
        """Una expresión, resolviendo el alcance de las etiquetas locales."""
        text = text.strip()
        if re.fullmatch(r":[+-]+", text):
            expression = Expression("0")
            self.anon_refs.append((expression, text, self.segment,
                                   len(self.items[self.segment])))
            return expression
        expression = Expression(text)
        base = expression.base_name()
        if base is not None and self.scope:
            # Dentro de un .proc, una etiqueta puede ser local; se decide en la
            # pasada 2, cuando ya están todas. Acá sólo se anota el alcance.
            expression.scope = self.scope
        return expression

    def resolve(self, name):
        return name

    def add(self, item):
        self.items[self.segment].append(item)

    # --- pasada 2: ubicar y emitir ---

    def place(self):
        """Le da una dirección a cada pieza y con eso a cada etiqueta."""
        self.addresses = {}
        self.offsets = {}

        for _, start, size, names in AREAS:
            offset = start
            for segment in names:
                for index, item in enumerate(self.items[segment]):
                    self.offsets[(segment, index)] = offset
                    self.addresses[(segment, index)] = lorom_address(offset)
                    offset += item.size
                self.offsets[(segment, len(self.items[segment]))] = offset
                self.addresses[(segment, len(self.items[segment]))] = \
                    lorom_address(offset)
            if offset > start + size:
                raise Error("el área no entra: %d bytes en %d"
                            % (offset - start, size))

        for _, start, _, names in RAM_AREAS:
            address = start
            for segment in names:
                for index, item in enumerate(self.items[segment]):
                    self.addresses[(segment, index)] = address
                    address += item.size
                self.addresses[(segment, len(self.items[segment]))] = address

        for segment, index, name in self.pending:
            self.symbols[name] = self.addresses[(segment, index)]

        # Las etiquetas anónimas: `:+` es la siguiente hacia adelante, `:-` la
        # anterior. Se ordenan por posición dentro de su segmento.
        spots = sorted(self.anonymous, key=lambda s: (SEGMENTS.index(s[0]), s[1]))
        for expression, text, segment, index in self.anon_refs:
            forward = text[1] == "+"
            count = len(text) - 1
            candidates = [s for s in spots if s[0] == segment
                          and (s[1] > index if forward else s[1] <= index)]
            if not forward:
                candidates = candidates[::-1]
            if len(candidates) < count:
                raise Error("no encuentro la etiqueta anónima %s" % text)
            spot = candidates[count - 1]
            expression.tokens = [("dec", str(self.addresses[spot]))]

        # Las etiquetas locales de cada .proc ganan sobre las globales.
        for name in list(self.symbols):
            if "::" in name:
                self.symbols.setdefault(name.split("::")[-1], None)

    def lookup(self, expression):
        """Resuelve una expresión respetando el alcance del .proc."""
        scope = getattr(expression, "scope", "")
        if scope:
            local = dict(self.symbols)
            for name, value in self.symbols.items():
                if name.startswith(scope):
                    local[name[len(scope):]] = value
            return expression.value(local)
        return expression.value(self.symbols)

    def emit(self):
        """Los bytes de la ROM, ubicando cada pieza por su desplazamiento."""
        rom = bytearray(BANK_SIZE * ROM_BANKS)
        for _, start, size, names in AREAS:
            offset = start
            for segment in names:
                for index, item in enumerate(self.items[segment]):
                    data = self.emit_item(item, self.addresses[(segment, index)])
                    rom[offset:offset + len(data)] = data
                    offset += item.size
        if self.checksum:
            checksum(rom)
        return bytes(rom)

    def emit_item(self, item, address):
        if isinstance(item, Instruction) and item.expression is not None:
            value = self.lookup(item.expression)
            if item.relative:
                value -= address + item.size
                if not -128 <= value <= 127:
                    raise Error("salto demasiado lejos: %d bytes" % value)
            return bytes([item.opcode]) + (
                value & ((1 << 8 * item.width) - 1)).to_bytes(item.width, "little")

        if isinstance(item, Data):
            out = bytearray()
            for part in item.parts:
                if isinstance(part, bytes):
                    out += part
                else:
                    expression, width = part
                    out += (self.lookup(expression) & ((1 << 8 * width) - 1)
                            ).to_bytes(width, "little")
            return bytes(out)

        return item.emit(self.symbols, address)


CHECKSUM_OFFSET = 0x07FDE        # $FFDE del banco 0
COMPLEMENT_OFFSET = 0x07FDC      # $FFDC


def checksum(rom):
    """Completa el checksum de la cabecera, en el lugar.

    Es la suma de todos los bytes de la ROM módulo 65536, y al lado va su
    complemento. mednafen no lo mira, pero el menú del EverDrive lee la cabecera
    para deducir el mapeo y el tamaño del cartucho, y con basura ahí puede
    adivinar mal. Sale gratis dejarlo bien.

    Los valores del fuente son $FFFF y $0000 a propósito: como el complemento es
    el checksum invertido, los cuatro bytes siempre suman 510 —255+255+0+0 antes,
    y (255-a)+(255-b)+a+b después—, así que la suma no cambia al escribirlos y
    no hace falta iterar.
    """
    before = sum(rom) & 0xFFFF
    rom[CHECKSUM_OFFSET:CHECKSUM_OFFSET + 2] = before.to_bytes(2, "little")
    rom[COMPLEMENT_OFFSET:COMPLEMENT_OFFSET + 2] = (
        before ^ 0xFFFF).to_bytes(2, "little")

    after = sum(rom) & 0xFFFF
    if after != before:
        raise Error("el checksum no cerró: %04X contra %04X" % (after, before))
    return before


def split_commas(text):
    """Parte por comas sin romper las que están adentro de comillas."""
    parts, current, quoted = [], "", False
    for char in text:
        if char == '"':
            quoted = not quoted
        if char == "," and not quoted:
            parts.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current)
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--sin-checksum", action="store_true",
                        help="no completar el checksum de la cabecera, para "
                             "poder comparar contra ca65, que no lo escribe")
    args = parser.parse_args()

    assembler = Assembler(checksum=not args.sin_checksum)
    try:
        rom = assembler.assemble(args.source)
    except Error as error:
        sys.exit("w65: %s" % error)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "wb") as handle:
        handle.write(rom)
    print("%s -> %s (%d bytes)" % (args.source, args.output, len(rom)))


if __name__ == "__main__":
    main()
