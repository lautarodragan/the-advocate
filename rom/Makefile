# Construye la ROM con ca65 + ld65, que ya NO es como se compila el proyecto.
#
# El build normal usa tools/w65.py, que es nuestro y no necesita contenedor.
# Esto queda como patrón de comparación: `just snes-validar` ensambla el mismo
# fuente con las dos cadenas y verifica que salgan los mismos 32.768 bytes.
#
# Por eso la salida se llama distinto: abl-ca65.sfc es la referencia, abl.sfc
# es la que produce w65.py y la que se emula.
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
