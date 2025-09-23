#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>
#include <time.h>
#include <stdint.h>

// VM opcodes - scattered to make analysis harder
#define VM_LOAD    0x47
#define VM_XOR     0xB3
#define VM_ADD     0x91
#define VM_CMP     0x5E
#define VM_JNE     0xC2
#define VM_STORE   0x7A
#define VM_HALT    0x00

// VM state
typedef struct {
    uint8_t registers[8];
    uint8_t *memory;
    uint8_t *code;
    int pc;  // program counter
    int flag;  // zero flag for comparisons
} vm_state_t;

// Hardened storage: two obfuscated shards whose XOR equals the encrypted flag bytes
static const uint8_t flag_shard_a[] = {
    0x20, 0xC7, 0x6E, 0x11, 0x3F, 0xED, 0x6C, 0x51,
    0xD2, 0x2A, 0x94, 0xDF, 0xF9, 0xAA, 0xE6, 0x1C,
    0xE4, 0xA7, 0x2B, 0xF9, 0x31, 0x97, 0xAD, 0xFA,
    0x08, 0x15, 0xB9, 0x0C, 0xF8, 0x90, 0xD6, 0x0C
};

static const uint8_t flag_shard_b[] = {
    0x47, 0xB9, 0x1A, 0x69, 0x6B, 0xAE, 0x3D, 0x3D,
    0xA4, 0x59, 0xF5, 0xFC, 0x80, 0xDE, 0x94, 0x6F,
    0xAC, 0xC6, 0x51, 0xB1, 0x16, 0xE2, 0xDC, 0x98,
    0x6C, 0x61, 0x9A, 0x6F, 0x86, 0xB7, 0xAF, 0x66
};

// Dynamic key generator using runtime factors
uint32_t generate_runtime_key() {
    uint32_t key = 0;
    
    // Factor 1: Process ID (masked to ensure consistency)
    key ^= (getpid() & 0xFF) << 8;
    
    // Factor 2: Stack address (lower bits for some consistency)
    uintptr_t stack_addr = (uintptr_t)&key;
    key ^= (stack_addr & 0xFF00) >> 4;
    
    // Factor 3: Time-based but predictable
    key ^= 0xDEAD;  // Fixed component to make it solvable
    
    // Factor 4: Binary base address influence
    key ^= 0xBEEF;
    
    return key;
}

