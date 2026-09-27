"""La persecución en auto, de la intro del 49 al fin de la demo en el 64.

Es el hito 1 de `workflow/tasks/*/la-carrera-y-lo-que-sigue.md`. El recorrido:

    49  primera vuelta. La intro —mensajes, la pantalla negra y un
        `KeyInputProc` que espera cualquier tecla— prende el 171; el 171 mete
        al auto en el grupo y prende el 170, y con el 170 corren el volante
        (`RaceController2`, paralela: empuja al héroe a la derecha y lo cambia
        de carril con arriba y abajo) y los autos (paralelas: cada uno compara
        su celda con la del héroe y, si coinciden, salta al 50). La meta,
        x = 255, salta al 52
    50  el choque: cuenta los choques en la variable 38 y vuelve a la vuelta
        que estaba; con cinco o más el compañero se ofrece a manejar, y con
        "Yes" salta al puente
    52  segunda vuelta, sin intro. Meta -> 54
    54  tercera vuelta. Meta -> 51
    51  el puente: la columna 75 salta al 53
    53  el premio, según las vueltas y los choques -> 64
    64  la despedida con el compañero, y el fin de la demo (el 64 está
        forkeado: `parches/manual/mapas/Map0064.json`, porque el original salta
        al mundo, el 66, que no entra)

**Todas las salidas de la carrera son un `Teleport` desde una página
paralela**, con el primer plano quieto, y el volante es el `KeyInputProc` que
no espera y mira lo apretado. Las dos cosas las estrenó este recorrido: hasta
el 2026-09-27 ninguna página de `release` las usaba, y la ROM no hacía
ninguna de las dos —ver el lazo principal y `tecla_valor`—.

El volante se maneja **sosteniendo** arriba o abajo con el arnés, y quien
decide es `piloto`: mira en la RAM la celda de cada auto y la del héroe, y se
cambia al carril libre más cercano cuando el suyo tiene un auto adelante. No
es un guion de cuadros: si la carrera cambia de velocidad, el piloto sigue
mirando dónde están los autos.

Arranca en el 49 por `ir_al_mapa`, con la celda del `Teleport` del 36: cómo
se llega ahí lo juegan los recorridos de Lashe City, que terminan entrando al
49 —ver `irse_lleva_a_la_carrera` en `test_recorrido_lashe_golden.py`—.

Las capturas van a `pruebas/snapshots/playthrough/carrera-*/` y **no están
bendecidas**: son para que taro las mire. Lo que cobra esta prueba es la RAM,
y **cuántos cuadros pierde manejando** —el hito 2—: ver `CUADROS_DE_MAS`.
"""

import datos
from batalla import grupo_de
from recorrido import TELEPORT, Trabado

from test_recorrido_lashe_golden import CON_ARDEN, CON_SALDRA

# La celda del `Teleport [49, 1, 26]` del 36, por donde el juego entra.
LA_LARGADA = (49, 1, 26)

# Los switches de la carrera.
ARRANCO = 171           # la intro terminó: mete al auto y prende el 170
CORRIENDO = 170         # corren el volante y los autos
CHOCO = 172             # apaga el volante hasta el 50
VUELTA_2 = 174          # la meta del 49
EL_COMPANERO_MANEJA = 173
VUELTA_3 = 178          # la meta del 52
EL_PUENTE = 179         # la meta del 54

# Los actores del auto: el 130 elige el rojo, y `RaceController1` lo prende.
AUTO_ROJO = 19

LAS_VUELTAS = (49, 52, 54)
EL_CHOQUE, EL_PUENTE_MAPA, EL_PREMIO, LA_DESPEDIDA = 50, 51, 53, 64

# Los carriles: `RaceController2` sube con la y en 24 o más y baja con la y
# en 27 o menos.
CARRILES = range(23, 29)
# Cuántas celdas adelante mira el piloto. El auto avanza media celda por tick
# y cambia de carril a la misma velocidad, así que siete le dan tiempo de
# cruzar tres carriles.
ADELANTE = 7

VARIABLE_DE_CHOQUES = 38

