"""Lo que el ensamblador no revisa de los tres bancos de código.

La regla está en el encabezado del `main.s` del runtime: un `jsr` o un
`jmp` absoluto no cambia el banco de programa, así que uno hacia una rutina
de otro banco ensambla, linkea y salta a la misma dirección **en el banco del
que llama**; `jmp (tabla, x)` lee la tabla del banco de programa; y
`lda tabla, x` lee del banco de datos, que es 0 —`$7E` en la pelea—, así que
una tabla de otro banco se lee del lugar equivocado sin ningún error. Esto lo
revisa sobre cada cartucho armado.

**Cómo lo sabe sin leer el fuente.** El `.dbg` de `ld65` dice, de cada
símbolo, su valor y **en qué líneas se lo nombra** (`ref=`), y de cada línea
qué bytes de la ROM salieron de ella (`span=`). Con eso alcanza: se lee el
opcode en la ROM —que dice el modo de direccionamiento sin adivinar nada del
texto— y se compara adónde va de verdad la instrucción con adónde está el
símbolo que nombra. Del desensamblador queda sólo la tabla de modos de los
256 opcodes y su largo: no hace falta seguir el código. El fuente se lee nada
más que para el mensaje.

Lo que **no** ve, para que no se lo crea más de lo que es:

* el banco de datos no se sigue: se dice por archivo y por rutina
  (`BANCO_DE_DATOS`), y lo que lo cambia a mitad de camino —los puentes
  `ba_t_*`, el intérprete, que corre con el del bytecode— no se modela;
* lo que se direcciona con un puntero —`[ptr], y`, `(ptr), y`— no nombra el
  símbolo en la instrucción, y no se puede revisar;
* de un símbolo de `=` no se sabe si es una dirección, y sólo se miran los
  que caen en la ROM y los registros: ver `problemas`;
* que a una rutina a la que se entra con `jsl` se salga con `rtl`.
"""

import bisect
import collections
import os
import re

import pytest

import cartuchos
import tanda

# --- El 65816, lo justo -------------------------------------------------------

# El modo de direccionamiento de cada opcode, de $00 a $FF, en filas de 16.
# `immM` e `immX` son los inmediatos que miden uno o dos bytes según el ancho
# de A o de X/Y; `absi` es `jmp (abs)`, `absil` es `jml [abs]` y `absix` es
# `jmp`/`jsr (abs, x)`.
_MODOS = """
imm8 dpix imm8 sr   dp dp  dp  dpil  imp immM imp imp abs   abs  abs  absl
rel  dpiy dpi  sriy dp dpx dpx dpily imp absy imp imp abs   absx absx abslx
abs  dpix absl sr   dp dp  dp  dpil  imp immM imp imp abs   abs  abs  absl
rel  dpiy dpi  sriy dpx dpx dpx dpily imp absy imp imp absx absx absx abslx
imp  dpix imm8 sr   bm dp  dp  dpil  imp immM imp imp abs   abs  abs  absl
rel  dpiy dpi  sriy bm dpx dpx dpily imp absy imp imp absl  absx absx abslx
imp  dpix rell sr   dp dp  dp  dpil  imp immM imp imp absi  abs  abs  absl
rel  dpiy dpi  sriy dpx dpx dpx dpily imp absy imp imp absix absx absx abslx
rel  dpix rell sr   dp dp  dp  dpil  imp immM imp imp abs   abs  abs  absl
rel  dpiy dpi  sriy dpx dpx dpy dpily imp absy imp imp abs   absx absx abslx
immX dpix immX sr   dp dp  dp  dpil  imp immM imp imp abs   abs  abs  absl
rel  dpiy dpi  sriy dpx dpx dpy dpily imp absy imp imp absx  absx absy abslx
immX dpix imm8 sr   dp dp  dp  dpil  imp immM imp imp abs   abs  abs  absl
rel  dpiy dpi  sriy dp dpx dpx dpily imp absy imp imp absil absx absx abslx
immX dpix imm8 sr   dp dp  dp  dpil  imp immM imp imp abs   abs  abs  absl
rel  dpiy dpi  sriy pea dpx dpx dpily imp absy imp imp absix absx absx abslx
""".split()
assert len(_MODOS) == 256

_LARGO = {"imp": 1, "imm8": 2, "rel": 2, "sr": 2, "sriy": 2, "dp": 2,
          "dpx": 2, "dpy": 2, "dpi": 2, "dpil": 2, "dpix": 2, "dpiy": 2,
          "dpily": 2, "abs": 3, "absx": 3, "absy": 3, "absi": 3, "absil": 3,
          "absix": 3, "rell": 3, "bm": 3, "pea": 3, "absl": 4, "abslx": 4}

