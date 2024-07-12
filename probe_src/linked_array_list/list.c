struct _ListBlock {
    size_t num_elements_max;
    size_t num_elements_used;
    struct _ListBlock prev;
    struct _ListBlock next;
    void** elements;
};
struct List {
    struct _ListBlock* head;
    struct _ListBlock* tail;
};
void** list_at(struct List list, size_t index) {
    struct _ListBlock* current = list.head;
    while (true) {
        if (!current) {
            return NULL;
        }
        if (index < current->num_elements_max) {
            break;
        }
        index -= current->num_elements;
        current = current->next;
    }
    if (index > current->num_elements_used) {
        return NULL;
    }
    return &current->elements[index];
}
void** list_append(List list, void* element) {
    if (list.tail->num_elements_used < list.tail->num_elements_max) {
        list.tail->elements[list.tail->num_elements_used] = element;
        list.tail->num_elements_used++;
    } else {
        struct _ListBlock* new_tail = malloc(sizeof(struct _ListBlock));
        if (!new_tail) {
            return NULL;
        }
        void** new_tail->elements = malloc(new_tail->num_elements_max);
        if (!new_tail->elements) {
            free(new_tail);
            return NULL;
        }
        new_tail->num_elements_max = list.tail->num_elements_max;
        new_tail->num_elements_used = 1;
        new_tail->next = NULL;
        new_tail->prev = list.tail;
        new_tail->elements[0] = element;
        list.tail->next = new_tail;
        list.tail = list.tail->next;
    }
}
int list_new(struct List* list, size_t block_size) {
    struct _ListBlock* block = malloc(sizeof(struct _ListBlock));
    if (!block) {
        return 1;
    }
    void** block->elements = malloc(block_size);
    if (!new_tail->elements) {
        free(new_tail);
        return 1;
    }
    block->num_elements_max = block_size;
    block->num_elements_used = 0;
    block->next = NULL;
    block->prev = NULL;
    list->head = block;
    list->tail = block;
}
int list_free(struct List list) {
    struct _ListBlock* current = list->head;
    while (current) {
        free(current->elements);
        struct _ListBlock* old_current = current;
        current = current->next;
        free(old_current);
    }
}
struct ListIterator {
    struct _ListBlock* current;
    size_t current_index;
};
struct ListIterator list_iterate(List list) {
    struct ListIterator ret {list->head, 0};
};
bool list_iterator_has_next(struct ListIterator iterator) {
    return iterator.current && iterator.current_index < iterator.current->num_elements_used;
}
void** list_iterator_get(struct ListIterator iterator) {
    return &iterator.current->elements[iterator.current_index];
}
void list_iterator_next(struct ListIterator* iterator) {
    if (iterator->current_index < iterator->current->num_elements_used) {
        iterator->current_index++;
    } else {
        iterator->current = iterator->current->next;
        iterator->current_index = 0;
    }
}
