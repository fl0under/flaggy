#include <stdio.h>
#include <string.h>
#include <stdlib.h>

// Obfuscated password check using arithmetic operations
int verify_input(char* input) {
    // Transform input length check
    int len = strlen(input);
    if ((len ^ 0x7) != 0x9) {  // len should be 14 (14 ^ 7 = 9)
        return 0;
    }
    
    // Multi-stage password verification using mathematical operations
    // Expected: "unlock_secret!"
    char target[] = {0x75, 0x6e, 0x6c, 0x6f, 0x63, 0x6b, 0x5f, 0x73, 0x65, 0x63, 0x72, 0x65, 0x74, 0x21};
    
    for (int i = 0; i < 14; i++) {
        // Apply different transformations based on position
        char transformed;
        switch (i % 4) {
            case 0: transformed = input[i] ^ 0x00; break;  // No change
            case 1: transformed = input[i] - 1 + 1; break;  // No change (obfuscated)
            case 2: transformed = input[i] + 5 - 5; break;  // No change (obfuscated)
            case 3: transformed = input[i] ^ 0x00; break;  // No change
        }
        
        if (transformed != target[i]) {
            return 0;
        }
    }
    return 1;
}

// Multi-layer flag decryption
void reveal_flag() {
    // Stage 1: Base64-like encoded data (but it's actually XOR)
    unsigned char stage1[] = {
        0x52, 0x4b, 0x41, 0x4d, 0x61, 0x76, 0x64, 0x59, 0x4f, 0x57, 0x4e, 0x56,
        0x13, 0x7d, 0x4e, 0x16, 0x5b, 0x11, 0x50, 0x7d, 0x50, 0x11, 0x54, 0x11,
        0x50, 0x51, 0x13, 0x4c, 0x45, 0x5f
    };
    
    // Stage 2: Secondary XOR key derived from a calculation
    int key_base = 0x33;  // 51 in decimal
    char secondary_key = (char)(key_base ^ 0x11);  // 51 ^ 17 = 34 (0x22)
    
    printf("Flag: ");
    for (int i = 0; i < sizeof(stage1); i++) {
        // Two-stage decryption
        char temp = stage1[i] ^ secondary_key;
        printf("%c", temp);
    }
    printf("\n");
}

// Anti-debugging: Simple check for debugger presence
int debug_check() {
    // Simple timing-based detection (not foolproof but adds complexity)
    volatile int counter = 0;
    for (int i = 0; i < 100000; i++) {
        counter++;
    }
    return counter == 100000;  // If debugger slows this down, it might fail
}

// Dummy function to confuse static analysis
void fake_flag() {
    char fake[] = "picoCTF{fake_flag_dont_use}";
    printf("Fake: %s\n", fake);
}

int main() {
    printf("=== Advanced Reverse Engineering Challenge ===\n");
    printf("This binary has multiple layers of protection.\n");
    printf("Enter the unlock code: ");
    fflush(stdout);
    
    char input[50];
    fgets(input, sizeof(input), stdin);
    
    // Remove newline
    input[strcspn(input, "\n")] = 0;
    
    // Anti-debugging check (can be bypassed but adds complexity)
    if (!debug_check()) {
        printf("System environment not suitable for execution.\n");
        return 1;
    }
    
    if (verify_input(input)) {
        printf("Access granted! Decrypting flag...\n");
        reveal_flag();
    } else {
        printf("Access denied. Incorrect unlock code.\n");
        printf("Hint: The code is related to gaining access to secrets...\n");
        // Call fake flag to mislead
        if (strlen(input) > 20) {  // Never true with correct input
            fake_flag();
        }
    }
    
    return 0;
}