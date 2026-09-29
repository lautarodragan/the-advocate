# Qué

**Agotar el presupuesto de teletransportes es un error, no un caso.** Al
agotarse, la ROM llama a `enter_panic` en vez de seguir.

# Por qué

Un salto descartado en silencio es la forma de falla que `AGENTS.md` nombra
—un camino que nadie ejecuta y nada cobra—, y ésta sobrevivió semanas porque la
partida seguía andando, sólo que en el mapa equivocado.
