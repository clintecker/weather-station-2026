# Host fuzzing of the node's input parsers (README.md in this directory).
#   make            standalone drivers with AddressSanitizer + UndefinedBehaviorSanitizer (any cc)
#   make check      run each standalone driver over its corpus plus RUNS mutated inputs
#   make libfuzzer  coverage-guided builds; needs clang with libFuzzer (Linux clang, Homebrew llvm;
#                   not Apple clang), then e.g. build/libfuzzer-reply corpus/reply -max_total_time=60
ROOT     = ../..
MBEDTLS  = $(ROOT)/vendor/STM32CubeWL/Middlewares/Third_Party/mbed-crypto
CC      ?= cc
CLANG   ?= clang
RUNS    ?= 200000
SEED    ?= 1
TARGETS  = reply provision console obs wsmp
SAN      = -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer
CFLAGS   = -std=c11 -g -O1 -Wall -Wextra -Werror -I. -I$(ROOT)/firmware -I$(ROOT)/firmware/common \
           -I$(MBEDTLS)/include -DMBEDTLS_CONFIG_FILE='"ws_mbedtls_config.h"'
CRYPTO   = $(ROOT)/firmware/common/ws_frame.c \
           $(addprefix $(MBEDTLS)/library/,aes.c ccm.c block_cipher.c platform_util.c constant_time.c)
SRC_reply     = fuzz_reply.c $(CRYPTO)
SRC_provision = fuzz_provision.c $(ROOT)/firmware/stage0.c
SRC_console   = fuzz_console.c $(ROOT)/firmware/common/ws_console.c $(ROOT)/firmware/stage0.c
SRC_obs       = fuzz_obs.c $(ROOT)/firmware/common/ws_obs.c
SRC_wsmp      = fuzz_wsmp.c $(ROOT)/firmware/common/wsmp.c

all: $(addprefix build/standalone-,$(TARGETS))

# Every source a target compiles is a prerequisite, so editing the firmware code under test
# rebuilds the target (without this, tests/test_fuzz.py could fuzz a stale binary).
.SECONDEXPANSION:
build/standalone-%: standalone.c fuzz.h $$(SRC_$$*) $$(wildcard $(ROOT)/firmware/common/*.h $(ROOT)/firmware/*.h)
	@mkdir -p build
	$(CC) $(CFLAGS) $(SAN) standalone.c $(SRC_$*) -o $@

build/libfuzzer-%: fuzz.h $$(SRC_$$*) $$(wildcard $(ROOT)/firmware/common/*.h $(ROOT)/firmware/*.h)
	@mkdir -p build
	$(CLANG) $(CFLAGS) -fsanitize=fuzzer,address,undefined -fno-sanitize-recover=all $(SRC_$*) -o $@

libfuzzer: $(addprefix build/libfuzzer-,$(TARGETS))

check: all
	@for t in $(TARGETS); do echo "fuzz $$t"; build/standalone-$$t corpus/$$t/* -runs=$(RUNS) -seed=$(SEED) || exit 1; done

clean:
	rm -rf build

.PHONY: all check libfuzzer clean
