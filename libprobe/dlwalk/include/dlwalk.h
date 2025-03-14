
// FIXME: REMOVE ME AFTER WRITING CODE
#ifndef DLWALK_USE_UNWRAPPED_LIBC
#define DLWALK_USE_UNWRAPPED_LIBC
#endif
#ifndef DLWALK_DEBUG
#define DLWALK_DEBUG
#endif
#ifndef DLWALK_STRICT
#define DLWALK_STRICT
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <sys/mman.h>
#include <sys/stat.h>

#include <elf.h>

// OWNED and BORROWED's meaning are defined in libprobe/src/util.c
#ifndef OWNED
#define OWNED
#endif
#ifndef BORROWED
#define BORROWED
#endif

#ifdef DLWALK_DEBUG
#define DLWALK_PERROR
#endif

#ifdef DLWALK_USE_UNWRAPPED_LIBC
#define unwrapped_mmap mmap
#define unwrapped_munmap munmap
#define unwrapped_fstat fstat
#endif

#ifdef DLWALK_PERROR
// ERRors ON expr == true, WITH a (p)error of desc
#define ERR_ON_WITH(expr, desc) \
    if (expr) { \
        fprintf(stderr, "%s\n", desc); \
        return -1; \
    }
#define PERR_ON_WITH(expr, desc) \
    if (expr) { \
        perror(desc); \
        return -1; \
    }
#define ERROR(x) fprintf(stderr, "%s\n", x)
#define PERROR(x) perror(x)
#else
#define ERR_ON_WITH(expr, desc) \
    if (expr) { \
        return -1; \
    }
#define PERR_ON_WITH(expr, desc) ERERR_ON_WITH(expr, desc)
#define ERROR(x) (void)(x)
#define PERROR(x) (void)(x)
#endif

typedef void (*dl_callback_t)(const char*);

typedef struct {
    void* data;
    size_t size;
} FileMmap;

