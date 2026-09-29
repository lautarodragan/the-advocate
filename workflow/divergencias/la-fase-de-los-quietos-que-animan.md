# Qué

`animation_type` 1 y 3 de RM2k —"Continuous" y "Fixed Dir/Continuous"— hacen que
el evento recorra el ciclo de caminata sin moverse; el save point de Lashe City
es del segundo tipo. En RM2k cada personaje lleva su propio contador y arranca
en cero cuando el mapa lo crea.

Acá el contador es **global**: la columna sale de dividir el tick del juego por
`ANIM_CONTINUA` de la velocidad. Un evento que aparece a mitad de la partida
entra con el ciclo empezado en cualquier punto. El porqué —no hay byte por
evento para guardarlo— está en `animar_quietos` de `tools/runtime/animated_stills.s`.

# Medido

Nada que medir: el ciclo es de cuatro pasos y lo único que cambia es en cuál
empieza cada evento.

# Cómo se ve hoy

Nada que se pueda ver en una pantalla quieta.
