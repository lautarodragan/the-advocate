# Qué

R sube la velocidad a la que camina el héroe y L la baja, de a una, entre
la 1 y la 6 de RM2k. RM2k no tiene nada parecido: es de taro, el 2026-09-30
—"poder incrementar o disminuir la velocidad del héroe con los botones R y
L"—. Como el autofire de X, **sólo suma**: en RM2k no hay botón que
corresponda a L ni a R. Está en `tools/runtime/hero_speed_keys.s`.

Lo que se decidió, y está comentado ahí:

* **No es la velocidad del juego sino un agregado encima.** La del juego
  —la que suben y bajan las órdenes 28 y 29 de una ruta, y la que viaja en la
  partida— no se toca: L y R mueven otro byte, y el héroe camina a la suma,
  con los topes 1 y 6. Con el agregado en cero todo es RM2k cuadro por
  cuadro.
* **Una ruta forzada sobre el héroe camina a la del juego**, sin el
  agregado, mientras dura —su último paso incluido—, y el pad vuelve al
  agregado en el primer paso que da el jugador. Si la ruta cambió la
  velocidad del juego, el agregado se suma a la nueva.
* **Sigue al cambiar de mapa y no se guarda en la partida**: es un gusto del
  que juega, no estado del mundo. Lo borra el reset.
* **Sólo se lee mientras el jugador tiene al héroe**: sin ruta, sin mensaje,
  sin una página corriendo adelante y sin eventos esperando para arrancar,
  que son las mismas guardas que caminar. El menú, la pelea, la tienda y el
  fundido de un teletransporte tienen su propio lazo o congelan el principal,
  así que ahí nunca se lee. Un toque que cae donde no se lee se pierde.
* **Un toque desde el tope ya cambia.** El agregado se recalcula desde lo que
  el héroe camina: con el juego en 6 y dos R que no hicieron nada, una L ya
  da 5.
* **Se apaga sin tocar el runtime**, con `--no-speed-keys` en los `flags` de
  un cartucho: el conversor emite `HERO_SPEED_KEYS = 0` y el lazo no los lee.
  Lo lleva `test-special`, para que el camino apagado tenga su prueba.

# Medido

A cada velocidad el héroe cruza una celda en 64, 32, 16, 8, 4 y 2 cuadros.
`rom/pruebas/rpgmaker/test_velocidad_con_l_y_r.py` lo mide con el pad: sin
tocar nada, 8; R una vez, 4; dos, 2; cinco, sigue en 2; L una vez, 16; tres,
64; cinco, sigue en 64. Además: el toque desde el tope, que sigue después de
un teletransporte, que `ruta-vel` con un agregado de +2 camina sus pasos a 4,
4, 4, 8 y 8 cuadros —los de la 5 y la 4, como sin él— y el pad después a 2,
que R con un mensaje abierto no hace nada, y que `test-special`, armado sin
L y R, no los lee.

# Cómo reproducirlo

En cualquier mapa, apretar R y caminar.