# Cuántos cuadros de hardware de más se le aceptan a cada vuelta, por cada
# cien ticks manejando: el hito 2 de la carrera, "a 60 cuadros". Hasta el
# 2026-09-27 cada tick costaba dos cuadros —cuarenta páginas paralelas, las de
# los autos, más el trabajo del cuadro—, o sea cien de más por cada cien, y
# la carrera corría a media velocidad. Lo que queda son los cuadros en que
# varios autos que andan arrancan su paso a la vez: ver
# workflow/tasks/*/carrera-2-a-sesenta-cuadros.md, que dice cómo se midió.
#
# Cuenta sólo los ticks manejando de verdad: con el 170, sin mensaje ni
# fundido, en el mismo mapa al empezar y al terminar, y con el auto ya fuera
# de la largada. Antes de eso la vuelta pone su tema, y subir las muestras se
# lleva sus cuadros sin que haya nada que manejar.
CUADROS_DE_MAS = 5
LA_LARGADA_X = 4


def los_choques(p):
    """La variable 38, que cuenta el 50 y pone en cero la intro del 49."""
    return p.variable(datos.ranuras_de_variable()[VARIABLE_DE_CHOQUES])


def autos(mundo, map_id):
    """(índice en la tabla de eventos de la ROM, si se mueve) de cada auto del
    mapa: los eventos cuya página salta al 50. El índice es el orden de los
    ids, que es como los guarda la ROM —ver `Partida.evento`—."""
    lista = []
    for indice, evento in enumerate(mundo.eventos(map_id)):
        pagina = evento.pages[0]
        if any(c.code == TELEPORT and c.parameters[0] == EL_CHOQUE
               for c in pagina.commands):
            lista.append((indice, pagina.move_type != 0))
    return lista


def piloto(p, los_autos):
    """Qué sostener este tick: "up", "down" o None.

    Un auto quieto ocupa su carril; uno que se mueve —suben y bajan— ocupa
    además los dos de al lado. Si el carril del héroe está libre en las
    `ADELANTE` celdas que vienen, no se toca nada; si no, se va hacia el libre
    más cercano, y a igual distancia hacia arriba.
    """
    hx, hy = p.heroe()
    ocupado = set()
    for indice, se_mueve in los_autos:
        x, y = p.evento(indice)
        if hx - 1 <= x <= hx + ADELANTE:
            alcance = 1 if se_mueve else 0
            ocupado.update(range(y - alcance, y + alcance + 1))
    if hy not in ocupado:
        return None
    libres = [c for c in CARRILES if c not in ocupado]
    if not libres:
        return None
    meta = min(libres, key=lambda c: (abs(c - hy), c))
    return "up" if meta < hy else "down"


def largar(r):
    """La intro del 49 hasta el 170: los mensajes, la espera de una tecla y
    el auto en el grupo. La paciencia de `esperar` toca A, que es la tecla que
    la espera acepta."""
    r.empezar("la intro de la carrera")
    r.p.ir_al_mapa(*LA_LARGADA)
    assert r.p.mapa() == 49, r.estado()
    r.esperar("el switch 170", lambda p: p.switch(CORRIENDO), tope=3000)
    assert r.p.switch(ARRANCO), r.estado()
    assert grupo_de(r.p) == [AUTO_ROJO], (
        "`RaceController1` saca a todos y mete al auto rojo, y el grupo es "
        "%s. %s" % (grupo_de(r.p), r.estado()))
    r.foto("la-largada", asentar=False)


