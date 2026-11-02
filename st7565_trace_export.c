#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WIDTH 132
#define PAGES 8

#pragma pack(push, 1)
typedef struct {
    uint64_t sample;
    uint8_t dc;
    uint8_t value;
    uint8_t page;
    uint8_t column;
} SpiEventBinary;
#pragma pack(pop)

static inline int bit(uint8_t sample, int channel) {
    return (sample >> channel) & 1;
}

static void update_cursor(int dc, uint8_t value, unsigned *page, unsigned *column) {
    if (dc) {
        *column = (*column + 1) % WIDTH;
        return;
    }
    if ((value & 0xf0) == 0xb0) {
        *page = value & 0x07;
    } else if ((value & 0xf0) == 0x10) {
        *column = ((*column & 0x0f) | ((unsigned)(value & 0x0f) << 4)) % WIDTH;
    } else if ((value & 0xf0) == 0x00) {
        *column = ((*column & 0xf0) | (unsigned)(value & 0x0f)) % WIDTH;
    }
}

static SpiEventBinary out_events[1024]; // 12 KB batch
static size_t out_count = 0;

static inline void flush_binary_events(void) {
    if (out_count > 0) {
        fwrite(out_events, sizeof(SpiEventBinary), out_count, stdout);
        out_count = 0;
        fflush(stdout);
    }
}

static inline void push_binary_event(uint64_t sample, uint8_t dc, uint8_t value, uint8_t page, uint8_t column) {
    out_events[out_count].sample = sample;
    out_events[out_count].dc = dc;
    out_events[out_count].value = value;
    out_events[out_count].page = page;
    out_events[out_count].column = column;
    out_count++;
    if (out_count >= 1024) {
        fwrite(out_events, sizeof(SpiEventBinary), out_count, stdout);
        out_count = 0;
    }
}

static int decode_stream_binary(double samplerate) {
    uint8_t in_buf[16384];
    size_t n_read;
    int first_sample;
    int previous_cs;
    int previous_clk;
    uint8_t byte = 0;
    unsigned bits = 0;
    int frame_dc = 0;
    unsigned page = 0;
    unsigned column = 0;
    uint64_t sample_index = 0;

    if (samplerate <= 0.0) {
        fprintf(stderr, "Invalid samplerate.\n");
        return 1;
    }

    first_sample = getchar();
    if (first_sample == EOF) {
        fprintf(stderr, "No usable samples.\n");
        return 1;
    }
    previous_cs = bit((uint8_t)first_sample, 0);
    previous_clk = bit((uint8_t)first_sample, 1);
    frame_dc = bit((uint8_t)first_sample, 3);

    while ((n_read = fread(in_buf, 1, sizeof(in_buf), stdin)) > 0) {
        for (size_t i = 0; i < n_read; i++) {
            uint8_t sample = in_buf[i];
            int cs = bit(sample, 0);
            int clk = bit(sample, 1);
            sample_index++;

            if (previous_cs == 1 && cs == 0) {
                byte = 0;
                bits = 0;
                frame_dc = bit(sample, 3);
            } else if (previous_cs == 0 && cs == 1) {
                byte = 0;
                bits = 0;
                // Burst end: immediately flush to pipe
                flush_binary_events();
            }

            if (cs == 0 && bits == 0) {
                frame_dc = bit(sample, 3);
            }

            if (cs == 0 && previous_clk == 0 && clk == 1) {
                byte = (uint8_t)((byte << 1) | bit(sample, 2));
                bits++;
                if (bits == 8) {
                    push_binary_event(sample_index, (uint8_t)frame_dc, byte, (uint8_t)page, (uint8_t)column);
                    if (frame_dc) {
                        column = (column + 1) % WIDTH;
                    } else {
                        update_cursor(0, byte, &page, &column);
                    }
                    byte = 0;
                    bits = 0;
                    frame_dc = bit(sample, 3);
                }
            }
            previous_cs = cs;
            previous_clk = clk;
        }
    }
    flush_binary_events();
    return 0;
}

int main(int argc, char **argv) {
    double samplerate = 4000000.0;
    if (argc >= 2 && (strcmp(argv[1], "--stream") == 0 || strcmp(argv[1], "--binary") == 0)) {
        if (argc >= 3) samplerate = strtod(argv[2], NULL);
        return decode_stream_binary(samplerate);
    }
    if (argc >= 2) samplerate = strtod(argv[1], NULL);
    return decode_stream_binary(samplerate);
}
