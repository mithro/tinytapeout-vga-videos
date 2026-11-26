// SPDX-License-Identifier: Apache-2.0
// tracetool: inspect, cut and hash a tb.cpp simulation trace (vgacap format v2, layout tt-um-43).
//
//   tracetool info TRACE
//   tracetool slice TRACE --from CLOCK --to CLOCK --out PATH
//   tracetool uohash TRACE [--clocks N]
//
// Exit 0 on success, 2 for a bad command line or range, 1 for a trace that
// cannot be read or written. Built by `tt-vga bootstrap` against the pinned
// vgacap (ttvga/remote.py, tracetool_build_commands).

#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sha256.h"
#include "vgacap/stream.h"
#include "vgacap/trace.h"
#include "zstd.h"

#define DEFAULT_UOHASH_CLOCKS (1ull << 25)
#define ERR_LEN 512
#define ZSTD_LEVEL 3
#define META_MAX 4096

// The tt-um-43 layout (docs/trace-format.md in vgacap).
enum { CLK_BIT = 42 };
static const struct { const char *name; unsigned lo, width; } PORTS[] = {
    {"uo_out", 0, 8}, {"uio_out", 8, 8}, {"uio_oe", 16, 8}, {"ui_in", 24, 8},
    {"uio_in", 32, 8}, {"rst_n", 40, 1}, {"ena", 41, 1},
};
#define NPORTS (sizeof PORTS / sizeof PORTS[0])

static int usage(const char *why) {
    if (why) fprintf(stderr, "tracetool: %s\n", why);
    fprintf(stderr,
            "usage: tracetool info TRACE\n"
            "       tracetool slice TRACE --from CLOCK --to CLOCK --out PATH\n"
            "       tracetool uohash TRACE [--clocks N]\n");
    return 2;
}

static int parse_u64(const char *s, uint64_t *out) {
    char *end;
    if (!*s || *s == '-' || *s == '+') return -1;
    errno = 0;
    unsigned long long v = strtoull(s, &end, 10);
    if (errno || *end) return -1;
    *out = v;
    return 0;
}

static vgacap_trace_reader_t *open_trace(const char *path) {
    char err[ERR_LEN];
    vgacap_trace_reader_t *r = vgacap_trace_open(path, err, sizeof err);
    if (!r) fprintf(stderr, "tracetool: %s: %s\n", path, err);
    return r;
}

// A trace must be the layout this tool decodes.
static int check_layout(const vgacap_trace_info_t *in) {
    const vgacap_header_t *h = &in->header;
    if (h->version != 2 || h->sample_bits != 43 || h->samples_per_clock != 2 || h->clock_bit != CLK_BIT) {
        fprintf(stderr, "tracetool: not a tt-um-43 trace (version %u, %u bits, %u samples a clock, clock bit %u)\n",
                h->version, h->sample_bits, h->samples_per_clock, h->clock_bit);
        return -1;
    }
    return 0;
}

// Print each `key=value` line of META text (except `meta=`) as `<prefix>.key: value`.
static void print_meta(const char *prefix, const char *text) {
    while (*text) {
        const char *nl = strchr(text, '\n');
        size_t len = nl ? (size_t)(nl - text) : strlen(text);
        const char *eq = memchr(text, '=', len);
        if (eq && !(eq - text == 4 && !memcmp(text, "meta", 4)))
            printf("%s.%.*s: %.*s\n", prefix, (int)(eq - text), text, (int)(len - (size_t)(eq - text) - 1), eq + 1);
        if (!nl) break;
        text = nl + 1;
    }
}

// ---- info ---------------------------------------------------------------

typedef struct { int have_prev; uint64_t prev; uint64_t changes[NPORTS]; } changes_t;

static int count_changes(void *user, const vgacap_trace_run_t *runs, size_t n) {
    changes_t *c = user;
    for (size_t i = 0; i < n; i++) {
        uint64_t v = runs[i].value & ~(1ull << CLK_BIT);   // a run's samples differ only in the clock bit
        if (c->have_prev) {
            uint64_t d = v ^ c->prev;
            for (size_t p = 0; p < NPORTS; p++)
                if ((d >> PORTS[p].lo) & ((1u << PORTS[p].width) - 1u)) c->changes[p]++;
        }
        c->have_prev = 1;
        c->prev = v;
    }
    return 0;
}

static int cmd_info(const char *path) {
    char err[ERR_LEN];
    vgacap_trace_reader_t *r = open_trace(path);
    if (!r) return 1;
    const vgacap_trace_info_t *in = vgacap_trace_info(r);
    if (check_layout(in)) return 1;
    const vgacap_header_t *h = &in->header;
    printf("version: %u\nsample_bits: %u\nmode: %u\nclock_hz: %" PRIu32 "\nsamples_per_clock: %u\n"
           "clock_bit: %u\nclock_first: %u\n",
           h->version, h->sample_bits, h->mode, h->clock_hz, h->samples_per_clock, h->clock_bit, h->clock_first);
    printf("samples: %" PRIu64 "\nclocks: %" PRIu64 "\nblocks: %" PRIu32 "\ntable_rebuilt: %u\n",
           in->samples, in->samples / h->samples_per_clock, in->blocks, in->table_rebuilt);
    if (in->open_meta) print_meta("open", in->open_meta);
    if (in->close_meta) print_meta("close", in->close_meta);
    else printf("close.status: truncated\n");
    changes_t c = {0};
    if (vgacap_trace_read_runs(r, 0, in->samples, count_changes, &c, err, sizeof err)) {
        fprintf(stderr, "tracetool: %s: %s\n", path, err);
        return 1;
    }
    for (size_t p = 0; p < NPORTS; p++) printf("changes.%s: %" PRIu64 "\n", PORTS[p].name, c.changes[p]);
    vgacap_trace_close(r);
    return 0;
}

// ---- slice --------------------------------------------------------------

typedef struct { vgacap_trace_writer_t *w; int failed; } slice_t;

static int push_runs(void *user, const vgacap_trace_run_t *runs, size_t n) {
    slice_t *s = user;
    for (size_t i = 0; i < n; i++) {
        // value carries the clock bit of the run's first sample; the clock
        // bit alternates, and the slice starts on an even sample, so every
        // sample keeps its parity and its clock bit.
        uint64_t v = runs[i].value;
        for (uint64_t k = 0; k < runs[i].run; k++) {
            if (vgacap_trace_push(s->w, v)) { s->failed = 1; return 1; }
            v ^= 1ull << CLK_BIT;
        }
    }
    return 0;
}

static unsigned char *read_file(const char *path, size_t *len) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    size_t cap = 1 << 20, n = 0;
    unsigned char *buf = malloc(cap);
    while (buf) {
        size_t got = fread(buf + n, 1, cap - n, f);
        n += got;
        if (n < cap) break;
        cap *= 2;
        unsigned char *nb = realloc(buf, cap);
        if (!nb) { free(buf); buf = NULL; }
        else buf = nb;
    }
    int bad = ferror(f);
    fclose(f);
    if (bad && buf) { free(buf); buf = NULL; }
    *len = n;
    return buf;
}

// The vgacap writer always ends a trace with META(close). A truncated
// original's slice must not have one, so rewrite the finished file `src` to
// `dst` as a kill would leave it: every frame but the last copied as is, the
// last without its trailing META(close) chunk, and no seek table. The reader
// then rebuilds the table and reports the trace as truncated.
static int strip_close(const char *src, const char *dst) {
    size_t len;
    unsigned char *data = read_file(src, &len);
    if (!data) { fprintf(stderr, "tracetool: cannot read %s\n", src); return -1; }
    int rc = -1;
    size_t pos = 0, last_pos = 0, last_len = 0;
    unsigned frames = 0;
    // Walk the data frames; the seek table is a skippable frame (magic 0x184D2A5E) at the end.
    while (pos + 4 <= len) {
        uint32_t magic = (uint32_t)data[pos] | (uint32_t)data[pos + 1] << 8 | (uint32_t)data[pos + 2] << 16 |
                         (uint32_t)data[pos + 3] << 24;
        if ((magic & 0xFFFFFFF0u) == 0x184D2A50u) break;
        size_t flen = ZSTD_findFrameCompressedSize(data + pos, len - pos);
        if (ZSTD_isError(flen)) { fprintf(stderr, "tracetool: bad frame in %s\n", src); goto out; }
        last_pos = pos; last_len = flen; frames++;
        pos += flen;
    }
    if (!frames) { fprintf(stderr, "tracetool: no frames in %s\n", src); goto out; }

    unsigned long long raw_len = ZSTD_getFrameContentSize(data + last_pos, last_len);
    if (raw_len == ZSTD_CONTENTSIZE_UNKNOWN || raw_len == ZSTD_CONTENTSIZE_ERROR) {
        fprintf(stderr, "tracetool: last frame has no content size\n");
        goto out;
    }
    unsigned char *raw = malloc(raw_len ? raw_len : 1);
    unsigned char *zbuf = malloc(ZSTD_compressBound(raw_len));
    FILE *f = fopen(dst, "wb");
    ZSTD_CCtx *cctx = ZSTD_createCCtx();
    if (!raw || !zbuf || !f || !cctx) { fprintf(stderr, "tracetool: cannot write %s\n", dst); goto cleanup; }
    size_t got = ZSTD_decompress(raw, raw_len, data + last_pos, last_len);
    if (ZSTD_isError(got) || got != raw_len) { fprintf(stderr, "tracetool: cannot decompress the last frame\n"); goto cleanup; }
    // Chunks are tag(4) length(u32) payload: find the last one.
    size_t off = 0, last_chunk = 0;
    while (off + 8 <= raw_len) {
        uint32_t clen = (uint32_t)raw[off + 4] | (uint32_t)raw[off + 5] << 8 | (uint32_t)raw[off + 6] << 16 |
                        (uint32_t)raw[off + 7] << 24;
        last_chunk = off;
        off += 8 + (size_t)clen;
    }
    if (off != raw_len || memcmp(raw + last_chunk, "META", 4) != 0 ||
        raw_len - last_chunk < 8 + 11 || memcmp(raw + last_chunk + 8, "meta=close\n", 11) != 0) {
        fprintf(stderr, "tracetool: the last chunk is not META(close)\n");
        goto cleanup;
    }
    ZSTD_CCtx_setParameter(cctx, ZSTD_c_compressionLevel, ZSTD_LEVEL);
    ZSTD_CCtx_setParameter(cctx, ZSTD_c_checksumFlag, 1);
    size_t zlen = ZSTD_compress2(cctx, zbuf, ZSTD_compressBound(last_chunk), raw, last_chunk);
    if (ZSTD_isError(zlen)) { fprintf(stderr, "tracetool: cannot recompress the last frame\n"); goto cleanup; }
    if (fwrite(data, 1, last_pos, f) != last_pos || fwrite(zbuf, 1, zlen, f) != zlen || fclose(f)) {
        f = NULL;
        fprintf(stderr, "tracetool: cannot write %s\n", dst);
        goto cleanup;
    }
    f = NULL;
    rc = 0;
cleanup:
    if (f) fclose(f);
    if (cctx) ZSTD_freeCCtx(cctx);
    free(raw); free(zbuf);
out:
    free(data);
    return rc;
}

