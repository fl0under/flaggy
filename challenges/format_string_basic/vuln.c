#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int target = 0x12345678;
char flag[] = "picoCTF{f0rmat_str1ng_le4k_4nd_0verwr1te}";

void check_target() {
    if (target == 0xdeadbeef) {
        printf("Target modified successfully!\n");
        printf("Flag: %s\n", flag);
        exit(0);
    }
}

int main() {
    char buffer[100];
    
    printf("Welcome to the format string challenge!\n");
    printf("Target variable is at: %p\n", &target);
    printf("Target value: 0x%08x\n", target);
    printf("You need to change it to 0xdeadbeef\n\n");
    
    printf("Enter your format string: ");
    fflush(stdout);
    
    fgets(buffer, sizeof(buffer), stdin);
    
    // Vulnerable format string
    printf("Your input: ");
    printf(buffer);  // No format string - vulnerable!
    
    check_target();
    
    printf("Target is still: 0x%08x\n", target);
    printf("Try again!\n");
    
    return 0;
}