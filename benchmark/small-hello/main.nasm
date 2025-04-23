[bits 64]
file_load_va: equ 4096 * 40

db 0x7f, 'E', 'L', 'F'
db 2
db 1
db 1
db 0
entry_point:
  xor eax, eax
  inc eax
  mov edi, eax
  jmp code_chunk_2
dw 2
dw 0x3e
dd 1
dq entry_point + file_load_va
dq program_headers_start
code_chunk_2:
  mov esi, file_load_va + message
  xor edx, edx
  mov dl, message_length
  jmp code_chunk_3
db 0
dw 64
dw 0x38
dw 1
; We simply deleted the three two-byte fields that used to be here. The only
; one that mattered, the number of section headers, will still be zero due to
; the upper two bytes of the field at the start of the program header being
; zero.

program_headers_start:
; These next two fields also serve as the final six bytes of the ELF header.
dd 1
dd 5
dq 0
dq file_load_va
code_chunk_3:
  syscall
  mov al, 60
  xor edi, edi
  syscall
dq file_end
dq file_end

message: db `Hello, world!\n`
message_length: equ $ - message

file_end:
