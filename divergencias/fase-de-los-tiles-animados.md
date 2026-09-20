# Qué

En una ruta forzada del héroe en el mapa 6, **dos tiles animados del chipset
cambian de paso un cuadro antes** de un lado que del otro.

# Medido

Encontrado de paso el 2026-09-12 armando los casos de la orden 34: el héroe
baja cuatro celdas desde (22,12), la ruta termina en el cuadro 32, y **del
cuadro 47 en adelante hay diez pixeles** de diferencia, siempre en esos dos
tiles.

**No es de la orden 34**: el control sin ella —la ruta `2 2 2 2` pelada— da
exactamente lo mismo. El sospechoso era la fase de los tiles animados, que los
dos lados contaban con relojes distintos.

# Cómo se ve hoy

**Dejó de poder investigarse así.** La referencia se borró el 2026-09-16 y con
ella sus dos contadores, y la golden hornea lo que hace la ROM, así que la
divergencia no existe como rojo. Si el paso de los tiles animados llegara a
estar mal, lo dice el ojo y no la tanda; los casos siguen mirando hasta el
cuadro 40.
