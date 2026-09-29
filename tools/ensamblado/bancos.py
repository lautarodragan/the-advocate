"""El acomodo de bancos, que lo decide el conversor y no el ensamblador.

Un DMA que cruza de banco no lee la ROM del banco siguiente: lee la WRAM. Por
eso todo lo que la ROM sube por DMA —una pose, un tilemap, un bloque de
muestras— tiene que entrar **entero** en un banco, y cuando no entra en lo que
queda del que corre hay que rellenar hasta el próximo.

Hasta el 2026-09-16 esa decisión la tomaba el ensamblador, con una directiva
nuestra: `.bloque N` quería decir "lo que sigue mide N bytes, rellená si no
entra". Funcionaba, pero ataba el port a tener un ensamblador propio: `ld65` no
sabe acomodar bloques de tamaño variable, y ésa es la única razón por la que la
directiva existía. Quien sí conoce los tamaños es el conversor, porque los
emite, así que el reparto se hace acá: lo que llega al ensamblador es un
segmento por banco, `BANKnn`, que es lo que espera un `.cfg` de `ld65` con un
área por banco.

**Lo único que este módulo asume del mapa de memoria es en qué banco arrancan
los datos generados**, `PRIMER_BANCO`. El resto lo sabe el `.cfg`.
"""

import re

BANCO = 0x8000

# Cuánto ocupa cada operando de las directivas que emiten bytes.
ANCHOS = {".byte": 1, ".word": 2, ".addr": 2, ".dword": 4}