static int cmd_slice(const char *path, uint64_t from, uint64_t to, const char *out) {
    char err[ERR_LEN];
    vgacap_trace_reader_t *r = open_trace(path);
    if (!r) return 1;
    const vgacap_trace_info_t *in = vgacap_trace_info(r);
    if (check_layout(in)) return 1;
    uint64_t clocks = in->samples / in->header.samples_per_clock;
    if (from >= to || to > clocks) {
        fprintf(stderr, "tracetool: range [%" PRIu64 ", %" PRIu64 ") is empty or past the end (%" PRIu64 " clocks)\n",
                from, to, clocks);
        return 2;
    }
    if (!in->open_meta) { fprintf(stderr, "tracetool: %s has no META(open)\n", path); return 1; }

    char open_meta[META_MAX + 256], close_meta[256];
    int n = snprintf(open_meta, sizeof open_meta, "%sslice_from_clock=%" PRIu64 "\nslice_to_clock=%" PRIu64 "\n",
                     in->open_meta, from, to);
    if (n < 0 || n > META_MAX) { fprintf(stderr, "tracetool: META(open) too long\n"); return 1; }

    // A trace with a META(close) gets one; the writer always writes one, so
    // a truncated original's slice is rewritten below.
    const char *status = NULL;
    size_t stlen = 0;
    if (in->close_meta) {
        const char *p = in->close_meta;
        while (*p) {
            const char *nl = strchr(p, '\n');
            size_t len = nl ? (size_t)(nl - p) : strlen(p);
            if (len > 7 && !memcmp(p, "status=", 7)) { status = p + 7; stlen = len - 7; }
            if (!nl) break;
            p = nl + 1;
        }
        if (!status) { fprintf(stderr, "tracetool: META(close) has no status\n"); return 1; }
        // The status is the original's; the slice has no frames and no capture start of its own.
        snprintf(close_meta, sizeof close_meta, "meta=close\nstatus=%.*s\ncapture_after_clock=0\nframes=0\n",
                 (int)stlen, status);
    } else {
        snprintf(close_meta, sizeof close_meta, "meta=close\nstatus=sim-timeout\ncapture_after_clock=0\nframes=0\n");
    }

    char tmp[4096];
    const char *written = out;
    if (!in->close_meta) {
        if (snprintf(tmp, sizeof tmp, "%s.tmp", out) >= (int)sizeof tmp) { fprintf(stderr, "tracetool: path too long\n"); return 1; }
        written = tmp;
    }
    slice_t s = {0};
    s.w = vgacap_trace_create(written, &in->header, open_meta, ZSTD_LEVEL, err, sizeof err);
    if (!s.w) { fprintf(stderr, "tracetool: %s: %s\n", written, err); return 1; }
    int rc = vgacap_trace_read_runs(r, 2 * from, 2 * to, push_runs, &s, err, sizeof err);
    if (rc || s.failed) {
        if (!rc) snprintf(err, sizeof err, "the trace writer failed");
        fprintf(stderr, "tracetool: slice: %s\n", err);
        vgacap_trace_abandon(s.w);
        remove(written);
        return 1;
    }
    if (vgacap_trace_finish(s.w, close_meta, err, sizeof err)) {
        fprintf(stderr, "tracetool: %s: %s\n", written, err);
        remove(written);
        return 1;
    }
    vgacap_trace_close(r);
    if (!in->close_meta) {
        rc = strip_close(tmp, out);
        remove(tmp);
        if (rc) { remove(out); return 1; }
    }
    return 0;
}

