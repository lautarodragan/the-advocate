AS   = ca65
LD   = ld65

ASFLAGS = --cpu 65816 -I src

OBJS = build/main.o

all: build/abl.sfc

build:
	mkdir -p build

build/%.o: src/%.s src/musicdata.inc | build
	$(AS) $(ASFLAGS) -o $@ $<

build/abl.sfc: $(OBJS) snes.cfg
	$(LD) -C snes.cfg -o $@ $(OBJS)

clean:
	rm -rf build

.PHONY: all clean
