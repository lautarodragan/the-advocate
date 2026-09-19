# Qué

Un ejecutor con pruebas declarativas

test --game … --tests …, y cada prueba es un archivo que dice qué caso, qué botones en qué cuadro, dónde capturar contra qué golden y qué memoria verificar. Los casos y las goldens ya son datos; falta el guion. 

# Status

Pausado. Probablemente lo descartemos. No vale aportar complejidad si no podemos cubrir todas las pruebas,
y probablemente siempre necesitemos esa libertad.

# Investigación

De ~465 pruebas, 253 ya tienen esa forma. 

┌─────────────────────────────────────────────────────────────────────────────────────┬──────────────────────────────────┐
│                                                                                     │             pruebas              │
├─────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────┤
│ Entran tal cual en el formato                                                       │ 259: las 253 de la tanda y 6 más │
├─────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────┤
│ Entran con agregados chicos                                                         │ 34 (±3)                          │
├─────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────┤
│ Corren la ROM y necesitan código                                                    │ 95                               │
├─────────────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────┤
│ No corren ninguna ROM (herramientas, conversor, cuentas sobre la tabla de símbolos) │ 78                               │
└─────────────────────────────────────────────────────────────────────────────────────┴──────────────────────────────────┘

Las 78 del final no cuentan para el ejecutor: se quedan en Python porque no hay ROM que correr.

Las 253 de la tanda entran todas. Ninguna decide nada según lo que ve. Si el chequeo automático marcó test_tanda.py y test_tanda_pantallas.py fue por costumbre, no por lógica: range() que se expanden a listas fijas, o funciones como plan() que devuelven números fijos. Para que entren, el formato base tiene que traer cuatro cosas:
- el cartucho como la lista de flags del conversor;
- dos relojes: ticks de juego y cuadros de hardware (este último para batalla, menú y título), con su arranque;
- los cuatro tipos de toque del arnés, más los botones sostenidos;
- varias capturas por prueba, cada una desde una consola nueva.

Por qué las 95 necesitan código:
- Esperar hasta que pase algo (35): tocar A hasta que cambie el mapa, jugar los turnos de una pelea según lo que muestra la pantalla, el recorrido hacia un destino.
- Guardar, reiniciar y cargar (25): guardar en una ranura, reiniciar, elegir la partida y leer lo que volvió. Con dos acciones nuevas en el formato entrarían unas 19, pero eso ya es un agregado grande.
- Lo esperado se calcula con el LDB o con un modelo en Python (15), como la pelea entera turno a turno contra batalla.Batalla.
- Lo esperado se dibuja en Python (12), como el menú contra titulo.render_menu.
- Otras lógicas (7): la diferencia entre dos corridas, los conjuntos de muestras en la ARAM, una medición de rendimiento.
- Una de test_cores, que mira los niveles de los canales de audio.

El matiz importante: unas 30 de esas 95 se podrían congelar como "en el tick N vale esto". Pero cambiaría lo que prueban: pasarían de "coincide con RM2k" (el valor sale del LDB o del modelo) a "coincide con lo que dio la ROM el día de la foto", y una golden no caza errores de nacimiento. Es la misma pérdida que asumimos el 16 al sacar la referencia. Esas yo las dejaría en Python a propósito.

Los agregados chicos que suman las 34:
1. Leer por número los datos de RM2k: switch N, ítem N, el mapa actual, variable N. La variable es la difícil, porque su ranura la calcula el conversor desde el LDB, y sin ella se caen 10 pruebas. Se resolvería sin que el ejecutor conozca el LDB si el conversor emite los símbolos (VAR_17 = ranura), como ya hace con CASO_RANURA.
2. Un estado inicial más rico: switches, grupo, ir_al_mapa, y bytes cuyo valor es el de otro símbolo.
3. Operadores simples, como "distinto de cero" o una máscara de bits. Casi todos se reemplazan congelando el valor exacto.
4. Comparar contra una constante del motor, por ejemplo ORO_MAX == 999999.
5. Correr en otro core y comparar contra la golden a 15 bits, para 4 de las 5 de test_cores.

Mi lectura: el ejecutor vale la pena para esas ~290 pruebas, que son tres cuartos de las que corren ROM. El resto se queda en Python sin que eso sea una derrota: son justamente las que comparan contra RM2k y no contra una foto.