def _operandos(resto):
    """Cuántos operandos tiene una lista separada por comas.

    Las comas de adentro de una cadena no separan. El conversor no emite
    cadenas hoy, pero la regla es la del ensamblador y sale más barato
    respetarla que descubrir el día que las emita.
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
    """Cuántos bytes ocupa una línea, o None si no ocupa ninguno."""
    partes = linea.strip().split(None, 1)
    if not partes:
        return 0
    if partes[0] == ".res":
        # Las que deja este mismo módulo, por si alguien lo corre dos veces.
        return int(partes[1].split(";")[0].strip())
    ancho = ANCHOS.get(partes[0])
    if ancho is None:
        return 0
    return ancho * _operandos(partes[1] if len(partes) > 1 else "")


# El banco donde arrancan los datos generados. El 0 es el código y las tablas,
# y el 1 es `FAR`, el código a mano que vive afuera del banco 0.
PRIMER_BANCO = 2


def segmento_de(banco):
    """El nombre del segmento que va fijo al principio de `banco`."""
    return "BANK%02X" % banco


def _partir(linea, entran):
    """Parte una línea de datos en los primeros `entran` bytes y el resto.

    Sólo se puede entre operandos: una palabra partida entre dos bancos no es
    una palabra. Si el corte cae en el medio de una, es un error.
    """
    codigo, _, comentario = linea.partition(";")
    directiva, resto = codigo.strip().split(None, 1)
    ancho = ANCHOS[directiva]
    if entran % ancho:
        raise ValueError("el final del banco cae en el medio de un operando "
                         "de %d bytes: %r" % (ancho, linea.strip()))
    operandos = [o.strip() for o in resto.split(",")]
    cuantos = entran // ancho
    cola = ("  ; " + comentario.strip()) if comentario.strip() else ""
    primera = ("    %s %s%s" % (directiva, ", ".join(operandos[:cuantos]), cola)
               if cuantos else None)
    segunda = "    %s %s" % (directiva, ", ".join(operandos[cuantos:]))
    return primera, segunda, (len(operandos) - cuantos) * ancho


class _Unidad:
    """Lo que el acomodo mueve de una pieza: un `.bloque`, un `.cruza` o lo
    que empieza sin ninguno de los dos, con todas sus líneas hasta el
    siguiente. `medida` es lo que ocupa a efectos de entrar —lo que declara
    el `.bloque` si es más que lo emitido—, y `orden` el lugar en el texto,
    que desempata para que el acomodo salga siempre igual."""

    def __init__(self, orden, cruza=False, pide=0):
        self.orden, self.cruza, self.pide = orden, cruza, pide
        self.lineas, self.tamano, self.alinear = [], 0, 1

    @property
    def medida(self):
        return max(self.pide, self.tamano)


def resolver(rutas, segmento="RODATA", primer_banco=PRIMER_BANCO):
    """Reparte en bancos lo que esos archivos mandan a `segmento`.

    **Es first-fit decreasing**, desde el 2026-09-27: cada pieza va al primer
    banco donde entra, de la más grande a la más chica. Hasta ese día era
    secuencial —cada pieza detrás de la anterior, y la que no entraba saltaba
    al banco siguiente dejando el hueco sin usar—, y los huecos llegaban a
    diez bancos en `release`. Las piezas no las elige este módulo: las
    declara el conversor, y hay tres clases.

    * **Un `.bloque N` de hasta un banco** entra entero en uno: casi todos se
      suben por DMA, y un DMA que cruza de banco lee la WRAM. Es la pieza que
      se acomoda, y lleva todo lo que sigue hasta la próxima directiva —las
      tablas que el `.bloque` mide juntas, y las etiquetas de un byte detrás—.
    * **Uno de más de un banco** —el bloque de textos— arranca un banco y
      sigue en los siguientes, partido entre operandos, como lo decidía el
      acomodo secuencial: lo recorre código que salta de banco a mano. Lo
      que sobra en su último banco lo usan las demás.
    * **Un `.cruza`** —el driver del SPC700, sus muestras, los streams de
      la música— se puede partir en cualquier lado **entre dos bancos
      seguidos**: `spc_block` y `advance` saltan del `$FFFF` al `$8000` del
      banco siguiente, no a cualquiera. Primero se prueba meterlo entero en
      un hueco; los que no entran van al final, uno detrás del otro, como
      una cadena que empieza en lo que quede del último banco y sigue en
      bancos nuevos. Es lo único que llena un banco sin dejar hueco.

    **Para mover las piezas hay que sacarlas de su lugar**, porque en `ca65`
    un segmento se llena en el orden del texto: lo que queda de `segmento` en
    cada archivo se borra, y todos los bancos se escriben al final del último
    de `rutas`, en orden. Se puede porque `musicdata.inc` y `mapdata.inc` van
    antes que todo el código en `main.s`, y nada de lo que se mueve depende
    del lugar: no hay restas entre etiquetas de piezas distintas, ni `*`, ni
    constantes que las usen. Las constantes (`X = …`) se quedan donde
    estaban. Si algún día la ROM leyera una pieza suponiendo que es vecina de
    otra, eso tendría que ir en un solo `.bloque`: separadas, el acomodo las
    reparte por donde entren.

    `rutas` va en el orden en que el ensamblador las lee, que es el de los
    `.include`. Lo que un archivo mande a otro segmento —las tablas del banco
    0— no cuenta.

    **Toda etiqueta de más de un byte tiene que estar cubierta por un
    `.bloque`**, o llevar `.cruza` delante si la recorre código que salta de
    banco a mano. Lo que se lee con `lda f:tabla, x` o con `[ptr], y` no salta:
    partida, la segunda mitad se lee del `$0000` del banco siguiente, que en
    LoROM no es ROM. La regla se cobra acá, en cada armado, y no el día que el
    corte cae encima de una: ver `sin_declarar`.

    Devuelve cuántas piezas acomodó y en cuántos bancos.
    """
    unidades, quedan = [], []
    # Las etiquetas que el acomodo podría partir: [nombre, cuánto mide, cuánto
    # de eso cubre un `.bloque`, si lleva `.cruza`]. La última es la que está
    # juntando sus bytes.
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
            # Un `.align` pegado a un `.bloque` o a un `.cruza` es de la misma
            # pieza: la alineación es de lo que sigue.
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
                # Ésta se queda: alinear no es acomodar bancos, y `ca65` la
                # sabe hacer. Acá sólo hay que contarla, y como el segmento
                # es el banco, el relleno depende de lo que haya antes en él.
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
            # Un `.bloque` que llegue al ensamblador es un error de `ca65`
            # lejos de acá, que no dice qué bloque ni por qué. `.cruza`, igual.
            raise ValueError(
                "%s dejó %d `.bloque` sin resolver, el primero %r: está fuera "
                "de %s, y ahí el acomodo no se puede calcular"
                % (ruta, len(colados), colados[0].strip(), segmento))
        quedan.append(suyas)
    sueltas = sin_declarar(etiquetas)
    if sueltas:
        raise ValueError(
            "%d etiqueta(s) de %s sin `.bloque` que las cubra, y el acomodo "
            "las puede partir entre dos bancos: %s. Si la ROM la recorre "
            "saltando de banco a mano, va `.cruza` delante"
            % (len(sueltas), segmento, ", ".join(sueltas)))

    bancos = _acomodar(unidades)
    entran = BANCOS - BANCOS_RESERVADOS - primer_banco
    if len(bancos) > entran:
        # Sin esto el que se queja es `ld65`, con un "Internal error: Invalid
        # file offset for memory area HEAD", que no dice que falta lugar.
        raise ValueError("los datos piden %d bancos y entran %d: del $%02X al "
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
    """Los bancos, como [usado, líneas], con las piezas adentro. Ver
    `resolver`, que dice qué es cada clase."""
    bancos = []
    grandes = [u for u in unidades if not u.cruza and u.medida > BANCO]
    enteras = [u for u in unidades if not u.cruza and u.medida <= BANCO]
    cruzan = [u for u in unidades if u.cruza]

    def cabe(banco, u):
        # Una etiqueta sola también ocupa: en el final de un banco apuntaría a
        # la dirección que sigue a `$FFFF`, que no es la ROM.
        return (banco[0] + _relleno(banco[0], u.alinear) + max(1, u.medida)
                <= BANCO)

    def poner(u):
        for banco in bancos:
            if cabe(banco, u):
                banco[0] += _relleno(banco[0], u.alinear) + u.tamano
                banco[1].extend(u.lineas)
                return True
        return False

    # Las grandes primero, cada una desde un banco nuevo: lo que les sobra en
    # el último lo aprovechan las demás.
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
    """Escribe `lineas` a partir del final del último banco, partiendo entre
    operandos y siguiendo en bancos nuevos: es el acomodo secuencial de antes,
    para lo que puede o tiene que cruzar."""
    for linea in lineas:
        banco = bancos[-1]
        directiva = linea.split(";")[0].strip()
        # Un banco lleno se deja antes de escribir nada más, etiquetas
        # incluidas: una etiqueta al final de un banco apuntaría a la
        # dirección que sigue a `$FFFF`, que no es la ROM.
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
    """Las que se pueden partir sin que nadie lo haya pedido.

    Una de un solo byte no se parte nunca, y por eso se deja pasar: las
    tablas vacías el conversor las emite con un byte de relleno, y la que
    crezca se cobra el día que crece.
    """
    return [nombre for nombre, mide, cubierto, cruza in etiquetas
            if mide > 1 and cubierto < mide and not cruza]


# --- el mapa de memoria, para `ld65` -----------------------------------------
#
# LoROM de 4 MB: 128 bancos de 32 KB, cada uno visto en `$8000-$FFFF` de su
# número. Los dos últimos del archivo no se usan: en la consola, los bancos
# `$7E` y `$7F` **son** la WRAM, y un dato ahí se leería como RAM.
BANCOS = 128
BANCOS_RESERVADOS = 2

# La pila arranca en `$1FFF` y crece hacia abajo, hacia el BSS: los dos
# comparten los 8 KB bajos. Esto es lo que se le deja, y el byte más bajo que le
# toca es `$2000 - PILA`.
#
# **Bajó de 256 a 128 el 2026-09-20, por decisión de taro**, para darle esos 128
# bytes a la BSS, que está llena. Lo que hace que el margen deje de ser ciego es
# `rom/pruebas/rpgmaker/test_pila.py`: marca la zona de la pila **antes del
# primer cuadro** y mide hasta dónde bajó de verdad en los caminos más hondos,
# con el umbral en la mitad de acá. Sin esa prueba bajar el número sería gastar
# un margen que no ve nadie —el modo de falla es la pila comiéndose la BSS, y
# las goldens no lo distinguen ni `test_cores.py` tampoco, porque los dos
# emuladores se corromperían igual—.
#
# Cuánto se usa **no se escribe acá**: lo imprime esa prueba, y el número que
# había escrito envejeció dos veces (decía 24 cuando ya eran 49). Lo que sí es
# de acá es de dónde sale el tope: la cadena más honda son las peleas, que
# cruzan al banco 1 con `jsl` y vuelven por los puentes.
PILA = 128


def cfg():
    """El `.cfg` de `ld65`: un área por banco, y cada segmento en la suya.

    Un área con `fill = yes` se rellena hasta el final, así que cada banco
    ocupa sus 32 KB en el archivo aunque su segmento no los llene, y un
    segmento que se pase hace fallar el link en vez de invadir el siguiente.
    Los `BANKnn` son opcionales porque cuántos se usan depende del cartucho.

    El `align = $8000` no mueve nada —cada segmento arranca al principio de su
    área, que ya está alineado a eso—, pero `ld65` exige que un segmento
    declare al menos la alineación de los `.align` que lleva adentro.
    """
    memoria = [
        # La RAM no va al archivo: se reparte por dirección, no por offset.
        'ZP:   start = $0000, size = $0100, type = rw, file = "";',
        'RAM:  start = $0100, size = $%04X, type = rw, file = "";'
        % (0x1F00 - PILA),
        # El banco 0: el código y las tablas, y la cabecera y los vectores
        # al final, donde los busca la consola.
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
        # El código a mano que vive afuera del banco 0.
        "FAR:      load = %s, type = ro, align = $8000;" % segmento_de(1),
    ]
    for banco in range(1, BANCOS - BANCOS_RESERVADOS):
        memoria.append("%s: start = $%02X8000, size = $8000, fill = yes;"
                       % (segmento_de(banco), banco))
        if banco >= PRIMER_BANCO:
            segmentos.append("%s: load = %s, type = ro, align = $8000, "
                             "optional = yes;"
                             % (segmento_de(banco), segmento_de(banco)))
    # Los dos reservados van igual al archivo, en cero: el cartucho mide 4 MB,
    # que es lo que dice la cabecera y lo que esperan los flash carts.
    memoria.append("RESERVADO: start = $%02X8000, size = $%X, fill = yes;"
                   % (BANCOS - BANCOS_RESERVADOS, 0x8000 * BANCOS_RESERVADOS))
    return ("# Generado por tools/ensamblado/bancos.py: el mapa de memoria de la ROM.\n"
            "MEMORY {\n%s\n}\nSEGMENTS {\n%s\n}\n"
            % ("\n".join("    " + m for m in memoria),
               "\n".join("    " + s for s in segmentos)))
