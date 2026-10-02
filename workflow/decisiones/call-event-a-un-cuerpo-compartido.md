# Qué

**Un evento común tiene un cuerpo compartido en el cartucho, y se lo llama
con `OP_CALL`** desde el 2026-10-02: los automáticos, los que llaman las
páginas que corren en primer plano, y los que ésos llaman. Reemplaza en parte
a `call-event-se-compila-en-linea.md`: **se sigue pegando en el lugar** cuando
la página es paralela, cuando el cuerpo compilado con el mapa no es el mismo
que sin mapa, y en las páginas de tropa y los comunes de equipo.

El intérprete tiene **una sola pila de llamadas**, la del primer plano: tres
niveles de cinco bytes en la RAM lejana (`$6110` a `$611F`), y una llamada
con la pila llena se saltea. El conversor emite la cadena más honda como
`COMMON_DEPTH` y el ensamblado se niega si no entra.

# Por qué

**La portable console no entra pegada.** El común 39 llama al 21, que llama
18 veces al 25, que llama a ocho de los 23 a 31: pegado son 140.193
comandos; compartidos, los 25 cuerpos del juego son 8 KB.

**Y lo pegado costaba más de lo que decía la decisión vieja.** Ésa midió
+608 bytes en todo el juego, cuando compilaban diez llamadas; con el común 35
compilando desde el 2026-09-30 —`ResetAfterBattles`, que llama la automática
`AfterBattleMint` de cada mapa con encuentros— el bytecode de los mapas de
`release` era 136,4 KB crudos, y sin ninguna llamada 81,5. Compartiendo
queda en 89,3 KB crudos, 46,7 KB en LZ2 contra 89,1 antes.

**Por qué no todas las llamadas.** Un cuerpo compartido se compila sin mapa,
y lo que un mapa resuelve no está: sus eventos —una ruta, "este evento"—, su
banco de sprites, las imágenes que lleva, el efecto que ahí suena con otra
muestra, un `TileSubstitution`. Por eso una página llama sólo si el cuerpo
compilado con su mapa es **byte por byte** el de sin mapa; si no, pega como
antes, y sigue igual de exacta. La única diferencia que se perdona es el
refresco: sin mapa, toda escritura de variable lo pide, y con el mapa sólo
las que alguna condición de página mira (`refresh` en `compile.rs`). En una
página de primer plano no cuesta nada —el refresco es una bandera, y corre una
vez cuando el intérprete suelta—; en una paralela, que corre cada cuadro, fue
lo que dejó media Lashe City a treinta cuadros por segundo, **y por eso las
paralelas pegan**. Además comparten las globales del primer plano: una pila
para ellas sería otra por intérprete.

**Por qué en el cartucho y no con el mapa.** Un común automático corre en
cualquier mapa, y uno compartido puede seguir corriendo después de un
`Teleport`: leído de la ROM no se mueve. Lo que sí se mueve es la página que
llamó, que está en el bytecode del mapa en la WRAM: `code_carry_before` muda
a `CODE_CARRY` también los marcos de la pila, no sólo el cursor.

# Lo medido

El 2026-10-02, en `release`: 25 cuerpos y 8.176 bytes en el cartucho;
corren los automáticos 7, 11, 39, 43 y 50, y no compilan 16, 42 y 44. Las
goldens no se movieron. Cuánto queda hoy lo dice `just espacio`, y qué
cuerpos hay, el reporte del conversor.
