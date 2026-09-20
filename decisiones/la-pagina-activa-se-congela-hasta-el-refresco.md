# Qué

**La página activa de un evento se congela hasta el refresco.** No se recalcula
cada vez que alguien pregunta.

# Por qué

Es `Game_Event::page`, y sólo la reescribe `Game_Map::Refresh()`, al principio
de `Game_Map::Update`. La ROM lo hace guardándola en la fila del NPC.

De ahí sale una regla para cualquier lazo que corte a mano: **no se corta con
un refresco pendiente**, porque el cuadro que viene sí hace algo.
