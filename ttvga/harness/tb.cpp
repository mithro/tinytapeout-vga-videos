// SPDX-License-Identifier: Apache-2.0
//
// Generic Verilator testbench for a Tiny Tapeout project with the Tiny VGA
// Pmod pinout. It clocks the design, applies the reset sequence the VGA
// Playground uses, works out the VGA timing from hsync/vsync on uo_out,
// decodes pixels and pipes raw frames to ffmpeg for encoding.
//
// Build with: verilator --cc --exe --build --prefix Vtop --top-module <top> tb.cpp <sources>
//
// Tiny VGA bit layout on uo_out (from vga-playground src/sim/vga.ts):
//   bit 7 hsync, bit 3 vsync, bits 0..2 = R1 G1 B1, bits 4..6 = R0 G0 B0.
//
// With --trace PATH it also records every pin at both halves of every clock
// through vgacap's trace writer (vgacap docs/trace-format.md, layout
// tt-um-43). The build then needs job.vgacap_link_flags. A clock whose pins
// are the last clock's is recorded from one raw compare of the model's port
// bytes (RawPorts below), without packing them.

#include "Vtop.h"
#include "Vtop___024root.h"
#include "qspi.h"
#include "verilated.h"
#include "vgacap/stream.h"
#include "vgacap/trace.h"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unordered_set>
#include <vector>

#if defined(TTVGA_TEST_FORCE_FALLBACK) && !defined(TTVGA_TEST_HOOKS)
#error "TTVGA_TEST_FORCE_FALLBACK is a test hook: it needs TTVGA_TEST_HOOKS"
#endif

namespace {

struct Mode {
    const char* name;
    int line_px, lines;        // total pixels per line, total lines per frame
    int hpulse, hback, width;  // pixels
    int vpulse, vback, height; // lines
};

// VESA/industry modes. Pixel clocks (MHz): 25.175, 31.5, 36, 40, 49.5, 50, 65, 74.25, 75, 108.
const Mode MODES[] = {
    {"640x480@60", 800, 525, 96, 48, 640, 2, 33, 480},
    {"640x480@72", 832, 520, 40, 128, 640, 3, 28, 480},
    {"640x480@75", 840, 500, 64, 120, 640, 3, 16, 480},
    {"800x600@56", 1024, 625, 72, 128, 800, 2, 22, 600},
    {"800x600@60", 1056, 628, 128, 88, 800, 4, 23, 600},
    {"800x600@72", 1040, 666, 120, 64, 800, 6, 23, 600},
    {"800x600@75", 1056, 625, 80, 160, 800, 3, 21, 600},
    {"1024x768@60", 1344, 806, 136, 160, 1024, 6, 29, 768},
    {"1024x768@70", 1328, 806, 136, 144, 1024, 6, 29, 768},
    {"1280x720@60", 1650, 750, 40, 220, 1280, 5, 20, 720},
    {"1280x1024@60", 1688, 1066, 112, 248, 1280, 3, 38, 1024},
};

struct Options {
    double clock_hz = 25175000.0;
    double seconds = 60.0;
    double calib_seconds = 1.0;   // how long to wait for stable sync
    std::string out_dir = ".";
    std::string ffmpeg = "ffmpeg";
    std::string inputs;           // optional input script
    std::string gamepad;          // optional gamepad button script
    std::string qspi;             // "" (off), "default", or a pin map
    std::string flash;            // file to preload into the modelled flash
    int ui_in = 0, uio_in = 0;    // constant inputs when no script
    double audio_rate = 192000.0; // audio sample rate, as the playground uses
    bool no_audio = false;
    bool quiet = false;
    std::string trace;            // "" (no trace) or the trace file to write
    std::vector<std::pair<std::string, std::string>> meta;   // --meta, in order
    std::string clock_hz_arg, seconds_arg = "60", calib_seconds_arg = "1";   // as given
};

// The zstd level of the trace's blocks. The pilot may change it.
constexpr int kTraceZstdLevel = 1;

// --meta keys tb.cpp writes itself into META(open).
bool meta_key_reserved(const std::string& k) {
    return k == "meta" || k == "calib_seconds" || k == "seconds" || k == "layout";
}

bool meta_key_ok(const std::string& k) {
    if (k.empty() || k[0] < 'a' || k[0] > 'z') return false;
    for (char c : k)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) return false;
    return true;
}

// The Audio Pmod carries one bit on uio[7]. The playground reads it as
// `(uio_out & uio_oe) >> 7`: only while the design is driving that pin, so a
// design that leaves it an input is silent rather than stuck high.
//
// Sampling follows the playground's AudioEngine. The bit is averaged over each
// sample period, which is the decimation, and then a moving average stands in
// for the 20 kHz low-pass filter on the Pmod itself. The playground runs this
// at 192 kHz because a higher rate leaves more room above the filter; the file
// is resampled to something ordinary when it is muxed into the video.
struct AudioCapture {
    double ticks_per_sample = 0;
    double phase = 0;             // fractional, so the rate stays exact over a minute
    double acc = 0;
    double ticks = 0;
    size_t filter = 1;
    size_t qi = 0;
    std::vector<float> queue;
    std::vector<float> samples;
    bool driven = false;          // did the design ever drive uio[7]?
    double hz = 0;                // the design clock, to judge the rate below
    uint64_t clocks = 0;          // clocks fed since capture began
    uint64_t transitions = 0;     // times the driven bit changed level
    int last_bit = -1;

    void begin(double clock_hz, double rate) {
        hz = clock_hz;
        ticks_per_sample = clock_hz / rate;
        filter = std::max<size_t>(1, static_cast<size_t>(std::ceil(rate / 20000.0)));
        queue.assign(filter, 0.0f);
    }

