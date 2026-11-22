// Mesen2's core behind the libretro calls `retro.py` makes, so the harness
// can play a state taro saved in their own Mesen2 on the same emulator, and
// count what that emulator counts. Mesen2 has no libretro core of its own
// —the `mesen-s` one is Mesen-S, an older and different emulator—, so this
// file is compiled together with Mesen2's sources by `just mesen2-core`,
// which says which commit and why.
//
// It is only what the harness uses: load, one frame per `retro_run`, the
// pad, the picture, the WRAM and the SRAM, reset. And four things no
// libretro core has:
//
//   * memory id 0x8100, a u32 with Mesen2's own lag counter
//     (`BaseControlManager::_lagCounter`), the number its HUD shows: a frame
//     in which nothing read the pad;
//   * `mesen2_load_state` and `mesen2_save_state`, Mesen2's `.mss` files;
//   * `mesen2_watch` and `mesen2_hits`, a line profiler that does not touch
//     the ROM: a list of CPU addresses, and for every instruction about to
//     run at one of them, which one, the PPU's frame and its scanline.
//
// Mesen2's public interface runs the emulation on a thread of its own and
// paces it with a clock. To run exactly one frame on the caller's thread,
// the shim parks that thread —it waits on `_runLock` before its loop, and
// the shim holds the lock from before the load— and calls the console's
// `RunFrame` itself. That needs members the headers keep private, hence the
// `#define private public` around them: it changes no layout, and it is
// what pins the shim to one Mesen2 commit.
#include "pch.h"
#define private public
#define protected public
#include "Shared/Emulator.h"
#include "Shared/EmuSettings.h"
#include "Shared/KeyManager.h"
#include "Shared/Interfaces/IKeyManager.h"
#include "Shared/Interfaces/IConsole.h"
#include "Shared/BaseControlManager.h"
#include "Shared/FrameLimiter.h"
#include "Shared/SystemActionManager.h"
#include "Shared/MemoryType.h"
#include "Shared/SaveStateManager.h"
#include "Utilities/FolderUtilities.h"
#include "Utilities/VirtualFile.h"
#include "SNES/SnesConsole.h"
#include "SNES/SnesCpu.h"
#include "SNES/SnesPpu.h"
#include "SNES/Spc.h"
#undef private
#undef protected
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <thread>
#include <unistd.h>
#include <unordered_map>
#include <vector>

// The commit the shim was built against: `just mesen2-core` defines it.
#ifndef MESEN2_PIN
#define MESEN2_PIN "unknown"
#endif

typedef bool (*env_cb)(unsigned, void*);
typedef void (*video_cb)(const void*, unsigned, unsigned, size_t);
typedef void (*poll_cb)();
typedef int16_t (*state_cb)(unsigned, unsigned, unsigned, unsigned);

static env_cb g_env;
static video_cb g_video;
static poll_cb g_poll;
static state_cb g_state;
static Emulator* g_emu;
static uint32_t g_lag;
static bool g_keys[16];
static uint16_t g_picture[512 * 478];
static std::unordered_map<uint32_t, uint32_t> g_watch;
static std::vector<uint32_t> g_hits;

// The pad: Mesen2 asks a key manager whether a key code is down, and the
// shim maps the twelve buttons to codes 1-12 —libretro's joypad ids, plus
// one— and answers from what `retro_input_state` said this frame.
class ShimKeys : public IKeyManager {
public:
	void RefreshState() override {}
	void UpdateDevices() override {}
	bool IsMouseButtonPressed(MouseButton) override { return false; }
	bool IsKeyPressed(uint16_t code) override { return code >= 1 && code <= 12 && g_keys[code]; }
	vector<uint16_t> GetPressedKeys() override { return {}; }
	string GetKeyName(uint16_t) override { return ""; }
	uint16_t GetKeyCode(string) override { return 0; }
	bool SetKeyState(uint16_t, bool) override { return false; }
	void ResetKeyState() override {}
	void SetDisabled(bool) override {}
};
static ShimKeys g_keymanager;

struct retro_system_info { const char* library_name; const char* library_version; const char* valid_extensions; bool need_fullpath; bool block_extract; };
struct retro_game_info { const char* path; const void* data; size_t size; const char* meta; };
struct retro_game_geometry { unsigned base_width, base_height, max_width, max_height; float aspect_ratio; };
struct retro_system_timing { double fps, sample_rate; };
struct retro_system_av_info { retro_game_geometry geometry; retro_system_timing timing; };

