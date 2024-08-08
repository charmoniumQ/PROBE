#define level0 8
#define level1 8
#define leveln 48
struct RadixTreeL0 {
    struct RadixTreeL1* level1[level0];
};
struct RadixTreeL1 {
    struct List* levelN[level1];
};
