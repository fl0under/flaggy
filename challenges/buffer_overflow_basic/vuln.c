#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void win() {
    printf("Congratulations! You've successfully exploited the buffer overflow!\n");
    printf("picoCTF{buffer_0verfl0w_basic_w1n_func}\n");
    exit(0);
}

void vuln() {
    char buffer[32];
    printf("Enter your input: ");
    fflush(stdout);
    gets(buffer);  // Vulnerable function - no bounds checking!
    printf("You entered: %s\n", buffer);
}

int main() {
    printf("Welcome to the basic buffer overflow challenge!\n");
    printf("Can you redirect execution to the win function?\n");
    vuln();
    printf("Normal program execution completed.\n");
    return 0;
}