#define API extern "C" __attribute__((visibility("default")))

static void read_the_pad()
{
	if(g_poll) g_poll();
	for(unsigned id = 0; id < 12; id++) {
		g_keys[id + 1] = g_state && g_state(0, 1 /* JOYPAD */, 0, id);
	}
}

// The frame Mesen2's PPU finished, to libretro's default pixel format,
// 0RGB1555: the console's colors are 0BGR, so red and blue swap. 256x239,
// or 512x478 when the frame had a high-resolution mode, with the 7 lines
// above and 8 below the picture black, as Mesen2 shows them —`retro.py`
// crops to the middle 224—.
static void send_the_picture()
{
	if(!g_video) return;
	SnesPpu* ppu = ((SnesConsole*)g_emu->_console.get())->_ppu.get();
	unsigned width = ppu->_useHighResOutput ? 512 : 256;
	unsigned height = ppu->_useHighResOutput ? 478 : 239;
	const uint16_t* bgr = ppu->GetScreenBuffer();
	for(unsigned i = 0; i < width * height; i++) {
		uint16_t c = bgr[i];
		g_picture[i] = ((c & 0x1F) << 10) | (c & 0x3E0) | ((c >> 10) & 0x1F);
	}
	g_video(g_picture, width, height, width * 2);
}

// One frame, one instruction at a time, noting the watched ones. It is
// `SnesConsole::RunFrame` with the lookup before each `Exec`: several times
// slower, so `retro_run` only takes this path while something is watched.
static void run_watching()
{
	SnesConsole* console = (SnesConsole*)g_emu->_console.get();
	SnesCpu* cpu = console->_cpu.get();
	SnesPpu* ppu = console->_ppu.get();
	console->UpdateRegion();
	console->_frameRunning = true;
	while(console->_frameRunning) {
		SnesCpuState& state = cpu->GetState();
		auto watched = g_watch.find(((uint32_t)state.K << 16) | state.PC);
		if(watched != g_watch.end()) {
			g_hits.push_back(watched->second);
			g_hits.push_back(ppu->GetFrameCount());
			g_hits.push_back(ppu->GetScanline());
		}
		cpu->Exec();
	}
	console->_spc->ProcessEndFrame();
}

static std::string g_home;

static void forget_the_home()
{
	std::error_code ignored;
	std::filesystem::remove_all(g_home, ignored);
}

API unsigned retro_api_version() { return 1; }
API void retro_get_system_info(retro_system_info* info)
{
	info->library_name = "Mesen2";
	info->library_version = MESEN2_PIN;
	info->valid_extensions = "sfc|smc";
	// Mesen2 opens the file itself, and finds the MSU-1's `.msu` and
	// `-N.pcm` next to that path.
	info->need_fullpath = true;
	info->block_extract = true;
}
API void retro_get_system_av_info(retro_system_av_info* av)
{
	av->geometry = {256, 239, 512, 478, 4.0f / 3.0f};
	av->timing = {60.0988, 32040.0};
}
API void retro_set_environment(env_cb cb) { g_env = cb; }
API void retro_set_video_refresh(video_cb cb) { g_video = cb; }
API void retro_set_audio_sample(void*) {}
API void retro_set_audio_sample_batch(void*) {}
API void retro_set_input_poll(poll_cb cb) { g_poll = cb; }
API void retro_set_input_state(state_cb cb) { g_state = cb; }
API void retro_set_controller_port_device(unsigned, unsigned) {}
API void retro_init() {}
API void retro_deinit() {}