// Generate VM bytecode at runtime (with backpatched conditional jumps)
void generate_vm_code(uint8_t *vm_code, const char *input, uint32_t runtime_key) {
    (void)input; // not used by codegen directly
    (void)runtime_key; // reserved for future use

    int pos = 0;

    // VM program to verify obfuscated password
    // Password bytes XOR'd with position-dependent keys
    uint8_t target_bytes[] = {
        0x77^1, 0x6d^2, 0x5f^3, 0x68^4, 0x34^5, 0x63^6, 0x6b^7, 0x33^8,
        0x72^9, 0x5f^10, 0x32^11, 0x30^12, 0x32^13, 0x34^14, 0x21^15
    };
    int pass_len = (int)sizeof(target_bytes);

    // Record locations where JNE target needs to be backpatched (store index of low byte)
    int jne_target_indices[64];
    int jne_count = 0;

    for (int i = 0; i < pass_len; i++) {
        // Load input character into register 0
        vm_code[pos++] = VM_LOAD;
        vm_code[pos++] = 0;  // register 0 (input char - special handling in VM)
        vm_code[pos++] = 0;  // dummy value

        // Load obfuscated target character, then deobfuscate
        vm_code[pos++] = VM_LOAD;
        vm_code[pos++] = 1;  // register 1
        vm_code[pos++] = target_bytes[i];  // obfuscated character

        // Load position key for deobfuscation
        vm_code[pos++] = VM_LOAD;
        vm_code[pos++] = 2;  // register 2
        vm_code[pos++] = (uint8_t)(i + 1);  // position-based key

        // Deobfuscate: target XOR position_key
        vm_code[pos++] = VM_XOR;
        vm_code[pos++] = 1;  // reg1 = reg1 XOR reg2
        vm_code[pos++] = 2;

        // Compare input with expected
        vm_code[pos++] = VM_CMP;
        vm_code[pos++] = 0;  // register 0 (input char)
        vm_code[pos++] = 1;  // register 1 (expected char)

        // Jump to fail if not equal (16-bit absolute address backpatched later)
        vm_code[pos++] = VM_JNE;
        jne_target_indices[jne_count++] = pos; // low byte position
        vm_code[pos++] = 0x00; // placeholder low
        vm_code[pos++] = 0x00; // placeholder high
    }

    // Success - store success marker in r7
    vm_code[pos++] = VM_LOAD;
    vm_code[pos++] = 7;  // register 7 (flag register)
    vm_code[pos++] = 0x42;  // success marker

    // Decrypt flag into VM memory: for each i, mem[i] = (a[i]^b[i]) ^ 0x17
    for (int i = 0; i < (int)sizeof(flag_shard_a); i++) {
        uint8_t enc_byte = (uint8_t)(flag_shard_a[i] ^ flag_shard_b[i]);
        vm_code[pos++] = VM_LOAD; // r1 <- enc_byte
        vm_code[pos++] = 1;
        vm_code[pos++] = enc_byte;

        vm_code[pos++] = VM_LOAD; // r2 <- 0x17
        vm_code[pos++] = 2;
        vm_code[pos++] = 0x17;

        vm_code[pos++] = VM_XOR;  // r1 ^= r2
        vm_code[pos++] = 1;
        vm_code[pos++] = 2;

        vm_code[pos++] = VM_STORE; // mem[i] = r1
        vm_code[pos++] = 1;
        vm_code[pos++] = (uint8_t)i;
    }

    vm_code[pos++] = VM_HALT;

    // Fail handler (place after success block + decrypt sequence)
    uint16_t fail_addr = (uint16_t)pos;
    vm_code[pos++] = VM_LOAD;
    vm_code[pos++] = 7;
    vm_code[pos++] = 0x00;  // fail marker
    vm_code[pos++] = VM_HALT;

    // Backpatch all JNE targets to the fail handler address
    for (int j = 0; j < jne_count; j++) {
        int idx = jne_target_indices[j];
        vm_code[idx] = (uint8_t)(fail_addr & 0xFF);
        vm_code[idx + 1] = (uint8_t)((fail_addr >> 8) & 0xFF);
    }
}

// VM interpreter with self-modification capabilities
int execute_vm(vm_state_t *vm, const char *input) {
    int input_pos = 0;  // Track position in input string
    
    while (1) {
        uint8_t opcode = vm->code[vm->pc];
        
        switch (opcode) {
            case VM_LOAD: {
                uint8_t reg = vm->code[vm->pc + 1];
                uint8_t val = vm->code[vm->pc + 2];
                
                // Special handling for register 0 - load from input
                if (reg == 0 && input_pos < strlen(input)) {
                    vm->registers[reg] = input[input_pos++];
                } else {
                    // Direct value load for other registers
                    vm->registers[reg] = val;
                }
                vm->pc += 3;
                break;
            }
            
            case VM_XOR: {
                uint8_t reg1 = vm->code[vm->pc + 1];
                uint8_t reg2 = vm->code[vm->pc + 2];
                vm->registers[reg1] ^= vm->registers[reg2];
                vm->pc += 3;
                break;
            }
            
            case VM_ADD: {
                uint8_t reg1 = vm->code[vm->pc + 1];
                uint8_t reg2 = vm->code[vm->pc + 2];
                vm->registers[reg1] += vm->registers[reg2];
                vm->pc += 3;
                break;
            }
            
            case VM_CMP: {
                uint8_t reg1 = vm->code[vm->pc + 1];
                uint8_t reg2 = vm->code[vm->pc + 2];
                vm->flag = (vm->registers[reg1] == vm->registers[reg2]) ? 0 : 1;
                // Debug comparison
                // printf("CMP: reg%d(0x%02X) vs reg%d(0x%02X) -> flag=%d\n", 
                //        reg1, vm->registers[reg1], reg2, vm->registers[reg2], vm->flag);
                vm->pc += 3;
                break;
            }
            
            case VM_JNE: {
                uint16_t target = (uint16_t)vm->code[vm->pc + 1] |
                                  ((uint16_t)vm->code[vm->pc + 2] << 8);
                if (vm->flag != 0) {
                    vm->pc = target;
                } else {
                    vm->pc += 3;
                }
                break;
            }
            
            case VM_STORE: {
                uint8_t reg = vm->code[vm->pc + 1];
                uint8_t addr = vm->code[vm->pc + 2];
                vm->memory[addr] = vm->registers[reg];
                vm->pc += 3;
                break;
            }
            
            case VM_HALT:
                return vm->registers[7];  // Return success/fail status
                
            default:
                // Unknown opcode or NOP
                vm->pc++;
                break;
        }
        
        // Prevent runaway execution (allow larger programs)
        if (vm->pc > 4000) break;
    }
    
    return 0;  // Execution error
}

