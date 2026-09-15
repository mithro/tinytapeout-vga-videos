// SPDX-License-Identifier: Apache-2.0
//
// Behavioural model of the Tiny Tapeout QSPI Pmod: one flash and two PSRAMs
// sharing four data lines, a clock and one chip select each.
// https://github.com/mole99/qspi-pmod
//
// Many VGA projects keep their framebuffer or their artwork out here, and
// without a memory to talk to they draw nothing at all. The model answers
// reads and remembers writes, so a design that paints into PSRAM and scans it
// out produces a picture with no outside help. Flash, which a design only
// reads, is filled with a test pattern unless a file is given.
//
// Modelled commands. Flash (W25Q-style):
//   0x03 read, 0x0B fast read, 0x3B dual output, 0x6B quad output,
//   0xEB quad I/O, 0x9F JEDEC id, 0x05/0x35 status, 0xAB release power-down.
// PSRAM (APS6404-style):
//   0x03 read, 0x02 write, 0xEB fast quad read, 0x38 quad write,
//   0x35 enter quad mode, 0xF5 leave it, 0x66/0x99 reset, 0x9F id.
//
// SPI mode 0: the controller changes the lines on the falling edge of SCK and
// samples on the rising edge, so this model does the opposite.

#ifndef TTVGA_QSPI_H
#define TTVGA_QSPI_H

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace ttvga {

struct QspiPins {
    // Bit numbers within uio. The defaults are the Tiny Tapeout QSPI Pmod.
    int cs_flash = 0, sd0 = 1, sd1 = 2, sck = 3, sd2 = 4, sd3 = 5, cs_ram_a = 6, cs_ram_b = 7;
};

enum class DeviceKind { Flash, Psram };

// One memory on the bus.
class QspiDevice {
  public:
    QspiDevice(DeviceKind kind, uint32_t size, uint32_t jedec)
        : kind_(kind), size_(size), jedec_(jedec) {}

    void fill_pattern() {
        // A coarse RGB332 gradient with a grid, so a design that reads the
        // flash as an image shows something recognisable rather than noise.
        mem_.assign(size_, 0);
        for (uint32_t i = 0; i < size_; i++) {
            const uint32_t x = i % 640, y = (i / 640) % 480;
            uint8_t r = static_cast<uint8_t>(x * 8 / 640), g = static_cast<uint8_t>(y * 8 / 480), b = 2;
            if (x % 64 == 0 || y % 64 == 0) { r = 7; g = 7; b = 3; }
            mem_[i] = static_cast<uint8_t>((r << 5) | (g << 2) | b);
        }
    }

    bool load(const std::string& path) {
        FILE* f = std::fopen(path.c_str(), "rb");
        if (!f) return false;
        mem_.assign(size_, 0xff);
        std::fread(mem_.data(), 1, size_, f);
        std::fclose(f);
        return true;
    }

    void ensure() { if (mem_.empty()) mem_.assign(size_, kind_ == DeviceKind::Flash ? 0xff : 0x00); }

    // --- bus events -------------------------------------------------------
    void select(bool on) {
        if (on == selected_) return;
        selected_ = on;
        if (on) { phase_ = Phase::Command; bits_ = 0; shift_ = 0; addr_ = 0; cmd_ = 0; out_bits_ = 0; }
    }

    bool driving() const { return selected_ && phase_ == Phase::Data && reading_; }
    int out_width() const { return quad_data_ ? 4 : (dual_data_ ? 2 : 1); }

    // Value currently presented on the data lines (low bits, MSB first order).
    uint8_t out_value() const { return out_nibble_; }

    // Called on the rising edge of SCK with the input lines.
    void rising(uint8_t lines) {
        if (!selected_) return;
        switch (phase_) {
        case Phase::Command:
            shift_in(lines, quad_cmd_ ? 4 : 1);
            if (bits_ >= 8) { cmd_ = static_cast<uint8_t>(shift_); bits_ = 0; shift_ = 0; start_command(); }
            break;
        case Phase::Address:
            shift_in(lines, addr_quad_ ? 4 : 1);
            if (bits_ >= 24) {
                addr_ = shift_ & 0xffffff; bits_ = 0; shift_ = 0;
                if (mode_bits_) { phase_ = Phase::ModeBits; }
                else if (dummy_) { phase_ = Phase::Dummy; dummy_left_ = dummy_; }
                else { begin_data(); }
            }
            break;
        case Phase::ModeBits:
            shift_in(lines, addr_quad_ ? 4 : 1);
            if (bits_ >= 8) {
                bits_ = 0; shift_ = 0;
                if (dummy_) { phase_ = Phase::Dummy; dummy_left_ = dummy_; } else { begin_data(); }
            }
            break;
        case Phase::Dummy:
            if (--dummy_left_ == 0) begin_data();
            break;
        case Phase::Data:
            if (!reading_) {
                shift_in(lines, quad_data_ ? 4 : 1);
                if (bits_ >= 8) { write_byte(static_cast<uint8_t>(shift_)); bits_ = 0; shift_ = 0; }
            }
            break;
        }
    }

    // Called on the falling edge of SCK: present the next output bits.
    void falling() {
        if (!selected_ || phase_ != Phase::Data || !reading_) return;
        const int w = out_width();
        if (out_bits_ == 0) { out_byte_ = read_byte(); out_bits_ = 8; }
        out_bits_ -= w;
        out_nibble_ = static_cast<uint8_t>((out_byte_ >> out_bits_) & ((1 << w) - 1));
    }

  private:
    enum class Phase { Command, Address, ModeBits, Dummy, Data };

    void shift_in(uint8_t lines, int width) {
        shift_ = (shift_ << width) | (lines & ((1u << width) - 1));
        bits_ += width;
    }

    void start_command() {
        quad_data_ = dual_data_ = addr_quad_ = false;
        dummy_ = 0; mode_bits_ = false; reading_ = true;
        id_read_ = status_read_ = false; count_ = 0;
        switch (cmd_) {
        case 0x03: phase_ = Phase::Address; break;                                   // read
        case 0x0B: phase_ = Phase::Address; dummy_ = 8; break;                       // fast read
        case 0x3B: phase_ = Phase::Address; dummy_ = 8; dual_data_ = true; break;    // dual output
        case 0x6B: phase_ = Phase::Address; dummy_ = 8; quad_data_ = true; break;    // quad output
        case 0xEB:                                                                   // quad I/O
            phase_ = Phase::Address; addr_quad_ = true; quad_data_ = true;
            if (kind_ == DeviceKind::Psram) { dummy_ = 6; }
            else { mode_bits_ = true; dummy_ = 4; }
            break;
        case 0x02: phase_ = Phase::Address; reading_ = false; break;                 // write
        case 0x38: phase_ = Phase::Address; reading_ = false; addr_quad_ = true; quad_data_ = true; break;
        case 0x35: if (kind_ == DeviceKind::Psram) { quad_cmd_ = true; phase_ = Phase::Data; reading_ = false; }
                   else { phase_ = Phase::Data; status_ = 0x02; status_read_ = true; }   // flash: read status 2
                   break;
        case 0xF5: quad_cmd_ = false; phase_ = Phase::Data; reading_ = false; break;
        case 0x66: case 0x99: phase_ = Phase::Data; reading_ = false; break;         // reset
        case 0x9F: id_read_ = true; phase_ = Phase::Data; reading_ = true; break;
        case 0x05: status_ = 0x00; phase_ = Phase::Data; reading_ = true; status_read_ = true; break;
        case 0xAB: phase_ = Phase::Data; reading_ = false; break;                    // release power-down
        default:   phase_ = Phase::Data; reading_ = false; break;                    // ignore quietly
        }
        if (phase_ == Phase::Data) begin_data();
    }

    void begin_data() {
        phase_ = Phase::Data;
        out_bits_ = 0;
        if (reading_) ensure();
    }

    uint8_t read_byte() {
        if (id_read_) {
            const uint8_t id[] = {static_cast<uint8_t>(jedec_ >> 16), static_cast<uint8_t>(jedec_ >> 8),
                                  static_cast<uint8_t>(jedec_)};
            return id[(count_++) % 3];
        }
        if (status_read_) return status_;
        const uint8_t v = mem_[addr_ % size_];
        addr_++;
        return v;
    }

    void write_byte(uint8_t v) {
        if (cmd_ == 0x02 || cmd_ == 0x38) { ensure(); mem_[addr_ % size_] = v; addr_++; }
    }

    DeviceKind kind_;
    uint32_t size_, jedec_;
    std::vector<uint8_t> mem_;
    bool selected_ = false, reading_ = true, quad_cmd_ = false, quad_data_ = false, dual_data_ = false;
    bool addr_quad_ = false, mode_bits_ = false, id_read_ = false, status_read_ = false;
    Phase phase_ = Phase::Command;
    uint8_t cmd_ = 0, out_byte_ = 0, out_nibble_ = 0, status_ = 0;
    int bits_ = 0, out_bits_ = 0, dummy_ = 0, dummy_left_ = 0, count_ = 0;
    uint32_t shift_ = 0, addr_ = 0;
};

// The three devices plus the wiring to the design's bidirectional pins.
class QspiBus {
  public:
    QspiBus() : flash_(DeviceKind::Flash, 16u << 20, 0xef4018),
                ram_a_(DeviceKind::Psram, 8u << 20, 0x0d5d52),
                ram_b_(DeviceKind::Psram, 8u << 20, 0x0d5d52) {}

    QspiPins pins;

    void init(const std::string& flash_file) {
        if (!flash_file.empty() && flash_.load(flash_file)) return;
        flash_.fill_pattern();
    }

    // Advance the model with the design's current outputs; returns the value to
    // present on uio_in (only the data lines the design is not driving matter).
    uint8_t step(uint8_t uio_out, uint8_t uio_oe, uint8_t uio_in) {
        const bool sck = bit(uio_out, pins.sck) && bit(uio_oe, pins.sck);
        flash_.select(!bit(uio_out, pins.cs_flash) && bit(uio_oe, pins.cs_flash));
        ram_a_.select(!bit(uio_out, pins.cs_ram_a) && bit(uio_oe, pins.cs_ram_a));
        ram_b_.select(!bit(uio_out, pins.cs_ram_b) && bit(uio_oe, pins.cs_ram_b));

        if (sck != last_sck_) {
            const uint8_t lines = data_lines(uio_out);
            for (QspiDevice* d : {&flash_, &ram_a_, &ram_b_}) {
                if (sck) d->rising(lines); else d->falling();
            }
            last_sck_ = sck;
        }
        QspiDevice* active = nullptr;
        for (QspiDevice* d : {&flash_, &ram_a_, &ram_b_}) if (d->driving()) active = d;
        uint8_t next = uio_in;
        if (active) {
            const uint8_t v = active->out_value();
            const int w = active->out_width();
            // Quad reads put the high bit on SD3; single reads answer on SD1.
            if (w == 4) {
                set(next, pins.sd0, v & 1); set(next, pins.sd1, (v >> 1) & 1);
                set(next, pins.sd2, (v >> 2) & 1); set(next, pins.sd3, (v >> 3) & 1);
            } else if (w == 2) {
                set(next, pins.sd0, v & 1); set(next, pins.sd1, (v >> 1) & 1);
            } else {
                set(next, pins.sd1, v & 1);
            }
        }
        return next;
    }

  private:
    static bool bit(uint8_t v, int b) { return (v >> b) & 1; }
    static void set(uint8_t& v, int b, int value) {
        v = static_cast<uint8_t>(value ? (v | (1u << b)) : (v & ~(1u << b)));
    }
    uint8_t data_lines(uint8_t uio_out) const {
        return static_cast<uint8_t>(bit(uio_out, pins.sd0) | (bit(uio_out, pins.sd1) << 1) |
                                    (bit(uio_out, pins.sd2) << 2) | (bit(uio_out, pins.sd3) << 3));
    }

    QspiDevice flash_, ram_a_, ram_b_;
    bool last_sck_ = false;
};

}  // namespace ttvga

#endif  // TTVGA_QSPI_H
