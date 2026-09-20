# Qué

Que el presupuesto de ARAM se reparta **por paquete y no por banco**: darle a
cada programa lo que su peor paquete puede pagar, en vez de una parte del banco
entero.

# Status

Anotado, sin empezar. Estaba en "Lo que falta del port" de `ESTADO.md`.

# Por qué

El banco compartido entero tiene que entrar en los 64 KB de ARAM, y eso era el
límite de verdad **antes** del paquete de audio por mapa: ahora en la ARAM viven
el directorio y un paquete, no el banco, y con todos los temas de la demo
aportando el hardware entra de sobra —lo dice el informe del conversor—.

Lo que no entra es la calidad: repartir los 40 KB de `ARAM_BUDGET` entre casi el
doble de programas **baja la tasa mediana a la mitad para todos**, incluidos los
que hoy suenan bien. Mientras esto no esté, los temas que no aportan suenan
incompletos y el recorte va por prioridad: ver "Varios temas en el cartucho" en
`README.md`.