// ---- uohash -------------------------------------------------------------

typedef struct { SHA256_CTX ctx; uint64_t done; } hash_t;

static int hash_runs(void *user, const vgacap_trace_run_t *runs, size_t n) {
    hash_t *h = user;
    static BYTE buf[65536];
    for (size_t i = 0; i < n; i++) {
        uint64_t a = runs[i].first_sample, b = a + runs[i].run;
        uint64_t odd = (b >> 1) - (a >> 1);        // samples 2c + 1 in [a, b)
        memset(buf, (int)(runs[i].value & 0xFF), odd < sizeof buf ? (size_t)odd : sizeof buf);
        for (uint64_t left = odd; left;) {
            size_t k = left < sizeof buf ? (size_t)left : sizeof buf;
            sha256_update(&h->ctx, buf, k);
            left -= k;
        }
        h->done += odd;
    }
    return 0;
}

static int cmd_uohash(const char *path, uint64_t limit) {
    char err[ERR_LEN];
    vgacap_trace_reader_t *r = open_trace(path);
    if (!r) return 1;
    const vgacap_trace_info_t *in = vgacap_trace_info(r);
    if (check_layout(in)) return 1;
    uint64_t clocks = in->samples / in->header.samples_per_clock;
    uint64_t m = limit < clocks ? limit : clocks;
    hash_t h = {0};
    sha256_init(&h.ctx);
    // Clocks [0, m) are samples [0, 2m): the half-open range.
    if (vgacap_trace_read_runs(r, 0, 2 * m, hash_runs, &h, err, sizeof err)) {
        fprintf(stderr, "tracetool: %s: %s\n", path, err);
        return 1;
    }
    if (h.done != m) { fprintf(stderr, "tracetool: hashed %" PRIu64 " clocks, expected %" PRIu64 "\n", h.done, m); return 1; }
    BYTE digest[SHA256_BLOCK_SIZE];
    sha256_final(&h.ctx, digest);
    printf("uo_out_sha256_clocks: 0 %" PRIu64 "\nuo_out_sha256: ", m);
    for (int i = 0; i < SHA256_BLOCK_SIZE; i++) printf("%02x", digest[i]);
    printf("\n");
    vgacap_trace_close(r);
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 3) return usage("a command and a trace are required");
    const char *cmd = argv[1], *trace = argv[2];
    if (!strcmp(cmd, "info")) {
        return argc == 3 ? cmd_info(trace) : usage("info takes only TRACE");
    }
    if (!strcmp(cmd, "slice")) {
        uint64_t from = 0, to = 0;
        const char *out = NULL;
        int have_from = 0, have_to = 0;
        for (int i = 3; i < argc; i++) {
            if (i + 1 >= argc) return usage("an option has no value");
            if (!strcmp(argv[i], "--from")) { if (parse_u64(argv[++i], &from)) return usage("bad --from"); have_from = 1; }
            else if (!strcmp(argv[i], "--to")) { if (parse_u64(argv[++i], &to)) return usage("bad --to"); have_to = 1; }
            else if (!strcmp(argv[i], "--out")) out = argv[++i];
            else return usage("unknown slice option");
        }
        if (!have_from || !have_to || !out) return usage("slice needs --from, --to and --out");
        return cmd_slice(trace, from, to, out);
    }
    if (!strcmp(cmd, "uohash")) {
        uint64_t n = DEFAULT_UOHASH_CLOCKS;
        for (int i = 3; i < argc; i++) {
            if (!strcmp(argv[i], "--clocks") && i + 1 < argc) { if (parse_u64(argv[++i], &n)) return usage("bad --clocks"); }
            else return usage("unknown uohash option");
        }
        return cmd_uohash(trace, n);
    }
    return usage("unknown command");
}