    // Driving the pin is not the same as putting sound on it. A great many
    // designs enable every uio output and hold them at one level, which
    // captures as a constant: a track of digital silence, and a page that
    // claims the clip has sound. The Audio Pmod's own filter starts at 20 Hz,
    // so a signal that does not cross that often has nothing audible in it
    // either, and the same number serves as the test.
    bool audible() const {
        const double secs = hz > 0 ? clocks / hz : 0.0;
        return secs > 0 && static_cast<double>(transitions) >= 20.0 * secs;
    }

    void feed(uint8_t uio_out, uint8_t uio_oe) {
        clocks += 1;
        if (uio_oe & 0x80) {
            driven = true;
            const int bit = (uio_out & 0x80) >> 7;
            if (last_bit >= 0 && bit != last_bit) transitions += 1;
            last_bit = bit;
        }
        acc += static_cast<double>((uio_out & uio_oe) >> 7);
        ticks += 1.0;
        phase += 1.0;
        if (phase < ticks_per_sample) return;
        phase -= ticks_per_sample;
        queue[qi] = static_cast<float>(ticks > 0 ? acc / ticks : 0.0);
        qi = (qi + 1) % filter;
        float sum = 0;
        for (float v : queue) sum += v;
        samples.push_back(sum / static_cast<float>(filter));
        acc = 0; ticks = 0;
    }
};

struct InputEvent { uint64_t clock; int ui_in; int uio_in; };

int parse_int(const std::string& s) {
    return static_cast<int>(std::strtol(s.c_str(), nullptr, 0));
}

// Gamepad Pmod emulation, as in the VGA Playground's InputController.ts:
// once per scan line the controller state advances one step of a 400-step
// cycle: 24 clock pulses shifting the 24-bit report (12 buttons of
// controller 1 in the upper half, LSB first), then a latch pulse. Pins on
// ui_in: bit 6 data, bit 5 clock, bit 4 latch.
struct GamepadEvent { uint64_t clock; int buttons; };

std::vector<GamepadEvent> load_gamepad(const std::string& path) {
    std::vector<GamepadEvent> ev;
    if (path.empty()) return ev;
    FILE* f = std::fopen(path.c_str(), "r");
    if (!f) { std::fprintf(stderr, "tb: cannot open gamepad script %s\n", path.c_str()); std::exit(2); }
    char line[512];
    while (std::fgets(line, sizeof line, f)) {
        if (line[0] == '#' || line[0] == '\n') continue;
        char a[64], b[64];
        if (std::sscanf(line, "%63s %63s", a, b) == 2)
            ev.push_back({std::strtoull(a, nullptr, 0), parse_int(b)});
    }
    std::fclose(f);
    std::stable_sort(ev.begin(), ev.end(), [](const GamepadEvent& x, const GamepadEvent& y) { return x.clock < y.clock; });
    return ev;
}

int gamepad_pins(int step, int buttons) {
    const int pulses = 24;
    const uint32_t data_reg = static_cast<uint32_t>(buttons & 0xfff) << 12;
    const int clk = step < pulses * 2 ? step % 2 : 0;
    const int idx = step < pulses * 2 + 1 ? step >> 1 : 0;
    const int data = (data_reg >> idx) & 1;
    const int latch = step == pulses * 2 + 1 ? 1 : 0;
    return (data << 6) | (clk << 5) | (latch << 4);
}

// Input script: lines of "<clock> <ui_in> <uio_in>", numbers in C syntax.
std::vector<InputEvent> load_inputs(const std::string& path) {
    std::vector<InputEvent> ev;
    if (path.empty()) return ev;
    FILE* f = std::fopen(path.c_str(), "r");
    if (!f) { std::fprintf(stderr, "tb: cannot open inputs %s\n", path.c_str()); std::exit(2); }
    char line[512];
    while (std::fgets(line, sizeof line, f)) {
        if (line[0] == '#' || line[0] == '\n') continue;
        char a[64], b[64], c[64];
        if (std::sscanf(line, "%63s %63s %63s", a, b, c) == 3)
            ev.push_back({std::strtoull(a, nullptr, 0), parse_int(b), parse_int(c)});
    }
    std::fclose(f);
    std::stable_sort(ev.begin(), ev.end(), [](const InputEvent& x, const InputEvent& y) { return x.clock < y.clock; });
    return ev;
}

// Records the length of every phase of one sync signal.
struct SyncTracker {
    bool last = false;
    uint64_t phase_start = 0;
    std::vector<std::pair<bool, uint64_t>> phases;  // (level, length in clocks)
    void feed(bool level, uint64_t clock) {
        if (level != last) {
            phases.push_back({last, clock - phase_start});
            phase_start = clock;
            last = level;
        }
    }
};

uint64_t median(std::vector<uint64_t> v) {
    if (v.empty()) return 0;
    std::sort(v.begin(), v.end());
    return v[v.size() / 2];
}

struct SyncInfo {
    bool found = false;
    bool active_low = true;
    uint64_t pulse = 0, period = 0;   // clocks
};

// The shorter of the two phases is the pulse; period = one pulse + one gap.
SyncInfo analyse(const SyncTracker& t) {
    SyncInfo s;
    std::vector<uint64_t> high, low;
    for (size_t i = 1; i < t.phases.size(); i++)   // skip the first (partial) phase
        (t.phases[i].first ? high : low).push_back(t.phases[i].second);
    if (high.size() < 3 || low.size() < 3) return s;
    uint64_t mh = median(high), ml = median(low);
    s.active_low = ml < mh;
    s.pulse = s.active_low ? ml : mh;
    s.period = ml + mh;
    s.found = true;
    return s;
}

// SIGTERM from the job runner's wall-clock limit: stop cleanly so ffmpeg can
// finish the AVI and timing.json reports what was captured so far.
volatile std::sig_atomic_t g_stop = 0;
void on_signal(int) { g_stop = 1; }

