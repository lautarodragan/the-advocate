#!/usr/bin/env python3
"""Arma las maquetas de las fuentes candidatas: el menú de pausa y la
ventana de estado de la pelea, dibujados con cada hoja de `hojas/`.

    maquetas.py <salida> --game-dir <juego> [--comparar <dir>]

No es el juego: son imágenes para mirar y para la ROM de prueba
(`just fuentes`). Las hojas son la fuente de verdad —se editan a mano, ver
el `LEEME.md` de acá— y esto se vuelve a correr sin tocar código.

**Qué arma.** Para cada candidata, las dos pantallas en su resolución:
256x224 las de baja, 512x224 las de alta. Y la referencia, el RM2k de 320x240
con la fuente de hoy y su disposición. Las candidatas **no** escalan la
disposición de RM2k: la empaquetan —cada columna empieza donde termina la
anterior más un hueco fijo, medido con la fuente— y miden si entra. Así la
respuesta a "¿entra la disposición de 320 en 256?" sale de la fuente y no
de un factor de escala. Los anchos se miden con los textos más largos del
juego —los nombres y títulos de todos los actores con cara, los estados,
los comandos—, no sólo con los del grupo que se dibuja, y `medidas.txt` lo
dice.

Lo que no es texto —ventanas, cursores y caras— se dibuja como RM2k, con
`rm2k-render`, en pixeles de baja; en alta, cada pixel ocupa dos. La sombra
del texto la agrega esto, como la ROM: corrida un pixel de baja a la
derecha y uno abajo.

Con `--comparar`, además, deja ahí las hojas de comparación: todas al mismo
tamaño físico y los recortes ×4 de una fila.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import hoja  # noqa: E402

DATOS = os.path.join(AQUI, os.pardir, os.pardir, "data", "db")

# Las candidatas, en el orden de la ROM. `k` es cuántas columnas de la
# pantalla ocupa un pixel de baja: 1 en baja, 2 en alta.
CANDIDATAS = [
    ("baja-ancho-variable", 1),
    ("alta-ancho-fijo", 2),
    ("alta-ancho-variable", 2),
]
ALTO = 224

# **Los huecos del empaquetado**, en pixeles de baja. Entre dos bloques de
# texto que RM2k separa por posición —el nombre y el título, el estado y
# los HP—, y entre el nivel y el estado. Son el aire que queda además del
# avance del último glifo; RM2k deja más, y por eso su disposición mide 320.
HUECO = 6
# Lo que la ventana de comandos deja a la derecha del texto más largo: el
# cursor de RM2k es un poco más ancho que el texto.
HOLGURA_COMANDOS = 4
BORDE = 8
CARA = 48
FILA_MENU = 58           # 48 de la cara y 10 de aire: Window_MenuStatus
ALTO_PELEA = 80          # las ventanas de abajo de la pelea de RM2k

# Lo que la ROM dibuja hoy, para compararlo: la maqueta del menú de
# `menu-modo-5` (sale de `rm2k-snes-screens`) y la golden de la pelea. Con
# la caja de la fila de Kersh, para los recortes.
HOY = {
    "menu": (os.path.join(AQUI, os.pardir, "menu-modo-5", "maqueta", "01-hoy.png"),
             (40, 0, 256, 60)),
    "pelea": (os.path.join(AQUI, os.pardir, os.pardir, "pruebas", "golden", "tanda",
                           "batalla.png"), (0, 124, 256, 152)),
}

# El grupo que se dibuja: el de las maquetas del menú (la captura de Tatú).
GRUPO = [
    # actor, nivel, hp, sp, exp, próximo
    (11, 20, 168, 168, 14522, 16708),
    (12, 15, 127, 127, 6473, 7750),
    (13, 15, 127, 127, 6473, 7750),
]


def cargar(nombre):
    with open(os.path.join(DATOS, nombre + ".json"), encoding="utf-8") as f:
        return json.load(f)


class Textos:
    def __init__(self, nombres, titulos, estados, comandos):
        self.nombres, self.titulos, self.estados = nombres, titulos, estados
        self.comandos = comandos


class Juego:
    """Los textos que el menú y la pelea pueden mostrar."""

    def __init__(self, juego):
        self.dir = juego
        actores = cargar("actors")
        self.actores = {a["id"]: a for a in actores}
        terminos = cargar("terms")
        self.t = terminos
        # Los que pueden estar en el grupo: los que tienen cara del juego.
        # Los de prueba y los del RTP no la tienen.
        con_cara = [a for a in actores if a["face_name"] == "ABLFaces"]
        self.nombres = sorted({a["name"] for a in con_cara})
        self.titulos = sorted({a["title"] for a in con_cara})
        self.tecnicas = sorted({a["skill_name"] for a in con_cara
                                if a["rename_skill"] and a["skill_name"]})
        self.estados = sorted({e["name"] for e in cargar("states") if e["name"]})
        self.menu = [terminos["command_item"], terminos["command_skill"],
                     terminos["menu_equipment"], terminos["menu_save"],
                     terminos["menu_quit"]]
        self.normal = terminos["normal_status"]

    def peor(self):
        return Textos(self.nombres, self.titulos, self.estados,
                      self.todos_los_comandos_pelea())

    def del_grupo(self):
        actores = [self.actores[g[0]] for g in GRUPO]
        return Textos([a["name"] for a in actores], [a["title"] for a in actores],
                      [self.normal], self.comandos_pelea(GRUPO[0][0]))

    def comandos_pelea(self, actor):
        a = self.actores[actor]
        tecnica = a["skill_name"] if a["rename_skill"] and a["skill_name"] \
            else self.t["command_skill"]
        return [self.t["command_attack"], tecnica, self.t["command_defend"],
                self.t["command_item"]]

    def todos_los_comandos_pelea(self):
        return [self.t["command_attack"], self.t["command_defend"],
                self.t["command_item"], self.t["command_skill"]] + self.tecnicas


class Piezas:
    """Lo que dibuja `rm2k-render`: ventanas, cursores, colores y caras,
    pedido todo junto y guardado por tamaño."""

    def __init__(self, juego):
        self.sistema = os.path.join(juego, "System", "ablskin.png")
        self.caras_png = os.path.join(juego, "FaceSet", "ABLFaces.png")
        self.pedidos = []
        self.hechas = {}

    def pedir(self, clave, pedido):
        if clave not in self.hechas and clave not in [c for c, _ in self.pedidos]:
            self.pedidos.append((clave, pedido))

    def ventana(self, w, h):
        self.pedir(("ventana", w, h), {"system_file": self.sistema, "draw": "window",
                                       "width": w, "height": h, "message_stretch": 0})
        return ("ventana", w, h)

    def cursor(self, w, h):
        self.pedir(("cursor", w, h), {"system_file": self.sistema, "draw": "cursor",
                                      "width": w, "height": h})
        return ("cursor", w, h)

    def resolver(self):
        pedidos = self.pedidos + [
            (("sombra",), {"system_file": self.sistema, "draw": "shadow"})] + [
            (("color", c), {"system_file": self.sistema, "draw": "text_color", "color": c})
            for c in range(20)]
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "s.json"), "w") as f:
                json.dump([p for _, p in pedidos], f)
            subprocess.run(["rm2k-render", "system", "--request", os.path.join(tmp, "s.json"),
                            "--out", os.path.join(tmp, "s")], check=True,
                           stdout=subprocess.DEVNULL)
            for i, (clave, _) in enumerate(pedidos):
                self.hechas[clave] = Image.open(os.path.join(tmp, "s", "%d.png" % i)).convert("RGBA")
            caras = sorted({a["face_index"] for a in JUEGO.actores.values()
                            if a["face_name"] == "ABLFaces"})
            with open(os.path.join(tmp, "c.json"), "w") as f:
                json.dump([{"faceset_file": self.caras_png, "index": i} for i in caras], f)
            subprocess.run(["rm2k-render", "face", "--request", os.path.join(tmp, "c.json"),
                            "--out", os.path.join(tmp, "c")], check=True,
                           stdout=subprocess.DEVNULL)
            for n, i in enumerate(caras):
                self.hechas[("cara", i)] = Image.open(
                    os.path.join(tmp, "c", "%d.png" % n)).convert("RGBA")
        self.pedidos = []


class Escena:
    """Una pantalla: ventanas, cursores y caras en pixeles de baja —que en
    alta ocupan `k` columnas cada uno— y corridas de texto en pixeles de la
    pantalla, con la fuente de la hoja."""

    def __init__(self, ancho, alto, k, fuente):
        self.ancho, self.alto, self.k, self.f = ancho, alto, k, fuente
        self.fondo = []       # (clave de pieza, x, y), x en pixeles de pantalla
        self.caras = []       # (índice, x, y)
        self.textos = []      # (x, y, texto, color)

    def ventana(self, x, y, w, h):
        assert x % self.k == 0 and w % self.k == 0, (x, w)
        self.fondo.append((PIEZAS.ventana(w // self.k, h), x, y))

    def cursor(self, x, y, w, h):
        w -= w % self.k
        x -= x % self.k
        self.fondo.append((PIEZAS.cursor(w // self.k, h), x, y))

    def cara(self, indice, x, y):
        self.caras.append((indice, x - x % self.k, y))

    def texto(self, x, y, texto, color=0, derecha=False):
        if derecha:
            x -= self.f.largo(texto)
        self.textos.append((x, y, texto, color))
        return x + self.f.largo(texto)

    def caja_de_caras(self):
        """Dónde están las caras, en pixeles de pantalla: x0, x1, y0, y1."""
        if not self.caras:
            return None
        return (min(x for _, x, _ in self.caras),
                max(x for _, x, _ in self.caras) + CARA * self.k,
                min(y for _, _, y in self.caras),
                max(y for _, _, y in self.caras) + CARA)

    def dibujar(self):
        out = Image.new("RGBA", (self.ancho, self.alto), (0, 0, 0, 255))

        def ancha(im):
            return im if self.k == 1 else im.resize((im.width * self.k, im.height), Image.NEAREST)

        for clave, x, y in self.fondo:
            out.alpha_composite(ancha(PIEZAS.hechas[clave]), (x, y))
        for indice, x, y in self.caras:
            out.alpha_composite(ancha(PIEZAS.hechas[("cara", indice)]), (x, y))
        pix = out.load()
        sombra = PIEZAS.hechas[("sombra",)].getpixel((0, 0))
        for x, y, texto, color in self.textos:
            bloque = PIEZAS.hechas[("color", color)]
            for c in texto:
                # Como `Font::Render`: la sombra de la letra y después la
                # letra, una letra por vez. El color de una fila del glifo
                # es uno solo: el degradé del System es vertical.
                for capa in ("sombra", "letra"):
                    for gx, gy in self.f.glifo(c):
                        if capa == "sombra":
                            px, py, col = x + gx + self.k, y + gy + 1, sombra
                        else:
                            px, py, col = x + gx, y + gy, bloque.getpixel((4, 4 + gy))
                        if 0 <= px < self.ancho and 0 <= py < self.alto and col[3]:
                            pix[px, py] = col
                x += self.f.avance(c)
        return out.convert("RGB")


def digitos(f, n):
    return n * max(f.avance(d) for d in "0123456789")


# --- el menú de pausa -------------------------------------------------------

def menu_rm2k(f, alto=240):
    """El menú de RM2k a 320, con la disposición de easyrpg (Scene_Menu): la
    que la maqueta de Ñacurutú comparó con la captura del RPG_RT."""
    e = Escena(320, alto, 1, f)
    e.ventana(0, 0, 88, 96)
    e.ventana(0, alto - 32, 88, 32)
    e.ventana(88, 0, 232, alto)
    e.cursor(8, 8 + 2 * 16, 72, 16)
    e.cursor(88 + 8 + 52, 8, 168, 48)
    for i, c in enumerate(JUEGO.menu):
        e.texto(8, 8 + 16 * i + 2, c, 3 if i == 3 else 0)
    e.texto(80, alto - 32 + 10, JUEGO.t["gold"], 1, derecha=True)
    e.texto(68, alto - 32 + 10, "0", 0, derecha=True)
    for i, (actor, nivel, hp, sp, ex, prox) in enumerate(GRUPO):
        a = JUEGO.actores[actor]
        e.cara(a["face_index"], 96, 8 + i * FILA_MENU)
        cx, y = 152, 8 + i * FILA_MENU + 2
        e.texto(cx, y, a["name"])
        e.texto(cx + 88, y, a["title"])
        e.texto(cx, y + 16, JUEGO.t["lvl_short"], 1)
        e.texto(cx + 24, y + 16, str(nivel), derecha=True)
        e.texto(cx + 42, y + 16, JUEGO.normal)
        e.texto(cx, y + 32, JUEGO.t["exp_short"], 1)
        e.texto(cx + 12, y + 32, "%6d/%6d" % (ex, prox))
        for dy, term, v in ((16, "hp_short", hp), (32, "sp_short", sp)):
            hx = cx + 106
            e.texto(hx, y + dy, JUEGO.t[term], 1)
            e.texto(hx + 30, y + dy, str(v), derecha=True)
            e.texto(hx + 30, y + dy, "/")
            e.texto(hx + 54, y + dy, str(v), derecha=True)
    return e, None


def medir_menu(f, k, tx, apretado=False):
    """Cuánto mide el menú empaquetado con la fuente `f` y los textos
    `tx`, en pixeles de pantalla.

    `apretado` son tres concesiones a la disposición de RM2k, las más
    baratas que se encontraron: 4 de aire a cada lado de la cara en vez de
    8, la ventana de comandos sin la holgura del cursor, y la experiencia
    en campos de 5 cifras y no de 6 —RM2k reserva 6, y un actor de ABL
    pasa de 99.999 recién cerca del nivel 40—."""
    t = JUEGO.t
    d, hueco, borde = (lambda n: digitos(f, n)), HUECO * k, BORDE * k
    margen = (4 if apretado else BORDE) * k
    holgura = 0 if apretado else HOLGURA_COMANDOS * k
    cifras_ex = 5 if apretado else 6
    wc = borde + max(f.largo(c) for c in JUEGO.menu) + holgura + borde
    wc += -wc % k
    izq = {
        "nombre": max(f.largo(n) for n in tx.nombres),
        "nivel y estado": f.largo(t["lvl_short"]) + d(2) + hueco
        + max(f.largo(s) for s in tx.estados),
        "exp": f.largo(t["exp_short"]) + d(cifras_ex) + f.largo("/") + d(cifras_ex),
    }
    der = {
        "título": max(f.largo(n) for n in tx.titulos),
        "hp": f.largo(t["hp_short"]) + d(3) + f.largo("/") + d(3),
    }
    texto = max(izq.values()) + hueco + max(der.values())
    necesario = wc + margen + CARA * k + margen + texto + borde
    return {"comandos": wc, "margen de la cara": margen, "cifras de exp": cifras_ex,
            "izquierda": izq, "derecha": der,
            "texto del grupo": texto, "necesario": necesario}


def elegir(medir, f, k, ancho):
    """Mide con los textos más largos del juego y con los del grupo que se
    dibuja, como RM2k y apretado; dibuja con el primero que entre, en ese
    orden, y si ninguno entra, con el último: el texto se choca, y eso es
    lo que se ve."""
    casos = {}
    for apretado in (False, True):
        for nombre, tx in (("peor caso", JUEGO.peor()),
                           ("con el grupo dibujado", JUEGO.del_grupo())):
            if apretado:
                nombre += ", apretado"
            casos[nombre] = medir(f, k, tx, apretado)
    elegido = next((n for n, c in casos.items() if c["necesario"] <= ancho), nombre)
    return casos[elegido], dict(casos, pantalla=ancho, **{"se dibuja con": elegido})


def menu_empaquetado(f, k, ancho):
    """El menú de RM2k con la fuente `f`, empaquetado: devuelve la escena y
    lo que mide."""
    t = JUEGO.t
    d, hueco, borde = (lambda n: digitos(f, n)), HUECO * k, BORDE * k
    m, medidas = elegir(medir_menu, f, k, ancho)
    wc, der = m["comandos"], m["derecha"]
    margen, cifras_ex = m["margen de la cara"], m["cifras de exp"]

    e = Escena(ancho, ALTO, k, f)
    e.ventana(0, 0, wc, 96)
    e.ventana(0, ALTO - 32, wc, 32)
    e.ventana(wc, 0, ancho - wc, ALTO)
    e.cursor(borde, 8 + 2 * 16, wc - 2 * borde, 16)
    cx = wc + margen + CARA * k + margen
    e.cursor(cx - 4 * k, 8, ancho - 4 * k - (cx - 4 * k), 48)
    for i, c in enumerate(JUEGO.menu):
        e.texto(borde, 8 + 16 * i + 2, c, 3 if i == 3 else 0)
    e.texto(wc - borde, ALTO - 32 + 10, t["gold"], 1, derecha=True)
    e.texto(wc - borde - f.largo(t["gold"]), ALTO - 32 + 10, "0", 0, derecha=True)
    # El bloque de la derecha, pegado al borde de adentro de la ventana: lo
    # que sobre queda entre los dos bloques.
    xd = ancho - borde - max(der.values())
    for i, (actor, nivel, hp, sp, ex, prox) in enumerate(GRUPO):
        a = JUEGO.actores[actor]
        e.cara(a["face_index"], wc + margen, 8 + i * FILA_MENU)
        y = 8 + i * FILA_MENU + 2
        e.texto(cx, y, a["name"])
        e.texto(xd, y, a["title"])
        x = e.texto(cx, y + 16, t["lvl_short"], 1)
        e.texto(x + d(2), y + 16, str(nivel), derecha=True)
        e.texto(x + d(2) + hueco, y + 16, JUEGO.normal)
        x = e.texto(cx, y + 32, t["exp_short"], 1)
        e.texto(x + d(cifras_ex), y + 32, str(ex), derecha=True)
        x = e.texto(x + d(cifras_ex), y + 32, "/")
        e.texto(x + d(cifras_ex), y + 32, str(prox), derecha=True)
        for dy, term, v in ((16, "hp_short", hp), (32, "sp_short", sp)):
            x = e.texto(xd, y + dy, t[term], 1)
            e.texto(x + d(3), y + dy, str(v), derecha=True)
            x = e.texto(x + d(3), y + dy, "/")
            e.texto(x + d(3), y + dy, str(v), derecha=True)
    return e, medidas


# --- la pelea ---------------------------------------------------------------

def pelea_rm2k(f, alto=240):
    """Las ventanas de abajo de la pelea de RM2k 2000 mientras se elige qué
    hace un actor: la de estado (244) y la de comandos (76), con las
    posiciones de easyrpg (Window_BattleStatus, Scene_Battle_Rpg2k)."""
    e = Escena(320, alto, 1, f)
    y0 = alto - ALTO_PELEA
    e.ventana(0, y0, 244, ALTO_PELEA)
    e.ventana(244, y0, 76, ALTO_PELEA)
    e.cursor(4, y0 + 8, 236, 16)
    e.cursor(244 + 8, y0 + 8 + 16, 60, 16)
    for i, (actor, nivel, hp, sp, ex, prox) in enumerate(GRUPO):
        a = JUEGO.actores[actor]
        y = y0 + 8 + 2 + 16 * i
        x = 8                               # border_x 4 y contents x 4
        e.texto(x, y, a["name"])
        e.texto(x + 82, y, JUEGO.normal)    # 86 con 3 dígitos, menos 4
        hx = x + 178 - 4 - 36
        e.texto(hx, y, JUEGO.t["hp_short"], 1)
        e.texto(hx + 12 + 18, y, str(hp), derecha=True)
        e.texto(hx + 30, y, "/")
        e.texto(hx + 36 + 18, y, str(hp), derecha=True)
        sx = x + 220 - 4 - 18
        e.texto(sx, y, JUEGO.t["sp_short"], 1)
        e.texto(sx + 12 + 18, y, str(sp), derecha=True)
    for i, c in enumerate(JUEGO.comandos_pelea(GRUPO[0][0])):
        e.texto(244 + 8, y0 + 8 + 2 + 16 * i, c)
    return e, None


def medir_pelea(f, k, tx, apretado=False):
    t = JUEGO.t
    d, hueco, borde = (lambda n: digitos(f, n)), HUECO * k, BORDE * k
    # Apretada, la pelea sólo pierde la holgura del cursor: es la única de
    # las tres concesiones del menú que tiene.
    holgura = 0 if apretado else HOLGURA_COMANDOS * k
    wcmd = borde + max(f.largo(c) for c in tx.comandos) + holgura + borde
    wcmd += -wcmd % k
    columnas = {
        "nombre": max(f.largo(n) for n in tx.nombres),
        "estado": max(f.largo(s) for s in tx.estados),
        "hp": f.largo(t["hp_short"]) + d(3) + f.largo("/") + d(3),
        "sp": f.largo(t["sp_short"]) + d(3),
    }
    necesario = borde + sum(columnas.values()) + 3 * hueco + borde + wcmd
    return {"comandos": wcmd, "columnas": columnas, "necesario": necesario}


def pelea_empaquetada(f, k, ancho):
    t = JUEGO.t
    d, hueco, borde = (lambda n: digitos(f, n)), HUECO * k, BORDE * k
    m, medidas = elegir(medir_pelea, f, k, ancho)
    wcmd, columnas = m["comandos"], m["columnas"]

    e = Escena(ancho, ALTO, k, f)
    y0 = ALTO - ALTO_PELEA
    ws = ancho - wcmd
    ws -= ws % k
    e.ventana(0, y0, ws, ALTO_PELEA)
    e.ventana(ws, y0, ancho - ws, ALTO_PELEA)
    e.cursor(4 * k, y0 + 8, ws - 8 * k, 16)
    e.cursor(ws + borde, y0 + 8 + 16, ancho - ws - 2 * borde, 16)
    # El nombre y el estado desde la izquierda; los SP contra el borde de
    # la derecha y los HP antes: lo que sobre queda entre el estado y los HP.
    xe = borde + columnas["nombre"] + hueco
    xs = ws - borde - columnas["sp"]
    xh = xs - hueco - columnas["hp"]
    for i, (actor, nivel, hp, sp, ex, prox) in enumerate(GRUPO):
        a = JUEGO.actores[actor]
        y = y0 + 8 + 2 + 16 * i
        e.texto(borde, y, a["name"])
        e.texto(xe, y, JUEGO.normal)
        x = e.texto(xh, y, t["hp_short"], 1)
        e.texto(x + d(3), y, str(hp), derecha=True)
        x = e.texto(x + d(3), y, "/")
        e.texto(x + d(3), y, str(hp), derecha=True)
        x = e.texto(xs, y, t["sp_short"], 1)
        e.texto(x + d(3), y, str(sp), derecha=True)
    for i, c in enumerate(JUEGO.comandos_pelea(GRUPO[0][0])):
        e.texto(ws + borde, y0 + 8 + 2 + 16 * i, c)
    return e, medidas


# --- la salida --------------------------------------------------------------

def vista_de_emulador(im):
    """Como la muestra un emulador: 512x448, las de 256 con cada pixel
    2x2 y las de 512 con cada línea dos veces."""
    return im.resize((512, 448), Image.NEAREST)


def rotulo(im, texto, ancho=None):
    ancho = ancho or im.width
    out = Image.new("RGB", (ancho, im.height + 28), (24, 24, 32))
    out.paste(im, (0, 28))
    ImageDraw.Draw(out).text((6, 6), texto, fill=(230, 230, 230))
    return out


def comparar(destino, imagenes):
    """`imagenes`: [(nombre, imagen, es_rm2k)]. Todas al mismo tamaño
    físico: las de la consola a 1024x896 (la vista de emulador ×2) y las de
    RM2k ×3 (960x720), como la hoja de Ñacurutú."""
    os.makedirs(destino, exist_ok=True)
    grandes = []
    for nombre, im, es_rm2k in imagenes:
        if es_rm2k:
            g = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
        else:
            g = vista_de_emulador(im).resize((1024, 896), Image.NEAREST)
        grandes.append(rotulo(g, nombre, 1024))
    columnas = 2
    filas = (len(grandes) + columnas - 1) // columnas
    alto = max(g.height for g in grandes)
    hoja_c = Image.new("RGB", (columnas * 1024 + 8, filas * (alto + 8)), (24, 24, 32))
    for i, g in enumerate(grandes):
        hoja_c.paste(g, ((i % columnas) * 1032, (i // columnas) * (alto + 8)))
    return hoja_c


def recorte(im, es_rm2k, caja_baja):
    """Un recorte ×4 sobre la vista de emulador (un pixel de baja, 8x8).
    `caja_baja` en pixeles de baja de una pantalla de 256 de ancho; en
    RM2k, en sus pixeles de 320, a ×8."""
    x0, y0, x1, y1 = caja_baja
    if es_rm2k:
        c = im.crop((x0, y0, x1, y1))
        return c.resize((c.width * 8, c.height * 8), Image.NEAREST)
    v = vista_de_emulador(im)
    c = v.crop((x0 * 2, y0 * 2, x1 * 2, y1 * 2))
    return c.resize((c.width * 4, c.height * 4), Image.NEAREST)


def vista_de_hoja(f, ruta_salida):
    """La hoja con la letra arriba de cada celda, ×4 (en alta, ×2 de ancho
    por ×4 de alto, para que se vea con la forma de la pantalla)."""
    im = Image.open(f).convert("RGB")
    fuente = hoja.Fuente(f)
    ex = 2 if fuente.ancho == 16 else 4
    grande = im.resize((im.width * ex, im.height * 4), Image.NEAREST)
    paso_y = (hoja.ALTO + 1) * 4
    out = Image.new("RGB", (grande.width, grande.height + 12 * (len(hoja.CARACTERES) // 16 + 1)),
                    (24, 24, 32))
    d = ImageDraw.Draw(out)
    for fila in range(6):
        y = fila * (paso_y + 12)
        out.paste(grande.crop((0, fila * paso_y, grande.width, (fila + 1) * paso_y + 4)), (0, y + 12))
        for col in range(16):
            i = fila * 16 + col
            if i < len(hoja.CARACTERES):
                d.text((col * (fuente.ancho + 1) * ex + 4, y), repr(hoja.CARACTERES[i])[1:-1],
                       fill=(255, 220, 120))
    out.save(ruta_salida)


def escribir_medidas(ruta, filas):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("Lo que mide cada candidata, en pixeles de su pantalla (en alta, la\n"
                "mitad es en pixeles de baja). El peor caso, con los textos más largos\n"
                "del juego —nombres y títulos de los actores con cara, estados y\n"
                "comandos—; y con los del grupo que se dibuja (Kersh, Core y Manta).\n"
                "\"Apretado\" son tres concesiones a la disposición de RM2k: ver\n"
                "`medir_menu` en maquetas.py. Se dibuja con el primer caso que entra.\n\n")
        for nombre, que, m in filas:
            pantalla = m["pantalla"]
            f.write("%s, %s, en %d (dibujado: %s):\n" % (
                nombre, que, pantalla, m["se dibuja con"]))
            for caso, c in m.items():
                if caso in ("pantalla", "se dibuja con"):
                    continue
                sobra = pantalla - c["necesario"]
                f.write("  %s: necesita %d -> %s\n" % (
                    caso, c["necesario"],
                    "entra, sobran %d" % sobra if sobra >= 0 else "NO entra, falta %d" % -sobra))
                for clave, v in c.items():
                    if clave != "necesario":
                        f.write("      %s: %s\n" % (clave, v))
            f.write("\n")


def main():
    global JUEGO, PIEZAS
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("salida")
    p.add_argument("--game-dir", required=True)
    p.add_argument("--comparar")
    args = p.parse_args()
    os.makedirs(args.salida, exist_ok=True)
    JUEGO = Juego(args.game_dir)
    PIEZAS = Piezas(args.game_dir)

    hojas = os.path.join(AQUI, "hojas")
    rm2k = hoja.Fuente(os.path.join(hojas, "rm2k.png"))
    escenas = [("rm2k-menu", menu_rm2k(rm2k)), ("rm2k-pelea", pelea_rm2k(rm2k))]
    for nombre, k in CANDIDATAS:
        f = hoja.Fuente(os.path.join(hojas, nombre + ".png"))
        if f.ancho != 8 * k:
            sys.exit("%s: celdas de %d, y una hoja de %s las tiene de %d"
                     % (nombre, f.ancho, "alta" if k == 2 else "baja", 8 * k))
        ancho = 256 * k
        escenas.append((nombre + "-menu", menu_empaquetado(f, k, ancho)))
        escenas.append((nombre + "-pelea", pelea_empaquetada(f, k, ancho)))
    PIEZAS.resolver()

    # La vara: la fuente de hoy medida igual. Empaquetada, la disposición
    # de RM2k mide justo sus 320, y eso dice que los huecos de acá son los
    # de RM2k y no unos más generosos.
    medidas = [("rm2k (la de hoy, empaquetada igual)", que,
                elegir(medir, rm2k, 1, 320)[1])
               for que, medir in (("menu", medir_menu), ("pelea", medir_pelea))]
    pantallas, imagenes = [], {}
    for nombre, (escena, m) in escenas:
        im = escena.dibujar()
        imagenes[nombre] = im
        ruta = os.path.join(args.salida, nombre + ".png")
        im.save(ruta)
        if m:
            medidas.append((nombre.rsplit("-", 1)[0], nombre.rsplit("-", 1)[1], m))
            # Para la ROM: dónde están las caras, que van en sprites.
            with open(ruta[:-4] + ".json", "w") as f:
                json.dump({"caras": escena.caja_de_caras()}, f)
            pantallas.append(ruta)
    with open(os.path.join(args.salida, "pantallas.txt"), "w") as f:
        f.write("\n".join(pantallas) + "\n")
    escribir_medidas(os.path.join(args.salida, "medidas.txt"), medidas)
    with open(os.path.join(args.salida, "medidas.txt"), encoding="utf-8") as f:
        print(f.read())

    if args.comparar:
        d = args.comparar
        os.makedirs(d, exist_ok=True)
        for que in ("menu", "pelea"):
            # Las cajas de los recortes: la fila de Kersh, en pixeles de la
            # pantalla de baja (de 320 en RM2k).
            caja_rm2k = (148, 0, 320, 60) if que == "menu" else (0, 160, 320, 188)
            caja = (40, 0, 256, 60) if que == "menu" else (0, 144, 256, 172)
            lista = [("RM2k, 320x240 (x3), la fuente de hoy", imagenes["rm2k-" + que],
                      True, caja_rm2k)]
            ruta_hoy, caja_hoy = HOY[que]
            lista.append(("Hoy, la ROM a 256x224", Image.open(ruta_hoy).convert("RGB"),
                          False, caja_hoy))
            for nombre, k in CANDIDATAS:
                lista.append(("%s, %dx224" % (nombre, 256 * k),
                              imagenes["%s-%s" % (nombre, que)], False, caja))
            comparar(d, [l[:3] for l in lista]).save(
                os.path.join(d, "comparacion-%s.png" % que))
            recortes = [rotulo(recorte(im, es_rm2k, c), nombre)
                        for nombre, im, es_rm2k, c in lista]
            ancho = max(r.width for r in recortes)
            alto = sum(r.height + 8 for r in recortes)
            junta = Image.new("RGB", (ancho, alto), (24, 24, 32))
            y = 0
            for r in recortes:
                junta.paste(r, (0, y))
                y += r.height + 8
            junta.save(os.path.join(d, "recortes-x4-%s.png" % que))
        for nombre in ["rm2k"] + [n for n, _ in CANDIDATAS]:
            vista_de_hoja(os.path.join(hojas, nombre + ".png"),
                          os.path.join(d, "hoja-%s-con-letras.png" % nombre))


if __name__ == "__main__":
    main()
