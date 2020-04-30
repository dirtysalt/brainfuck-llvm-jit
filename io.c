#include <stdio.h>

void sys_write(unsigned char c, int rep) {
    for(int i=0;i<rep;i++) {
        putchar(c);
    }
    fflush(stdout);
}

unsigned char sys_read(int rep) {
    unsigned char res = 0;
    for(int i=0;i<rep;i++) {
        res = getchar();
    }
    return res;
}
