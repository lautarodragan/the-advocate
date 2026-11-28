// The C face of SPC_DSP, which `src/lib.rs` calls: four functions over the
// class, so that Rust does not have to know C++'s calling convention.
#include "SPC_DSP.h"

extern "C" {

// A DSP over `ram`, at its power-on state, or NULL if there is no memory:
// the class's own `operator new` returns NULL instead of throwing, and
// `new (std::nothrow)` does not compile against it.
SPC_DSP* spc_dsp_new(unsigned char* ram) {
    SPC_DSP* dsp = new SPC_DSP;
    if (dsp) {
        dsp->init(ram);
    }
    return dsp;
}

void spc_dsp_free(SPC_DSP* dsp) { delete dsp; }

void spc_dsp_write(SPC_DSP* dsp, int address, int data) { dsp->write(address, data); }

// Runs `clocks` clocks, which must be at least one —`run(0)` counts down
// through four billion—, into `out`, with room for `room` samples, and says
// how many it wrote.
int spc_dsp_run(SPC_DSP* dsp, int clocks, short* out, int room) {
    dsp->set_output(out, room);
    dsp->run(clocks);
    return dsp->sample_count();
}

}