// Anti-analysis: reconstruct encrypted flag from shards, then decrypt and print
void decrypt_and_print_flag(uint32_t runtime_key) {
    (void)runtime_key; // currently unused in decryption

    printf("Congratulations! Here's your flag:\n");

    int flag_len = (int)sizeof(flag_shard_a);
    for (int i = 0; i < flag_len; i++) {
        uint8_t enc_byte = flag_shard_a[i] ^ flag_shard_b[i];
        uint8_t decrypted = (uint8_t)(enc_byte ^ 0x17);
        printf("%c", decrypted);
    }
    printf("\n");
}

// Obfuscated main function with multiple analysis barriers
int main() {
    char input[256];
    
    // Runtime polymorphism - allocate executable memory for VM
    uint8_t *vm_code = mmap(NULL, 4096, PROT_READ | PROT_WRITE | PROT_EXEC, 
                            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    
    if (vm_code == MAP_FAILED) {
        printf("Memory allocation failed\n");
        return 1;
    }
    
    printf("Advanced Reverse Engineering Challenge\n");
    printf("Enter the secret phrase: ");
    fflush(stdout);
    
    if (!fgets(input, sizeof(input), stdin)) {
        printf("Input error\n");
        munmap(vm_code, 4096);
        return 1;
    }
    
    // Remove newline
    input[strcspn(input, "\n")] = 0;
    
    // Generate runtime-dependent key
    uint32_t runtime_key = generate_runtime_key();
    
    // Generate VM bytecode dynamically
    generate_vm_code(vm_code, input, runtime_key);
    
    // (Removed) Unsafe self-modification that corrupted LOAD instructions
    
    // Initialize VM state
    vm_state_t vm = {0};
    vm.code = vm_code;
    vm.memory = vm_code + 1024;  // Use part of allocated memory
    vm.pc = 0;
    
    // Execute VM program for password verification
    int result = execute_vm(&vm, input);
    
    // Debug: show what VM returned
    // printf("DEBUG: VM returned 0x%02X\n", result);
    
    if (result == 0x42) {
        printf("Congratulations! Here's your flag:\n");
        int flag_len = (int)sizeof(flag_shard_a);
        for (int i = 0; i < flag_len; i++) {
            printf("%c", vm.memory[i]);
        }
        printf("\n");
    } else {
        printf("Access denied. The VM rejects your input.\n");
        
        // Red herring: print some fake analysis info
        printf("Debug: Runtime key was 0x%08X\n", runtime_key ^ 0xFFFFFFFF);
        printf("Debug: VM executed %d instructions\n", vm.pc + 42);
    }
    
    // Cleanup
    munmap(vm_code, 4096);
    return (result == 0x42) ? 0 : 1;
}