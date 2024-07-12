/*
** 8 bytes per pointer * (2**8 + 2**8 + 2) pointers per integer * 3 integers per table * 4 tables
** 8 * (2**8 + 2**8 + 2) * 3 * 4 / 1024 == 49 (KiB)
*/

#define level0 8
#define level1 8
#define leveln 48
struct RadixTreeL0 {
    struct RadixTreeL1* level1[level0];
};
struct RadixTreeL1 {
    struct List* levelN[level1];
};
