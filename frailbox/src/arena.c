#include "arena.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>
#include <errno.h>

#define ALIGN_UP(x, a) (((x) + (a) - 1) & ~((a) - 1))
#define DEFAULT_ALIGNMENT 16

static arena_region_t *region_alloc(size_t size, uint32_t flags) {
    int mmap_flags = MAP_PRIVATE | MAP_ANONYMOUS;
    int mmap_prot = PROT_READ | PROT_WRITE;

    if (flags & ARENA_HUGE_PAGES) {
#ifdef MAP_HUGETLB
        mmap_flags |= MAP_HUGETLB;
#endif
    }

    void *addr = mmap(NULL, size, mmap_prot, mmap_flags, -1, 0);
    if (addr == MAP_FAILED) {
        return NULL;
    }

    arena_region_t *region = malloc(sizeof(arena_region_t));
    if (!region) {
        munmap(addr, size);
        return NULL;
    }

    region->start = addr;
    region->size = size;
    region->used = 0;
    region->flags = flags;
    region->next = NULL;

    return region;
}

arena_t *arena_create(size_t default_region_size, uint32_t flags) {
    arena_t *arena = calloc(1, sizeof(arena_t));
    if (!arena) {
        return NULL;
    }

    if (default_region_size == 0) {
        default_region_size = 1024 * 1024 * 64;
    }

    arena->default_region_size = default_region_size;
    arena->flags = flags;

    arena_region_t *region = region_alloc(default_region_size, flags);
    if (!region) {
        free(arena);
        return NULL;
    }

    arena->regions = region;
    arena->current = region;
    arena->stats.region_count = 1;

    return arena;
}

void arena_destroy(arena_t *arena) {
    if (!arena) return;

    arena_region_t *region = arena->regions;
    while (region) {
        arena_region_t *next = region->next;
        munmap(region->start, region->size);
        free(region);
        region = next;
    }

    memset(&arena->stats, 0, sizeof(arena_stats_t));
    free(arena);
}

void *arena_alloc(arena_t *arena, size_t size) {
    return arena_alloc_aligned(arena, size, DEFAULT_ALIGNMENT);
}

void *arena_alloc_aligned(arena_t *arena, size_t size, size_t alignment) {
    if (!arena || size == 0) return NULL;

    size = ALIGN_UP(size, alignment);

    if (arena->current->used + size > arena->current->size) {
        size_t new_size = (size > arena->default_region_size)
                         ? size : arena->default_region_size;
        if (!arena_new_region(arena, new_size)) {
            return NULL;
        }
    }

    void *ptr = (char *)arena->current->start + arena->current->used;
    arena->current->used += size;

    if (arena->flags & ARENA_ZERO_INIT) {
        memset(ptr, 0, size);
    }

    arena->stats.total_allocated += size;
    arena->stats.current_usage += size;
    arena->stats.allocation_count++;

    if (arena->stats.current_usage > arena->stats.peak_usage) {
        arena->stats.peak_usage = arena->stats.current_usage;
    }

    return ptr;
}

void *arena_calloc(arena_t *arena, size_t nmemb, size_t size) {
    size_t total = nmemb * size;
    void *ptr = arena_alloc(arena, total);
    if (ptr) {
        memset(ptr, 0, total);
    }
    return ptr;
}

void arena_reset(arena_t *arena) {
    if (!arena) return;

    arena_region_t *region = arena->regions;
    while (region) {
        region->used = 0;
        region = region->next;
    }
    arena->current = arena->regions;
    arena->stats.current_usage = 0;
}

arena_region_t *arena_new_region(arena_t *arena, size_t min_size) {
    size_t size = (min_size > arena->default_region_size)
                 ? min_size : arena->default_region_size;

    arena_region_t *region = region_alloc(size, arena->flags);
    if (!region) return NULL;

    arena->current->next = region;
    arena->current = region;
    arena->stats.region_count++;

    return region;
}

int arena_merge_regions(arena_t *arena) {
    (void)arena;
    return 0;
}

int arena_trim(arena_t *arena) {
    (void)arena;
    return 0;
}

arena_stats_t arena_get_stats(const arena_t *arena) {
    return arena->stats;
}

size_t arena_total_capacity(const arena_t *arena) {
    size_t total = 0;
    arena_region_t *region = arena->regions;
    while (region) {
        total += region->size;
        region = region->next;
    }
    return total;
}

int arena_contains(const arena_t *arena, const void *ptr) {
    arena_region_t *region = arena->regions;
    while (region) {
        if ((const char *)ptr >= (const char *)region->start &&
            (const char *)ptr < (const char *)region->start + region->size) {
            return 1;
        }
        region = region->next;
    }
    return 0;
}