API bool retro_load_game(const retro_game_info* game)
{
	// Mesen2 keeps its settings, its saves and its states in a home folder.
	// One of its own per process, and gone at exit: the frontend's system
	// directory can be the ROM's —`retro.Console` with the MSU-1 on— and
	// the SRAM Mesen2 left there would be loaded the next time.
	const char* tmp = getenv("TMPDIR");
	std::string pattern = std::string(tmp && *tmp ? tmp : "/tmp") + "/mesen2-XXXXXX";
	std::vector<char> buffer(pattern.begin(), pattern.end());
	buffer.push_back(0);
	if(!mkdtemp(buffer.data())) return false;
	g_home = buffer.data();
	atexit(forget_the_home);
	FolderUtilities::SetHomeFolder(g_home);

	g_emu = new Emulator();
	KeyManager::RegisterKeyManager(&g_keymanager);
	KeyManager::SetSettings(g_emu->GetSettings());
	g_emu->Initialize(false);

	SnesConfig& snes = g_emu->GetSettings()->GetSnesConfig();
	snes.Port1.Type = ControllerType::SnesController;
	KeyMapping& k = snes.Port1.Keys.Mapping1;
	k.B = 1; k.Y = 2; k.Select = 3; k.Start = 4; k.Up = 5; k.Down = 6;
	k.Left = 7; k.Right = 8; k.A = 9; k.X = 10; k.L = 11; k.R = 12;
	g_emu->GetSettings()->GetAudioConfig().EnableAudio = false;
	g_emu->GetSettings()->SetFlag(EmulationFlags::MaximumSpeed);

	g_emu->_runLock.Acquire();
	if(!g_emu->LoadRom(VirtualFile(string(game->path)), VirtualFile())) {
		return false;
	}
	// What `Emulator::Run` would set on its own thread: the code that checks
	// it is on the emulation thread has to find this one.
	g_emu->_emulationThreadId = std::this_thread::get_id();
	g_emu->_frameDelay = 0;
	g_emu->_frameLimiter.reset(new FrameLimiter(0));
	return true;
}

API void retro_run()
{
	read_the_pad();
	if(g_watch.empty()) {
		g_emu->_console->RunFrame();
	} else {
		run_watching();
	}
	g_lag = g_emu->GetLagCounter();
	send_the_picture();
}

// From here on, every instruction about to run at one of these 24-bit CPU
// addresses is noted with its index in the list; an empty list stops.
// The CPU address, not the ROM's: code that runs from a mirror —bank $80
// and bank $00— is two addresses, and the caller passes both.
API void mesen2_watch(const uint32_t* addresses, int count)
{
	g_watch.clear();
	for(int i = 0; i < count; i++) g_watch[addresses[i]] = i;
	g_hits.clear();
}

// The oldest of what was noted and not yet asked for, up to `max` hits of
// three u32 each —index, PPU frame, scanline—, which are forgotten. Returns
// how many: fewer than `max` is all there was.
API int mesen2_hits(uint32_t* out, int max)
{
	int n = (int)g_hits.size() / 3;
	if(n > max) n = max;
	memcpy(out, g_hits.data(), n * 3 * sizeof(uint32_t));
	g_hits.erase(g_hits.begin(), g_hits.begin() + n * 3);
	return n;
}

API void retro_reset()
{
	g_emu->_console->Reset();
	g_emu->_systemActionManager->ResetState();
}

API void* retro_get_memory_data(unsigned id)
{
	if(id == 0x8100) return &g_lag;
	if(id == 2) return g_emu->GetMemory(MemoryType::SnesWorkRam).Memory;
	if(id == 0) return g_emu->GetMemory(MemoryType::SnesSaveRam).Memory;
	if(id == 3) return g_emu->GetMemory(MemoryType::SnesVideoRam).Memory;
	return nullptr;
}
API size_t retro_get_memory_size(unsigned id)
{
	if(id == 0x8100) return sizeof(g_lag);
	if(id == 2) return g_emu->GetMemory(MemoryType::SnesWorkRam).Size;
	if(id == 0) return g_emu->GetMemory(MemoryType::SnesSaveRam).Size;
	if(id == 3) return g_emu->GetMemory(MemoryType::SnesVideoRam).Size;
	return 0;
}
API void retro_unload_game() {}
API unsigned retro_get_region() { return 0; }
// libretro's own states are not offered: the harness does not use them, and
// Mesen2's are the `.mss` below.
API size_t retro_serialize_size() { return 0; }
API bool retro_serialize(void*, size_t) { return false; }
API bool retro_unserialize(const void*, size_t) { return false; }

// Mesen2's own save states. The stream versions and not the path ones: those
// take the emulator's lock, which is the one parking its thread, and
// releasing it would wake that thread.
API bool mesen2_save_state(const char* path)
{
	ofstream file(path, ios::out | ios::binary);
	if(!file) return false;
	g_emu->GetSaveStateManager()->SaveState(file);
	return true;
}
API bool mesen2_load_state(const char* path)
{
	ifstream file(path, ios::in | ios::binary);
	if(!file) return false;
	return g_emu->GetSaveStateManager()->LoadState(file);
}
