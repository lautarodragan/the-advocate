---
name: "Optimizar los eventos paralelos al compilar"
description: "Detectar patrones en las páginas paralelas y generar algo más barato: correr menos seguido, o sólo cuando algo se mueve"
type: refactor
---

Idea de taro, el 2026-09-26, a partir de lo que midió la investigación de
los chips (`chips-sa-1-y-s-dd1.md`): en el mapa 11 las 13 páginas paralelas
sin espera se comen ~123 de las 262 líneas del cuadro, y casi todas
comparan coordenadas. *"Es completamente normal que los compiladores
optimicen código"*: el conversor ya es un compilador de RM2k a bytecode.

Ideas, de la más barata a la más ambiciosa:

1. **Correr las paralelas cada N cuadros** en vez de cada cuadro. El
   experimento está en curso: diez ROMs con N de 1 a 60 para que taro busque
   a mano el punto donde deja de funcionar (`/shared/experimentos/
   2026-09-26-paralelos-cada-n/`). Además dice si el lag es de las paralelas o
   de otra cosa.
2. **Un disparador sintético "al moverse"**: además de "paralelo", páginas
   que corren sólo cuando un evento (o el héroe) **cambia de celda** —no de
   pixel—. El código que mueve un evento hace una llamada que recorre las
   páginas con ese disparador. El conversor detecta qué paralelas son
   "comparar coordenadas y hacer algo" y las compila así. Y en build time se
   sabe si un mapa tiene alguna: un booleano por mapa, así el runtime no paga
   nada en los mapas sin ellas.
   - El caso de las luces del mapa 11 es el primero.
   - El segundo: **el evento paralelo que prende y apaga el guardado en el
     menú según si el héroe está parado sobre un save point** (compara
     coordenadas). Hoy no está implementado.
3. **Hornear patrones que se repiten** en las paralelas ("leer la X de un
   evento y compararla"), en opcodes compuestos. Sólo en paralelas, que son
   las que pesan.
4. **Eliminar código que no puede correr** y otras optimizaciones clásicas,
   si aparecen.

Lo que tiene que cuidar: la semántica de RM2k (el orden de `Game_Map::Update`,
qué ve una página en el cuadro en que otra la cambia), y que sea general del
motor y no específico de ABL.

**El 2026-09-27 se hizo la 3 para un patrón**, el de "¿está este personaje en
la celda de estas variables?", que es el de los autos de la carrera, las luces
del mapa 11 y unas doscientas cincuenta páginas del juego: `OP_CELL_TEST`, y
un atajo que corre esas páginas sin el intérprete cuando no pasan de la
condición. Ver `testing/carrera-2-a-sesenta-cuadros.md`, que tiene medido
también el límite de la 2 para la carrera: cero en el tick más pesado,
porque el héroe cambia de celda cada dos ticks.
