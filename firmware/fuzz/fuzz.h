#ifndef FUZZ_H
#define FUZZ_H
/* Host fuzz targets for the code that parses input from outside the node: radio replies, the
 * provisioning command and console lines. Each target is a libFuzzer entry point; standalone.c
 * drives the same entry point without libFuzzer (Apple clang does not ship it). README.md here. */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size);
/* A broken property is a bug: report it and abort, so both drivers keep the input. */
#define FUZZ_CHECK(cond) do { if (!(cond)) { fprintf(stderr, "property failed: %s (%s:%d)\n", #cond, __FILE__, __LINE__); abort(); } } while (0)
#endif
