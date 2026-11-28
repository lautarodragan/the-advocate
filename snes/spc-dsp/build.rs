//! Compiles blargg's S-DSP, `vendor/snes_spc/`, and the C face the wrapper
//! calls, `src/shim.cpp`, into a static library.

fn main() {
    cc::Build::new()
        .cpp(true)
        // `throw()`, which `BLARGG_DISABLE_NOTHROW` puts on its `operator
        // new`, is gone from C++20, and a compiler's default standard moves:
        // the one the sources were written for, named.
        .std("c++11")
        // Nothing here throws or asks a type at run time, so no C++ runtime
        // is needed: the class brings its own `new` and `delete`, over
        // `malloc` and `free`. Without these, and with `cpp_link_stdlib`,
        // the release binaries would link libstdc++ for nothing.
        .flag_if_supported("-fno-exceptions")
        .flag_if_supported("-fno-rtti")
        .cpp_link_stdlib(None)
        .include("vendor/snes_spc")
        .file("vendor/snes_spc/SPC_DSP.cpp")
        .file("src/shim.cpp")
        // `NDEBUG` turns blargg's `assert` and `require` off: they would
        // abort the process. What `require` guards —`run` with no clocks—
        // the wrapper guards instead.
        .define("NDEBUG", "1")
        // Optimized in every profile: it is not debugged here, and the
        // debug profile's tests play whole songs through it.
        .opt_level(2)
        .warnings(false)
        .compile("spc_dsp");
    println!("cargo:rerun-if-changed=vendor/snes_spc");
    println!("cargo:rerun-if-changed=src/shim.cpp");
}
