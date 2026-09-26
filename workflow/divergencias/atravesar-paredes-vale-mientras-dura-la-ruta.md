# Qué

La orden 36 de una ruta —`walk_everywhere_on`— es **pegajosa** en RM2k:
escribe `move_route_through` de `Game_Player`, que es un campo de la partida
guardada —`SaveMapEventBase` en liblcf— y que no repone nadie, ni
`CancelMoveRoute`, ni `ForceMoveRoute`, ni `MoveTo` al cambiar de mapa. Una
página que la prenda y no la apague deja al héroe atravesándolo todo hasta el
final de la partida.

Acá la bandera vale **sólo mientras el paso lo dé la ruta forzada**. El
porqué, con el síntoma que lo delató, está en `celda_bloqueada`
(`rom/src/paginas_de_eventos.s`), que es donde se lee `atravesando` y no la
pegajosa `ruta_atraviesa`.

Para la pregunta al revés —un evento que camina contra el héroe— se sigue
mirando la pegajosa, `ruta_atraviesa`. Es una asimetría, y se deja porque
ninguna ruta del juego la ejercita: haría falta un evento caminando encima del
héroe justo después de una página que dejó la 36 prendida.

# Medido

Sobre el juego entero: de las 153 páginas que mueven la bandera, **4 la dejan
prendida**, y dos de ésas —el Hover-Tram del mapa 13, `EV0028`, y el mapa 14—
están en el camino principal. Con la regla de RM2k, cualquiera que llegue
caminando al Sector 30 pisa los cofres que no debería.

# Cuándo deja de alcanzar

Un juego que use la 36 a propósito para dejar al héroe atravesando más allá de
la ruta. En éste las cuatro que la dejan prendida son descuidos del original.
