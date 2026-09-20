# Qué

Después del tercer teletransporte interno de la escena del mapa 16, **la ROM
arranca el `MoveEvent` que sigue cuatro ticks antes** que RM2k, y la pantalla
queda corrida ocho pixeles hasta que el teletransporte siguiente vuelve a
sincronizar al héroe con la cámara.

# Medido

Contra la referencia en Python, mientras existió: el **cuadro 500** de esa
escena daba **43,86%** de pixeles distintos —25.153 de 57.344—, en los dos
cartuchos de entonces.

Leyendo la WRAM, en el **tick 490** la ROM tiene al héroe en 368 y la cámara en
248, y la referencia 378 y 258.

# Cómo se ve hoy

No da rojo: la golden es la captura de la propia ROM. Se coló porque **ningún
caso de la tanda corre una página con un `Teleport` al mismo mapa**, y ahí está
la prueba que falta si alguna vez se encara.
