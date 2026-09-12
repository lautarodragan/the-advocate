"""La batalla por turnos de RM2k, modelada con las mismas reglas que la ROM.

Es el hermano de `pantallas.py` para la pelea: acá viven las fórmulas —daño,
acierto, crítico, varianza, orden de turnos, huida— y la máquina de turnos, y
la ROM las copia. Que los dos lados hagan la misma cuenta es lo que le permite
a `pruebas/test_batalla.py` predecir **el número exacto** que la consola va a
poner en cada HP, en vez de conformarse con "bajó".

**Ningún número de acá se escribió de memoria.** Todos salen de
easyrpg-player, que está clonado en `/extras/ref`, y cada uno dice de dónde:

    src/algo.cpp                CalcNormalAttackEffect, CalcNormalAttackToHit,
                                CalcCriticalHitChance, VarianceAdjustEffect,
                                AdjustDamageForDefend
    src/scene_battle_rpg2k.cpp  CreateExecutionOrder, CreateEnemyActions
    src/scene_battle.cpp        InitEscapeChance, TryEscape
    src/game_enemy.cpp          GetHitChance, GetCriticalHitChance
    src/game_actor.cpp          GetHitChance, GetCriticalHitChance
    src/rand.cpp                PercentChance

Tres cosas **no** son de RM2k, y las tres son a propósito:

* **El azar.** RPG_RT tira de un generador que no podemos reproducir. Acá el
  azar es el mismo xorshift de dieciséis bits que el port ya usa para
  `ControlVars` —`eventos.azar_siguiente`—, pero con **semilla propia**:
  `BATALLA_SEMILLA`. Tener la suya y no compartir `FAR_AZAR` es lo que hace que
  pelear no le corra el azar al mapa, que es lo que la referencia de pixeles
  supone cuando dice que una batalla no cuesta ningún tick.

* **Las divisiones.** Donde easyrpg hace la cuenta en punto flotante y la
  trunca al devolverla, acá es entera. En el ajuste por agilidad eso importa y
  por eso va con **división hacia arriba**: truncar `100 - x` hacia cero es lo
  mismo que restarle el techo de `x`, así que la cuenta entera da exactamente
  lo mismo que la flotante. Ver `acierto_por_agilidad`.

* **Lo que no está.** Habilidades, ítems, estados, atributos, filas, el ataque
  doble, los battlers dibujados y las páginas de evento de la tropa. Está todo
  en el informe de "lo que falta" del README; acá lo que importa es que las
  fórmulas que sí están son las de verdad y no una aproximación.
"""

import eventos

# La semilla del azar de la batalla. Es otra que `AZAR_SEMILLA` a propósito:
# ver arriba. El valor no significa nada, sólo tiene que ser distinto de cero
# —el xorshift se queda clavado en el cero— y ser el mismo de los dos lados.
BATALLA_SEMILLA = 0x2B1D

# Cuántos caben en una pelea. El grupo es el de RM2k, cuatro; los enemigos, lo
# que entra en la pantalla de texto sin taparle nada al grupo. La tropa más
# grande del juego tiene ocho miembros, así que con ocho no se pierde ninguna.
GRUPO_MAX = 4
ENEMIGOS_MAX = 8

# Los tres resultados, en el orden en que el bytecode lleva sus destinos.
VICTORIA, HUIDA, DERROTA = 0, 1, 2

# Las órdenes que el jugador puede dar: `command_attack`, `command_defend` y
# `battle_escape` del LDB. Atacar pide blanco; las otras dos, no.
#
# En RM2k huir es una orden **del grupo**, de un menú que va antes de repartir
# las órdenes; acá es una orden de cada actor y se resuelve en el momento en
# que se elige. Si sale, la pelea termina ahí; si no, ese actor se queda con
# `ORDEN_HUIR`, que en el turno no hace nada más que decirlo. Es una
# simplificación declarada: ahorra un modo entero de la máquina de la ROM y
# deja a los dos lados con una sola lista de acciones.
ORDEN_ATACAR, ORDEN_DEFENDER, ORDEN_HUIR = 0, 1, 2