// NOT standard FNV-1a 64: the offset basis should be 14695981039346656037
// (0xcbf29ce484222325) and this one lost its last digit. Every published
// frame hash used this value, and each
// frames/tb-v1/frame_hashes.fnv1a64-tb2026-rgb888.txt states it. Changing it
// means re-simulating everything, or the published hashes and new ones stop
// being comparable. tb.cpp writes its own list to tb_frame_hashes.txt, which
// the job checks against vgacap's tb-v1 sampler.
// ---- The trace's fast path. Verilator keeps the 8 ports as bytes in the
// model's root. When they are 8 contiguous bytes, one 8-byte load holds every
// pin, and a clock whose two loads equal the current run's raw image is
// recorded with vgacap_trace_repeat2, with nothing packed. The layout is
// Verilator's choice, not a promise, so init() checks it at run time; when
// it does not hold, tb.cpp packs and pushes every sample instead.
struct RawPorts {
    const uint8_t* base = nullptr;   // the lowest of the 8 port bytes; nullptr: not contiguous
    int off[8] = {};                 // byte offset of uo_out, uio_out, uio_oe, ui_in, uio_in, rst_n, ena, clk
    uint64_t clk_raw = 0;            // the clk byte's bit 0, in the raw word

    bool init(const Vtop___024root* r) {
        const uint8_t* p[8] = {&r->uo_out, &r->uio_out, &r->uio_oe, &r->ui_in,
                               &r->uio_in, &r->rst_n,   &r->ena,    &r->clk};
        const uint8_t* lo = *std::min_element(p, p + 8);
        unsigned seen = 0;
        for (int i = 0; i < 8; i++) {
            const std::ptrdiff_t d = p[i] - lo;
            if (d < 0 || d > 7 || (seen & (1u << d))) return false;
            seen |= 1u << d;
            off[i] = static_cast<int>(d);
        }
        uint8_t b[8] = {};
        b[off[7]] = 1;
        std::memcpy(&clk_raw, b, 8);
        base = lo;
        return true;
    }
};

inline uint64_t load_raw(const uint8_t* b) {
    uint64_t x;
    std::memcpy(&x, b, 8);
    return x;
}

// A raw image as a tt-um-43 sample: the same packing as record() in main.
uint64_t pack_raw(uint64_t raw, const RawPorts& rp) {
    uint8_t b[8];
    std::memcpy(b, &raw, 8);
    const int* o = rp.off;
    return static_cast<uint64_t>(b[o[0]]) | static_cast<uint64_t>(b[o[1]]) << 8 |
           static_cast<uint64_t>(b[o[2]]) << 16 | static_cast<uint64_t>(b[o[3]]) << 24 |
           static_cast<uint64_t>(b[o[4]]) << 32 | static_cast<uint64_t>(b[o[5]] & 1) << 40 |
           static_cast<uint64_t>(b[o[6]] & 1) << 41 | static_cast<uint64_t>(b[o[7]] & 1) << 42;
}

// A clock that differs from the run's raw image (or the first clock): pack
// and push both samples, and make the clk-high image, clock bit cleared, the
// new image to compare against. Out of line, so the fast path stays short.
__attribute__((noinline)) int raw_slow(vgacap_trace_writer_t* t, const RawPorts& rp, uint64_t r0, uint64_t r1,
                                       uint64_t* want_raw) {
    *want_raw = r1 & ~rp.clk_raw;
    return vgacap_trace_push2(t, pack_raw(r0, rp), pack_raw(r1, rp));
}

uint64_t fnv1a(const uint8_t* p, size_t n) {
    uint64_t h = 1469598103934665603ULL;
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
    return h;
}

}  // namespace

int main(int argc, char** argv) {
    Options opt;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) { std::fprintf(stderr, "tb: %s needs a value\n", a.c_str()); std::exit(2); }
            return argv[++i];
        };
        if (a == "--clock-hz") { opt.clock_hz_arg = next(); opt.clock_hz = std::atof(opt.clock_hz_arg.c_str()); }
        else if (a == "--seconds") { opt.seconds_arg = next(); opt.seconds = std::atof(opt.seconds_arg.c_str()); }
        else if (a == "--calib-seconds") {
            opt.calib_seconds_arg = next(); opt.calib_seconds = std::atof(opt.calib_seconds_arg.c_str());
        }
        else if (a == "--trace") opt.trace = next();
        else if (a == "--meta") {
            const std::string kv = next();
            const size_t eq = kv.find('=');
            const std::string key = eq == std::string::npos ? kv : kv.substr(0, eq);
            if (eq == std::string::npos || !meta_key_ok(key) || meta_key_reserved(key)) {
                std::fprintf(stderr, "tb: bad --meta key in %s (want key=value, key [a-z][a-z0-9_]*, "
                                     "not meta, calib_seconds, seconds or layout)\n", kv.c_str());
                return 2;
            }
            const std::string value = kv.substr(eq + 1);
            if (value.find('\n') != std::string::npos || value.find('\r') != std::string::npos) {
                std::fprintf(stderr, "tb: --meta %s: the value has a newline\n", key.c_str());
                return 2;
            }
            for (const auto& m : opt.meta)
                if (m.first == key) { std::fprintf(stderr, "tb: --meta %s given twice\n", key.c_str()); return 2; }
            opt.meta.emplace_back(key, value);
        }
        else if (a == "--out") opt.out_dir = next();
        else if (a == "--audio-rate") opt.audio_rate = std::atof(next().c_str());
        else if (a == "--no-audio") opt.no_audio = true;
        else if (a == "--ffmpeg") opt.ffmpeg = next();
        else if (a == "--inputs") opt.inputs = next();
        else if (a == "--gamepad") opt.gamepad = next();
        else if (a == "--qspi") opt.qspi = next();
        else if (a == "--flash") opt.flash = next();
        else if (a == "--ui-in") opt.ui_in = parse_int(next());
        else if (a == "--uio-in") opt.uio_in = parse_int(next());
        else if (a == "--quiet") opt.quiet = true;
        else if (a.rfind("+", 0) == 0) continue;   // Verilator plusargs
        else { std::fprintf(stderr, "tb: unknown option %s\n", a.c_str()); return 2; }
    }
    // A trace stores the clock as whole hertz in a u32, so refuse anything else
    // before simulating rather than round it.
    if (!opt.trace.empty() && !opt.clock_hz_arg.empty()) {
        const char* s = opt.clock_hz_arg.c_str();
        char* end = nullptr;
        const double v = std::strtod(s, &end);
        if (end == s || *end != '\0' || !(v >= 1.0 && v <= 4294967295.0) || v != std::floor(v)) {
            std::fprintf(stderr, "tb: --trace needs an integer --clock-hz from 1 to 4294967295, not %s\n", s);
            return 2;
        }
    }
    if (opt.clock_hz <= 0) opt.clock_hz = 25175000.0;

    const auto t_start = std::chrono::steady_clock::now();
    auto wall = [&]() { return std::chrono::duration<double>(std::chrono::steady_clock::now() - t_start).count(); };

    std::signal(SIGTERM, on_signal);
    std::signal(SIGINT, on_signal);
    // A dead ffmpeg must not kill the model: the write fails with EPIPE
    // instead, and the run goes on so the trace and timing.json are finished.
    std::signal(SIGPIPE, SIG_IGN);
