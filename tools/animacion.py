#!/usr/bin/env python3
"""El **dibujo** de una animación de batalla sobre el mapa.

Vive aparte de `snes_convert.py` por la misma razón que `imagen.py`: no es un
mapa. Es un dibujo suelto que hay que meter en la pantalla, y lo único que el
conversor y la referencia tienen que compartir es **exactamente dónde cae y de
qué color es cada pixel**. Los sonidos y los destellos de la misma animación
no están acá: ésos son `OP_ANIMATION` en `eventos.py`, y existen desde el
2026-09-11.

El presupuesto, que es de donde sale todo lo demás:

* La VRAM de sprites que le queda libre a un mapa son **101 tiles en el mapa 2
  y 162 en el 3**, que son los dos peores de los que muestran animaciones. Una
  caja de 96x96 son 144 tiles y no entra en el mapa 2.
* Un objeto de 32x32 lee cuatro tiles de cuatro filas seguidas de la grilla de
  nombres, así que **una fila de bloques son 64 tiles y cuatro objetos**, ni
  uno más. Cuatro objetos en dos por dos son 64x64 pixeles.
* Un cuadro de esos son 2 KB de DMA, y sube uno cada dos cuadros de consola,
  que es lo que dura un cuadro de animación en RM2k.

De ahí sale **la caja de 64x64, la misma para toda la ROM**. No es por
comodidad: que la caja no dependa del mapa es lo que deja que los 388
`ShowBattleAnimation` de los 81 mapas del juego compartan los cuadros ya
convertidos en el cartucho en vez de emitir una copia por mapa.

Y de ahí sale también lo que taro aceptó el 2026-09-12 —*"deberíamos poder
lograrlo si reducimos el tamaño de algunos de los efectos"*—: **la animación se
achica entera hasta entrar en la caja**, con su proporción, y cuánto se achicó
lo dice el conversor animación por animación. Las chicas casi no se tocan —una
de 96x96 queda en 64x64, el 67%— y las grandes de la intro sí: la 82 mide
536x416 y queda en 64x49, el 11%. Nada se dibuja mal en silencio: el criterio
es una cuenta, la emite el conversor y la referencia la repite.

Lo que se pierde, y está declarado en `assets/LIMITACIONES.md`:

* **La transparencia de una celda no existe.** Un objeto de la consola es opaco
  o no está. Lo que se hace es componer las celdas con su alfa en el cuadro y
  después **redondear el alfa**: un pixel con 128 o más queda, el resto no. Una
  celda que se desvanece desaparece al pasar la mitad, en vez de irse de a poco.
* **La animación no la tiñe el tinte de pantalla ni la alcanza el destello.**
  Lo primero es fiel: `Spriteset_Map::Update` le pone el tono al tilemap, a los
  personajes, al panorama y a las sombras, y a las animaciones no. Lo segundo es
  deuda, la misma que ya tiene el cartel: su paleta cae arriba de `SPRITE_CGRAM`.
* **Un objetivo sin fila de NPC, o con la fila escondida, no lleva
  animación.** En la consola no hay de dónde sacar su posición; en RM2k la
  animación se dibuja igual sobre un evento invisible.
* **`global` —la que RM2k repite en tres por tres para tapar la pantalla— no se
  dibuja.** Ninguna de las once de la intro la pide.
"""