def manejar(r, mundo, hasta, tope=6000, sin_volante=False, choques=None,
            cuadros=None):
    """Maneja hasta que `hasta(partida)`, con el piloto o —`sin_volante`— sin
    tocar nada. En el 50 pasa los mensajes con A y cuenta el choque en
    `choques`, si se le pasa una lista. Una elección abierta corta: es la del
    compañero, y la contesta quien llamó.

    En `cuadros`, si se le pasa, anota por mapa [ticks, cuadros de hardware]
    de los ticks manejando: ver `CUADROS_DE_MAS`."""
    p = r.p
    cache = {}
    gastado = 0
    mapa = p.mapa()
    while not hasta(p):
        if gastado >= tope:
            raise Trabado("manejando no se llegó en %d ticks. %s"
                          % (tope, r.estado()))
        if r._eleccion_lista():
            return r
        m = p.mapa()
        if m != mapa:
            mapa = m
            if m == EL_CHOQUE and choques is not None:
                choques.append(p.cuadro)
        antes = p.cuadro
        if m in LAS_VUELTAS + (EL_PUENTE_MAPA,) and not p.byte("msg_abierto"):
            if m not in cache:
                cache[m] = autos(mundo, m)
            tecla = None if sin_volante else piloto(p, cache[m])
            manejando = (p.switch(CORRIENDO) and not p.byte("fundido")
                         and not p.byte("msg_estado")
                         and p.heroe()[0] >= LA_LARGADA_X)
            hardware = p.hardware
            p.correr(1, sosteniendo=(tecla,) if tecla else ())
            if (cuadros is not None and manejando and p.mapa() == m
                    and p.switch(CORRIENDO) and not p.byte("fundido")):
                cuenta = cuadros.setdefault(m, [0, 0])
                cuenta[0] += p.cuadro - antes
                cuenta[1] += p.hardware - hardware
        else:
            p.correr(4, apretar_a=(p.cuadro + 3,)
                     if p.byte("msg_abierto") else ())
        gastado += p.cuadro - antes
    return r


def la_meta(r, mundo, vuelta, siguiente, cuadros=None):
    """Una vuelta entera, de la largada del mapa `vuelta` a `siguiente`. Si
    choca, el 50 la devuelve a la misma vuelta y se sigue manejando."""
    r.empezar("la vuelta del mapa %d" % vuelta)
    choques = []
    manejar(r, mundo, lambda p: p.mapa() == siguiente, tope=8000,
            choques=choques, cuadros=cuadros)
    r.asentar()
    return choques


def fin_de_la_demo(r):
    """La escena del 64 hasta el cartel del fin de la demo y la vuelta al
    título. Por cuadros de hardware y no por ticks: la pantalla de título no
    hace correr `vueltas`. El reinicio se ve en los switches, que `reset`
    borra; el cartel es el último mensaje antes de eso, así que se guarda la
    pantalla de cada mensaje compuesto y se fotografía la del último."""
    r.empezar("la despedida del 64 y el fin de la demo")
    p = r.p
    ultimo = None
    for _ in range(4000):
        if not p.switch(ARRANCO):
            break
        if p.byte("msg_estado") or p.byte("msg_abierto"):
            # Un mensaje componiéndose o ya en pantalla: se lo deja terminar
            # de a un cuadro. Con el toque de A a ciegas, el cartel del fin
            # se abre en medio del toque y se cierra en el mismo cuadro, y lo
            # que quedaba guardado era el mensaje de antes.
            for _ in range(120):
                if p.byte("msg_abierto") and p.byte("msg_estado") != 1:
                    break
                p.consola.correr(1)
            ultimo = p.imagen()
        p.consola.apretar("a")
        p.consola.correr(2)
        p.consola.apretar()
        p.consola.correr(6)
    else:
        raise AssertionError("la escena del 64 no volvió al título. %s"
                             % r.estado())
    assert ultimo is not None, (
        "entre el 64 y el título no hubo ningún mensaje. %s" % r.estado())
    r.foto("el-fin-de-la-demo", imagen=ultimo)
    p.consola.correr(p.simbolos["BOOT_CUADROS"] + 60)
    r.foto("el-titulo-despues-del-fin", asentar=False)