# El tope de un parámetro, como `Game_Actor::GetAtk` y sus hermanas.
PARAM_MAX = 999
# Y el del daño: `Game_BattleAlgorithm::MaxDamageValue()` para RM2k.
DANO_MAX = 999


class Azar:
    """El xorshift de la batalla, con su propia semilla.

    `hasta(n)` devuelve un número de 0 a n **inclusive**, que es el rango de
    `Rand::GetRandomNumber(0, n)` de easyrpg. El resto no es uniforme y no
    importa que no lo sea: lo que importa es que la ROM saque exactamente lo
    mismo, y la ROM hace esta misma cuenta con el divisor del hardware.
    """

    def __init__(self, semilla=BATALLA_SEMILLA):
        self.estado = semilla

    def hasta(self, n):
        self.estado = eventos.azar_siguiente(self.estado)
        return self.estado % (n + 1) if n >= 0 else 0

    def porciento(self, tanto):
        """`Rand::PercentChance(int)`: `GetRandomNumber(0, 99) < rate`.

        **Se tira siempre**, aunque `tanto` sea cero: es lo que hace
        `Normal::vExecute` con el crítico, y si acá no se tirara los dos lados
        se irían de fase en el tiro siguiente.
        """
        return self.hasta(99) < tanto


class Combatiente:
    """Uno de los que pelean, del lado que sea.

    `es_actor` decide dos cosas y no es cosmético: de qué lado cuenta para
    elegir blanco, y que el crítico exista —`CalcCriticalHitChance` lo pone en
    cero cuando los dos son del mismo tipo—.
    """

    def __init__(self, nombre, hp_max, ataque, defensa, agilidad, acierto,
                 critico=0, es_actor=True, numero=0):
        self.nombre = nombre
        self.hp_max = hp_max
        self.hp = hp_max
        self.ataque = ataque
        self.defensa = defensa
        self.agilidad = agilidad
        self.acierto = acierto
        self.critico = critico          # en por ciento, ya entero
        self.es_actor = es_actor
        self.numero = numero            # el actor del LDB, o el lugar en la tropa
        self.defendiendo = False
        self.orden = 0

    @property
    def vivo(self):
        return self.hp > 0


