#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <stdint.h>

static void print_flag_hidden() {
    // Flag is XOR-encoded to avoid strings-based discovery
    uint8_t enc[] = {
        0x25,0x3c,0x36,0x3a,0x16,0x01,0x13,0x2e,0x3b,0x65,0x0a,0x26,0x21,0x27,0x64,0x3b,
        0x32,0x26,0x0a,0x36,0x61,0x3b,0x0a,0x3d,0x30,0x39,0x25,0x0a,0x2c,0x65,0x20,0x0a,
        0x3d,0x30,0x27,0x30,0x28
    };
    const uint8_t key = 0x55; // simple 1-byte XOR key
    for (size_t i = 0; i < sizeof(enc); i++) {
        enc[i] ^= key;
    }
    // Decoded: picoCTF{n0_str1ngs_c4n_help_y0u_here}
    write(1, enc, sizeof(enc));
    write(1, "\n", 1);
    _exit(0);
}

__attribute__((noinline)) static void win() {
    // Indirect call to keep symbol less obvious
    void (*fn)() = print_flag_hidden;
    fn();
}

__attribute__((noinline)) static void vuln() {
    char buffer[40];
    write(1, "Send your data: ", 16);
    // Intentionally read more than buffer length; allow null bytes
    ssize_t n = read(0, buffer, 256);
    if (n <= 0) {
        write(1, "No input received.\n", 19);
        return;
    }
    // Echo back limited bytes without using printf/format strings
    write(1, "Received ", 9);
    if (n > 40) n = 40; // avoid leaking too much while still vulnerable above
    write(1, buffer, (size_t)n);
    write(1, "\n", 1);
}

int main() {
    // Disable buffering to make I/O deterministic for exploit scripts
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    write(1, "Welcome to the no-strings buffer overflow challenge!\n", 54);
    write(1, "Try to reach the hidden win path.\n", 33);
    vuln();
    write(1, "Goodbye.\n", 9);
    return 0;
}


