# Qué

Una animación de batalla sobre el mapa se dibuja **achicada, entera y con su
proporción, hasta entrar en una caja de 64x64**, y sin transparencia: un objeto
de la consola es opaco o no está. RM2k la dibuja a su tamaño, con el alfa de
cada celda.

De dónde sale la caja, y la lista entera de lo que se pierde —el alfa
redondeado, el destello de pantalla que no la alcanza, el objetivo sin fila,
las `global`—, está en el docstring de `tools/port/animacion.py`, que es donde
se decide. taro aceptó el precio el 2026-09-12.

# Medido

Cuánto se achica cada una lo dice el conversor. El 2026-09-12: una de 96x96
queda en 64x64, el 67%; la 78 de la intro al 36%, y la 82, que mide 536x416, al
11%.

# Cómo se ve hoy

Las grandes de la intro se ven chicas. Una celda que se desvanece desaparece al
pasar la mitad en vez de irse de a poco.

# Cuándo deja de alcanzar

Un mapa que llene las ocho paletas de sprite y además necesite el cronómetro:
ahí la caja se queda sin paleta, y el conversor lo dice y no dibuja. Ver
`siete-paletas-en-un-mapa-con-animaciones.md`.
