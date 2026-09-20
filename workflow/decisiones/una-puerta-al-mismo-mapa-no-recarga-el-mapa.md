# Qué

**Una puerta al mismo mapa no recarga el mapa.**

# Por qué

Recargar vuelve a leer del cartucho las posiciones de los eventos, y con eso se
pierde lo que los haya movido aunque el jugador nunca haya salido. Es el
`map_changed` de `Game_Player::PerformTeleport`.

Lo cuida `test_puerta_misma.py`.
