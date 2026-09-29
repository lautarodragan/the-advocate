"""The bank packing, which the converter decides and not the assembler.

A DMA that crosses a bank does not read the next bank's ROM: it reads the
WRAM. That is why everything the ROM uploads by DMA —a pose, a tilemap, a
block of samples— has to fit **whole** in a bank, and when it does not fit in
what is left of the current one, it has to be padded up to the next.

Until 2026-09-16 that decision was taken by the assembler, with a directive of
ours: `.bloque N` meant "what follows is N bytes long, pad if it does not
fit". It worked, but it tied the port to having an assembler of its own:
`ld65` cannot pack variable-size blocks, and that is the only reason the
directive existed. Whoever does know the sizes is the converter, because it
emits them, so the split is done here: what reaches the assembler is one
segment per bank, `BANKnn`, which is what an `ld65` `.cfg` with one area per
bank expects.

**The only thing this module assumes about the memory map is which bank the
generated data starts in**, `PRIMER_BANCO`. The `.cfg` knows the rest.
"""

import re

BANCO = 0x8000

# How much each operand of the byte-emitting directives takes.
ANCHOS = {".byte": 1, ".word": 2, ".addr": 2, ".dword": 4}


def _operandos(resto):
    """How many operands a comma-separated list has.

    Commas inside a string do not separate. The converter does not emit
    strings today, but the rule is the assembler's and it is cheaper to
    respect it than to find out the day it emits them.
    """
    resto = resto.split(";")[0].strip()
    if not resto:
        return 0
    cuantos, comillas = 1, False
    for c in resto:
        if c == '"':
            comillas = not comillas
        elif c == "," and not comillas:
            cuantos += 1
    return cuantos


def _tamano(linea):
    """How many bytes a line takes, or None if it takes none."""
    partes = linea.strip().split(None, 1)
    if not partes:
        return 0
    if partes[0] == ".res":
        # The ones this very module leaves, in case someone runs it twice.
        return int(partes[1].split(";")[0].strip())
    ancho = ANCHOS.get(partes[0])
    if ancho is None:
        return 0
    return ancho * _operandos(partes[1] if len(partes) > 1 else "")


# The bank where the generated data starts. Bank 0 is the code and the
# tables, and bank 1 is `FAR`, the hand-written code that lives outside bank 0.
PRIMER_BANCO = 2


def segmento_de(banco):
    """The name of the segment pinned at the start of `banco`."""
    return "BANK%02X" % banco


def _partir(linea, entran):
    """Splits a data line into the first `entran` bytes and the rest.

    It can only be done between operands: a word split across two banks is
    not a word. If the cut falls in the middle of one, it is an error.
    """
    codigo, _, comentario = linea.partition(";")
    directiva, resto = codigo.strip().split(None, 1)
    ancho = ANCHOS[directiva]
    if entran % ancho:
        raise ValueError("the end of the bank falls in the middle of a "
                         "%d-byte operand: %r" % (ancho, linea.strip()))
    operandos = [o.strip() for o in resto.split(",")]
    cuantos = entran // ancho
    cola = ("  ; " + comentario.strip()) if comentario.strip() else ""
    primera = ("    %s %s%s" % (directiva, ", ".join(operandos[:cuantos]), cola)
               if cuantos else None)
    segunda = "    %s %s" % (directiva, ", ".join(operandos[cuantos:]))
    return primera, segunda, (len(operandos) - cuantos) * ancho


class _Unidad:
    """What the packing moves as one piece: a `.bloque`, a `.cruza` or what
    starts with neither, with all its lines up to the next one. `medida` is
    what it takes for the purpose of fitting —what the `.bloque` declares if
    it is more than what was emitted—, and `orden` its place in the text,
    which breaks ties so that the packing always comes out the same."""

    def __init__(self, orden, cruza=False, pide=0):
        self.orden, self.cruza, self.pide = orden, cruza, pide
        self.lineas, self.tamano, self.alinear = [], 0, 1

    @property
    def medida(self):
        return max(self.pide, self.tamano)


