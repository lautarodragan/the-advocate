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
rom/src/main.s y falla ruidosamente ante cualquier otra cosa, que para una
herramienta interna es la conducta correcta: es preferible un error a una ROM
sutilmente distinta.

Uso:
    python3 tools/w65.py rom/src/main.s -o rom/build/abl.sfc
"""

import argparse
import os
import re
import sys


# --- el mapa de memoria -----------------------------------------------------
# LoROM de 256 KB: ocho bancos de 32 KB, cada uno mapeado en $8000-$FFFF del
# banco que le toca. La cabecera y los vectores van al final del primero.
#
# Eran cuatro bancos hasta que los mapas grandes entraron en escena. No es que
# los datos no entraran: el mapa más pesado son unos 100 KB contando la música.
# Lo que no entra es el relleno. Todo lo que se sube por DMA tiene que caer
# entero dentro de un banco, y con bloques de 25 y 42 KB acomodarlos sin
# desperdicio es imposible. Doscientos cincuenta y seis kilobytes es un tamaño
# de cartucho absolutamente común y saca el problema de encima.
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
ROM_BANKS = 32          # 1 MB desde el 2026-09-07; 512 KB desde el 2026-09-05.
                        # Ver el README, "El cartucho".

# TABLAS va en el banco 0, junto al código, y no es un detalle de acomodo: el
# direccionamiento absoluto indexado —`lda tabla, x`— usa el registro de banco
# de datos, que dejamos en 0. Una tabla en otro banco se leería del lugar
# equivocado sin dar ningún error. Todo lo que la CPU recorra con un índice
# tiene que estar acá.
AREAS = [
    ("ROM",  0x00000, 0x07FC0, ["CODE", "TABLAS"]),
    ("HEAD", 0x07FC0, 0x00020, ["HEADER"]),
    ("VECT", 0x07FE0, 0x00020, ["VECTORS"]),
    ("DATA", 0x08000, BANK_SIZE * ROM_BANKS - 0x08000, ["RODATA"]),
]
# La RAM no sale en el archivo: se ubica por dirección, no por desplazamiento.
# La pila arranca en $1FFF y **crece hacia abajo, contra la BSS**: los dos
# comparten los ocho kilos del banco 0. Así que la BSS no puede llegar hasta el
# final, y esto es cuánto se le deja.
#
# El número está medido, no elegido: con la BSS bien lejos, la pila del caso
# `core-puerta` —el más hondo de la tanda, con el intérprete adentro de una NMI—
# baja 24 bytes. 256 son diez veces eso.
#
# Existe porque faltaba, y costó una tarde: la BSS creció catorce bytes, llegó a
# ocupar los 7936 exactos, y la pila empezó a escribir arriba de `pal_buf`. La
# ROM no fallaba al armarse ni en el arranque; fallaba en el cuadro 406 de una
# escena, con la RAM entera pisada. Es el mismo agujero que ya había tenido el
# ZEROPAGE, y la misma cura.
PILA_RESERVADA = 256

RAM_AREAS = [
    ("ZP",  0x0000, 0x0100, ["ZEROPAGE"]),
    ("RAM", 0x0100, 0x1F00 - PILA_RESERVADA, ["BSS"]),
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
#   long  absoluto largo, 3 bytes          lda f:$7E30A0
#   dpil  indirecto largo por página       lda [$12]
#         directa, 1 byte
#   dpily indirecto largo indexado por Y   lda [$12],y
#   dpi   indirecto por página directa     lda ($12)
#   dpiy  indirecto indexado por Y         lda ($12),y
#   rel   relativo al PC, 1 byte con signo bne etiqueta
#
# El índice va pegado al modo y no aparte porque `[$12]` y `[$12],y` son
# opcodes distintos. El largo indexado es el que permite recorrer una tabla que
# no vive en el banco de datos, que es como se leen las tablas del mapa cuando
# hay más de uno en la ROM.

OPCODES = {
    "lda": {"long": 0xAF, "longx": 0xBF, "dpx": 0xB5, "absx": 0xBD, "absy": 0xB9, "imm": 0xA9, "dp": 0xA5, "abs": 0xAD, "dpil": 0xA7, "dpily": 0xB7, "dpi": 0xB2, "dpiy": 0xB1},
    "sta": {"long": 0x8F, "longx": 0x9F, "dpx": 0x95, "absx": 0x9D, "absy": 0x99, "dp": 0x85, "abs": 0x8D, "dpil": 0x87, "dpily": 0x97, "dpi": 0x92, "dpiy": 0x91},
    "ldx": {"dpy": 0xB6, "absy": 0xBE, "imm": 0xA2, "dp": 0xA6, "abs": 0xAE},
    "stx": {"dpy": 0x96, "dp": 0x86, "abs": 0x8E},
    "ldy": {"dpx": 0xB4, "absx": 0xBC, "imm": 0xA0, "dp": 0xA4, "abs": 0xAC},
    "sty": {"dpx": 0x94, "dp": 0x84, "abs": 0x8C},
    "cmp": {"long": 0xCF, "longx": 0xDF, "dpx": 0xD5, "absx": 0xDD, "absy": 0xD9, "imm": 0xC9, "dp": 0xC5, "abs": 0xCD},
    "cpx": {"imm": 0xE0, "dp": 0xE4, "abs": 0xEC},
    "cpy": {"imm": 0xC0, "dp": 0xC4, "abs": 0xCC},
    "inc": {"dpx": 0xF6, "absx": 0xFE, "acc": 0x1A, "dp": 0xE6, "abs": 0xEE},
    "dec": {"dpx": 0xD6, "absx": 0xDE, "acc": 0x3A, "dp": 0xC6, "abs": 0xCE},
    "stz": {"dpx": 0x74, "absx": 0x9E, "dp": 0x64, "abs": 0x9C},
    "and": {"long": 0x2F, "longx": 0x3F, "dpx": 0x35, "absx": 0x3D, "absy": 0x39, "imm": 0x29, "dp": 0x25, "abs": 0x2D},
    "ora": {"long": 0x0F, "longx": 0x1F, "dpx": 0x15, "absx": 0x1D, "absy": 0x19, "imm": 0x09, "dp": 0x05, "abs": 0x0D},
    "eor": {"long": 0x4F, "longx": 0x5F, "dpx": 0x55, "absx": 0x5D, "absy": 0x59, "imm": 0x49, "dp": 0x45, "abs": 0x4D},
    "adc": {"long": 0x6F, "longx": 0x7F, "dpx": 0x75, "absx": 0x7D, "absy": 0x79, "imm": 0x69, "dp": 0x65, "abs": 0x6D},
    "sbc": {"long": 0xEF, "longx": 0xFF, "dpx": 0xF5, "absx": 0xFD, "absy": 0xF9, "imm": 0xE9, "dp": 0xE5, "abs": 0xED},
    "bit": {"imm": 0x89, "dp": 0x24, "abs": 0x2C},
    "asl": {"dpx": 0x16, "absx": 0x1E, "acc": 0x0A, "dp": 0x06, "abs": 0x0E},
    "lsr": {"dpx": 0x56, "absx": 0x5E, "acc": 0x4A, "dp": 0x46, "abs": 0x4E},
    "rol": {"dpx": 0x36, "absx": 0x3E, "acc": 0x2A, "dp": 0x26, "abs": 0x2E},
    "ror": {"dpx": 0x76, "absx": 0x7E, "acc": 0x6A, "dp": 0x66, "abs": 0x6E},
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
        value, pos = self._product(symbols, pos)
        while pos < len(self.tokens) and self.tokens[pos][1] in "+-|&":
            operator = self.tokens[pos][1]
            right, pos = self._product(symbols, pos + 1)
            if operator == "+":
                value = value + right
            elif operator == "-":
                value = value - right
            elif operator == "|":
                value = value | right
            else:
                value = value & right
        return value, pos

    def _product(self, symbols, pos):
        """Multiplicación y división, que atan más fuerte que la suma."""
        value, pos = self._term(symbols, pos)
        while pos < len(self.tokens) and self.tokens[pos][1] in "*/":
            operator = self.tokens[pos][1]
            right, pos = self._term(symbols, pos + 1)
            if operator == "/" and not right:
                raise Error("división por cero en %r" % self.text)
            value = value * right if operator == "*" else value // right
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
            if symbols[text] is None:
                # El nombre existe pero sin valor, que es como quedan las
                # etiquetas de adentro de un `.proc` cuando se las mira desde
                # afuera: no están en este alcance. Sin este control el valor
                # None seguía viaje y reventaba con un TypeError sin línea ni
                # nombre, que es de las peores maneras de enterarse.
                raise Error("símbolo fuera de alcance: %s. Si es una etiqueta "
                            "de otro .proc, no se puede saltar ahí desde acá"
                            % text)
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
        return self.bytes_con(self.expression.value(symbols), address)

    def bytes_con(self, value, address):
        """Los bytes de la instrucción con el operando ya resuelto.

        Está separado porque el ensamblador resuelve las expresiones él —tiene
        que respetar el alcance de los `.proc`— y antes se armaba los bytes por
        su cuenta. Eran dos copias de la misma cuenta, y se notó de la peor
        manera: un control agregado acá no corría nunca.
        """
        if self.relative:
            # El salto se cuenta desde el byte siguiente a la instrucción.
            value -= address + self.size
            if not -128 <= value <= 127:
                raise Error("salto demasiado lejos: %d bytes" % value)
            value &= 0xFF

        # Un operando que no entra en su modo es un error, no un truncado. El
        # caso que lo motivó: `lda [msg_ptr], y` con `msg_ptr` en BSS y no en la
        # página cero. El modo indirecto largo direcciona sólo la página
        # directa, así que el ensamblador emitía el byte bajo de $0129 y la ROM
        # leía el puntero de $0029, que es otra variable. Todo compilaba y la
        # pantalla decía "algo está mal" sin decir dónde.
        # Los negativos entran: `lda #-WALK_SPEED` es complemento a dos y es
        # una forma normal de escribirlo.
        elif not -(1 << (8 * self.width - 1)) <= value < (1 << 8 * self.width):
            raise Error("el operando no entra en %d byte(s): %d. Si es un modo"
                        " de página directa, la variable tiene que vivir en el"
                        " segmento ZEROPAGE" % (self.width, value))

        return bytes([self.opcode]) + (value & ((1 << 8 * self.width) - 1)
                                       ).to_bytes(self.width, "little")


class Align:
    """Relleno para que lo que sigue arranque en una dirección múltiplo de N.

    Hace falta cuando la ROM va a leer palabras de una tabla con un puntero de
    24 bits: si la tabla arrancara en una dirección impar, una de sus palabras
    caería justo entre el $FFFF de un banco y el $8000 del siguiente, y esa
    lectura traería un byte de cada lado.
    """

    def __init__(self, unit):
        self.unit = unit
        self.size = 0

    def emit(self, symbols, address):
        return b"\x00" * self.size


class BankFit:
    """Relleno para que lo que sigue no cruce de banco.

    Un DMA incrementa su dirección de origen linealmente, y en LoROM el byte que
    sigue a $02FFFF no es la ROM del banco 3 sino la RAM: cualquier bloque que
    se suba por DMA y cruce ese límite se lee basura de la mitad para adelante.

    Lo declara el que emite los datos, porque es el único que sabe cuánto va a
    ocupar el bloque. Cuánto hay que rellenar se resuelve al ubicar, que es
    cuando se sabe dónde cayó.
    """

    def __init__(self, needed):
        self.needed = needed
        self.size = 0

    def emit(self, symbols, address):
        return b"\x00" * self.size


class Reserve:
    """Espacio reservado en RAM: ocupa lugar pero no se escribe a la ROM."""

    def __init__(self, size):
        self.size = size

    def emit(self, symbols, address):
        return b"\x00" * self.size


# --- el ensamblador ---------------------------------------------------------

OPERAND = re.compile(r"^(?P<mnemonic>[A-Za-z]+)(?:\s+(?P<operand>.*))?$")


class Assembler:

    def __init__(self, checksum=True, incluir=()):
        self.checksum = checksum
        self.incluir = [os.path.abspath(d) for d in incluir]
        self.items = {name: [] for name in SEGMENTS}
        self.segment = "CODE"
        self.origen = "?"       # de qué línea salió lo último que se agregó
        self.symbols = {}
        self.pending = []       # (segmento, índice del item, nombre) de etiquetas
        self.definidas = set()  # para que una repetida no pase en silencio
        self.zeropage = set()   # nombres que viven en la página directa
        self.scope = ""         # el .proc en curso, para las etiquetas locales
        self.anonymous = []     # (segmento, índice) de cada `:`
        self.anon_refs = []     # referencias `:+` / `:-` a resolver
        self.a16 = False        # ancho vigente del acumulador
        self.i16 = False        # ancho vigente de X e Y
        # Con qué ancho declarado se definió cada etiqueta, y con cuál llega
        # cada salto. Se comparan al final: ver `revisar_anchos`.
        self.ancho_de_etiqueta = {}
        self.saltos = []
        # Las etiquetas definidas desde el último byte emitido. Un `.a8` que
        # venga pegado detrás de una etiqueta habla de ella, no del código de
        # más arriba: sin esto, `no_arriba:` seguido de `.a8` quedaba anotado
        # con el ancho que había antes y el control se quejaba de lo que estaba
        # bien.
        self.etiquetas_frescas = []

    # --- pasada 1: leer el fuente y ubicar cada pieza ---

    def assemble(self, path):
        self.read(path)
        self.revisar_anchos()
        self.place()
        return self.emit()

    def buscar(self, nombre, directory):
        """Dónde está un `.include`: primero los -I, después el del fuente.

        Los -I van adelante a propósito. Es lo que permite ensamblar con un
        mapdata.inc que no es el del árbol —uno recién generado en el
        directorio de una corrida— sin pisar el que otra tanda esté usando:
        `rom/src/mapdata.inc` es estado global y compartido, y hasta que
        existió esto la única forma de armar otra ROM era sobreescribirlo.
        """
        for base in list(self.incluir) + [directory]:
            candidato = os.path.join(base, nombre)
            if os.path.exists(candidato):
                return candidato
        raise Error("no encuentro %r; busqué en %s"
                    % (nombre, ", ".join(list(self.incluir) + [directory])))

    def read(self, path):
        directory = os.path.dirname(os.path.abspath(path))
        for numero, raw in enumerate(open(path, encoding="utf-8"), 1):
            line = raw.split(";")[0].strip()
            if not line:
                continue
            # De dónde salió cada cosa. No se usa al leer —ahí el error se
            # atrapa acá mismo— sino al emitir, que es una pasada aparte y
            # donde aparecen los errores que dependen de dónde cayó todo: un
            # salto que quedó lejos, una expresión que no entra en su ancho.
            self.origen = "%s:%d: %s" % (path, numero, line)
            try:
                self.line(line, directory)
            except Error as error:
                raise Error("%s\n  en %s" % (error, self.origen))

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
            nombre, valor = match.group(1), Expression(match.group(2)).value(
                self.symbols)
            # Una constante repetida es un error igual que una etiqueta
            # repetida, y por el mismo motivo: ganaba la última en silencio.
            # `main.s` tenía `VENTANA_FILA`, `VENTANA_FILAS` y
            # `VIEW_COLS_TILEMAP` declaradas dos veces, del mismo copiado que
            # había dejado cinco variables duplicadas. Redefinirla con el mismo
            # valor se deja pasar: los `.inc` generados definen constantes que
            # el fuente también puede tener, y ahí no hay ambigüedad.
            if nombre in self.symbols and self.symbols[nombre] != valor:
                raise Error("la constante %r ya valía %s y acá vale %s (%s)"
                            % (nombre, self.symbols[nombre], valor,
                               self.origen))
            self.symbols[nombre] = valor
            return

        self.instruction(line)

    def label(self, name):
        full = self.scope + name if self.scope else name
        # Una etiqueta repetida siempre es un error, y hasta acá pasaba en
        # silencio: las dos quedaban en `pending` y ganaba la última. Así
        # main.s llegó a declarar cinco variables de la ventana dos veces, con
        # diez bytes de página cero muertos que nadie usaba y nada que lo
        # dijera. El nombre lleva el `.proc` adelante, así que dos `loop:` en
        # procedimientos distintos siguen siendo dos etiquetas distintas.
        if full in self.definidas:
            raise Error("la etiqueta %r está definida dos veces (%s)"
                        % (full, self.origen))
        self.definidas.add(full)
        self.ancho_de_etiqueta[full] = (self.a16, self.i16, self.origen)
        self.etiquetas_frescas.append(full)
        self.pending.append((self.segment, len(self.items[self.segment]), full))
        if self.segment == ZP_SEGMENT:
            self.zeropage.add(full)

    def directive(self, line, directory):
        parts = line.split(None, 1)
        name = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if name == ".controlar":
            # Una condición que tiene que valer al ensamblar. Existe para atar
            # una cuenta escrita a mano a la constante de la que depende: la
            # ROM multiplica por doce con dos corrimientos y una suma, y eso
            # estuvo de acuerdo con NPC_STRIDE hasta que la ranura creció y
            # nadie se enteró. Con esto no se puede volver a pasar.
            partes = rest.split(",", 1)
            izq, _, der = partes[0].partition("=")
            if not der:
                raise Error(".controlar quiere `expresión = expresión`")
            a = Expression(izq.strip()).value(self.symbols)
            b = Expression(der.strip()).value(self.symbols)
            if a != b:
                raise Error("%s vale %d y %s vale %d%s"
                            % (izq.strip(), a, der.strip(), b,
                               ": " + partes[1].strip().strip('"')
                               if len(partes) > 1 else ""))
            return
        if name in (".p816", ".smart", ".endproc", ".setcpu", ".feature"):
            if name == ".endproc":
                self.scope = ""
            return
        if name in (".a8", ".a16", ".i8", ".i16"):
            if name == ".a8":
                self.a16 = False
            elif name == ".a16":
                self.a16 = True
            elif name == ".i8":
                self.i16 = False
            else:
                self.i16 = True
            self.reanotar_etiquetas()
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
            self.read(self.buscar(rest.strip('"'), directory))
            return
        if name == ".bloque":
            self.add(BankFit(Expression(rest).value(self.symbols)))
            return
        if name == ".alinear":
            self.add(Align(Expression(rest).value(self.symbols)))
            return
        if name == ".res":
            self.add(Reserve(Expression(rest).value(self.symbols)))
            return
        if name in (".byte", ".word", ".addr", ".dword"):
            width = {".byte": 1, ".word": 2, ".addr": 2, ".dword": 4}[name]
            self.add(Data(self.data(rest, width)))
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
            destino = self.target(operand)
            self.saltos.append((mnemonic, operand.strip(), self.scope,
                                self.a16, self.i16, self.origen))
            self.add(Instruction(BRANCHES[mnemonic], destino, 1,
                                 relative=True))
            return

        modes = OPCODES.get(mnemonic)
        if modes is None:
            raise Error("no conozco la instrucción %s" % mnemonic)
        mode, expression = self.decode(mnemonic, operand, modes)
        if mode not in modes:
            raise Error("%s no acepta el modo %s" % (mnemonic, mode))
        width = {"imp": 0, "acc": 0, "dp": 1, "dpx": 1, "dpy": 1,
                 "dpil": 1, "dpily": 1, "dpi": 1, "dpiy": 1, "imm8": 1,
                 "abs": 2, "absx": 2, "absy": 2,
                 "long": 3, "longx": 3}.get(mode)
        if mode == "imm":
            wide = self.i16 if mnemonic in INDEX_WIDTH else self.a16
            width = 2 if wide else 1
        if width is None:
            raise Error("no sé cuánto ocupa el operando del modo %s" % mode)
        self.add(Instruction(modes[mode], expression, width))

    def revisar_anchos(self):
        """Que cada salto llegue a su etiqueta con el ancho que ésta declara.

        Es el control de la trampa que más cara salió en este archivo, porque no
        la ve nadie: el ancho de `sep`/`rep` lo lleva el ensamblador **en orden
        de lectura**, así que una etiqueta a la que se llega por un `bra` que se
        saltea el cambio de ancho queda declarada con el ancho del camino de
        caída, no con el del salto. El `cmp #2` que sigue se emite entonces con
        un inmediato de dos bytes, la CPU en ocho lee uno solo, y el segundo
        —que suele ser el $00 del byte alto— se ejecuta como BRK.

        No se ve en el diff, no se ve en la comparación pixel a pixel —la ROM se
        va por la ventana y dibuja cualquier cosa— y sólo se encuentra
        bisecando. Acá sale como un error con nombre y línea.

        Sólo se miran los saltos relativos. Un `jsr` no cuenta: ahí el
        procedimiento declara el ancho con el que quiere que lo llamen, que es
        una convención y no un error.
        """
        for mnemonic, destino, scope, a16, i16, origen in self.saltos:
            if not re.fullmatch(r"[A-Za-z_@][A-Za-z0-9_]*", destino):
                continue            # `:+`, una expresión: no es una etiqueta
            nombre = scope + destino if scope + destino in self.ancho_de_etiqueta \
                else destino
            declarado = self.ancho_de_etiqueta.get(nombre)
            if declarado is None:
                continue
            if (a16, i16) != declarado[:2]:
                raise Error(
                    "%s %s salta con el acumulador en %d y los índices en %d, "
                    "y la etiqueta está declarada con %d y %d (%s).\n"
                    "  Si el salto se saltea un sep/rep, a la etiqueta le falta "
                    "un .a8/.a16/.i8/.i16 que diga con qué ancho se llega.\n"
                    "  en %s"
                    % (mnemonic, destino, 16 if a16 else 8, 16 if i16 else 8,
                       16 if declarado[0] else 8, 16 if declarado[1] else 8,
                       declarado[2], origen))

    def decode(self, mnemonic, operand, modes):
        """Qué modo de direccionamiento pide este operando."""
        if not operand or operand.lower() == "a":
            return "acc", None

        # Los modos indexados se reconocen por el sufijo. Van después de mirar
        # el inmediato y los indirectos, que no lo llevan.
        index = ""
        if not operand.startswith("#") and not operand.endswith(("]", ")")):
            match = re.match(r"^(.*?)\s*,\s*([xXyY])$", operand)
            if match:
                operand, index = match.group(1), match.group(2).lower()

        if operand.startswith("#"):
            return ("imm8" if "imm8" in modes else "imm",
                    Expression(operand[1:]))
        # Los indirectos llevan el índice pegado al modo, no aparte: `[dp]` y
        # `[dp],y` son opcodes distintos. Si el índice se descartara acá, un
        # `lda [ptr],y` se ensamblaría como `lda [ptr]` sin decir nada, que es
        # exactamente la clase de error que este ensamblador existe para no
        # tener. Se lo pasa al modo y que falle si no existe.
        if operand.startswith("[") and operand.endswith("]"):
            return "dpil" + index, self.target(operand[1:-1])
        if operand.startswith("(") and operand.endswith(")"):
            return "dpi" + index, self.target(operand[1:-1])

        # El largo, con el prefijo de ca65: `lda f:$7E30A0`. La dirección lleva
        # el banco, así que no depende de B. Existe por la música, que corre
        # adentro de una interrupción y lee el estado de los efectos en la RAM
        # lejana: la ventana de WMADD no se puede usar ahí, porque la
        # interrupción caería en el medio de un recorrido del código principal
        # y le movería el puntero.
        if operand[:2].lower() == "f:":
            return "long" + index, self.target(operand[2:])

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
        mode = "dp" if direct and ("dp" + index) in modes else "abs"
        return mode + index, expression

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

    def reanotar_etiquetas(self):
        """El ancho de las etiquetas que todavía no emitieron nada."""
        for nombre in self.etiquetas_frescas:
            self.ancho_de_etiqueta[nombre] = (
                self.a16, self.i16, self.ancho_de_etiqueta[nombre][2])

    def add(self, item):
        item.origen = self.origen
        self.items[self.segment].append(item)
        self.etiquetas_frescas = []

    # --- pasada 2: ubicar y emitir ---

    def place(self):
        """Le da una dirección a cada pieza y con eso a cada etiqueta."""
        self.addresses = {}
        self.offsets = {}

        for _, start, size, names in AREAS:
            offset = start
            for segment in names:
                for index, item in enumerate(self.items[segment]):
                    if isinstance(item, BankFit):
                        # Si el bloque que viene no entra en lo que queda del
                        # banco, se rellena hasta el siguiente.
                        queda = BANK_SIZE - (offset % BANK_SIZE)
                        item.size = queda if item.needed > queda else 0
                    elif isinstance(item, Align):
                        item.size = -offset % item.unit
                    self.offsets[(segment, index)] = offset
                    self.addresses[(segment, index)] = lorom_address(offset)
                    offset += item.size
                self.offsets[(segment, len(self.items[segment]))] = offset
                self.addresses[(segment, len(self.items[segment]))] = \
                    lorom_address(offset)
            if offset > start + size:
                raise Error("el área no entra: %d bytes en %d"
                            % (offset - start, size))

        # La RAM se reparte igual que la ROM, y con el mismo control de que
        # entre. No lo tenía, y no era teórico: ZEROPAGE llegó a 260 bytes
        # —diez de ellos por unas variables declaradas dos veces— o sea que las
        # últimas caían en $0100, encima de la pila y del principio de BSS.
        # Nada lo dijo y la tanda siguió en verde.
        for nombre, start, size, names in RAM_AREAS:
            address = start
            for segment in names:
                for index, item in enumerate(self.items[segment]):
                    self.addresses[(segment, index)] = address
                    address += item.size
                self.addresses[(segment, len(self.items[segment]))] = address
            if address > start + size:
                raise Error("%s no entra: %d bytes en %d%s"
                            % (nombre, address - start, size,
                               " (y %d más reservados para la pila)"
                               % PILA_RESERVADA if nombre == "RAM" else ""))

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
                    try:
                        data = self.emit_item(
                            item, self.addresses[(segment, index)])
                    except Error as error:
                        raise Error("%s\n  en %s"
                                    % (error, getattr(item, "origen", "?")))
                    rom[offset:offset + len(data)] = data
                    offset += item.size
        if self.checksum:
            checksum(rom)
        return bytes(rom)

    def emit_item(self, item, address):
        if isinstance(item, Instruction) and item.expression is not None:
            return item.bytes_con(self.lookup(item.expression), address)

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
    parser.add_argument("-I", "--incluir", action="append", default=[],
                        metavar="DIR",
                        help="dónde buscar los .include antes que en el "
                             "directorio del fuente. Se puede repetir. Es lo "
                             "que permite armar una ROM con un mapdata.inc "
                             "propio sin tocar el del árbol")
    parser.add_argument("--sin-checksum", action="store_true",
                        help="no completar el checksum de la cabecera, para "
                             "poder comparar contra ca65, que no lo escribe")
    parser.add_argument("--simbolos", metavar="ARCHIVO",
                        help="escribir la tabla de símbolos, un `nombre valor` "
                             "por línea. Es lo que deja mirar la RAM de la "
                             "ROM corriendo desde snes_correr.py: hoy, "
                             "`cuadros_perdidos`")
    args = parser.parse_args()

    assembler = Assembler(checksum=not args.sin_checksum,
                          incluir=args.incluir)
    try:
        rom = assembler.assemble(args.source)
    except Error as error:
        sys.exit("w65: %s" % error)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "wb") as handle:
        handle.write(rom)
    print("%s -> %s (%d bytes)" % (args.source, args.output, len(rom)))
    if args.simbolos:
        with open(args.simbolos, "w") as handle:
            for nombre, valor in sorted(assembler.symbols.items()):
                if isinstance(valor, int):
                    handle.write("%s %d\n" % (nombre, valor))


if __name__ == "__main__":
    main()