# La caja, y los objetos de 32x32 con que se dibuja.
CAJA = 64
OBJ = 32
OBJ_LADO = OBJ // 8
GRILLA = 16                 # tiles por fila de la grilla de nombres de OAM
OBJETOS = (CAJA // OBJ) ** 2
TILES = 4 * GRILLA          # una fila de bloques: los cuatro objetos
COLORES = 15

# La hoja de `Battle`: cinco celdas por fila, de 96x96 —o de 128x128 si la
# animación es `large`, que en el ABL no lo es ninguna—. Es el `size` de
# `BattleAnimation::DrawAt`.
CELDA = 96
CELDA_GRANDE = 128
COLUMNAS = 5

# `character_height` de `BattleAnimationMap::DrawSingle`, y el centro de la
# pantalla de RM2k, que es donde caen las de alcance "pantalla".
ALTO_PERSONAJE = 24
PANTALLA_RM = (320, 240)
PANTALLA = (256, 224)

# Los tres valores de `Animation::Position`, que es lo que corre la animación
# para arriba o para abajo del objetivo.
POS_ARRIBA, POS_CENTRO, POS_ABAJO = 0, 1, 2
ALCANCE_PANTALLA = 1        # `Animation::Scope_screen`

# El alfa a partir del cual un pixel se dibuja. La mitad, y redondeando para
# arriba: un pixel medio a medio se queda. Los dos lados hacen esta cuenta.
ALFA_MINIMO = 128

_CACHE = {}


def hoja_de(renderer, anim):
    """La hoja de `Battle` de esta animación, o None si no tiene o no está."""
    import render_map
    nombre = anim.get("imagen") or ""
    if not nombre:
        return None
    carpeta = "Battle2" if anim.get("grande") else "Battle"
    path = render_map.find_resource(renderer.search_dirs, carpeta, nombre)
    return render_map.load_image(path) if path else None


def _celdas_vivas(anim, i):
    """Las celdas válidas del cuadro `i`, en el orden del LDB.

    `valid` viene en 1 de fábrica —liblcf, `AnimationCellData`— así que una
    celda sin el campo cuenta. Las inválidas son los huecos que deja el editor
    al borrar una celda del medio.
    """
    return [c for _k, c in sorted((anim["cuadros"][i] or {}).items())
            if c.get("valid", 1)]


def _lado(anim, celda):
    """Cuánto mide en pantalla una celda con su zoom, en pixeles de RM2k."""
    lado = CELDA_GRANDE if anim.get("grande") else CELDA
    return max(1, lado * celda.get("zoom", 100) // 100)


def caja_rm(anim):
    """El rectángulo que la animación entera ocupa en pixeles de RM2k,
    relativo a su ancla: (x0, y0, ancho, alto).

    Es la unión de todas las celdas de todos los cuadros, no la del cuadro más
    grande: la caja de la consola es una sola para toda la animación, así que
    un cuadro que se corra para un lado tiene que entrar igual.
    """
    x0 = y0 = None
    x1 = y1 = None
    for i in range(len(anim["cuadros"])):
        for celda in _celdas_vivas(anim, i):
            lado = _lado(anim, celda)
            cx, cy = celda.get("x", 0), celda.get("y", 0)
            a, b = cx - lado // 2, cy - lado // 2
            x0 = a if x0 is None else min(x0, a)
            y0 = b if y0 is None else min(y0, b)
            x1 = a + lado if x1 is None else max(x1, a + lado)
            y1 = b + lado if y1 is None else max(y1, b + lado)
    if x0 is None:
        return None
    return x0, y0, x1 - x0, y1 - y0


def tamano(ancho, alto):
    """A qué tamaño se achica una animación de `ancho` x `alto` para entrar en
    la caja, con su proporción.

    El denominador es el lado que más se pasa, y nunca menos que la caja: una
    animación que ya entra no se agranda. Va con enteros de los dos lados.
    """
    den = max(ancho, alto, CAJA)
    return max(1, ancho * CAJA // den), max(1, alto * CAJA // den)


def _pintar_cuadro(anim, hoja, i, caja):
    """Un cuadro en pixeles de RM2k, del tamaño de `caja`, con alfa.

    Es `BattleAnimation::DrawAt` sin la pantalla: cada celda sale de la hoja,
    se escala por su zoom, se le aplica el tono y la transparencia, y se compone
    centrada en su (x, y).
    """
    from PIL import Image
    import eventos
    x0, y0, ancho, alto = caja
    canvas = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    lado_hoja = CELDA_GRANDE if anim.get("grande") else CELDA
    for celda in _celdas_vivas(anim, i):
        cid = celda.get("cell_id", 0)
        sx, sy = (cid % COLUMNAS) * lado_hoja, (cid // COLUMNAS) * lado_hoja
        if sx + lado_hoja > hoja.width or sy + lado_hoja > hoja.height:
            continue            # una celda que la hoja no tiene: RM2k no dibuja
        trozo = hoja.crop((sx, sy, sx + lado_hoja, sy + lado_hoja))
        lado = _lado(anim, celda)
        if lado != lado_hoja:
            trozo = trozo.resize((lado, lado), Image.BILINEAR)
        tono = (celda.get("tone_red", 100), celda.get("tone_green", 100),
                celda.get("tone_blue", 100), celda.get("tone_gray", 100))
        if tono != (100, 100, 100, 100):
            trozo = _tenir(trozo, tono)
        opacidad = 100 - max(0, min(100, celda.get("transparency", 0)))
        if opacidad != 100:
            alfa = trozo.getchannel("A").point(
                lambda v: v * opacidad // 100)
            trozo.putalpha(alfa)
        canvas.alpha_composite(
            trozo, (celda.get("x", 0) - lado // 2 - x0,
                    celda.get("y", 0) - lado // 2 - y0))
    return canvas


def _tenir(trozo, tono):
    """El tono de una celda, con la misma cuenta que el tinte de pantalla.

    `eventos.tenir` trabaja sobre los quince bits de la consola, que es donde
    la comparación mira: teñir los ocho del PNG y recortar después daría otro
    número, y sería una diferencia que los dos lados no comparten.
    """
    import eventos
    from PIL import Image
    salida = Image.new("RGBA", trozo.size)
    memo = {}
    datos = []
    for r, g, b, a in trozo.convert("RGBA").get_flattened_data():
        clave = (r >> 3, g >> 3, b >> 3)
        if clave not in memo:
            p = eventos.tenir(clave[0] | (clave[1] << 5) | (clave[2] << 10),
                              tono)
            memo[clave] = ((p & 0x1F) << 3, ((p >> 5) & 0x1F) << 3,
                           ((p >> 10) & 0x1F) << 3)
        datos.append(memo[clave] + (a,))
    salida.putdata(datos)
    return salida


def convertir(anim, hoja):
    """La animación lista para las dos puntas, o None si no se puede dibujar.

    Devuelve un diccionario con:

      `cuadros`  por cada cuadro de RM2k, la caja de 64x64 como índices de la
                 paleta corridos uno: el 0 es el transparente de la consola.
      `paleta`   sus quince colores de 15 bits, elegidos **sobre todos los
                 cuadros de una**: la paleta se sube una sola vez al empezar.
      `ancla`    dónde cae adentro de la caja el punto que RM2k pone sobre el
                 objetivo. La ROM le resta esto a la posición del objetivo y
                 le sale la esquina de la caja.
      `tam`      a cuánto quedó achicada, y `caja_rm` de cuánto venía.
    """
    caja = caja_rm(anim)
    if caja is None or hoja is None:
        return None
    from PIL import Image
    import titulo
    x0, y0, ancho, alto = caja
    ta, tal = tamano(ancho, alto)
    ox, oy = (CAJA - ta) // 2, (CAJA - tal) // 2
    cuadros = []
    for i in range(len(anim["cuadros"])):
        chico = _pintar_cuadro(anim, hoja, i, caja).resize(
            (ta, tal), Image.LANCZOS)
        entero = Image.new("RGBA", (CAJA, CAJA), (0, 0, 0, 0))
        entero.paste(chico, (ox, oy))
        cuadros.append(entero)
    # Los colores de todos los cuadros juntos, a quince. `titulo.reducir` no
    # promedia, así que no inventa un color que haya que volver a cuantizar, y
    # da lo mismo en el conversor y en la referencia.
    pixeles = []
    for entero in cuadros:
        for r, g, b, a in entero.get_flattened_data():
            if a >= ALFA_MINIMO:
                pixeles.append((r >> 3, g >> 3, b >> 3))
    if not pixeles:
        return None
    paleta, mapa = titulo.reducir(pixeles, COLORES)
    donde = {color: i + 1 for i, color in enumerate(paleta)}
    indices = []
    for entero in cuadros:
        datos = entero.get_flattened_data()
        indices.append([
            [donde[mapa[(datos[y * CAJA + x][0] >> 3,
                         datos[y * CAJA + x][1] >> 3,
                         datos[y * CAJA + x][2] >> 3)]]
             if datos[y * CAJA + x][3] >= ALFA_MINIMO else 0
             for x in range(CAJA)]
            for y in range(CAJA)])
    return {
        "cuadros": indices,
        "paleta": paleta,
        "ancla": (ox + (-x0) * ta // ancho, oy + (-y0) * tal // alto),
        "tam": (ta, tal),
        "caja_rm": (ancho, alto),
        "alcance": anim.get("alcance", 0),
        "posicion": anim.get("posicion", POS_CENTRO),
    }


def de_numero(renderer, numero):
    """La animación `numero` convertida, cacheada por proceso.

    Convertir una son unos cuantos `resize` grandes y el conversor la pide una
    vez por mapa que la muestre; la referencia, una vez por cuadro que dibuje.
    """
    import eventos
    if numero in _CACHE:
        return _CACHE[numero]
    anim = eventos.ANIMACIONES.get(numero)
    salida = convertir(anim, hoja_de(renderer, anim)) if anim else None
    _CACHE[numero] = salida
    return salida


def ancla_rom(info):
    """El ancla tal como la lleva la tabla de la ROM: (ax, ay).

    Se le hornea la corrida vertical de `Animation::Position`, que es fija por
    animación, así que la consola sólo tiene que restar. Con alcance "pantalla"
    no va ninguna corrida: `DrawSingle` dibuja en el centro sin preguntarle
    nada al objetivo.
    """
    ax, ay = info["ancla"]
    if info["alcance"] == ALCANCE_PANTALLA:
        return ax, ay
    corrida = {POS_ARRIBA: -(ALTO_PERSONAJE // 2), POS_CENTRO: 0,
               POS_ABAJO: ALTO_PERSONAJE // 2}[info["posicion"]]
    return ax, ay + ALTO_PERSONAJE // 2 - corrida


def esquina(info, px, py):
    """Dónde cae la esquina de la caja, para un objetivo parado en el pixel
    (px, py) de su celda del mapa.

    Con alcance "pantalla" el resultado es de pantalla y no del mapa: ahí no
    hay cámara que restar, que es lo que hace `DrawAt(screen_width / 2, ...)`.
    Con el otro, es `GetScreenX()` —el centro de la celda— y `GetScreenY(false)`
    —sus pies— en pixeles del mapa, y la cámara se resta después. La ROM hace
    esta misma cuenta en `animacion_dibujo_oam`.
    """
    ax, ay = ancla_rom(info)
    if info["alcance"] == ALCANCE_PANTALLA:
        return PANTALLA[0] // 2 - ax, PANTALLA[1] // 2 - ay
    return px + 8 - ax, py + 16 - ay


def celdas(cuadro):
    """Un cuadro cortado en tiles de 8x8, en el orden en que los numera OAM.

    Los cuatro objetos entran en una fila de bloques —64 tiles— y el objeto `o`
    arranca en `o * 4`; adentro de él, el tile (tx, ty) está `ty` filas de la
    grilla más adelante. Es la misma aritmética de `imagen.celdas`, que es de
    donde salió.

    En pantalla los objetos van en dos por dos: el `o` en
    `(o % 2 * 32, o // 2 * 32)` de la caja.
    """
    salida = {}
    for o in range(OBJETOS):
        arranca = (o % 4) * OBJ_LADO
        base_x, base_y = (o % 2) * OBJ, (o // 2) * OBJ
        for ty in range(OBJ_LADO):
            for tx in range(OBJ_LADO):
                celda = tuple(
                    tuple(cuadro[base_y + ty * 8 + py][base_x + tx * 8 + px]
                          for px in range(8))
                    for py in range(8))
                salida[arranca + ty * GRILLA + tx] = celda
    return salida


def render(info, cuadro):
    """El cuadro como se ve en la pantalla: una imagen RGBA de 64x64 para
    pegar donde diga `ancla_en_pantalla`."""
    from PIL import Image
    colores = [(0, 0, 0, 0)] + [(r << 3, g << 3, b << 3, 255)
                                for r, g, b in info["paleta"]]
    salida = Image.new("RGBA", (CAJA, CAJA))
    salida.putdata([colores[i] for fila in info["cuadros"][cuadro]
                    for i in fila])
    return salida


def informe(numero, info):
    """Los números que justifican el reparto, para que la receta los imprima."""
    ancho, alto = info["caja_rm"]
    ta, tal = info["tam"]
    return {
        "animacion": numero,
        "cuadros": len(info["cuadros"]),
        "original": (ancho, alto),
        "caja": (ta, tal),
        "porciento": 100 * ta // ancho,
        "colores": len(info["paleta"]),
        "bytes": len(info["cuadros"]) * TILES * 32,
    }
