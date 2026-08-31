CROSS   = m68k-linux-gnu-
CC      = $(CROSS)gcc
LD      = $(CROSS)ld
OBJCOPY = $(CROSS)objcopy

CFLAGS  = -m68000 -Os -fomit-frame-pointer -fno-builtin -ffreestanding \
          -fno-pic -Wall -Wextra -Isrc
LDFLAGS = -T md.ld -nostdlib --no-warn-rwx-segments

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
	python3 ../tools/md_fixrom.py $@

clean:
	rm -rf build

.PHONY: all clean