_JSR, _JMP, _JSL, _JML = 0x20, 0x4C, 0x22, 0x5C
_REP, _SEP = 0xC2, 0xE2


def _largo(opcode, m8, x8):
    modo = _MODOS[opcode]
    if modo == "immM":
        return 2 if m8 else 3
    if modo == "immX":
        return 2 if x8 else 3
    return _LARGO[modo]


def _lugar(direccion):
    """A qué memoria va a parar una dirección de 24 bits, con los espejos de
    la consola resueltos: dos direcciones con el mismo lugar leen lo mismo."""
    banco, desplazamiento = direccion >> 16, direccion & 0xFFFF
    if banco == 0x7E:
        return ("wram", desplazamiento)
    if banco == 0x7F:
        return ("wram", 0x10000 + desplazamiento)
    if banco & 0x7F < 0x40:
        if desplazamiento < 0x2000:
            return ("wram", desplazamiento)
        if desplazamiento < 0x8000:
            return ("registros", desplazamiento)
        # Los bancos 0 y 1 están dos veces en el archivo, para que `$00` y su
        # espejo `$80` lean lo mismo: ver "ExHiROM" en el README.
        if banco & 0x7F in (0, 1):
            banco &= 0x7F
    return ("rom", banco, desplazamiento)


def _registro(valor):
    """Los registros de la PPU, la CPU y el DMA, que sólo se ven en los
    bancos `$00-$3F` y `$80-$BF`."""
    return (0x2100 <= valor < 0x2200 or 0x4016 <= valor < 0x4018
            or 0x4200 <= valor < 0x4380)


# --- El `.dbg` ----------------------------------------------------------------

_CAMPO = re.compile(r'(\w+)=("[^"]*"|[^,]*)')
_TIPOS = ("seg", "span", "line", "file", "sym")


def _leer_dbg(ruta):
    registros = {t: {} for t in _TIPOS}
    with open(ruta) as archivo:
        for renglon in archivo:
            tipo, _, resto = renglon.rstrip("\n").partition("\t")
            if tipo not in registros:
                continue
            campos = {k: v.strip('"') for k, v in _CAMPO.findall(resto)}
            registros[tipo][int(campos["id"])] = campos
    return registros


