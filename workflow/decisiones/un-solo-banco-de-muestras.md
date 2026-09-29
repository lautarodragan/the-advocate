# Qué

**Los temas comparten un solo banco de muestras** —una por programa de General
MIDI y una por golpe, en todo el cartucho—, que se sube a la ARAM **de a
paquetes, uno por mapa**. Cada muestra tiene el presupuesto de su peor
paquete, **salvo que ese paquete no tenga a todos los temas que la usan**:
entonces, mientras quepa en el directorio, los de adentro tocan una copia y
los de afuera dejan de pagarlo.

# Por qué

**Un banco y no una copia por tema** es por la numeración y por el
directorio. El SRCN que escribe el stream es el número de la muestra en el
cartucho, así que dos temas que tocan piano apuntan a la misma, y el SRCN
es de un byte. Una copia por tema (la opción B del paso 6 de
`tasks/testing/la-calidad-de-la-musica.md`) serían unas 370 entradas contra
255. Hasta el 2026-09-26 el SRCN numeraba también cada efecto del cartucho;
desde ese día los efectos comparten los lugares del final del directorio,
porque a la ARAM va un paquete por vez: ver
`tasks/*/el-directorio-de-los-efectos.md`.

**El presupuesto es por paquete y no por banco** desde el 2026-09-26 (la
opción A del mismo paso, elegida por taro). A la ARAM nunca va el banco sino
un paquete, así que lo que tiene que entrar en los 64 KB es cada paquete con
sus efectos, y el tema que puede venir sonando del mapa anterior (ver
`el-tema-que-suena-gana-y-los-efectos-esperan.md`). Hasta ese día el banco
**entero** tenía que entrar, y diecinueve de los treinta y dos temas del
`release` no aportaban programas.

**Las copias**, desde el mismo día y por taro: *"No me parece aceptable que
instrumentos pierdan calidad por un solo mapa, pero tampoco quiero perder
calidad en los efectos de sonido."* Con una muestra por programa, los 43 KB
de efectos del mapa 3 dejaban la batería de todos los temas a 10 kHz y el
oboe a 7. Una copia es la misma clave como otra muestra, sólo para los temas
del grupo que la limita; se hacen la peor primero hasta llenar el
directorio como era cuando cada efecto tenía su entrada, y con las entradas
que los efectos liberaron, sólo las que no le bajan la tasa a nadie (ver
`copies` en `tools/rm2k-snes/rm2k-snes-audio/src/bank.rs`). Y los temas que un mapa prende sólo para irse —`lufsorr` en el 3,
que suena cuando ya no quedan efectos— no cuentan en el paquete del mapa:
ver `Temas.de_salida` en `tools/port/eventos.py`.

**Lo que cuesta**: cada paquete llena la ARAM casi entera, así que subirlo
tarda más —la pelea, 58 cuadros al entrar en vez de 36—; taro lo dio por
bueno ("1,3 s es un costo muy bajo que pagar por lo que obtenemos a
cambio"). Las copias pesan en el cartucho, y lo que se libera de un paquete
compite en los otros: el reparto le da a todo la misma fracción, así que lo
que antes sonaba a 22 kHz porque la batería estaba a 10 queda cerca de 16.
Un tema de salida que no entra al lado de su paquete congela, al prenderlo,
lo que tarda en subir él solo.

Cómo se reparte, en `allocate`, `copies` y `Bank` de `tools/rm2k-snes/rm2k-snes-audio/src/bank.rs`; qué grupo
limita a cada muestra y qué temas usan cada copia, en el informe del
conversor.
