// FIXME: REMOVE ME AFTER WRITING CODE
#ifndef DLWALK_USE_UNWRAPPED_LIBC
#define unwrapped_openat openat
#define unwrapped_access access
#define unwrapped_mmap mmap
#define unwrapped_munmap munmap
#define unwrapped_fstat fstat
#define unwrapped_fstat fstat
#include <fcntl.h>
#include <unistd.h>
#endif

#include <elf.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>

#ifdef DLWALK_DEBUG
#define DLWALK_PERROR
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

struct FileMmap {
    void* _Nonnull data;
    uint32_t size;
};

int file_mmap_alloc(struct FileMmap* _Nonnull self, int fd) {
    struct stat statbuf;
    PERR_ON_WITH(unwrapped_fstat(fd, &statbuf) != 0, "file_mmap_alloc: fstat");

    void* mapping = unwrapped_mmap(NULL, statbuf.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
    PERR_ON_WITH(mapping == MAP_FAILED, "file_mmap_alloc: mmap");

    self->data = (uint8_t*)mapping;
    self->size = statbuf.st_size;

    return 0;
}

int file_mmap_free(const struct FileMmap self) {
    PERR_ON_WITH(unwrapped_munmap(self.data, self.size) != 0, "file_mmap_free: munmap");
    return 0;
}

struct String {
    const char* _Nonnull data;
    uint16_t size;
};

struct String from_null_terminated(char* _Nonnull null_terminated, size_t max_len) {
  return (struct String){
    .data = null_terminated,
    .size = strnlen(null_terminated, max_len),
  };
}

struct String string_copy(struct String input) {
    return (struct String) {
      .data = strndup(input.data, input.size + 1),
      .size = input.size,
    };
}

struct StringArray {
    const struct String* data;
    uint16_t size;
};

void string_array_empty(struct StringArray* self) {
  self->data = NULL;
  self->size = 0;
}

int string_array_concat(struct StringArray sa1, struct StringArray sa2, struct StringArray* output) {
  output->size = sa1.size + sa2.size;
  output->data = malloc(output->size);
  if (output->data) {
    memcpy()
    output->data
    return 0;
  }
}

void string_array_free_array_not_underlying_strings(struct StringArray* _Nonnull self) {
  free((void*)self->data);
  self->size = 0;
}

int string_array_from_colon_terminated(const char* _Nonnull null_terminated, struct StringArray* _Nonnull ret) {
    size_t count = 1;
    size_t len = 0;

    while (null_terminated[len] != '\0') {
        if (null_terminated[len] == ':')
            ++count;
        ++len;
    }

    ret->size = count;
    ret->data = malloc(count * sizeof(struct String));
    ERR_ON_WITH(ret->data == NULL, "Allocation failed");

    size_t start = 0;
    size_t n = 0;

    for (size_t i = 0; i <= len; ++i) {
        if (i == len || null_terminated[i] == ':') {
            ret->data[n++] = (struct String) {
                .data = null_terminated + start,
                .size = i - start,
            };
            start = i + 1;
        }
    }

    return 0;
}

struct HashTable;
int hash_table_set(struct HashTable* table, struct String key);

struct String allocate_string_join(struct String prefix, struct String suffix) {
  struct String ret;
  ret.data = malloc(prefix.size + 1 + suffix.size + 1);
  if (!ret.data) {
    ret.data = NULL;
    ret.size = 0;
  }
  memcpy((void*)ret.data, prefix.data, prefix.size);
  ((char*)ret.data)[prefix.size] = '/';
  memcpy((void*)&ret.data[prefix.size + 1], suffix.data, suffix.size);
  ret.size = prefix.size + 1 + suffix.size;
  ((char*)ret.data)[prefix.size + 1 + suffix.size] = '\0';
  return ret;
}

ssize_t search_path(const struct String library, const struct StringArray search_path) {
  char path_candidate[PATH_MAX];
  ssize_t search_path_len = (ssize_t)search_path.size;
  for (ssize_t i = 0; i < search_path_len; ++i) {
    memcpy(path_candidate, search_path.data[i].data, search_path.data[i].size);
    path_candidate[search_path.data[i].size] = '/';
    memcpy(&path_candidate[search_path.data[i].size + 1], library.data, library.size);
    path_candidate[search_path.data[i].size + 1 + library.size] = '\0';
    if (unwrapped_access(path_candidate, R_OK)) {
      return i;
    }
  }
  return -1;
}
int validate_elf(struct FileMmap elf_mmap) {
  const char* elf = (const char*)elf_mmap.data;
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

struct DynLibInfo {
  struct StringArray runpath;
  struct StringArray rpath;
};

int resolve_library(struct String library, String elf_path,
                    struct StringArray rpath, struct StringArray runpath,
                    struct StringArray ld_library_path,
                    struct HashTable* _Nonnull loaded
                   );

int extract_dynlibs64(struct String elf_path, struct FileMmap elf_contents, struct StringArray parent_rpath,
                      struct StringArray ld_library_path,
                      struct HashTable* _Nonnull loaded)

    {
    void* base = (char*)elf_contents.data;
    const Elf64_Ehdr* elf_header = (Elf64_Ehdr*)elf_contents.data;

    ERR_ON_WITH(
        elf_header->e_shoff == 0,
        "extract_dynlibs64: ELF file contains no section header tab"
    );
    const Elf64_Shdr* section_headers = (Elf64_Shdr*)(base + elf_header->e_shoff);

    // "the number of entries in the section header table."
    // "If a file has no section header table, e_shnum holds the value of zero."
    size_t n_sections = elf_header->e_shnum;

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

    const Elf64_Shdr* dynamic_section_header = NULL;
    const Elf64_Shdr* interp = NULL;
    for (const Elf64_Shdr* section_header = &section_headers[0];
       section_header < &section_headers[n_sections]; ++section_header) {
        if (section_header->sh_type == SHT_DYNAMIC) {
            dynamic_section_header = section_header;
            break;
        }
    }

    // FIXME: this is not an error, but actually our base case of a ELF file
    // with no dynamic dependencies, but we should also validate that it then
    // has no .interp section
    ERR_ON_WITH(dynamic_section_header == NULL, "extract_dynlibs64: unable to find '.dynamic' section");

    // this is the list of fixed size entries in the .dynamic section
    const Elf64_Dyn* dynamic_entries = (const Elf64_Dyn*)(base + dynamic_section_header->sh_offset);

    size_t strtab_virtual_address = 0;
    size_t strtab_size = 0;
    const size_t NOT_SET = 0xFFFFFFFF;
    size_t rpath_offset_in_strtab = NOT_SET;
    size_t runpath_offset_in_strtab = NOT_SET;
    size_t n_needed_libraries = 0;
    for (const Elf64_Dyn* dynamic_entry = &dynamic_entries[0]; dynamic_entry->d_tag != DT_NULL;
         ++dynamic_entry) {
        switch (dynamic_entry->d_tag) {
            case DT_STRTAB:
                strtab_virtual_address = dynamic_entry->d_un.d_ptr;
                break;
            case DT_STRSZ:
                strtab_size = dynamic_entry->d_un.d_val;
                break;
            case DT_RPATH:
                rpath_offset_in_strtab = dynamic_entry->d_un.d_val;
                break;
            case DT_RUNPATH:
                runpath_offset_in_strtab = dynamic_entry->d_un.d_val;
                break;
            case DT_NEEDED:
              ++n_needed_libraries;
              break;
        }
    }

    ERR_ON_WITH(strtab_virtual_address == 0, "DT_STRTAB entry not found");
    ERR_ON_WITH(strtab_size == 0, "DT_STRSZ entry not found");

    const Elf64_Shdr* dynamic_strings_section_header = NULL;
    for (const Elf64_Shdr* section_header = &section_headers[0];
       section_header < &section_headers[n_sections]; ++section_header) {
      if (section_header->sh_addr <= strtab_virtual_address &&
          strtab_virtual_address < section_header->sh_addr + section_header->sh_size) {
            dynamic_strings_section_header = section_header;
            break;
        }
    }

    ERR_ON_WITH(!dynamic_strings_section_header, "Referrent of DT_STRTAB not found");

    if (strtab_virtual_address + strtab_size >
        dynamic_strings_section_header->sh_addr + dynamic_strings_section_header->sh_size) {
        ERROR("Dynamic strings table is not within one section; I thought this was unlikely to show up in practice, so I did not implement it.");
    }

    const char* dynamic_strings_section = (const char*)(base + dynamic_strings_section_header->sh_offset + strtab_virtual_address - dynamic_strings_section_header->sh_addr);

    struct StringArray rpath;
    if (rpath_offset_in_strtab != NOT_SET) {
      struct StringArray child_rpath;
        ERR_ON_WITH(from_colon_terminated(&dynamic_strings_section[rpath_offset_in_strtab], &child_rpath),
                    "failed to allocate");
        rpath = concat_lists(child_rpath, parent_rpath);
    }
    struct StringArray runpath;
    if (runpath_offset_in_strtab != NOT_SET) {
        ERR_ON_WITH(from_colon_terminated(&dynamic_strings_section[runpath_offset_in_strtab],
                                          &runpath),
                    "failed to allocate");
    }

    for (const Elf64_Dyn* dynamic_entry = &dynamic_entries[0]; dynamic_entry->d_tag != DT_NULL;
                                                               ++dynamic_entry) {
      if (dynamic_entry->d_tag == DT_NEEDED) {
        const char* needed_library = &dynamic_strings_section[dynamic_entry->d_un.d_val];
        struct String library = from_null_terminated((char*)needed_library, PATH_MAX);
        ERR_ON_WITH(resolve_library(library, elf_path, rpath, runpath, ld_library_path, loaded), "failed to resolve");
      }
    }
    return 0;
}

int extract_dynlibs_from_elf(struct String elf, struct DynLibInfo* _Nonnull info);

int resolve_library(struct String library, struct String elf_path,
                    struct StringArray rpath, struct StringArray runpath,
                    struct StringArray ld_library_path,
                    struct HashTable* _Nonnull loaded
                   ) {
    for (size_t i = 0; i < library.size; ++i) {
      if (library.data[i] == '/') {
          if (library.data[0] == '/') {
            if (!unwrapped_access(&library.data[0], R_OK)) {
              hash_table_set(loaded, string_copy(library.data));
              extract_dynlibs_from_elf(library, info);
              return 0;
            } else {
              return 1;
            }
          } else {
            size_t last_slash = i;
            for (size_t j = i + 1; j < library.size; ++j) {
                if (library.data[j] == '/') {
                  last_slash = j;
                }
            }
            struct String elf_dir = {.data = elf_path.data, .size = last_slash};
            struct String library = allocate_string_join(elf_dir, library);
            if (!unwraped_access(library.data, R_OK)) {
              hash_table_set(loaded, library);
              extract_dynlibs_from_elf(library, info);
              return 0;
            } else {
              return 1;
            }
          }
        }
    }
    if (rpath.size && !runpath.size) {
      ssize_t index = search_path(library, rpath);
      if (index != -1) {
        struct String library = allocate_string_join(rpath.data[index], library);
        hash_table_set(loaded, library);
        extract_dynlibs_from_elf(library, info);
        return 0;
      }
    }
    if (ld_library_path.size) {
      ssize_t index = search_path(library, ld_library_path);
      if (index != -1) {
        struct String library = allocate_string_join(ld_library_path.data[index], library);
        hash_table_set(loaded, library);
        extract_dynlibs_from_elf(library, info);
        return 0;
      }
    }
    if (runpath.size) {
      ssize_t index = search_path(library, runpath);
      if (index != -1) {
        struct String library = allocate_string_join(runpath.data[index], library);
        hash_table_set(loaded, library);
        extract_dynlibs_from_elf(library, info);
        return 0;
      }
    }
    // Other search paths not configured: ldconfig --print-cache, /lib, /lib64
    return 2;
}

static int extract_dynlibs32(struct FileMmap elf, struct DynLibInfo* _Nonnull info) {
    (void)elf;
    (void)info;
    return -1;
}

int extract_dynlibs_from_elf(struct String elf, struct DynLibInfo* _Nonnull info) {
  int fd = unwrapped_openat(AT_FDCWD, elf.data, O_RDONLY);
  ERR_ON_WITH(fd <= 0, "Unable to open file");
  struct FileMmap file;
  file_mmap_alloc(&file, fd);
  ERR_ON_WITH(!validate_elf(file), "Not actually ELF");

    // WARN: we do implicitly assume that the ELF file is valid if
    // validate_elf() returns 0, this means we could theoretically segfault if
    // an invalid file intentionally or accidentally passes the validation and
    // we assume that any offsets we find ELF or section headers are valid

    unsigned char elf_class = ((unsigned char*)file.data)[EI_CLASS];
    if (elf_class == ELFCLASS64) {
      extract_dynlibs64(file, info);
    } else if (elf_class == ELFCLASS32) {
      extract_dynlibs32(file, info);
    } else {
        ERROR("extrac_dynlibs: unknown ELF class");
        return -1;
    }
  file_mmap_free(file);
}
