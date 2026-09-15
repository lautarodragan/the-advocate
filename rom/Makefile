# Construye la ROM con ca65 + ld65, que NO es como se compila el proyecto hoy:
# eso lo hace `just snes-build`, con el ensamblador propio de `w65/`.
#
# Hoy no anda, y se sabe dónde: de las 30.300 líneas de `main.s`, ca65 acepta
# todo salvo `.bloque` —el acomodo de bloques en bancos, 974 usos—, `.alinear`
# (28), `.controlar` (10) y dos `lda #-1`. `.bloque` es el único trabajo de
# fondo y cae en el asignador.
#
# Queda porque taro decidió que el port va a pasar a ca65 + ld65 —un proyecto
# mantenido y con ecosistema, antes que sostener el nuestro—, y esto con
# `snes.cfg` es por dónde empieza esa migración. Hasta el 2026-09-15 existía
# para otra cosa: ser el patrón de comparación de `just snes-validar`, que se
# borró junto con la segunda implementación del ensamblador.
#
# Por eso la salida se llama distinto: abl-ca65.sfc no es la que se emula.
AS   = ca65
LD   = ld65

ASFLAGS = --cpu 65816 -I src

OBJS = build/main.o

all: build/abl-ca65.sfc

build:
	mkdir -p build

build/%.o: src/%.s src/musicdata.inc | build
	$(AS) $(ASFLAGS) -o $@ $<

build/abl-ca65.sfc: $(OBJS) snes.cfg
	$(LD) -C snes.cfg -o $@ $(OBJS)

clean:
	rm -rf build

.PHONY: all clean
