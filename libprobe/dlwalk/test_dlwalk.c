
#include "include/dlwalk.h"

#include <stdio.h>
#include <fcntl.h>

void print(const char* str) {
	printf("%s\n", str);
}

int main(int argc, char** argv, char**envp) {
	(void)envp;
	if (argc < 2) return -1;

	int fd = open(argv[1], O_RDONLY);

	FileMmap file;
	if (file_mmap_alloc(&file, fd) != 0) return -1;;

	extract_dynlibs(&file, print);

	file_mmap_free(&file);
}