def actor_de(db, numero, equipo=None):
    """El combatiente de un actor del LDB, con lo que tenga puesto.

    Los parámetros salen de `pantallas.parametros`, que es la misma función que
    usa la pantalla de equipo: el del nivel más lo que suma cada pieza, topado
    en [1, 999]. Los HP son los del nivel y no llevan equipo, como
    `Game_Actor::GetMaxHp` en RM2k, donde el equipo no toca los HP.

    El acierto es 90: `Game_Actor::GetHitChance` con un arma sin `hit` propio.
    **El `hit` del arma no se lee**, y es deuda declarada: ningún arma del ABL
    lo baja, pero el día que una lo haga esto se equivoca en silencio.
    """
    import pantallas
    actor = db.actors[numero]
    if equipo is None:
        equipo = list(actor.initial_equipment)
    ataque, defensa, _espiritu, agilidad = pantallas.parametros(db, numero,
                                                                equipo)
    critico = (100 // actor_critico_cada(db, numero)) \
        if actor_tiene_critico(db, numero) else 0
    return Combatiente(actor.name, actor.hp_max[0], ataque, defensa, agilidad,
                       90, critico, True, numero)


def actor_tiene_critico(db, numero):
    """`critical_hit` del actor, del LDB. En el ABL ninguno lo tiene."""
    return bool(getattr(db.actors[numero], "critical_hit", False))


def actor_critico_cada(db, numero):
    return getattr(db.actors[numero], "critical_hit_chance", 30) or 30


def enemigo_de(db, enemy_id, lugar):
    """El combatiente de un enemigo del LDB.

    El acierto es `Game_Enemy::GetHitChance`: 70 el que tiene `miss` puesto y
    90 el que no. El crítico, `GetCriticalHitChance` por cien y truncado, que
    con el 30 de fábrica da 3.
    """
    e = db.enemies[enemy_id]
    critico = (100 // (e.critical_hit_chance or 30)) if e.critical_hit else 0
    return Combatiente(e.name, e.max_hp, e.attack, e.defense, e.agility,
                       e.hit, critico, False, lugar)


def acierto_por_agilidad(base, agi_fuente, agi_blanco):
    """`CalcToHitAgiAdjustment` de algo.cpp.

        to_hit = 100 - (100 - to_hit) * (1 + (tgt_agi / src_agi - 1) / 2)

    que es lo mismo que restarle a 100 el producto por `(src + tgt) / (2 src)`.
    easyrpg lo hace en `float` y devuelve un `int`, o sea que trunca hacia cero
    el resultado entero: `trunc(100 - x)` es `100 - ceil(x)` mientras el
    resultado sea positivo, y por eso acá la división es **hacia arriba**. Sin
    eso los dos lados se separan en un punto de acierto cada tanto, que es
    justo la clase de diferencia que no se ve hasta que un golpe falla.
    """
    fuente = max(1, agi_fuente)
    resta = (100 - base) * (fuente + agi_blanco)
    return 100 - -(-resta // (2 * fuente))


def dano_normal(fuente, blanco, critico, azar):
    """`CalcNormalAttackEffect` y `VarianceAdjustEffect` con varianza 4.

        dmg = max(0, atk / 2 - def / 4)
        crítico: * 3
        varianza: adj = max(1, 4 * dmg / 10); dmg += rand(0, adj) - adj / 2

    Las filas, los atributos del arma y el ataque cargado no están: este port
    no tiene ninguna de las tres.
    """
    dano = max(0, fuente.ataque // 2 - blanco.defensa // 4)
    if critico:
        dano *= 3
    if dano > 0:
        ajuste = max(1, 4 * dano // 10)
        dano = dano + azar.hasta(ajuste) - ajuste // 2
    return dano


def ajustar_por_defensa(dano, blanco):
    """`AdjustDamageForDefend`: el que se defiende recibe la mitad. La "defensa
    fuerte" es un estado y no hay estados."""
    return dano // 2 if blanco.defendiendo else dano


class Batalla:
    """Una pelea, turno por turno. Es `Scene_Battle_Rpg2k` de easyrpg con lo
    que este port hace.

    El lazo de un turno, en el orden en que consume azar —y ese orden es el
    contrato con la ROM—:

    1. el jugador elige la orden de cada actor vivo (no tira azar);
    2. cada enemigo vivo elige atacar a un actor vivo al azar
       —`CreateEnemyActions`—: **un tiro por enemigo**;
    3. `CreateExecutionOrder`: **un tiro por combatiente que actúa**, para su
       `agi + rand(0, agi / 4 + 3)`, y después se ordena de mayor a menor con
       un orden estable;
    4. se ejecutan en ese orden, salteando a los que hayan muerto en el
       camino. Cada ataque tira **tres veces**: acierto, crítico y varianza, y
       el del crítico se tira aunque la probabilidad sea cero.

    Que el punto 2 vaya antes que el 3 no es un detalle: es el orden de
    `SelectNextActor`, que llama a `CreateEnemyActions()` y después a
    `CreateExecutionOrder()`.
    """

    def __init__(self, actores, enemigos, semilla=BATALLA_SEMILLA):
        self.actores = list(actores)
        self.enemigos = list(enemigos)
        self.azar = Azar(semilla)
        self.turno = 0
        self.resultado = None
        self.huida_chance = self._chance_de_huir()
        self.registro = []          # lo que pasó, para que una prueba lo cuente

    # --- la huida ---------------------------------------------------------
    def _promedio(self, quienes):
        vivos = [c for c in quienes if c.vivo] or list(quienes)
        return sum(c.agilidad for c in vivos) // max(1, len(vivos))

    def _chance_de_huir(self):
        """`Scene_Battle::InitEscapeChance`:

            base = redondear(100 * agi_enemigos / agi_grupo)
            chance = recortar(150 - base, 0, 100)

        El redondeo de easyrpg es `RoundTo`, o sea al entero más cercano; acá
        es `(2a + b) // (2b)`, que es lo mismo con enteros y sin flotantes.
        """
        enemigos = self._promedio(self.enemigos)
        grupo = max(1, self._promedio(self.actores))
        base = (2 * 100 * enemigos + grupo) // (2 * grupo)
        return max(0, min(100, 150 - base))

    def huir(self):
        """`TryEscape`: se tira contra la chance y, si falla, sube diez.

        Devuelve True si se escapó. `first_strike` no está: las dos peleas de
        la intro lo traen en cero.
        """
        if self.azar.porciento(self.huida_chance):
            self.resultado = HUIDA
            return True
        self.huida_chance = min(100, self.huida_chance + 10)
        return False

    # --- el turno ---------------------------------------------------------
    def vivos(self, quienes):
        return [c for c in quienes if c.vivo]

    def acciones_de_los_enemigos(self):
        """`CreateEnemyActions`: cada enemigo vivo ataca a un actor vivo al
        azar. Sólo la acción "básica: atacar" —`kind` 0, `basic` 0—, que es la
        única que tienen los enemigos de las dos peleas de la intro."""
        acciones = []
        for enemigo in self.vivos(self.enemigos):
            blancos = self.vivos(self.actores)
            if not blancos:
                break
            blanco = blancos[self.azar.hasta(len(blancos) - 1)]
            acciones.append((enemigo, ORDEN_ATACAR, blanco))
        return acciones

    def orden_de_ejecucion(self, acciones):
        """`CreateExecutionOrder`: `agi + rand(0, agi / 4 + 3)`, de mayor a
        menor y con un orden **estable**, que es lo que hace `std::sort` sobre
        una lista que ya viene en el orden en que se apiló."""
        for quien, _orden, _blanco in acciones:
            quien.orden = quien.agilidad + self.azar.hasta(
                quien.agilidad // 4 + 3)
        return sorted(range(len(acciones)),
                      key=lambda i: -acciones[i][0].orden)

    def atacar(self, fuente, blanco):
        """Un ataque normal, con sus tres tiros. Devuelve (pegó, crítico,
        daño)."""
        acierto = acierto_por_agilidad(fuente.acierto, fuente.agilidad,
                                       blanco.agilidad)
        pego = self.azar.porciento(acierto)
        critico = self.azar.porciento(fuente.critico if pego else 0)
        if not pego:
            # El tiro del crítico se hizo igual, pero el golpe falló.
            return False, False, 0
        dano = dano_normal(fuente, blanco, critico, self.azar)
        dano = ajustar_por_defensa(dano, blanco)
        dano = max(-DANO_MAX, min(DANO_MAX, dano))
        blanco.hp = max(0, blanco.hp - dano)
        return True, critico, dano

    def jugar_turno(self, ordenes):
        """Un turno entero. `ordenes` es, por actor vivo y en el orden del
        grupo, `(ORDEN_ATACAR, lugar_del_enemigo)` o `(ORDEN_DEFENDER, 0)`.

        Devuelve el resultado si la pelea terminó, o None.
        """
        self.turno += 1
        for quien in self.actores + self.enemigos:
            quien.defendiendo = False
        acciones = []
        for actor, (orden, blanco) in zip(self.vivos(self.actores), ordenes):
            acciones.append((actor, orden,
                             self.enemigos[blanco] if orden == ORDEN_ATACAR
                             else None))
        acciones += self.acciones_de_los_enemigos()
        for i in self.orden_de_ejecucion(acciones):
            quien, orden, blanco = acciones[i]
            if not quien.vivo:
                continue
            if orden == ORDEN_DEFENDER:
                # `Defend` marca al que se defiende **cuando le toca**, no al
                # elegir: un enemigo que actúe antes le pega entero. Es lo de
                # RM2k.
                quien.defendiendo = True
                continue
            if orden == ORDEN_HUIR:
                continue
            if not blanco.vivo:
                # `Game_BattleAlgorithm` reapunta a otro del mismo lado cuando
                # el blanco murió antes de que le tocara.
                lado = self.enemigos if not blanco.es_actor else self.actores
                candidatos = self.vivos(lado)
                if not candidatos:
                    continue
                blanco = candidatos[0]
            pego, critico, dano = self.atacar(quien, blanco)
            self.registro.append((self.turno, quien.nombre, blanco.nombre,
                                  pego, critico, dano, blanco.hp))
        if not self.vivos(self.enemigos):
            self.resultado = VICTORIA
        elif not self.vivos(self.actores):
            self.resultado = DERROTA
        return self.resultado
