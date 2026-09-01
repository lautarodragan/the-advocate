CROSS   = m68k-linux-gnu-
CC      = $(CROSS)gcc
LD      = $(CROSS)ld
OBJCOPY = $(CROSS)objcopy

# -MMD -MP hace que gcc escriba las dependencias de cada .o. Sin eso, cambiar
# de mapa recompila mapdata.c pero no main.c, que quedaría con las dimensiones
# del mapa anterior y leería el tilemap con el stride equivocado.
CFLAGS  = -m68000 -Os -fomit-frame-pointer -fno-builtin -ffreestanding \
          -fno-pic -Wall -Wextra -Isrc -MMD -MP
LDFLAGS = -T md.ld -nostdlib --no-warn-rwx-segments

PAD ?= 0

OBJS = build/boot.o build/main.o build/mapdata.o

all: build/abl.bin

build:
	mkdir -p build

build/%.o: src/%.c | build
	$(CC) $(CFLAGS) -c $< -o $@

build/%.o: src/%.S | build
	$(CC) $(CFLAGS) -c $< -o $@

build/abl.elf: $(OBJS) md.ld
	$(LD) $(LDFLAGS) $(OBJS) -o $@

build/abl.bin: build/abl.elf
	$(OBJCOPY) -O binary $< $@
	python3 ../tools/md_fixrom.py $@ --pad $(PAD)

clean:
	rm -rf build

-include $(OBJS:.o=.d)

.PHONY: all clean
