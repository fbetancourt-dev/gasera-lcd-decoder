#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WIDTH 132
#define PAGES 8

static uint8_t *read_samples(size_t *count) {
    size_t capacity = 1u << 20;
    uint8_t *samples = malloc(capacity);
    int value;

    if (!samples) return NULL;
    *count = 0;
    while ((value = getchar()) != EOF) {
        if (*count == capacity) {
            capacity *= 2;
            uint8_t *next = realloc(samples, capacity);
            if (!next) {
                free(samples);
                return NULL;
            }
            samples = next;
        }
        samples[(*count)++] = (uint8_t)value;
    }
    return samples;
}

static int bit(uint8_t sample, int channel) {
    return (sample >> channel) & 1;
}

static const char *command_name(uint8_t value) {
    if ((value & 0xf0) == 0xb0) return "Set page";
    if ((value & 0xf0) == 0x10) return "Set column high";
    if ((value & 0xf0) == 0x00) return "Set column low";
    if (value == 0xe2) return "Reset";
    if (value == 0xaf) return "Display on";
    if (value == 0xae) return "Display off";
    if ((value & 0xfe) == 0xa0) return "ADC select";
    if ((value & 0xfe) == 0xc0) return "COM direction";
    if ((value & 0xf8) == 0x20) return "Resistor ratio";
    if (value == 0x81) return "Electronic volume mode";
    if ((value & 0xfc) == 0xa4) return "Display all points";
    if ((value & 0xfe) == 0xa6) return "Display normal/reverse";
    return "Command";
}

static int command_is_known(uint8_t value) {
    if (value <= 0x2f) return 1;
    if (value >= 0x40 && value <= 0x7f) return 1;
    if (value >= 0xb0 && value <= 0xb7) return 1;
    switch (value) {
        case 0x81:
        case 0xa0:
        case 0xa1:
        case 0xa2:
        case 0xa3:
        case 0xa4:
        case 0xa5:
        case 0xa6:
        case 0xa7:
        case 0xab:
        case 0xac:
        case 0xad:
        case 0xae:
        case 0xaf:
        case 0xc0:
        case 0xc8:
        case 0xe0:
        case 0xe2:
        case 0xe3:
        case 0xee:
        case 0xf8:
            return 1;
        default:
            return 0;
    }
}

static unsigned command_parameter_count(uint8_t value) {
    return value == 0x81 || value == 0xac || value == 0xf8;
}

static void emit_event(FILE *out, int *first, uint64_t sample_index,
                       int dc, uint8_t value, unsigned page, unsigned column) {
    if (!*first) fputs(",\n", out);
    *first = 0;
    fprintf(out, "    [%lu,%d,%u,%u,%u,\"%s\"]",
            (unsigned long)sample_index, dc, value, page, column,
            dc ? "Data" : command_name(value));
}

static void update_cursor(int dc, uint8_t value, unsigned *page,
                          unsigned *column) {
    if (dc) {
        *column = (*column + 1) % WIDTH;
        return;
    }
    if ((value & 0xf0) == 0xb0) {
        *page = value & 0x0f;
    } else if ((value & 0xf0) == 0x10) {
        *column = ((*column & 0x0f) | ((unsigned)(value & 0x0f) << 4)) % WIDTH;
    } else if ((value & 0xf0) == 0x00) {
        *column = ((*column & 0xf0) | (unsigned)(value & 0x0f)) % WIDTH;
    }
}