def resolver(rutas, segmento="RODATA", primer_banco=PRIMER_BANCO):
    """Splits into banks what those files send to `segmento`.

    **It is first-fit decreasing**, since 2026-09-27: each piece goes to the
    first bank where it fits, from the largest to the smallest. Until that day
    it was sequential —each piece after the previous one, and the one that
    did not fit jumped to the next bank leaving the gap unused—, and the gaps
    added up to ten banks in `release`. The pieces are not chosen by this
    module: the converter declares them, and there are three kinds.

    * **A `.bloque N` of up to one bank** fits whole in one: almost all of
      them are uploaded by DMA, and a DMA that crosses a bank reads the WRAM.
      It is the piece that gets packed, and it carries everything that
      follows up to the next directive —the tables the `.bloque` measures
      together, and the one-byte labels after them—.
    * **One of more than a bank** —the text block— starts a bank and goes on
      into the following ones, split between operands, as the sequential
      packing used to decide: it is walked by code that jumps banks by hand.
      What is left over in its last bank is used by the others.
    * **A `.cruza`** —the SPC700 driver, its samples, the music streams— can
      be split anywhere **between two consecutive banks**: `spc_block` and
      `advance` jump from `$FFFF` to the next bank's `$8000`, not to any
      bank. First it is tried whole in a gap; the ones that do not fit go at
      the end, one after the other, as a chain that starts in whatever is
      left of the last bank and continues in new banks. It is the only thing
      that fills a bank without leaving a gap.

    **To move the pieces they have to be taken out of their place**, because
    in `ca65` a segment is filled in the order of the text: what is left of
    `segmento` in each file is deleted, and all the banks are written at the
    end of the last of `rutas`, in order. It can be done because
    `musicdata.inc` and `mapdata.inc` come before all the code in `main.s`,
    and nothing that moves depends on its place: there are no subtractions
    between labels of different pieces, no `*`, no constants that use them.
    The constants (`X = …`) stay where they were. If some day the ROM read a
    piece assuming it is next to another, that would have to go in a single
    `.bloque`: separate, the packing spreads them wherever they fit.

    `rutas` comes in the order the assembler reads them, which is that of
    the `.include`s. What a file sends to another segment —the bank 0
    tables— does not count.

    **Every label of more than one byte has to be covered by a `.bloque`**,
    or carry `.cruza` in front if it is walked by code that jumps banks by
    hand. What is read with `lda f:tabla, x` or with `[ptr], y` does not
    jump: split, the second half is read from the next bank's `$0000`, which
    in LoROM is not ROM. The rule is enforced here, on every build, and not
    on the day the cut lands on one: see `sin_declarar`.

    Returns how many pieces it packed and into how many banks.
    """
    unidades, quedan = [], []
    # The labels the packing could split: [name, how long it is, how much of
    # that a `.bloque` covers, whether it carries `.cruza`]. The last one is
    # the one gathering its bytes.
    etiquetas, cubre, cruza = [], 0, False
    for ruta in rutas:
        with open(ruta) as handle:
            lineas = handle.read().splitlines()
        suyas, actual, unidad, abierta = [], None, None, None
        for linea in lineas:
            directiva = linea.split(";")[0].strip()
            if directiva.startswith(".segment"):
                actual = directiva.split(None, 1)[1].strip().strip('"')
                unidad, abierta = None, None
                if actual != segmento:
                    suyas.append(linea)
                continue
            if actual != segmento or _CONSTANTE.match(directiva):
                suyas.append(linea)
                continue
            # An `.align` right after a `.bloque` or a `.cruza` belongs to the
            # same piece: the alignment is of what follows.
            recien = unidad is not None and unidad.alinear > 1 \
                and len(unidad.lineas) == 1
            if directiva.startswith(".bloque "):
                cubre = int(directiva.split()[1])
                if not recien:
                    unidad = _Unidad(len(unidades))
                    unidades.append(unidad)
                unidad.pide = cubre
                continue
            if directiva == ".cruza":
                cruza = True
                if not recien:
                    unidad = _Unidad(len(unidades))
                    unidades.append(unidad)
                unidad.cruza = True
                continue
            if directiva.startswith(".align "):
                # This one stays: aligning is not packing banks, and `ca65`
                # knows how to do it. Here it only has to be counted, and since
                # the segment is the bank, the padding depends on what comes
                # before it in the bank.
                if unidad is None or unidad.lineas:
                    unidad = _Unidad(len(unidades))
                    unidades.append(unidad)
                unidad.alinear = int(directiva.split()[1])
                unidad.lineas.append(linea)
                continue
            if unidad is None:
                if not directiva:
                    suyas.append(linea)
                    continue
                unidad = _Unidad(len(unidades))
                unidades.append(unidad)
            if _ETIQUETA.match(directiva):
                abierta = [directiva.split(":")[0], 0, cubre, cruza]
                etiquetas.append(abierta)
                cruza = False
            tamano = _tamano(linea)
            cubre = max(0, cubre - tamano)
            if abierta:
                abierta[1] += tamano
            unidad.lineas.append(linea)
            unidad.tamano += tamano
        colados = [l for l in suyas if l.split(";")[0].strip()
                   .startswith((".bloque", ".cruza"))]
        if colados:
            # A `.bloque` that reaches the assembler is a `ca65` error far
            # from here, which does not say which block or why. Same for
            # `.cruza`.
            raise ValueError(
                "%s left %d `.bloque` unresolved, the first one %r: it is outside "
                "%s, and there the packing cannot be computed"
                % (ruta, len(colados), colados[0].strip(), segmento))
        quedan.append(suyas)
    sueltas = sin_declarar(etiquetas)
    if sueltas:
        raise ValueError(
            "%d label(s) in %s without a `.bloque` covering them, and the packing "
            "may split them across two banks: %s. If the ROM walks one "
            "jumping banks by hand, put `.cruza` in front of it"
            % (len(sueltas), segmento, ", ".join(sueltas)))

    bancos = _acomodar(unidades)
    entran = BANCOS - BANCOS_RESERVADOS - primer_banco
    if len(bancos) > entran:
        # Without this the one complaining is `ld65`, with an "Internal error:
        # Invalid file offset for memory area HEAD", which does not say that
        # space ran out.
        raise ValueError("the data needs %d banks and %d fit: from $%02X to "
                         "$%02X" % (len(bancos), entran, primer_banco,
                                    primer_banco + entran - 1))
    for k, (_usado, lineas) in enumerate(bancos):
        quedan[-1].append('.segment "%s"' % segmento_de(primer_banco + k))
        quedan[-1].extend(lineas)
    for ruta, suyas in zip(rutas, quedan):
        with open(ruta, "w") as handle:
            handle.write("\n".join(suyas) + "\n")
    return len(unidades), len(bancos)


def _relleno(usado, alinear):
    return (alinear - usado % alinear) % alinear


def _acomodar(unidades):
    """The banks, as [used, lines], with the pieces inside. See `resolver`,
    which says what each kind is."""
    bancos = []
    grandes = [u for u in unidades if not u.cruza and u.medida > BANCO]
    enteras = [u for u in unidades if not u.cruza and u.medida <= BANCO]
    cruzan = [u for u in unidades if u.cruza]

    def cabe(banco, u):
        # A lone label takes space too: at the end of a bank it would point
        # to the address after `$FFFF`, which is not the ROM.
        return (banco[0] + _relleno(banco[0], u.alinear) + max(1, u.medida)
                <= BANCO)

    def poner(u):
        for banco in bancos:
            if cabe(banco, u):
                banco[0] += _relleno(banco[0], u.alinear) + u.tamano
                banco[1].extend(u.lineas)
                return True
        return False

    # The large ones first, each from a new bank: what is left over in their
    # last bank is used by the others.
    for u in grandes:
        bancos.append([0, []])
        _volcar(bancos, u.lineas)
    por_tamano = lambda u: (-u.medida, u.orden)
    for u in sorted(enteras, key=por_tamano):
        if not poner(u):
            bancos.append([0, []])
            poner(u)
    cadena = [u for u in sorted(cruzan, key=por_tamano)
              if u.medida > BANCO or not poner(u)]
    if cadena and not bancos:
        bancos.append([0, []])
    for u in sorted(cadena, key=lambda u: u.orden):
        _volcar(bancos, u.lineas)
    return bancos


def _volcar(bancos, lineas):
    """Writes `lineas` from the end of the last bank, splitting between
    operands and continuing in new banks: it is the old sequential packing,
    for what can or has to cross."""
    for linea in lineas:
        banco = bancos[-1]
        directiva = linea.split(";")[0].strip()
        # A full bank is left behind before writing anything else, labels
        # included: a label at the end of a bank would point to the address
        # after `$FFFF`, which is not the ROM.
        if banco[0] == BANCO and directiva:
            bancos.append([0, []])
            banco = bancos[-1]
        if directiva.startswith(".align "):
            banco[0] += _relleno(banco[0], int(directiva.split()[1]))
            banco[1].append(linea)
            continue
        tamano = _tamano(linea)
        while banco[0] + tamano > BANCO:
            primera, linea, tamano = _partir(linea, BANCO - banco[0])
            if primera:
                banco[1].append(primera)
            bancos.append([0, []])
            banco = bancos[-1]
        banco[0] += tamano
        banco[1].append(linea)


_CONSTANTE = re.compile(r"^[A-Za-z_]\w*\s*=")


_ETIQUETA = re.compile(r"^[A-Za-z_]\w*:")


def sin_declarar(etiquetas):
    """The ones that can be split without anyone having asked for it.

    A single-byte one is never split, and that is why it is let through: the
    converter emits empty tables with one byte of padding, and one that grows
    is caught the day it grows.
    """
    return [nombre for nombre, mide, cubierto, cruza in etiquetas
            if mide > 1 and cubierto < mide and not cruza]


# --- the memory map, for `ld65` ----------------------------------------------
#
# 4 MB LoROM: 128 banks of 32 KB, each seen at `$8000-$FFFF` of its number.
# The last two in the file are not used: on the console, banks `$7E` and `$7F`
# **are** the WRAM, and data there would be read as RAM.
BANCOS = 128
BANCOS_RESERVADOS = 2

# The stack starts at `$1FFF` and grows downwards, towards the BSS: the two
# share the low 8 KB. This is what it is given, and the lowest byte it gets is
# `$2000 - PILA`.
#
# **It went down from 256 to 128 on 2026-09-20, by taro's decision**, to give
# those 128 bytes to the BSS, which is full. What keeps the margin from being
# blind is `rom/pruebas/rpgmaker/test_pila.py`: it marks the stack area
# **before the first frame** and measures how far down it really went on the
# deepest paths, with the threshold at half of this value. Without that test,
# lowering the number would be spending a margin nobody sees —the failure mode
# is the stack eating into the BSS, and the goldens do not tell it apart, nor
# does `test_cores.py`, because both emulators would get corrupted the same
# way—.
#
# How much is used **is not written here**: that test prints it, and the
# number that was written went stale twice (it said 24 when it was already
# 49). What does belong here is where the cap comes from: the deepest chain is
# the battles, which cross into bank 1 with `jsl` and come back through the
# bridges.
PILA = 128


def cfg():
    """The `ld65` `.cfg`: one area per bank, and each segment in its own.

    An area with `fill = yes` is padded to the end, so each bank takes its
    32 KB in the file even if its segment does not fill them, and a segment
    that overflows makes the link fail instead of spilling into the next one.
    The `BANKnn` are optional because how many are used depends on the
    cartridge.

    The `align = $8000` moves nothing —each segment starts at the beginning
    of its area, which is already aligned to that—, but `ld65` requires a
    segment to declare at least the alignment of the `.align`s it carries.
    """
    memoria = [
        # The RAM does not go into the file: it is laid out by address, not
        # by offset.
        'ZP:   start = $0000, size = $0100, type = rw, file = "";',
        'RAM:  start = $0100, size = $%04X, type = rw, file = "";'
        % (0x1F00 - PILA),
        # Bank 0: the code and the tables, and the header and the vectors at
        # the end, where the console looks for them.
        "ROM:  start = $008000, size = $7FC0, fill = yes;",
        "HEAD: start = $00FFC0, size = $0020, fill = yes;",
        "VECT: start = $00FFE0, size = $0020, fill = yes;",
    ]
    segmentos = [
        "ZEROPAGE: load = ZP,   type = zp;",
        "BSS:      load = RAM,  type = bss;",
        "CODE:     load = ROM,  type = ro;",
        "TABLAS:   load = ROM,  type = ro;",
        "HEADER:   load = HEAD, type = ro;",
        "VECTORS:  load = VECT, type = ro;",
        # The hand-written code that lives outside bank 0.
        "FAR:      load = %s, type = ro, align = $8000;" % segmento_de(1),
    ]
    for banco in range(1, BANCOS - BANCOS_RESERVADOS):
        memoria.append("%s: start = $%02X8000, size = $8000, fill = yes;"
                       % (segmento_de(banco), banco))
        if banco >= PRIMER_BANCO:
            segmentos.append("%s: load = %s, type = ro, align = $8000, "
                             "optional = yes;"
                             % (segmento_de(banco), segmento_de(banco)))
    # The two reserved ones go into the file anyway, as zeros: the cartridge
    # is 4 MB, which is what the header says and what flash carts expect.
    memoria.append("RESERVADO: start = $%02X8000, size = $%X, fill = yes;"
                   % (BANCOS - BANCOS_RESERVADOS, 0x8000 * BANCOS_RESERVADOS))
    return ("# Generated by tools/ensamblado/bancos.py: the ROM's memory map.\n"
            "MEMORY {\n%s\n}\nSEGMENTS {\n%s\n}\n"
            % ("\n".join("    " + m for m in memoria),
               "\n".join("    " + s for s in segmentos)))
