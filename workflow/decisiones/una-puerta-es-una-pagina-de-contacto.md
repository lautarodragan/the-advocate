# Qué

**Una puerta no es un caso aparte: es una página de contacto con un `Teleport`
adentro**, y cruza por el intérprete como cualquier otro evento.

# Por qué

Tuvo tabla propia mientras no hubo intérprete —`collect_doors`,
`cruzar_puerta`—; se fue el 2026-09-20 porque **la tabla congelaba la página
activa al empezar la partida**, y con eso mentía en las dos puertas del mapa 10
que el switch 231 cambia de destino.

El único que sobrevive de ese camino es `FUNDIDO_PUERTA`, que hoy sólo escribe
el arnés para plantar la partida en un mapa: está explicado en su línea de
`rom/src/ram_baja.s`.
