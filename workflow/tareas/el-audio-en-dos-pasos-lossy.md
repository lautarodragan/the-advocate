# Qué

Partir la conversión de audio en **dos pasos lossy explícitos y versionados**,
para que el último paso sea mecánico:

    (todos los MIDIs + SoundFont)  ->  SoundFont reducida     [decisión artística]
    (MIDI + SoundFont reducida)    ->  MIDI reducido          [decisión artística]
    (MIDIs reducidos + SoundFont reducida)  ->  streams + muestras BRR

Los dos primeros son artefactos que se miran, se comparan con el original y
**se pueden editar a mano** cuando una decisión queda mal. El tercero deja de
decidir nada.

# Status

Anotado el 2026-09-21, sin empezar. Es la tercera y cuarta clase de parche de
`parches-de-decisiones-artisticas.md`, que quedaron afuera porque la clave "el
tema" no identifica la decisión.

# Los cuatro sacrificios de hoy, y de qué paso son

1. **La polifonía**: ocho voces, y una nota que arranca sin voz libre se la
   saca a la que termina antes. **Es del tema y de nadie más** —nunca suenan
   dos temas a la vez— así que va en el paso del MIDI.
2. **Qué temas aportan programas al banco**: el recorte cuando no entra todo.
3. **La resolución de cada muestra**: `ARAM_BUDGET` repartido en partes
   iguales, con lo que sobra redistribuido.
4. **La tasa que baja para todos** al sumar temas: mediana de 12,5 a 8,4 kHz
   con diecinueve en vez de once.

2, 3 y 4 son el mismo paso: son función de **todos los temas del juego** + la
SoundFont + el presupuesto de ARAM + la prioridad.

# El acoplamiento que fija el orden

**Una nota se cae del stream cuando su programa no está en el banco**
—el `continue` de `build_events`—. O sea que el MIDI reducido no se puede
decidir sin saber qué quedó en la SoundFont reducida. Primero la SoundFont,
después el MIDI.

# Decisiones a tomar

* **Qué es la "SoundFont reducida"**: un `.sf2` de verdad, que se abre con
  cualquier editor, o un directorio de muestras ya resampleadas con su
  metadata. Lo primero es más útil para mirarlo; lo segundo es más fiel a lo
  que el paso final consume.
* **Qué lleva cada muestra ya decidido**: tasa, loop, normalización, recorte.
  Cuanto más lleve, menos decide el paso final.
* **Cómo se expresa el recorte por programa faltante** en el MIDI reducido:
  la nota se borra, o queda marcada.
* **El tope de polifonía**: no es ocho. Hay una voz reservada para los efectos
  de sonido, y el reparto de voces entre canales también es una decisión que
  conviene que viva en el mismo artefacto.
* **De qué conjunto de temas sale la decisión**: los de `abl`, siguiendo la
  regla de que lo versionado es lo del ROM jugable.

# Para qué sirve el artefacto: iterar sin armar la ROM

El MIDI reducido y la SoundFont reducida **se cargan en un DAW**, y ahí se
prueban ajustes sin pedir un build. Es el equivalente de los PNG que deja el
asignador en `rom/build/<cartucho>/asignador/`: se juzga el paso lossy mirando
—u oyendo— su salida.

Eso lo hace taro, así que el artefacto tiene que abrirse con herramientas de
todos los días, y **esa es la razón de que las envolventes salgan del
SoundFont** —`ataque-y-decaimiento-desde-el-soundfont.md`—: si la ROM usa las
ocho familias de `sdsp.py` y el DAW usa las del SoundFont, los ataques suenan
distinto y el artefacto miente donde más se nota.

**No reemplaza probar la ROM**, y hay dos diferencias que van a quedar siempre,
porque no son decisiones nuestras: el SPC700 interpola con su filtro gaussiano,
que redondea los agudos, y el DSP tiene eco por hardware que el driver no usa.

**La SoundFont reducida no pasa por BRR**, y es una decisión, no un olvido.
Meter un `encode` + `decode` para que el DAW reproduzca la pérdida de los 4 bits
dejaría **dos pasadas lossy** —la del artefacto y la del paso final—, que no
tienen por qué dar lo mismo. Vale más que el artefacto sea exactamente lo que
el paso final consume.

# Lo que no es una decisión

La codificación a BRR. Pierde señal —16 bits a 4— pero no hay nada que
elegir: es el formato del hardware, como los tiles de 8x8.
