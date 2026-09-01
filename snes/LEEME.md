# PoC de audio en Super Nintendo

Reproduce un tema en loop, sin dibujar nada ni leer el control. No reemplaza
nada del port a Mega Drive: es una rama aparte para ver si la SNES se acerca
más al original.

## Por qué

El sonido de la Mega Drive quedó lejos del MIDI de la PC, y no por falta de
voces sino por el método: el YM2612 es síntesis FM y el MIDI de Windows XP lo
tocaba un sintetizador **por muestras**. La SNES también es por muestras, así
que el problema deja de ser "imitar un piano con cuatro operadores" y pasa a ser
"comprimir estas muestras", que es mecánico.

De paso: 15 bits de color contra 9, y 8 paletas contra 4. Los 108 colores de los
seis CharSets del Auditorium entran sin fusionar ninguno.

## Veredicto

Probado en emulador: **suena mucho mejor que la Mega Drive y cerca del
original**, con muestras que todavía son ondas de un ciclo generadas en Python.
Esa era la pregunta que motivaba la rama, y la contesta a favor de la SNES.

## Cómo está armado

El audio lo maneja el **SPC700**, un procesador aparte con sus propios 64 KB. El
65816 no puede tocar el DSP: sólo hablarle al SPC700 por cuatro puertos. Al
encender, el SPC700 corre una ROM interna con un protocolo de carga; se lo usa
para meterle las muestras y un driver, y después ese driver se queda esperando
pares (registro, valor) que le pasa el 65816.

Eso deja el mismo reparto que en la Mega Drive: **toda la lógica en Python, y en
la consola sólo un intérprete de un stream de escrituras.** El driver del SPC700
son **20 bytes**.

    snes/src/main.s      65816: arranque, carga al SPC700, reproductor
    snes/snes.cfg        enlazado LoROM de 32 KB
    snes/record.sh       corre la ROM sin pantalla y graba el audio a WAV
    tools/spc700.py      ensamblador de SPC700, porque no hay uno empaquetado
    tools/brr.py         codificador del formato de muestras de la SNES
    tools/sdsp.py        registros del DSP y el banco de timbres
    tools/snes_music.py  el MIDI del mapa a muestras y stream
    tools/snes_check.py  compara lo que suena contra el MIDI
    tools/wavtone.py     mide la frecuencia de un WAV, para un tono suelto

## El banco de timbres

Que la SNES reproduzca muestras cambia el problema por completo. En el YM2612
cada timbre había que construirlo con cuatro operadores y nueve parámetros cada
uno, a ciegas; acá el timbre **es** la forma de onda, y una forma de onda se
describe diciendo cuánto pesa cada armónico — que es como se suele describir un
instrumento.

Por eso `sdsp.py` define cada uno como una lista de pesos: las cuerdas son un
diente de sierra (todos los armónicos cayendo como 1/n), la caña una cuadrada
(sólo los impares), el órgano unas pocas barras. Son ondas de un ciclo de 32
muestras, 18 bytes cada una en BRR: **las ocho entran en 144 bytes** de los 64 KB
del SPC700. Suenan a sintetizador, no a instrumento grabado, pero el espacio
para muestrear de verdad está entero sin usar.

Ocho voces, todas iguales, contra las nueve de la Mega Drive —seis de FM
decentes y tres de onda cuadrada—. Con el reparto de voces por cobertura, que es
el mismo código de `md_music.py`, se reproduce el **90%** del tiempo-nota del
tema de prueba contra el 95% de la Mega Drive.

## Toolchain

Todo de paquetes de Debian, dentro del contenedor: `cc65` para el 65816 y
`mednafen` para emular. **Nada clonado de internet ni compilado de fuentes sin
revisar**: para el SPC700, que no tiene ensamblador empaquetado, el de
`tools/spc700.py` es código propio y revisable, con los opcodes anotados.

## Cómo se verifica

`mednafen -soundrecord` vuelca lo que sale del DSP a un WAV. Sobre eso hay dos
medidas, ninguna de las cuales necesita escuchar.

Para un tono suelto alcanza con la frecuencia: `wavtone.py` la saca por
autocorrelación, y si se pidió un La de 440 tiene que dar 440.

    tono de prueba: 440.4 Hz medidos contra 440 pedidos, 1 cent de diferencia

Para un tema entero eso no sirve, porque suenan varias notas a la vez. Así que
`snes_check.py` lo hace al revés: del MIDI ya sabemos qué notas deberían estar
sonando en cada momento, así que en vez de preguntarle al audio qué frecuencia
tiene se le pregunta cuánta energía tiene en esa frecuencia. La prueba está en
que además se mide un **señuelo** un cuarto de tono más arriba, que no cae en
ninguna nota: si el mapeo de alturas estuviera mal, el señuelo tendría tanta
energía como la nota buena.

    tema 11h035: 57 de 60 ventanas con la nota por encima de su señuelo (95%)

La medida es ciega en los graves, y conviene saberlo: a 87 Hz el señuelo cae a
1,3 Hz de la nota y la ventana de análisis resuelve 11,7 Hz, así que ahí empatan.
Sirve de los medios para arriba.

También se controla el pico del WAV. El DSP suma las ocho voces y recién después
aplica el volumen general, sin limitar en el medio: la primera versión saturaba
(pico 32768 clavado) y hubo que bajar el techo por voz. Los números de `sdsp.py`
salen de medir, no de la teoría, porque la teoría supone que todas las voces
pican juntas y en fase y eso no pasa nunca.

## Lo que falta

* **Muestras de verdad.** Es lo único que separa esto de sonar parecido al
  original, y es donde está toda la ventaja de la consola. Las de ahora son
  ondas de un ciclo generadas en Python y ocupan 144 bytes de los 64 KB.
* Mejorar el BRR: hoy usa el filtro 0, sin predicción, y pierde un 10%. Los
  filtros con predicción bajan bastante eso.
* El stream del tema son 19 KB en una ROM de 32. El puntero de música no sabe
  cruzar de banco, así que para temas más largos —o para varios— hay que
  resolver eso antes de agrandar la ROM.