static int decode_stream(double samplerate) {
    int first_sample = getchar();
    int previous_cs;
    int previous_clk;
    uint8_t byte = 0;
    unsigned bits = 0;
    int frame_dc;
    unsigned page = 0;
    unsigned column = 0;
    uint64_t sample_index = 0;
    uint64_t events = 0;
    uint64_t commands = 0;
    uint64_t data = 0;
    uint64_t invalid_frames = 0;
    uint64_t ignored_bytes = 0;
    uint64_t unknown_commands = 0;
    unsigned page_valid = 0;
    unsigned column_high_valid = 0;
    unsigned column_low_valid = 0;
    unsigned parameter_bytes = 0;
    int byte_invalid = 0;
    int value;

    if (first_sample == EOF || samplerate <= 0.0) {
        fprintf(stderr, "No usable samples.\n");
        return 1;
    }
    setvbuf(stdout, NULL, _IOLBF, 0);
    previous_cs = bit((uint8_t)first_sample, 0);
    previous_clk = bit((uint8_t)first_sample, 1);
    frame_dc = bit((uint8_t)first_sample, 3);

    while ((value = getchar()) != EOF) {
        uint8_t sample = (uint8_t)value;
        int cs;
        int clk;
        sample_index++;
        cs = bit(sample, 0);
        clk = bit(sample, 1);

        if (previous_cs == 1 && cs == 0) {
            byte = 0;
            bits = 0;
            frame_dc = bit(sample, 3);
            byte_invalid = 0;
        } else if (previous_cs == 0 && cs == 1) {
            if (bits != 0) {
                invalid_frames++;
                page_valid = 0;
                column_high_valid = 0;
                column_low_valid = 0;
                parameter_bytes = 0;
            }
            byte = 0;
            bits = 0;
            byte_invalid = 0;
        }

        if (cs == 0) {
            int dc = bit(sample, 3);
            if (bits == 0) frame_dc = dc;
            else if (dc != frame_dc) byte_invalid = 1;
        }

        if (cs == 0 && previous_clk == 0 && clk == 1) {
            byte = (uint8_t)((byte << 1) | bit(sample, 2));
            bits++;
            if (bits == 8) {
                int cursor_valid =
                    page_valid && column_high_valid && column_low_valid;
                if (byte_invalid ||
                    (frame_dc && (page >= PAGES || !cursor_valid ||
                                  parameter_bytes != 0))) {
                    ignored_bytes++;
                    if (byte_invalid || parameter_bytes != 0) {
                        page_valid = 0;
                        column_high_valid = 0;
                        column_low_valid = 0;
                        parameter_bytes = 0;
                    }
                } else if (!frame_dc && parameter_bytes != 0) {
                    printf("E %lu %d %u %u %u\n",
                           (unsigned long)sample_index, frame_dc, byte, page, column);
                    events++;
                    commands++;
                    parameter_bytes--;
                } else if (!frame_dc && !command_is_known(byte)) {
                    ignored_bytes++;
                    unknown_commands++;
                    page_valid = 0;
                    column_high_valid = 0;
                    column_low_valid = 0;
                    parameter_bytes = 0;
                } else {
                    printf("E %lu %d %u %u %u\n",
                           (unsigned long)sample_index, frame_dc, byte, page, column);
                    events++;
                    if (frame_dc) data++;
                    else {
                        commands++;
                        if ((byte & 0xf0) == 0xb0) page_valid = 1;
                        else if ((byte & 0xf0) == 0x10) column_high_valid = 1;
                        else if ((byte & 0xf0) == 0x00) column_low_valid = 1;
                        else if (byte == 0xe2) {
                            page_valid = 0;
                            column_high_valid = 0;
                            column_low_valid = 0;
                        }
                        parameter_bytes = command_parameter_count(byte);
                    }
                    update_cursor(frame_dc, byte, &page, &column);
                }
                byte = 0;
                bits = 0;
                frame_dc = bit(sample, 3);
                byte_invalid = 0;
            }
        }
        previous_cs = cs;
        previous_clk = clk;
        if ((sample_index & ((1u << 20) - 1u)) == 0)
            printf("P %lu %lu %lu %lu\n",
                   (unsigned long)sample_index,
                   (unsigned long)invalid_frames,
                   (unsigned long)ignored_bytes,
                   (unsigned long)unknown_commands);
    }
    if (previous_cs == 0 && bits != 0) invalid_frames++;
    printf("S %lu %lu %lu %lu %lu %lu %lu\n",
           (unsigned long)(sample_index + 1), (unsigned long)events,
           (unsigned long)commands, (unsigned long)data,
           (unsigned long)invalid_frames, (unsigned long)ignored_bytes,
           (unsigned long)unknown_commands);
    return 0;
}