#ifdef TTVGA_TEST_HOOKS
    // Test only (job.py --test-hooks, tests/sim/build.py): a model that
    // ignores SIGTERM, for the job's killed-model test. A production build
    // has no such code, so nothing can make it ignore SIGTERM.
    if (const char* e = std::getenv("TTVGA_TB_IGNORE_SIGTERM"); e && std::strcmp(e, "1") == 0)
        std::signal(SIGTERM, SIG_IGN);
#endif
    VerilatedContext ctx;
    // The model is Verilated single-threaded. Without this the context defaults to the
    // process's parallelism and starts that many minus one idle pool threads (87 on an
    // 88-CPU host), which the queue scope's TasksMax refuses: std::system_error, EAGAIN.
    ctx.threads(1);
    ctx.commandArgs(argc, argv);
    Vtop top{&ctx};
    // QSPI Pmod model (flash and two PSRAMs on the bidirectional pins).
    ttvga::QspiBus qspi;
    const bool use_qspi = !opt.qspi.empty();
    if (use_qspi) {
        if (opt.qspi != "default") {
            // "cs0=0,sd0=1,sd1=2,sck=3,sd2=4,sd3=5,cs1=6,cs2=7"
            size_t pos = 0;
            std::string spec = opt.qspi + ",";
            while ((pos = spec.find(',')) != std::string::npos) {
                std::string item = spec.substr(0, pos);
                spec.erase(0, pos + 1);
                const size_t eq = item.find('=');
                if (eq == std::string::npos) continue;
                const std::string key = item.substr(0, eq);
                const int bit = std::atoi(item.c_str() + eq + 1);
                if (key == "cs0") qspi.pins.cs_flash = bit;
                else if (key == "sd0") qspi.pins.sd0 = bit;
                else if (key == "sd1") qspi.pins.sd1 = bit;
                else if (key == "sck") qspi.pins.sck = bit;
                else if (key == "sd2") qspi.pins.sd2 = bit;
                else if (key == "sd3") qspi.pins.sd3 = bit;
                else if (key == "cs1") qspi.pins.cs_ram_a = bit;
                else if (key == "cs2") qspi.pins.cs_ram_b = bit;
            }
        }
        qspi.init(opt.flash);
        if (!opt.quiet)
            std::fprintf(stderr, "tb: QSPI model on uio: cs0=%d sd0=%d sd1=%d sck=%d sd2=%d sd3=%d cs1=%d cs2=%d%s\n",
                         qspi.pins.cs_flash, qspi.pins.sd0, qspi.pins.sd1, qspi.pins.sck, qspi.pins.sd2,
                         qspi.pins.sd3, qspi.pins.cs_ram_a, qspi.pins.cs_ram_b,
                         opt.flash.empty() ? " (flash: test pattern)" : " (flash: file)");
    }

    std::vector<InputEvent> events = load_inputs(opt.inputs);
    std::vector<GamepadEvent> pad_events = load_gamepad(opt.gamepad);
    const bool use_gamepad = !opt.gamepad.empty();
    size_t next_event = 0, next_pad = 0;
    int pad_buttons = 0, pad_step = 0;
    uint64_t pad_line_clocks = 800;   // one scan line; refined once the line period is known
    uint64_t pad_next_step_clock = 0;
    int ui_in_base = opt.ui_in & 0xff;

    // ---- The trace. Sample 2c is clock c with clk low, 2c + 1 with clk high;
    // clock 0 is the first clock of reset.
    vgacap_trace_writer_t* tw = nullptr;
    if (!opt.trace.empty()) {
        vgacap_header_t h;
        vgacap_header_init_v2(&h, 43, 2, 42, 0);
        h.mode = 2;
        h.clock_hz = static_cast<uint32_t>(opt.clock_hz);
        std::string open_meta = "meta=open\n";
        for (const auto& m : opt.meta) open_meta += m.first + "=" + m.second + "\n";
        open_meta += "calib_seconds=" + opt.calib_seconds_arg + "\nseconds=" + opt.seconds_arg + "\nlayout=tt-um-43\n";
        char err[512];
        tw = vgacap_trace_create(opt.trace.c_str(), &h, open_meta.c_str(), kTraceZstdLevel, err, sizeof err);
        if (!tw) { std::fprintf(stderr, "tb: cannot start the trace %s: %s\n", opt.trace.c_str(), err); return 2; }
    }
    // The fast path, when the ports allow it (RawPorts). want_raw is the
    // current run's raw image at clk low. It starts as ~0, which no clk-low
    // image can be (its clk byte is 0), so the first clock takes the slow
    // path: vgacap_trace_repeat2 is valid only after a sample is pushed.
    RawPorts raw;
    uint64_t want_raw = ~0ull;
    if (tw) {
#if defined(TTVGA_TEST_HOOKS) && defined(TTVGA_TEST_FORCE_FALLBACK)
        // Test only (tests/sim/test_tb_trace.py): the fallback on any model,
        // to check that both paths write the same trace.
        const bool contiguous = false;
#else
        const bool contiguous = raw.init(top.rootp);
#endif
        if (!contiguous)
            std::fprintf(stderr, "tb: the model's 8 port bytes are not contiguous; the trace packs every sample\n");
    }
    const uint8_t* const raw_base = raw.base;
    const uint64_t clk_raw = raw.clk_raw;
    // The exits that write no timing.json leave no trace either.
    auto abandon_trace = [&]() {
        if (!tw) return;
        vgacap_trace_abandon(tw);
        tw = nullptr;
        std::remove(opt.trace.c_str());
    };
    // META(close), the seek table, and the file closed. `extra` is more
    // key=value lines for META(close) ("" for none). False, with the writer's
    // message on stderr and the file removed, if the writer failed at any
    // point: a trace the writer gave up on is not kept.
    auto finish_trace = [&](const char* status, uint64_t capture_after, uint64_t frames,
                            const std::string& extra) -> bool {
        if (!tw) return true;
        char close_meta[256];
        std::snprintf(close_meta, sizeof close_meta, "meta=close\ncapture_after_clock=%llu\nstatus=%s\nframes=%llu\n%s",
                      (unsigned long long)capture_after, status, (unsigned long long)frames, extra.c_str());
        char err[512];
        const int rc = vgacap_trace_finish(tw, close_meta, err, sizeof err);
        tw = nullptr;
        if (rc != 0) {
            std::fprintf(stderr, "tb: trace %s: %s\n", opt.trace.c_str(), err);
            std::remove(opt.trace.c_str());
            return false;
        }
        return true;
    };
    // The fallback: one sample of every pin, in the tt-um-43 layout, as the
    // ports hold them now. The inline push: no call, allocation or syscall in
    // the common case. A failed writer stops the run, which then exits 4.
    auto record = [&]() {
        const uint64_t v = static_cast<uint64_t>(top.uo_out) | static_cast<uint64_t>(top.uio_out) << 8 |
                           static_cast<uint64_t>(top.uio_oe) << 16 | static_cast<uint64_t>(top.ui_in) << 24 |
                           static_cast<uint64_t>(top.uio_in) << 32 | static_cast<uint64_t>(top.rst_n & 1) << 40 |
                           static_cast<uint64_t>(top.ena & 1) << 41 | static_cast<uint64_t>(top.clk & 1) << 42;
        if (vgacap_trace_push(tw, v)) g_stop = 1;
    };

    uint64_t clock = 0;
    auto tick = [&, raw_base, clk_raw]() {
        while (next_event < events.size() && events[next_event].clock <= clock) {
            ui_in_base = events[next_event].ui_in & 0xff;
            top.ui_in = ui_in_base;
            top.uio_in = events[next_event].uio_in & 0xff;
            next_event++;
        }
        if (use_gamepad) {
            while (next_pad < pad_events.size() && pad_events[next_pad].clock <= clock)
                pad_buttons = pad_events[next_pad++].buttons;
            if (clock >= pad_next_step_clock) {
                top.ui_in = (ui_in_base & ~0x70) | gamepad_pins(pad_step, pad_buttons);
                pad_step = (pad_step + 1) % 400;
                pad_next_step_clock = clock + pad_line_clocks;
            }
        }
        top.clk = 0; top.eval(); ctx.timeInc(1);
        uint64_t r0 = 0;
        if (raw_base) r0 = load_raw(raw_base);
        else if (tw) record();
        top.clk = 1; top.eval(); ctx.timeInc(1);
        if (use_qspi) {
            // Answer the design's memory bus. Re-evaluating only when the
            // lines actually change keeps the common case at one eval.
            const uint8_t v = qspi.step(top.uio_out, top.uio_oe, top.uio_in);
            if (v != top.uio_in) { top.uio_in = v; top.eval(); }
        }
        if (raw_base) {
            // Both samples equal the run's: the run grows by one clock.
            const uint64_t r1 = load_raw(raw_base);
            if (__builtin_expect(((r0 ^ want_raw) | (r1 ^ want_raw ^ clk_raw)) != 0, 0)) {
                if (raw_slow(tw, raw, r0, r1, &want_raw)) g_stop = 1;
            } else if (vgacap_trace_repeat2(tw)) {
                g_stop = 1;
            }
        } else if (tw) {
            record();
        }
        clock++;
    };

    // Reset sequence as in the VGA Playground: ena=1, rst_n low for 10 clocks.
    top.ena = 1; top.rst_n = 0; top.ui_in = opt.ui_in & 0xff; top.uio_in = opt.uio_in & 0xff; top.clk = 0;
    top.eval();
    for (int i = 0; i < 10; i++) tick();
    top.rst_n = 1;

    // ---- Calibration: watch the sync bits until both show stable periods.
    SyncTracker ht, vt;
    SyncInfo hs, vs;
    const uint64_t calib_limit = static_cast<uint64_t>(opt.calib_seconds * opt.clock_hz);
    const uint64_t check_every = 1 << 16;
    while (clock < calib_limit && !g_stop) {
        tick();
        const uint8_t uo = top.uo_out;
        ht.feed(uo & 0x80, clock);
        vt.feed(uo & 0x08, clock);
        if ((clock & (check_every - 1)) == 0) {
            hs = analyse(ht); vs = analyse(vt);
            if (hs.found && vs.found && vt.phases.size() >= 8) break;
        }
        if (ht.phases.size() > 4000000) break;   // hsync toggling every few clocks: not a sync signal
    }
    hs = analyse(ht); vs = analyse(vt);
    const uint64_t first_sync_clock = vt.phases.size() > 1 ? vt.phases[0].second : 0;

    std::string timing_path = opt.out_dir + "/timing.json";
    std::string hashes_path = opt.out_dir + "/tb_frame_hashes.txt";
    FILE* tj = std::fopen(timing_path.c_str(), "w");
    if (!tj) { std::fprintf(stderr, "tb: cannot write %s\n", timing_path.c_str()); abandon_trace(); return 2; }
    FILE* th = std::fopen(hashes_path.c_str(), "w");
    if (!th) {
        std::fprintf(stderr, "tb: cannot write %s\n", hashes_path.c_str());
        std::fclose(tj);
        std::remove(timing_path.c_str());
        abandon_trace();
        return 2;
    }

    auto fail = [&](const char* status) {
        std::fclose(th);   // no frames: an empty list
        std::fprintf(tj, "{\n  \"status\": \"%s\",\n  \"clock_hz\": %.0f,\n  \"clocks_simulated\": %llu,\n"
                         "  \"hsync_transitions\": %zu,\n  \"vsync_transitions\": %zu,\n"
                         "  \"hsync_pulse_clocks\": %llu,\n  \"hsync_period_clocks\": %llu,\n"
                         "  \"vsync_pulse_clocks\": %llu,\n  \"vsync_period_clocks\": %llu,\n  \"wall_seconds\": %.1f\n}\n",
                     status, opt.clock_hz, (unsigned long long)clock, ht.phases.size(), vt.phases.size(),
                     (unsigned long long)hs.pulse, (unsigned long long)hs.period,
                     (unsigned long long)vs.pulse, (unsigned long long)vs.period, wall());
        std::fclose(tj);
        std::fprintf(stderr, "tb: %s after %llu clocks (hsync transitions %zu, vsync transitions %zu)\n",
                     status, (unsigned long long)clock, ht.phases.size(), vt.phases.size());
        // The calibration ended here, so this is where a sampler would start.
        return finish_trace(status, clock, 0, "") ? 3 : 4;
    };
    if (!hs.found || !vs.found) return fail("no-sync");
    if (hs.period == 0 || vs.period < 2 * hs.period) return fail("bad-timing");

    // ---- Work out the mode.
    const uint64_t line_clocks = hs.period;
    pad_line_clocks = line_clocks;
    const int lines = static_cast<int>((vs.period + line_clocks / 2) / line_clocks);
    // Match a mode by line count, then by the sync pulse's share of the line. The
    // clocks-per-pixel ratio may be fractional: a 48 MHz design producing 640x480
    // timing has 1525 clocks per 800-pixel line, so pixels are resampled.
    const Mode* mode = nullptr;
    double cpp = 1.0;  // clocks per pixel
    double best = 0.03;
    for (const Mode& m : MODES) {
        double k = static_cast<double>(line_clocks) / m.line_px;
        if (k < 0.9 || k > 4.5) continue;
        double ev = std::fabs(static_cast<double>(lines) - m.lines) / m.lines;
        double ep = std::fabs(static_cast<double>(hs.pulse) / line_clocks - static_cast<double>(m.hpulse) / m.line_px);
        double e = ev + ep;
        if (e < best) { best = e; mode = &m; cpp = k; }
    }
    // A design may use a standard line but a non-standard number of lines per
    // frame (the tennis game has 506). Take the horizontal crop from the mode
    // and keep every line, so the picture is the right shape with black bars.
    const int vpulse_lines = static_cast<int>((vs.pulse + line_clocks / 2) / line_clocks);
    bool vertical_matched = false;
    if (mode == nullptr) {
        for (const Mode& m : MODES) {
            double k = static_cast<double>(line_clocks) / m.line_px;
            if (k < 0.9 || k > 4.5) continue;
            double eh = std::fabs(k - std::round(k * m.line_px) / m.line_px);
            double ep = std::fabs(static_cast<double>(hs.pulse) / line_clocks - static_cast<double>(m.hpulse) / m.line_px);
            if (ep < 0.01 && eh < 0.02 && lines > m.height) { mode = &m; cpp = k; break; }
        }
    } else {
        vertical_matched = true;
    }
    int width, height, hback, vback;
    if (mode) {
        width = mode->width; hback = mode->hback;
        height = vertical_matched ? mode->height : lines - vpulse_lines;
        vback = vertical_matched ? mode->vback : 0;
        if (std::fabs(cpp - std::round(cpp)) < 0.01) cpp = std::round(cpp);
    } else {
        // Unknown mode: keep everything after the sync pulses at one clock per pixel.
        width = static_cast<int>(line_clocks - hs.pulse);
        height = lines - vpulse_lines;
        hback = 0; vback = 0;
    }
    if (width > 4096 || height > 4096 || width < 16 || height < 16) return fail("bad-timing");
    const double fps = opt.clock_hz / static_cast<double>(vs.period);
    const uint64_t target_frames = static_cast<uint64_t>(opt.seconds * fps + 0.5);
    const uint64_t clock_limit = clock + static_cast<uint64_t>((opt.seconds + 2.5 / fps) * opt.clock_hz);
    // Calibration ends here; frame 0 starts at the next end of a vsync pulse.
    const uint64_t capture_after_clock = clock;

    if (!opt.quiet)
        std::fprintf(stderr, "tb: sync at clock %llu: line %llu clocks, %d lines, hsync %s, vsync %s, mode %s, %.3f clk/px, %dx%d @ %.3f fps\n",
                     (unsigned long long)clock, (unsigned long long)line_clocks, lines,
                     hs.active_low ? "active-low" : "active-high", vs.active_low ? "active-low" : "active-high",
                     mode ? mode->name : "unknown", cpp, width, height, fps);

    // ---- ffmpeg pipe: raw RGB frames in, MJPEG out. This is the capture, not
    // the deliverable: it is cheap to write while the simulation runs, and the
    // job runner turns it into the MP4 that browsers can play. `-cpucount 2`: the
    // MJPEG encoder's automatic frame threads, sized by the host's CPUs (88), fail
    // to start inside the queue scope's TasksMax (64); the scope has 2 CPUs anyway.
    char cmd[2048];
    std::snprintf(cmd, sizeof cmd,
                  "%s -hide_banner -loglevel error -y -cpucount 2 -f rawvideo -pix_fmt rgb24 -s %dx%d -framerate %.4f -i - "
                  "-c:v mjpeg -q:v 2 -pix_fmt yuvj444p -huffman optimal \"%s/capture.avi\"",
                  opt.ffmpeg.c_str(), width, height, fps, opt.out_dir.c_str());
    FILE* ff = popen(cmd, "w");
    if (!ff) {
        std::fprintf(stderr, "tb: cannot start ffmpeg: %s\n", cmd);
        std::fclose(tj); std::fclose(th);
        std::remove(timing_path.c_str()); std::remove(hashes_path.c_str());
        abandon_trace();
        return 2;
    }

    // ---- Capture.
    std::vector<uint8_t> frame(static_cast<size_t>(width) * height * 3, 0);
    std::vector<uint8_t> prev(frame.size(), 0);      // last frame, to measure motion
    std::vector<uint8_t> ever(static_cast<size_t>(width) * height, 0);  // pixels that ever changed
    uint64_t colours = 0;                            // bitmask of the 64 possible RGB values
    double delta_sum = 0;                            // mean fraction of pixels changing per frame
    std::vector<uint64_t> hashes;
    std::unordered_set<uint64_t> distinct;
    uint64_t frames = 0, uniform_frames = 0, black_frames = 0, short_lines = 0, long_lines = 0, lines_seen = 0;
    uint64_t line_min = UINT64_MAX, line_max = 0, frame_min = UINT64_MAX, frame_max = 0;
    bool in_frame = false, prev_h = false, prev_v = false;
    uint64_t line_start = 0, last_line_start = 0, last_frame_start = 0;
    int y = -1, last_px = -1;
    const double half = cpp / 2.0;   // sample in the middle of each pixel period

    // Once a write to ffmpeg fails (it exited, or never started: popen runs
    // a shell, so a bad --ffmpeg only shows here), stop feeding it and carry
    // on; ffmpeg_status records the failure.
    bool ffmpeg_ok = true;
    auto emit_frame = [&]() {
        if (ffmpeg_ok && std::fwrite(frame.data(), 1, frame.size(), ff) != frame.size()) {
            ffmpeg_ok = false;
            std::fprintf(stderr, "tb: writing to ffmpeg failed at frame %llu: %s; the run continues without video\n",
                         (unsigned long long)frames, std::strerror(errno));
        }
        uint64_t h = fnv1a(frame.data(), frame.size());
        hashes.push_back(h); distinct.insert(h);
        bool uniform = true;
        size_t changed = 0;
        const size_t pixels = static_cast<size_t>(width) * height;
        for (size_t p = 0; p < pixels; p++) {
            const uint8_t* c = &frame[p * 3];
            const uint8_t* q = &prev[p * 3];
            if (uniform && (c[0] != frame[0] || c[1] != frame[1] || c[2] != frame[2])) uniform = false;
            // 2 bits per channel came out of the design, so 64 colours are possible.
            colours |= 1ull << (((c[0] / 85) << 4) | ((c[1] / 85) << 2) | (c[2] / 85));
            if (c[0] != q[0] || c[1] != q[1] || c[2] != q[2]) { changed++; if (frames) ever[p] = 1; }
        }
        if (frames) delta_sum += static_cast<double>(changed) / static_cast<double>(pixels);
        if (uniform) { uniform_frames++; if (frame[0] == 0 && frame[1] == 0 && frame[2] == 0) black_frames++; }
        prev.swap(frame);
        std::fill(frame.begin(), frame.end(), 0);
        frames++;
    };

    AudioCapture audio;
    audio.begin(opt.clock_hz, opt.audio_rate);
    bool audio_started = false;

    while (frames < target_frames && clock < clock_limit && !g_stop) {
        tick();
        // Audio runs only while a frame is being captured, so the track starts
        // where the picture does and the two stay in step.
        if (!opt.no_audio && audio_started) audio.feed(top.uio_out, top.uio_oe);
        const uint8_t uo = top.uo_out;
        const bool h_pulse = hs.active_low ? !(uo & 0x80) : !!(uo & 0x80);
        const bool v_pulse = vs.active_low ? !(uo & 0x08) : !!(uo & 0x08);

        if (prev_v && !v_pulse) {                       // vsync pulse ended: new frame
            if (in_frame) emit_frame();
            if (last_frame_start) {
                uint64_t d = clock - last_frame_start;
                frame_min = std::min(frame_min, d); frame_max = std::max(frame_max, d);
            }
            last_frame_start = clock;
            in_frame = true; y = -1;
            audio_started = true;
        }
        if (prev_h && !h_pulse) {                       // hsync pulse ended: new line
            if (last_line_start) {
                uint64_t d = clock - last_line_start; lines_seen++;
                line_min = std::min(line_min, d); line_max = std::max(line_max, d);
                if (d + d / 50 < line_clocks) short_lines++;
                else if (d > line_clocks + line_clocks / 50) long_lines++;
            }
            last_line_start = line_start = clock;
            last_px = -1;
            if (in_frame) y++;
        }
        if (in_frame && y >= 0 && !h_pulse) {
            const double x_clock = static_cast<double>(clock - line_start);
            const int pixel = static_cast<int>((x_clock + half) / cpp);
            if (pixel != last_px) {           // first clock inside a new pixel period
                last_px = pixel;
                const int px = pixel - hback;
                const int py = y - vback;
                if (px >= 0 && px < width && py >= 0 && py < height) {
                    uint8_t* p = &frame[(static_cast<size_t>(py) * width + px) * 3];
                    p[0] = static_cast<uint8_t>(((((uo >> 0) & 1) << 1) | ((uo >> 4) & 1)) * 85);
                    p[1] = static_cast<uint8_t>(((((uo >> 1) & 1) << 1) | ((uo >> 5) & 1)) * 85);
                    p[2] = static_cast<uint8_t>(((((uo >> 2) & 1) << 1) | ((uo >> 6) & 1)) * 85);
                }
            }
        }
        prev_h = h_pulse; prev_v = v_pulse;
    }
    int rc = pclose(ff);
    // A flush that fails in pclose has lost frames too; a shell that cannot
    // run --ffmpeg exits 127, so rc is nonzero then as well.
    if (rc == 0 && !ffmpeg_ok) rc = -1;
    top.final();

    // The audio track, mono 32 bit float at opt.audio_rate. Written raw
    // because the job runner muxes it, and only when the pin carried something
    // audible: a silent file would be noise in every sense.
    size_t audio_written = 0;
    if (audio.driven && audio.audible() && !audio.samples.empty()) {
        const std::string apath = opt.out_dir + "/capture.f32";
        if (FILE* af = std::fopen(apath.c_str(), "wb")) {
            audio_written = std::fwrite(audio.samples.data(), sizeof(float), audio.samples.size(), af);
            std::fclose(af);
        }
    }

    const char* status = "ok";
    if (g_stop || frames < target_frames / 2) status = "sim-timeout";
    else if (frame_max > frame_min + frame_min / 100 || long_lines + short_lines > lines_seen / 100) status = "unstable-sync";
    const double wall_s = wall();
    std::fprintf(tj, "{\n  \"status\": \"%s\",\n  \"clock_hz\": %.0f,\n  \"first_sync_clock\": %llu,\n"
                     "  \"capture_after_clock\": %llu,\n  \"hsync_active_low\": %s,\n  \"vsync_active_low\": %s,\n"
                     "  \"line_clocks\": %llu,\n  \"lines\": %d,\n  \"hsync_pulse_clocks\": %llu,\n  \"vsync_pulse_clocks\": %llu,\n"
                     "  \"line_clocks_range\": [%llu, %llu],\n  \"frame_clocks_range\": [%llu, %llu],\n"
                     "  \"mode\": \"%s\",\n  \"clocks_per_pixel\": %.4f,\n  \"width\": %d,\n  \"height\": %d,\n  \"fps\": %.4f,\n"
                     "  \"frames\": %llu,\n  \"target_frames\": %llu,\n  \"distinct_frames\": %zu,\n"
                     "  \"uniform_frames\": %llu,\n  \"black_frames\": %llu,\n"
                     "  \"colours\": %d,\n  \"mean_frame_delta\": %.6f,\n  \"pixels_ever_changed\": %.6f,\n"
                     "  \"lines_seen\": %llu,\n  \"short_lines\": %llu,\n  \"long_lines\": %llu,\n"
                     "  \"clocks_simulated\": %llu,\n  \"sim_seconds\": %.3f,\n  \"wall_seconds\": %.1f,\n"
                     "  \"clocks_per_wall_second\": %.0f,\n  \"ffmpeg_status\": %d,\n"
                     "  \"audio_driven\": %s,\n  \"audio_transitions\": %llu,\n"
                     "  \"audio_rate\": %.0f,\n  \"audio_samples\": %zu\n}\n",
                 status, opt.clock_hz, (unsigned long long)first_sync_clock,
                 (unsigned long long)capture_after_clock, hs.active_low ? "true" : "false", vs.active_low ? "true" : "false",
                 (unsigned long long)line_clocks, lines, (unsigned long long)hs.pulse, (unsigned long long)vs.pulse,
                 (unsigned long long)(lines_seen ? line_min : 0), (unsigned long long)line_max,
                 (unsigned long long)(frame_max ? frame_min : 0), (unsigned long long)frame_max,
                 mode ? mode->name : "unknown", cpp, width, height, fps,
                 (unsigned long long)frames, (unsigned long long)target_frames, distinct.size(),
                 (unsigned long long)uniform_frames, (unsigned long long)black_frames,
                 __builtin_popcountll(colours),
                 frames > 1 ? delta_sum / static_cast<double>(frames - 1) : 0.0,
                 static_cast<double>(std::count(ever.begin(), ever.end(), 1)) /
                     static_cast<double>(std::max<size_t>(1, ever.size())),
                 (unsigned long long)lines_seen, (unsigned long long)short_lines, (unsigned long long)long_lines,
                 (unsigned long long)clock, clock / opt.clock_hz, wall_s, clock / std::max(wall_s, 1e-3), rc,
                 audio.driven ? "true" : "false", (unsigned long long)audio.transitions,
                 opt.audio_rate, audio_written);
    std::fclose(tj);
    for (uint64_t hv : hashes) std::fprintf(th, "%016llx\n", (unsigned long long)hv);
    std::fclose(th);
    const bool trace_ok = finish_trace(status, capture_after_clock, frames, "ffmpeg_status=" + std::to_string(rc) + "\n");
    if (!opt.quiet)
        std::fprintf(stderr, "tb: %s: %llu frames (%zu distinct, %llu uniform, %d colours, %.3f%% of pixels change "
                             "per frame, %.1f%% ever), %llu clocks in %.1fs wall (%.2f Mclk/s)\n",
                     status, (unsigned long long)frames, distinct.size(), (unsigned long long)uniform_frames,
                     __builtin_popcountll(colours),
                     100.0 * (frames > 1 ? delta_sum / static_cast<double>(frames - 1) : 0.0),
                     100.0 * static_cast<double>(std::count(ever.begin(), ever.end(), 1)) /
                         static_cast<double>(std::max<size_t>(1, ever.size())),
                     (unsigned long long)clock, wall_s, clock / std::max(wall_s, 1e-3) / 1e6);
    if (!trace_ok) return 4;
    return std::strcmp(status, "ok") == 0 ? 0 : 3;
}
