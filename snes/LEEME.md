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
    tools/wavtone.py     mide la frecuencia de un WAV, para verificar

## Toolchain

Todo de paquetes de Debian, dentro del contenedor: `cc65` para el 65816 y
`mednafen` para emular. **Nada clonado de internet ni compilado de fuentes sin
revisar**: para el SPC700, que no tiene ensamblador empaquetado, el de
`tools/spc700.py` es código propio y revisable, con los opcodes anotados.

## Cómo se verifica

`mednafen -soundrecord` vuelca lo que sale del DSP a un WAV, y `wavtone.py` le
mide la frecuencia por autocorrelación. No hace falta escuchar: si se pidió un
La de 440 y lo grabado tiene su período en 440, la cadena funcionó.

    tono de prueba: 440.4 Hz medidos contra 440 pedidos, 1 cent de diferencia

## Lo que falta

* Convertir un MIDI entero, no un tono suelto.
* Mejorar el BRR: hoy usa el filtro 0, sin predicción, y pierde un 10%. Los
  filtros con predicción bajan bastante eso.
* Muestras de verdad. Las de ahora son formas de onda de un ciclo generadas en
  Python; entran los 64 KB de ARAM de sobra, pero suenan a sintetizador básico.