class Ensamblado:
    """El código a mano de un cartucho, instrucción por instrucción, con los
    símbolos que nombra cada línea."""

    def __init__(self, sfc, raiz, runtime):
        """`raiz` es desde donde nombra los fuentes el `.dbg`, y `runtime`
        el directorio del código a mano, que es lo único que se revisa: lo
        generado son datos."""
        with open(sfc, "rb") as archivo:
            self.rom = archivo.read()
        dbg = _leer_dbg(sfc + ".dbg")
        self.raiz = raiz
        self._runtime = os.path.relpath(runtime, raiz) + "/"
        self.segmentos = dbg["seg"]
        self.spans = dbg["span"]
        self.lineas = dbg["line"]
        self.archivos = {i: f["name"] for i, f in dbg["file"].items()}
        self.simbolos = dbg["sym"]
        self._fuentes = {}
        # Dónde empieza cada instrucción que es sola en su span, y cada dato
        # —un `.byte`, un `.addr`—: casi todas las líneas, y cada línea de la
        # expansión de una macro, que el `.dbg` marca con `type=2`. Los datos,
        # de cualquier archivo: la tabla del despacho de `run_code` es una
        # macro del runtime que expande un `.inc` generado
        # —`EVENT_HANDLERS`, de `event_opcodes.inc`—, y desde el 2026-10-02
        # ese `.inc` está en el directorio del cartucho, no en el runtime.
        self.inicios, self.datos = {}, set()
        for linea in self.lineas.values():
            del_runtime = self.del_runtime(linea)
            for direccion, offset, largo, dato in self._spans(linea):
                if dato:
                    self.datos.add(direccion)
                elif del_runtime and self._sola(offset, largo):
                    self.inicios[direccion] = offset
        etiquetas = [s for s in self.simbolos.values()
                     if s.get("type") == "lab" and "val" in s]
        # Todas, para saber dónde termina una tabla de saltos y si una
        # entrada cae en una; las de afuera de todo `.proc`, para nombrar la
        # rutina de una dirección.
        self.etiquetas = sorted({int(s["val"], 16) for s in etiquetas})
        self._etiquetas = set(self.etiquetas)
        self._rutinas = sorted((int(s["val"], 16), s["name"])
                               for s in etiquetas if s["scope"] == "0")
        self._por_desplazamiento = {}
        for valor, nombre in self._rutinas:
            self._por_desplazamiento.setdefault(valor & 0xFFFF, []).append(
                "`%s` en $%06X" % (nombre, valor))

    def del_runtime(self, linea):
        return self.archivo(linea).startswith(self._runtime)

    def archivo(self, linea):
        """El fuente de la línea, como lo nombra el `.dbg`: desde la raíz."""
        return self.archivos[int(linea["file"])]

    def en_el_runtime(self, linea):
        """El fuente de la línea, desde el directorio del runtime."""
        return self.archivo(linea)[len(self._runtime):]

    def _spans(self, linea):
        """Los spans de una línea que van a la ROM —su segmento tiene
        `ooffs`—, como (dirección, offset en el archivo, largo, si es dato).
        Un span con tipo es un dato: es como `ca65` distingue un `.byte` de
        una instrucción."""
        if "span" not in linea:
            return
        for id_span in linea["span"].split("+"):
            span = self.spans[int(id_span)]
            segmento = self.segmentos[int(span["seg"])]
            if "ooffs" not in segmento:
                continue
            inicio = int(span["start"], 0)
            yield (int(segmento["start"], 16) + inicio,
                   int(segmento["ooffs"]) + inicio, int(span["size"], 0),
                   "type" in span)

    def _sola(self, offset, largo):
        """Si `largo` bytes desde `offset` son una sola instrucción, con
        algún ancho de A y de X/Y."""
        return largo in {_largo(self.rom[offset], m, x)
                         for m in (True, False) for x in (True, False)}

    def instrucciones_de(self, linea):
        """Las instrucciones de una línea, como (dirección, offset). Una
        macro las trae de su expansión, donde puede haber datos; un
        `.repeat`, que no tiene líneas propias, se decodifica de corrido con
        el ancho que haga cerrar el span justo. Devuelve None si no hay
        manera de leerla."""
        todas = []
        for direccion, offset, largo, dato in self._spans(linea):
            if dato:
                continue
            if self._sola(offset, largo):
                todas.append((direccion, offset))
                continue
            adentro = [d for d in range(direccion, direccion + largo)
                       if d in self.inicios or d in self.datos]
            if adentro and adentro[0] == direccion:
                todas.extend((d, self.inicios[d]) for d in adentro
                             if d in self.inicios)
                continue
            corrido = self._de_corrido(direccion, offset, largo)
            if corrido is None:
                return None
            todas.extend(corrido)
        return todas

    def _de_corrido(self, direccion, offset, largo):
        for m0 in (True, False):
            for x0 in (True, False):
                m, x, d, salida = m0, x0, 0, []
                while d < largo:
                    opcode = self.rom[offset + d]
                    salida.append((direccion + d, offset + d))
                    if opcode in (_REP, _SEP):
                        bits = self.rom[offset + d + 1]
                        if bits & 0x20:
                            m = opcode == _SEP
                        if bits & 0x10:
                            x = opcode == _SEP
                    d += _largo(opcode, m, x)
                if d == largo:
                    return salida
        return None

    def operando(self, offset):
        n = 3 if _MODOS[self.rom[offset]] in ("absl", "abslx") else 2
        return int.from_bytes(self.rom[offset + 1:offset + 1 + n], "little")

    def es_etiqueta(self, direccion):
        return direccion in self._etiquetas

    def palabras(self, direccion):
        """Las palabras de una tabla de `.addr`, desde `direccion` hasta la
        etiqueta siguiente."""
        for segmento in self.segmentos.values():
            inicio = int(segmento["start"], 16)
            fin = inicio + int(segmento["size"], 16)
            if "ooffs" in segmento and inicio <= direccion < fin:
                break
        else:
            return []
        siguiente = min(fin, next(
            (e for e in self.etiquetas if e > direccion), fin))
        offset = int(segmento["ooffs"]) + direccion - inicio
        return [int.from_bytes(self.rom[o:o + 2], "little")
                for o in range(offset, offset + siguiente - direccion - 1, 2)]

    def que_es(self, palabra):
        """Una entrada de 16 bits, con las rutinas de cualquier banco que
        tienen esa dirección: la que se quiso poner es una de ésas."""
        donde = self._por_desplazamiento.get(palabra)
        return "$%04X (%s)" % (palabra, ", ".join(donde)) if donde else (
            "$%04X" % palabra)

    def rutina(self, direccion):
        """La etiqueta de afuera de todo `.proc` que está antes de
        `direccion`: la rutina, casi siempre."""
        i = bisect.bisect_right(self._rutinas, (direccion, "￿"))
        return self._rutinas[i - 1][1] if i else "?"

    def texto(self, linea):
        """La línea del fuente, sin el comentario."""
        nombre = self.archivo(linea)
        if nombre not in self._fuentes:
            try:
                with open(os.path.join(self.raiz, nombre)) as archivo:
                    self._fuentes[nombre] = archivo.read().split("\n")
            except OSError:
                self._fuentes[nombre] = []
        renglones = self._fuentes[nombre]
        n = int(linea["line"])
        return (renglones[n - 1].split(";")[0].strip()
                if 0 < n <= len(renglones) else "?")


