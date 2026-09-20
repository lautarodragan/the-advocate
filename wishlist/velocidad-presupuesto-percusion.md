# Qué

Buscar el presupuesto del banco de percusión por búsqueda binaria en vez de
bajarlo de a un 10% hasta que entre.

# Status

Anotado, sin empezar. El caché de muestras del 2026-09-20 lo **tapó en vez de
arreglarlo**: ya no cuesta tiempo, pero sigue estando.

# Por qué

El recorte de `snes_music.Banco` pide el banco de percusión, pregunta si entra,
y si no entra vuelve a pedirlo con el presupuesto bajado un 10%. Bajar de a un
10% hasta llegar a cero son unas ciento veinte vueltas, y por eso
`build_drum_bank` se llama **790 veces** en una conversión de `abl` en lugar de
diez.

Con el caché en disco esas vueltas ya no cuestan tiempo, pero **son lo que hoy
llena el caché de claves**, y sigue siendo una búsqueda lineal donde cabe una
binaria.

Lo que hay que cuidar: tocarlo **cambia qué muestras salen** —la binaria puede
aterrizar en otro presupuesto que la lineal—, así que pide medir la ROM byte
por byte y, si se mueve, decidir y rebendecir lo que se mueva. No es urgente.
