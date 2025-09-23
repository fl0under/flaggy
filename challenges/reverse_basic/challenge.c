#include <stdio.h>
#include <string.h>
#include <stdlib.h>

int check_password(char* input) {
    char expected[] = {'s', 'e', 'c', 'r', 'e', 't', '_', 'p', 'a', 's', 's', '\0'};
    
    if (strlen(input) != 11) {
        return 0;
    }
    
    for (int i = 0; i < 11; i++) {
        if (input[i] != expected[i]) {
            return 0;
        }
    }
    return 1;
}

void decrypt_flag() {
    // Simple XOR encryption
    char encrypted_flag[] = {0x32, 0x2b, 0x21, 0x2d, 0x01, 0x16, 0x04, 0x39, 
                           0x30, 0x71, 0x34, 0x71, 0x30, 0x31, 0x71, 0x1d, 
                           0x71, 0x2c, 0x25, 0x73, 0x2c, 0x71, 0x71, 0x30, 
                           0x73, 0x2c, 0x25, 0x3f, 0x00};
    char key = 0x42;
    
    printf("Flag: ");
    for (int i = 0; encrypted_flag[i] != 0; i++) {
        printf("%c", encrypted_flag[i] ^ key);
    }
    printf("\n");
}

int main() {
    char input[100];
    
    printf("Welcome to the basic reverse engineering challenge!\n");
    printf("Enter the secret password to get the flag: ");
    fflush(stdout);
    
    fgets(input, sizeof(input), stdin);
    
    // Remove newline
    input[strcspn(input, "\n")] = 0;
    
    if (check_password(input)) {
        printf("Correct password!\n");
        decrypt_flag();
    } else {
        printf("Wrong password! Try analyzing the binary.\n");
    }
    
    return 0;
}