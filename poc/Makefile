CROSS   = m68k-linux-gnu-
CC      = $(CROSS)gcc
LD      = $(CROSS)ld
OBJCOPY = $(CROSS)objcopy

CFLAGS  = -m68000 -Os -fomit-frame-pointer -fno-builtin -ffreestanding \
          -fno-pic -Wall -Wextra -Isrc
LDFLAGS = -T md.ld -nostdlib --no-warn-rwx-segments

OBJS = build/boot.o build/main.o build/assets.o

all: build/rm2k.bin

build/%.o: src/%.c
	$(CC) $(CFLAGS) -c $< -o $@

build/%.o: src/%.S
	$(CC) $(CFLAGS) -c $< -o $@

build/rm2k.elf: $(OBJS) md.ld
	$(LD) $(LDFLAGS) $(OBJS) -o $@

build/rm2k.bin: build/rm2k.elf
	$(OBJCOPY) -O binary $< $@
	python3 tools/fixrom.py $@

assets:
	python3 tools/rm2k2md.py assets/ChipSet_placeholder.png assets/CharSet_placeholder.png -o src/assets

clean:
	rm -f build/*.o build/*.elf build/*.bin

.PHONY: all clean assets