static inline int file_mmap_alloc(BORROWED FileMmap* self, int fd) {
    struct stat statbuf;
    PERR_ON_WITH(unwrapped_fstat(fd, &statbuf) != 0, "file_mmap_alloc: fstat");

    void* mapping = unwrapped_mmap(NULL, statbuf.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    PERR_ON_WITH(mapping == MAP_FAILED, "file_mmap_alloc: mmap");

    self->data = (uint8_t*)mapping;
    self->size = statbuf.st_size;

    return 0;
}

static inline int file_mmap_free(OWNED const FileMmap* self) {
    PERR_ON_WITH(unwrapped_munmap(self->data, self->size) != 0, "file_mmap_free: munmap");
    return 0;
}

static inline int validate_elf(const unsigned char* elf) {
    ERR_ON_WITH(
        elf[EI_MAG0] != ELFMAG0 ||
        elf[EI_MAG1] != ELFMAG1 ||
        elf[EI_MAG2] != ELFMAG2 ||
        elf[EI_MAG3] != ELFMAG3,
        "validate_elf: invalid ELF magic bytes"
    );
    ERR_ON_WITH(elf[EI_VERSION] != EV_CURRENT, "validate_elf: unknown elf version");
    ERR_ON_WITH(
        !((elf[EI_OSABI] == ELFOSABI_NONE) || (elf[EI_OSABI] == ELFOSABI_LINUX)),
        "validate_elf: not a Linux ELF file"
    );
    ERR_ON_WITH(elf[EI_ABIVERSION] != 0, "validate_elf: unknown ABI version");

    return 0;
}

static int extract_dynlibs64(BORROWED const FileMmap* elf, dl_callback_t callback) {
    const uintptr_t base = (uintptr_t)elf->data;
    const Elf64_Ehdr* elf_header = (Elf64_Ehdr*)elf->data;

    ERR_ON_WITH(
        elf_header->e_shoff == 0,
        "extract_dynlibs64: ELF file contains no section header tab"
    );
    const Elf64_Shdr* section_tab = (Elf64_Shdr*)(base + elf_header->e_shoff);

    size_t section_tab_length = elf_header->e_shnum;
    if (section_tab_length == 0) {
        section_tab_length = section_tab[0].sh_size;
    }

    // NOTE: this extracts the section string table (used for finding the names
    // of sections) but seems to be un-needed for the information we need
    //
    // uint16_t sect_tab_str_idx = elf_header->e_shstrndx;
    // ERR_ON_WITH(
    //     sect_tab_str_idx == SHN_UNDEF,
    //     "extract_dynlibs64: ELF file contains no section string tab"
    // );
    // if (sect_tab_str_idx == SHN_XINDEX) {
    //     sect_tab_str_idx = section_tab[0].sh_link;
    // }
    // const char* strings = (const char*)(base + section_tab[sect_tab_str_idx].sh_offset);

    const Elf64_Shdr* dynamic = NULL;
    const Elf64_Shdr* interp = NULL;
    for (size_t i = 0; i < section_tab_length; ++i) {
        const Elf64_Shdr* curr = section_tab + i;
        if (curr->sh_type == SHT_DYNAMIC) {
            dynamic = curr;
        }
    }

    // FIXME: this is not an error, but actually our base case of a ELF file
    // with no dynamic dependencies, but we should also validate that it then
    // has no .interp section
    ERR_ON_WITH(dynamic == NULL, "extract_dynlibs64: unable to find '.dynamic' section");

    // this is the list of fixed size entries in the .dynamic section
    const Elf64_Dyn* dyn_list = (const Elf64_Dyn*)(base + dynamic->sh_offset);

    const char* dynstr = NULL;

    for (size_t i = 0; dyn_list[i].d_tag != DT_NULL; ++i) {
        const Elf64_Dyn* curr = dyn_list + i;

        if (curr->d_tag == DT_STRTAB) {
            bool found = false;

            for (size_t i = 0; i < section_tab_length; ++i) {
                const Elf64_Shdr* curr_section = section_tab + i;

                bool is_section;
                #ifdef DLWALK_STRICT 
                    is_section = curr_section->sh_addr == curr->d_un.d_ptr;
                #else
                    is_section = (curr_section->sh_addr <= curr->d_un.d_ptr) && 
                    curr_section->sh_addr + curr_section->sh_size < curr->d_un.d_ptr;
                #endif

                if (is_section) {
                    dynstr = (const char*)(base + curr_section->sh_offset);
                    found = true;
                    break;
                }
            }
            ERR_ON_WITH(!found, "extract_dynlibs64: found DT_STRTAB, but couldn't find valid section");

            break;
        }
    }
    ERR_ON_WITH(dynstr == NULL, "extract_dynlibs64: unable to find DT_STRTAB dynamic entry");

    for (size_t i = 0; dyn_list[i].d_tag != DT_NULL; ++i) {
        const Elf64_Dyn* curr = dyn_list + i;
        switch (curr->d_tag) {
            case DT_NEEDED:
                printf("DT_NEEDED: %s\n", (dynstr + curr->d_un.d_val));
            break;
            case DT_RPATH:
                printf("DT_RPATH: %s\n", (dynstr + curr->d_un.d_val));
            break;
            case DT_RUNPATH:
                printf("DT_RUNPATH: %s\n", (dynstr + curr->d_un.d_val));
            break;
            case DT_AUDIT:
                printf("DT_AUDIT: %s\n", (dynstr + curr->d_un.d_val));
            break;
            case DT_DEPAUDIT:
                printf("DT_DEPAUDIT: %s\n", (dynstr + curr->d_un.d_val));
            break;
            default:
            break;
        }
    }

    return 0;
}

static int extract_dynlibs32(BORROWED const FileMmap* elf, dl_callback_t callback) {
    (void)elf;
    (void)callback;
    return -1; 
}

static int extract_dynlibs(BORROWED const FileMmap* elf, dl_callback_t callback) {
    #ifdef DLWALK_DEBUG
        if (elf == NULL) {
            ERROR("extract_dynlibs: null FileMmap pointer");
            return -1;
        }
        if (elf->data == NULL) {
            ERROR("extract_dynlibs: null data pointer");
            return -1;
        }
    #endif

    if (elf->size < EI_NIDENT) {
        ERROR("extract_dynlibs: size too small for elf ident table");
    }
    if (validate_elf((unsigned char*)elf->data) != 0) return -1;

    // WARN: we do implicitly assume that the ELF file is valid if
    // validate_elf() returns 0, this means we could theoretically segfault if
    // an invalid file intentionally or accidentally passes the validation and
    // we assume that any offsets we find ELF or section headers are valid

    unsigned char elf_class = ((unsigned char*)elf->data)[EI_CLASS];
    if (elf_class == ELFCLASS64) return extract_dynlibs64(elf, callback);
    else if (elf_class == ELFCLASS32) return extract_dynlibs32(elf, callback);
    else {
        ERROR("extrac_dynlibs: unknown ELF class");
        return -1;
    }
}