def test_la_carrera_entera(recorrido, mundo):
    """Con Arden, las tres vueltas manejando, el puente, el premio y la
    despedida, hasta el título. El piloto puede chocar alguna vez —el 50
    devuelve a la misma vuelta—, pero no cinco: con cinco el compañero se
    ofrece a manejar, y eso es la otra prueba."""
    r = recorrido("carrera-entera", switch=[CON_ARDEN])
    largar(r)
    choques = []
    cuadros = {}
    for vuelta, siguiente in zip(LAS_VUELTAS, LAS_VUELTAS[1:] + (EL_PUENTE_MAPA,)):
        choques += la_meta(r, mundo, vuelta, siguiente, cuadros)
        r.foto("llega-al-%d" % siguiente)
    for vuelta in LAS_VUELTAS:
        ticks, hardware = cuadros[vuelta]
        assert (hardware - ticks) * 100 <= CUADROS_DE_MAS * ticks, (
            "manejando, la vuelta del mapa %d gastó %d cuadros de hardware en "
            "%d ticks: %d de más, y el tope es %d cada cien. Ver "
            "`CUADROS_DE_MAS`." % (vuelta, hardware, ticks, hardware - ticks,
                                   CUADROS_DE_MAS))
    assert r.p.switch(VUELTA_2) and r.p.switch(VUELTA_3) \
        and r.p.switch(EL_PUENTE), r.estado()
    assert len(choques) < 5, (
        "el piloto chocó %d veces: con cinco el compañero se ofrece a manejar "
        "y esta prueba no lo contesta. %s" % (len(choques), r.estado()))

    r.empezar("el puente")
    manejar(r, mundo, lambda p: p.mapa() == EL_PREMIO, tope=3000)
    assert r.p.switch(CHOCO), (
        "la columna 75 del 51 prende el 172, que apaga el volante. %s"
        % r.estado())
    r.asentar()
    r.foto("el-premio")

    r.empezar("el premio")
    oro = r.p.oro()
    r.esperar("el mapa 64", lambda p: p.mapa() == LA_DESPEDIDA, tope=3000)
    assert r.p.oro() >= oro + 2000, (
        "la primera vuelta da dos veces mil créditos, y el oro pasó de %d a "
        "%d. %s" % (oro, r.p.oro(), r.estado()))
    assert los_choques(r.p) == len(choques), (
        "la variable 38 cuenta los choques: vale %d y el piloto chocó %d "
        "veces. %s" % (los_choques(r.p),
                       len(choques), r.estado()))
    r.asentar()
    r.foto("la-despedida")
    fin_de_la_demo(r)


def test_cinco_choques_y_maneja_saldra(recorrido, mundo):
    """Sin tocar el volante el auto va derecho por el carril 26 y choca
    siempre con el mismo, el de (101, 26): cada choque pasa por el 50 y
    vuelve a largar en el 49. Al quinto, Saldra se ofrece a manejar; con "Yes"
    salta al puente, y de ahí al premio y a la despedida."""
    r = recorrido("carrera-cinco-choques", switch=[CON_SALDRA])
    largar(r)
    choques = []
    for n in range(1, 5):
        r.empezar("el choque %d" % n)
        manejar(r, mundo, lambda p: len(choques) >= n, tope=3000,
                sin_volante=True, choques=choques)
        r.empezar("de vuelta en el 49 después del choque %d" % n)
        manejar(r, mundo, lambda p: p.mapa() == 49 and p.switch(CORRIENDO),
                tope=3000, sin_volante=True)
        assert los_choques(r.p) == n, r.estado()
        if n == 1:
            r.foto("de-vuelta-en-el-49")

    r.empezar("el quinto choque")
    manejar(r, mundo, lambda p: False, tope=3000, sin_volante=True,
            choques=choques)
    assert r.p.mapa() == EL_CHOQUE, r.estado()
    r.marcar(1)
    r.foto("maneja-saldra")
    r.confirmar()
    # El 173 va **después** del `Teleport` en la página del 50, que sigue
    # corriendo del otro lado: se prende ya en el puente.
    r.esperar("el puente con el 173",
              lambda p: p.mapa() == EL_PUENTE_MAPA
              and p.switch(EL_COMPANERO_MANEJA), tope=2000)

    r.empezar("el puente y el premio")
    manejar(r, mundo, lambda p: p.mapa() == LA_DESPEDIDA, tope=5000,
            sin_volante=True)
    assert los_choques(r.p) == 5, r.estado()
    r.asentar()
    r.foto("la-despedida")
    fin_de_la_demo(r)
