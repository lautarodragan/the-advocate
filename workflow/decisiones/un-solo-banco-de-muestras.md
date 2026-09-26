# Qué

**Los temas comparten un solo banco de muestras** —una por programa de General
MIDI y una por golpe, en todo el cartucho—, que se sube a la ARAM **de a
paquetes, uno por mapa**, y **cada muestra tiene el presupuesto de su peor
paquete**.

# Por qué

**Un banco y no una copia por tema** es por la numeración y por el
directorio. El SRCN que escribe el stream es el número de la muestra en el
cartucho, así que dos temas que tocan piano apuntan a la misma, y una copia
por tema serían unas 430 muestras contra un SRCN de un byte que también
numera los 92 efectos. Es la opción B del paso 6 de
`tasks/todo/la-calidad-de-la-musica.md`: saca el techo que un paquete ajeno
le pone a un programa, y para entrar pediría darles a los efectos su propio
lugar en el directorio.

**El presupuesto es por paquete y no por banco** desde el 2026-09-26 (la
opción A del mismo paso, elegida por taro). A la ARAM nunca va el banco sino
un paquete, así que lo que tiene que entrar en los 64 KB es cada paquete con
sus efectos, y el tema que puede venir sonando del mapa anterior (ver
`el-tema-que-suena-gana-y-los-efectos-esperan.md`). Hasta ese día el banco
**entero** tenía que entrar, con 40 KB para lo melódico: para que entrara,
diecinueve de los treinta y dos temas del `release` no aportaban programas y
sonaban con lo que otros habían puesto, y la mediana de los programas estaba
en 11 kHz. Con el presupuesto por paquete aportan todos y la mediana pasa de
21 kHz.

**Lo que cuesta**: cada paquete llena la ARAM casi entera, así que subirlo
tarda más —la pelea, 58 cuadros al entrar en vez de 36—; taro lo dio por
bueno ("1,3 s es un costo muy bajo que pagar por lo que obtenemos a
cambio"), y taparlo con un fundido es `tasks/todo/el-fundido-al-entrar-y-salir-de-la-pelea.md`.
Y una muestra que comparten un mapa lleno y uno vacío queda a la tasa del
lleno en los dos: los efectos de los mapas 2 y 3 son los que más limitan.

Cómo se reparte, en `snes_music.repartir` y `Banco`; qué paquete limita a
cada muestra, en el informe del conversor.
