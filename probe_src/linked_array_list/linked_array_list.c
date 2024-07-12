#define linked_list_array(name, Type, block_size) \
    #define _NameListBlock _combine3(_, Name, ListbLock) \
    #define NameList _combine2(Name, List) \
    #define name_at combine2(name, _at) \
    #include "linked_array_list_internal.c" \
    #undefine _NameListBlock \
    #undefine NameList \
    #undefine name_at