# --- La revisión --------------------------------------------------------------

# El banco de datos con que corre cada archivo o cada rutina, si no es el 0. No
# se sigue el código: se dice acá, de lo que corre entero con otro banco, y si
# una rutina está en las dos tablas vale la de la rutina.
_PELEA = (0x7E,)
BANCO_DE_DATOS = {
    # La pelea: `op_battle` pone `$7E` antes del `jsl battle_run` y lo
    # devuelve al volver. Ver el encabezado de bank1.s.
    **{archivo: _PELEA for archivo in (
        "battle.s", "battle_items.s", "battle_loop.s", "battle_run.s",
        "battle_scene.s", "battle_skills.s", "battle_troop.s",
        "battle_victory.s")},
    # Los encuentros, igual que la pelea: ver su encabezado.
    "encounters.s": _PELEA,
    # Vive en battle_scene.s pero no corre en la pelea: la llama
    # `back_from_battle`, en el banco 0, con el banco de datos en 0 —lo dice
    # su comentario—, y por eso escribe los registros con direcciones
    # absolutas.
    "scene_cgram_restore": (0,),
}

_DATOS = ("abs", "absx", "absy")
_CLASE = {"absix": "tabla", "absi": "indirecto", "absil": "indirecto",
          "absl": "largo", "abslx": "largo"}
_LARGOS = ("absl", "abslx")

# Cuánto puede sumarle una línea al símbolo que nombra —`tabla + 2`,
# `NPC_ROW_SEPARATE + k * 2`— para que se lo tome como su operando. Lo que se
# pase de esto no es una dirección del símbolo sino otra cuenta.
_CORRIMIENTO = 0x200


def _con_signo(n):
    return n - 0x10000 if n >= 0x8000 else n


def problemas(ensamblado, revisadas=None):
    """Cada instrucción que va a otro lado que el símbolo que nombra, como
    texto: qué rutina, desde dónde, y por qué. En `revisadas`, si se pasa un
    `Counter`, cuántas se miraron de cada clase."""
    if revisadas is None:
        revisadas = collections.Counter()
    salida = set()
    for simbolo in ensamblado.simbolos.values():
        if "ref" not in simbolo or "val" not in simbolo:
            continue
        valor = int(simbolo["val"], 16)
        # De un `=` no se sabe si es una dirección: `EX_VOICES = 6` es una
        # cuenta, y `FAR_HP = $3700` es la mitad de una —se escribe
        # `f:FAR_LENGTH + FAR_HP`—. Se miran los que no pueden ser otra cosa:
        # los que caen en la ROM, como `op_reserved_39 = op_done`, y los
        # registros.
        if (simbolo.get("type") != "lab" and _lugar(valor)[0] != "rom"
                and not _registro(valor)):
            continue
        for id_linea in {int(r) for r in simbolo["ref"].split("+")}:
            linea = ensamblado.lineas[id_linea]
            if not ensamblado.del_runtime(linea):
                continue
            instrucciones = ensamblado.instrucciones_de(linea)
            if instrucciones is None:
                salida.add("%s:%s: no se pudo leer la línea, que nombra a "
                           "`%s`" % (ensamblado.archivo(linea), linea["line"],
                                     simbolo["name"]))
                continue
            for direccion, offset in instrucciones:
                por = _por_que(ensamblado, linea, simbolo["name"], valor,
                               direccion, offset, revisadas)
                if por:
                    salida.add("%s:%s, en `%s` ($%06X): `%s`. %s" % (
                        ensamblado.archivo(linea), linea["line"],
                        ensamblado.rutina(direccion), direccion,
                        ensamblado.texto(linea), por))
    return sorted(salida)


def _por_que(ensamblado, linea, nombre, valor, direccion, offset, revisadas):
    """Por qué la instrucción no va adonde está `nombre`, o None si va."""
    opcode = ensamblado.rom[offset]
    modo = _MODOS[opcode]
    if modo not in _DATOS + _LARGOS + ("absi", "absil", "absix"):
        return None
    operando = ensamblado.operando(offset)
    corrimiento = _con_signo((operando - valor) & 0xFFFF)
    if abs(corrimiento) > _CORRIMIENTO:
        return None                     # nombra al símbolo para otra cosa
    destino = valor + corrimiento       # adonde quiso ir el que lo escribió
    banco = direccion >> 16
    revisadas[_CLASE.get(modo, "salto" if opcode in (_JSR, _JMP) else
                         "largo" if opcode in (_JSL, _JML) else "datos")] += 1

    if opcode in (_JSR, _JMP):
        if destino >> 16 == banco:
            return None
        return ("`%s` está en el banco $%02X, y un %s no cambia de banco: "
                "salta a $%02X:%04X. Entre bancos va jsl, con un rtl o una "
                "entrada `_l`." % (nombre, destino >> 16,
                                    "jsr" if opcode == _JSR else "jmp",
                                    banco, operando))
    if modo == "absix":
        if destino >> 16 != banco:
            return ("`%s` está en el banco $%02X, y la tabla de un salto "
                    "indexado se lee del banco de programa, $%02X."
                    % (nombre, destino >> 16, banco))
        # Y cada entrada es una dirección de 16 bits, también en el banco de
        # programa: una rutina de otro banco ensambla, y se salta a su
        # dirección en éste. Una entrada que no cae en una etiqueta de este
        # banco es eso, o la tabla sigue más allá de donde se la cree.
        fuera = [ensamblado.que_es(w) for w in ensamblado.palabras(destino)
                 if not ensamblado.es_etiqueta((banco << 16) | w)]
        if fuera:
            return ("Las entradas de `%s` se saltan en el banco $%02X, y "
                    "éstas no caen en una etiqueta de ahí: %s."
                    % (nombre, banco, ", ".join(fuera)))
        return None
    if modo in ("absi", "absil"):
        if _lugar(operando) == _lugar(destino):
            return None
        return ("El puntero de un salto indirecto se lee del banco 0, y "
                "`%s` está en $%06X." % (nombre, destino))
    if modo in _LARGOS or opcode in (_JSL, _JML):
        # Lo largo lleva el banco en la instrucción, y lo único que puede
        # errarle es un `+ FAST` de más. A `FAR2` no llega ni a armarse:
        # `$C0 + $80` no entra en 24 bits y `ld65` se niega con un "Range
        # error" —probado el 2026-10-02—. Esto queda para lo demás.
        if _lugar(operando) == _lugar(destino):
            return None
        return "`%s` está en $%06X, y esto va a $%06X." % (
            nombre, destino, operando)
    # Lo absoluto de datos: el banco lo pone el registro de banco de datos.
    rutina = ensamblado.rutina(direccion)
    bancos = BANCO_DE_DATOS.get(
        rutina, BANCO_DE_DATOS.get(ensamblado.en_el_runtime(linea), (0,)))
    for dbr in bancos:
        efectivo = (dbr << 16) | operando
        if _lugar(efectivo) != _lugar(destino):
            return ("`%s` está en $%06X, y con el banco de datos en $%02X "
                    "esto va a $%06X: lo que no está en ese banco va con `f:`."
                    % (nombre, destino, dbr, efectivo))
    return None


def _ensamblado(nombre):
    return Ensamblado(tanda.cartucho(nombre).sfc, cartuchos.raiz(),
                      cartuchos.runtime())


@pytest.mark.parametrize("nombre", sorted(cartuchos.nombres()))
def test_ningun_salto_ni_acceso_absoluto_cae_en_otro_banco(nombre):
    revisadas = collections.Counter()
    encontrados = problemas(_ensamblado(nombre), revisadas)
    assert encontrados == [], "\n" + "\n".join(encontrados)
    # Y que haya mirado algo de cada clase: la primera versión leía mal el
    # `type=` del final de cada renglón del `.dbg`, no reconocía ninguna
    # etiqueta, y daba cero sin revisar casi nada.
    faltan = {"salto", "tabla", "largo", "datos"} - set(revisadas)
    assert not faltan, "no revisó ninguna instrucción de: %s" % faltan


def test_lo_que_tiene_otro_banco_de_datos_existe():
    """Un archivo renombrado o una rutina que se mudó dejarían su entrada de
    `BANCO_DE_DATOS` sin efecto, y lo suyo se revisaría con el banco 0."""
    ensamblado = _ensamblado(cartuchos.RELEASE)
    archivos = {ensamblado.en_el_runtime(linea)
                for linea in ensamblado.lineas.values()
                if ensamblado.del_runtime(linea)}
    rutinas = {nombre for _, nombre in ensamblado._rutinas}
    sobran = set(BANCO_DE_DATOS) - archivos - rutinas
    assert not sobran, sobran