int main(int argc, char **argv) {
    double samplerate = 4000000.0;
    const char *capture_name = "capture";
    size_t count = 0;
    uint8_t *samples = NULL;
    int previous_cs;
    int previous_clk;
    uint8_t byte = 0;
    unsigned bits = 0;
    int frame_dc = 0;
    unsigned page = 0;
    unsigned column = 0;
    uint64_t events = 0;
    uint64_t commands = 0;
    uint64_t data = 0;
    uint64_t invalid_frames = 0;
    uint64_t ignored_bytes = 0;
    unsigned page_valid = 0;
    unsigned column_high_valid = 0;
    unsigned column_low_valid = 0;
    unsigned parameter_bytes = 0;
    int first = 1;
    int summary_only = 0;
    int stream_mode = 0;
    int byte_invalid = 0;

    if (argc >= 2 && strcmp(argv[1], "--stream") == 0) {
        stream_mode = 1;
        if (argc >= 3) samplerate = strtod(argv[2], NULL);
    } else if (argc >= 2 && strcmp(argv[1], "--summary-only") == 0) {
        summary_only = 1;
        if (argc >= 3) samplerate = strtod(argv[2], NULL);
        if (argc >= 4) capture_name = argv[3];
    } else {
        if (argc >= 2) samplerate = strtod(argv[1], NULL);
        if (argc >= 3) capture_name = argv[2];
    }

    if (stream_mode) return decode_stream(samplerate);

    samples = read_samples(&count);
    if (!samples || count < 2 || samplerate <= 0.0) {
        fprintf(stderr, "No usable samples.\n");
        free(samples);
        return 1;
    }

    previous_cs = bit(samples[0], 0);
    previous_clk = bit(samples[0], 1);
    frame_dc = bit(samples[0], 3);

    if (!summary_only) {
        puts("const LCD_TRACE = {");
        printf("  capture: \"%s\",\n", capture_name);
        printf("  sampleRate: %.0f,\n", samplerate);
        puts("  width: 132,");
        puts("  height: 64,");
        puts("  channels: { cs: \"D0\", sclk: \"D1\", mosi: \"D2\", dc: \"D3\" },");
        puts("  eventFields: [\"sample\", \"dc\", \"value\", \"page\", \"column\", \"label\"],");
        puts("  events: [");
    }

    for (size_t i = 1; i < count; i++) {
        int cs = bit(samples[i], 0);
        int clk = bit(samples[i], 1);

        if (previous_cs == 1 && cs == 0) {
            byte = 0;
            bits = 0;
            frame_dc = bit(samples[i], 3);
            byte_invalid = 0;
        } else if (previous_cs == 0 && cs == 1) {
            if (bits != 0) {
                invalid_frames++;
                page_valid = 0;
                column_high_valid = 0;
                column_low_valid = 0;
                parameter_bytes = 0;
            }
            byte = 0;
            bits = 0;
            byte_invalid = 0;
        }

        if (cs == 0) {
            int dc = bit(samples[i], 3);
            if (bits == 0) frame_dc = dc;
            else if (dc != frame_dc) byte_invalid = 1;
        }

        if (cs == 0 && previous_clk == 0 && clk == 1) {
            byte = (uint8_t)((byte << 1) | bit(samples[i], 2));
            bits++;
            if (bits == 8) {
                int cursor_valid =
                    page_valid && column_high_valid && column_low_valid;
                if (byte_invalid ||
                    (frame_dc && (page >= PAGES || !cursor_valid ||
                                  parameter_bytes != 0))) {
                    ignored_bytes++;
                    if (byte_invalid || parameter_bytes != 0) {
                        page_valid = 0;
                        column_high_valid = 0;
                        column_low_valid = 0;
                        parameter_bytes = 0;
                    }
                } else if (!frame_dc && parameter_bytes != 0) {
                    if (!summary_only)
                        emit_event(stdout, &first, (uint64_t)i, frame_dc, byte, page, column);
                    events++;
                    commands++;
                    parameter_bytes--;
                } else if (!frame_dc && !command_is_known(byte)) {
                    ignored_bytes++;
                    page_valid = 0;
                    column_high_valid = 0;
                    column_low_valid = 0;
                    parameter_bytes = 0;
                } else {
                    if (!summary_only)
                        emit_event(stdout, &first, (uint64_t)i, frame_dc, byte, page, column);
                    events++;
                    if (frame_dc) data++;
                    else {
                        commands++;
                        if ((byte & 0xf0) == 0xb0) page_valid = 1;
                        else if ((byte & 0xf0) == 0x10) column_high_valid = 1;
                        else if ((byte & 0xf0) == 0x00) column_low_valid = 1;
                        else if (byte == 0xe2) {
                            page_valid = 0;
                            column_high_valid = 0;
                            column_low_valid = 0;
                        }
                        parameter_bytes = command_parameter_count(byte);
                    }
                    update_cursor(frame_dc, byte, &page, &column);
                }
                byte = 0;
                bits = 0;
                frame_dc = bit(samples[i], 3);
                byte_invalid = 0;
            }
        }

        previous_cs = cs;
        previous_clk = clk;
    }

    if (previous_cs == 0 && bits != 0) invalid_frames++;

    if (summary_only) {
        printf("%zu %lu %lu %lu %lu %lu\n", count, (unsigned long)events,
               (unsigned long)commands, (unsigned long)data,
               (unsigned long)invalid_frames, (unsigned long)ignored_bytes);
    } else {
        puts("");
        puts("  ],");
        printf("  summary: { samples: %zu, events: %lu, commandBytes: %lu, dataBytes: %lu, invalidFrames: %lu, ignoredBytes: %lu }\n",
               count, (unsigned long)events, (unsigned long)commands,
               (unsigned long)data, (unsigned long)invalid_frames,
               (unsigned long)ignored_bytes);
        puts("};");
    }

    free(samples);
    return 0;
}
