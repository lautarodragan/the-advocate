---
name: "La victoria no da oro ni ítems"
description: "RM2k da y cuenta el oro y los ítems al ganar; el port todavía no"
type: feature
---

Quedó afuera de `testing/la-victoria-avisa-la-experiencia.md` (2026-09-26): en
RM2k, al ganar, la misma página de la victoria cuenta el oro ganado y los
ítems que dejaron los enemigos (`ProcessSceneActionVictory` en EasyRPG), y el
grupo los recibe. El port todavía no da ni oro ni ítems al ganar. Los datos
están en las tropas y los enemigos del LDB (`gold`, `drop_id`,
`drop_probability`); el azar de los ítems tiene que usar el generador de la
pelea (ver `ENC_SEMILLA` y la semilla propia de la pelea).

## Cómo quedó, el 2026-09-27

Al ganar, `ba_vic_empezar` hace lo que `ProcessSceneActionVictory` hace en su
primer sub-estado, en el mismo orden: reparte la experiencia, suma el oro de
la tropa —`GetMoney`, topado en ORO_MAX como `GainGold`— y tira el botín
—`GenerateDrops`—: por cada enemigo, en el orden de la tropa, **un tiro si
tiene ítem**, con `ba_pct` sobre la semilla de la pelea. `ChanceOf(n, 100)` es
`GetRandomNumber(1, 100) <= n`, que con nuestro azar es lo mismo que
`PercentChance`; el de chance 100 se tira igual. Lo que sale suma uno al
inventario, topado en 99.

El modelo tira lo mismo: `batalla.Batalla.tirar_el_botin`, que `jugar_turno`
llama al ganar, después del último golpe, y es el punto 5 del orden de azar
de la clase. Como es lo último que tira la pelea, no le mueve nada a ninguna
predicción anterior.

La primera página cuenta ahora, detrás de la victoria y la experiencia, el
oro —" You found 285Cr credits!", que es `gold_recieved_a`, un espacio, el
número pegado a `gold` y `gold_recieved_b`, como lo arma RM2k sin
placeholders— y un renglón por ítem, "Healing Draught-HP obtained!"
(`item_recieved` pegado al nombre, sin espacio: el espacio es de RM2k3). Son
renglones del mismo mensaje, así que lo que no entra en los cuatro sigue en
otra página con A, igual que las habilidades de un actor (`ba_vic_linea`).
Con la victoria partida en dos renglones, la experiencia y el oro llenan la
primera página y los ítems van siempre en la segunda.

Lo del conversor:

* `tropa_oro`, `enemigo_botin` y `enemigo_botin_pct`, en RODATA con su
  `.bloque`;
* los ítems que puede soltar algún enemigo de las tropas del cartucho entran
  en la lista de ítems (`items_del_botin`), para tener su nombre;
* `cobrar_la_victoria` cobra también el renglón del oro y el de cada ítem que
  se puede soltar.

La suma del oro con tope salió de la venta de la tienda a una rutina,
`oro_sumar`, que usan las dos.

RAM lejana: `$7E79E0-$7E79E8` (`BA_BOTIN*` en `ram_lejana.s`), del rango
repartido. Ningún opcode.

Lo cubre `pruebas/rpgmaker/test_victoria.py` con el caso nuevo `pelea-222`,
tres Crazed Marauder: la semilla la elige el modelo —la primera con la que
gana sin bajas y los tres tiros no salen iguales— y se escribe en `BA_SEM` al
abrir la pelea, con 1 HP a cada enemigo. La prueba compara el oro, el
inventario y las dos primeras páginas contra el modelo y los renglones de
`pantallas`, y otra cobra el tope de 99.

## Qué tiene que mirar taro

Ninguna pelea del juego que entra en `release` suelta ítems salvo las de
las tropas 219 a 236 (las de los mapas de prueba); en Lashe City lo que se ve
es **el oro**: después de cualquier pelea con enemigos que den oro, la
primera página dice " You found NCr credits!" y el oro del menú sube eso.

* Que la página del oro se lea bien y que la A la pase como antes.
* Que el oro del menú después de pelear sea el de antes más lo que dijo la
  página.
