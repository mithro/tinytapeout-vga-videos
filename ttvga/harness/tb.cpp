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

#include "Vtop.h"
#include "verilated.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unordered_set>
#include <vector>

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
    int ui_in = 0, uio_in = 0;    // constant inputs when no script
    bool quiet = false;
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
        if (a == "--clock-hz") opt.clock_hz = std::atof(next().c_str());
        else if (a == "--seconds") opt.seconds = std::atof(next().c_str());
        else if (a == "--calib-seconds") opt.calib_seconds = std::atof(next().c_str());
        else if (a == "--out") opt.out_dir = next();
        else if (a == "--ffmpeg") opt.ffmpeg = next();
        else if (a == "--inputs") opt.inputs = next();
        else if (a == "--gamepad") opt.gamepad = next();
        else if (a == "--ui-in") opt.ui_in = parse_int(next());
        else if (a == "--uio-in") opt.uio_in = parse_int(next());
        else if (a == "--quiet") opt.quiet = true;
        else if (a.rfind("+", 0) == 0) continue;   // Verilator plusargs
        else { std::fprintf(stderr, "tb: unknown option %s\n", a.c_str()); return 2; }
    }
    if (opt.clock_hz <= 0) opt.clock_hz = 25175000.0;

    const auto t_start = std::chrono::steady_clock::now();
    auto wall = [&]() { return std::chrono::duration<double>(std::chrono::steady_clock::now() - t_start).count(); };

    VerilatedContext ctx;
    ctx.commandArgs(argc, argv);
    Vtop top{&ctx};
    std::vector<InputEvent> events = load_inputs(opt.inputs);
    std::vector<GamepadEvent> pad_events = load_gamepad(opt.gamepad);
    const bool use_gamepad = !opt.gamepad.empty();
    size_t next_event = 0, next_pad = 0;
    int pad_buttons = 0, pad_step = 0;
    uint64_t pad_line_clocks = 800;   // one scan line; refined once the line period is known
    uint64_t pad_next_step_clock = 0;
    int ui_in_base = opt.ui_in & 0xff;

    uint64_t clock = 0;
    auto tick = [&]() {
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
        top.clk = 1; top.eval(); ctx.timeInc(1);
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
    while (clock < calib_limit) {
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
    FILE* tj = std::fopen(timing_path.c_str(), "w");
    if (!tj) { std::fprintf(stderr, "tb: cannot write %s\n", timing_path.c_str()); return 2; }

    auto fail = [&](const char* status) {
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
        return 3;
    };
    if (!hs.found || !vs.found) return fail("no-sync");
    if (hs.period == 0 || vs.period < 2 * hs.period) return fail("bad-timing");

    // ---- Work out the mode.
    const uint64_t line_clocks = hs.period;
    pad_line_clocks = line_clocks;
    const int lines = static_cast<int>((vs.period + line_clocks / 2) / line_clocks);
    const Mode* mode = nullptr;
    int cpp = 1;  // clocks per pixel
    double best = 0.03;
    for (const Mode& m : MODES) {
        for (int k = 1; k <= 4; k++) {
            double eh = std::fabs(static_cast<double>(line_clocks) - static_cast<double>(m.line_px) * k) / (m.line_px * k);
            double ev = std::fabs(static_cast<double>(lines) - m.lines) / m.lines;
            // The sync pulse width breaks ties between modes with similar totals (800x600@60 vs @75).
            double ep = std::fabs(static_cast<double>(hs.pulse) - static_cast<double>(m.hpulse) * k) / (m.line_px * k);
            double e = std::max(eh, ev) + ep * 0.1;
            if (e < best) { best = e; mode = &m; cpp = k; }
        }
    }
    int width, height, hback, vback;
    if (mode) {
        width = mode->width; height = mode->height; hback = mode->hback; vback = mode->vback;
    } else {
        // Unknown mode: keep everything after the sync pulses at one clock per pixel.
        width = static_cast<int>(line_clocks - hs.pulse);
        height = lines - static_cast<int>((vs.pulse + line_clocks / 2) / line_clocks);
        hback = 0; vback = 0;
        if (width > 4096 || height > 4096 || width < 16 || height < 16) return fail("bad-timing");
    }
    const double fps = opt.clock_hz / static_cast<double>(vs.period);
    const uint64_t target_frames = static_cast<uint64_t>(opt.seconds * fps + 0.5);
    const uint64_t clock_limit = clock + static_cast<uint64_t>((opt.seconds + 2.5 / fps) * opt.clock_hz);

    if (!opt.quiet)
        std::fprintf(stderr, "tb: sync at clock %llu: line %llu clocks, %d lines, hsync %s, vsync %s, mode %s, %d clk/px, %dx%d @ %.3f fps\n",
                     (unsigned long long)clock, (unsigned long long)line_clocks, lines,
                     hs.active_low ? "active-low" : "active-high", vs.active_low ? "active-low" : "active-high",
                     mode ? mode->name : "unknown", cpp, width, height, fps);

    // ---- ffmpeg pipe: raw RGB frames in, MJPEG AVI out.
    char cmd[2048];
    std::snprintf(cmd, sizeof cmd,
                  "%s -hide_banner -loglevel error -y -f rawvideo -pix_fmt rgb24 -s %dx%d -framerate %.4f -i - "
                  "-c:v mjpeg -q:v 2 -pix_fmt yuvj444p -huffman optimal \"%s/60s.avi\"",
                  opt.ffmpeg.c_str(), width, height, fps, opt.out_dir.c_str());
    FILE* ff = popen(cmd, "w");
    if (!ff) { std::fprintf(stderr, "tb: cannot start ffmpeg: %s\n", cmd); return 2; }

    // ---- Capture.
    std::vector<uint8_t> frame(static_cast<size_t>(width) * height * 3, 0);
    std::vector<uint64_t> hashes;
    std::unordered_set<uint64_t> distinct;
    uint64_t frames = 0, uniform_frames = 0, black_frames = 0, short_lines = 0, long_lines = 0, lines_seen = 0;
    uint64_t line_min = UINT64_MAX, line_max = 0, frame_min = UINT64_MAX, frame_max = 0;
    bool in_frame = false, prev_h = false, prev_v = false;
    uint64_t line_start = 0, last_line_start = 0, last_frame_start = 0;
    int y = -1;

    auto emit_frame = [&]() {
        std::fwrite(frame.data(), 1, frame.size(), ff);
        uint64_t h = fnv1a(frame.data(), frame.size());
        hashes.push_back(h); distinct.insert(h);
        bool uniform = true;
        for (size_t i = 3; i < frame.size() && uniform; i += 3)
            uniform = frame[i] == frame[0] && frame[i + 1] == frame[1] && frame[i + 2] == frame[2];
        if (uniform) { uniform_frames++; if (frame[0] == 0 && frame[1] == 0 && frame[2] == 0) black_frames++; }
        std::fill(frame.begin(), frame.end(), 0);
        frames++;
    };

    while (frames < target_frames && clock < clock_limit) {
        tick();
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
        }
        if (prev_h && !h_pulse) {                       // hsync pulse ended: new line
            if (last_line_start) {
                uint64_t d = clock - last_line_start; lines_seen++;
                line_min = std::min(line_min, d); line_max = std::max(line_max, d);
                if (d + d / 50 < line_clocks) short_lines++;
                else if (d > line_clocks + line_clocks / 50) long_lines++;
            }
            last_line_start = line_start = clock;
            if (in_frame) y++;
        }
        if (in_frame && y >= 0 && !h_pulse) {
            const uint64_t x_clock = clock - line_start;
            if (x_clock % cpp == static_cast<uint64_t>(cpp / 2)) {
                const int px = static_cast<int>(x_clock / cpp) - hback;
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
    top.final();

    const char* status = "ok";
    if (frames < target_frames / 2) status = "sim-timeout";
    else if (frame_max > frame_min + frame_min / 100 || long_lines + short_lines > lines_seen / 100) status = "unstable-sync";
    const double wall_s = wall();
    std::fprintf(tj, "{\n  \"status\": \"%s\",\n  \"clock_hz\": %.0f,\n  \"first_sync_clock\": %llu,\n"
                     "  \"hsync_active_low\": %s,\n  \"vsync_active_low\": %s,\n"
                     "  \"line_clocks\": %llu,\n  \"lines\": %d,\n  \"hsync_pulse_clocks\": %llu,\n  \"vsync_pulse_clocks\": %llu,\n"
                     "  \"line_clocks_range\": [%llu, %llu],\n  \"frame_clocks_range\": [%llu, %llu],\n"
                     "  \"mode\": \"%s\",\n  \"clocks_per_pixel\": %d,\n  \"width\": %d,\n  \"height\": %d,\n  \"fps\": %.4f,\n"
                     "  \"frames\": %llu,\n  \"target_frames\": %llu,\n  \"distinct_frames\": %zu,\n"
                     "  \"uniform_frames\": %llu,\n  \"black_frames\": %llu,\n"
                     "  \"lines_seen\": %llu,\n  \"short_lines\": %llu,\n  \"long_lines\": %llu,\n"
                     "  \"clocks_simulated\": %llu,\n  \"sim_seconds\": %.3f,\n  \"wall_seconds\": %.1f,\n"
                     "  \"clocks_per_wall_second\": %.0f,\n  \"ffmpeg_status\": %d,\n  \"frame_hashes\": [",
                 status, opt.clock_hz, (unsigned long long)first_sync_clock,
                 hs.active_low ? "true" : "false", vs.active_low ? "true" : "false",
                 (unsigned long long)line_clocks, lines, (unsigned long long)hs.pulse, (unsigned long long)vs.pulse,
                 (unsigned long long)(lines_seen ? line_min : 0), (unsigned long long)line_max,
                 (unsigned long long)(frame_max ? frame_min : 0), (unsigned long long)frame_max,
                 mode ? mode->name : "unknown", cpp, width, height, fps,
                 (unsigned long long)frames, (unsigned long long)target_frames, distinct.size(),
                 (unsigned long long)uniform_frames, (unsigned long long)black_frames,
                 (unsigned long long)lines_seen, (unsigned long long)short_lines, (unsigned long long)long_lines,
                 (unsigned long long)clock, clock / opt.clock_hz, wall_s, clock / std::max(wall_s, 1e-3), rc);
    for (size_t i = 0; i < hashes.size(); i++)
        std::fprintf(tj, "%s\"%016llx\"", i ? ", " : "", (unsigned long long)hashes[i]);
    std::fprintf(tj, "]\n}\n");
    std::fclose(tj);
    if (!opt.quiet)
        std::fprintf(stderr, "tb: %s: %llu frames (%zu distinct, %llu uniform), %llu clocks in %.1fs wall (%.2f Mclk/s)\n",
                     status, (unsigned long long)frames, distinct.size(), (unsigned long long)uniform_frames,
                     (unsigned long long)clock, wall_s, clock / std::max(wall_s, 1e-3) / 1e6);
    return std::strcmp(status, "ok") == 0 ? 0 : 3;
}
