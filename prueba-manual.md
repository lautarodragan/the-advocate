# 2026-09-05 02.48pm (ART)

Anoto por aquí porque la sesión llegó al límite.
De casualidad el turno terminó justo a tiempo (estamos al 99% de la sesión, en realidad,
pero sospecho que cualquier mensaje que envíe ahora va a ser cortado a mitad de turno).

Prueba manual en medfen:
- Efectivamente, el bug de la pared que rompe CORE está arreglado.
- Ahora puedo avanzar por el pasillo que lleva al ascensor
- Puedo interactuar con la puerta del ascensor, y se abre
- Pero no puedo _entrar_ al ascensor. Entrar al tile del portal del ascensor no triggerea ningún teleport.

## Teleport Bug

Un bug, que existe desde siempre, pero no lo había reportado antes.

Probado manualmente con Mesen, bajando la velocidad del emulador, teniendo el lua script
de debugging que viene por defecto (que imprime el frame count en pantalla), y
tomando screenshots manualmente:
- Entro en la puerta para activar el teleport al siguiente cuarto
- Hay 3 frames con la pantalla negra
- 1 frame con la pantalla negra, excepto tiles que aparecen en el borde inferior
- Se vuelve a ver la pantalla, pero sigo en el mismo cuarto por un frame
- En el siguiente frame, ya estoy en el siguiente cuarto

Jugando a velocidad normal, esto se percibe como un "flash" del cuarto actual después de
la pantalla negra, que es molesto.

Lo ideal sería:
- fade out
- cargar lo que haga falta
- fade in

El RPG Maker original, y el EasyRPG, hacen siempre fade-out y fade-in con los teleports.

En cualquier caso, podemos considerar a la falta de fade in/out como un feature no implementado, pero el flash por 1 frame como un bug, y el que a veces (medio random) se vean partes del mapa cargando durante la pantalla negra como otro bug distinto.

Te dejé varios screenshots en /extras/capturas/teleport-bug-manual. Son muchos como para cargar enteros en contexto,
así que, idealmente, evitá cargarlos directamente si podés, y analizalos con algún script.
Tal vez ni los necesites, y con mi descripción alcance.
