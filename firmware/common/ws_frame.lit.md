# ws_frame: the radio frame format

`ws_frame.c` seals and opens the frames that the transmitting node (the TX node) exchanges with the
gateway over LoRa. The frames use AES-128 in CCM mode (counter with CBC-MAC). The file builds the
8-byte clear header, the 13-byte CCM nonce and the 8-byte tag. It also opens ACK and NACK replies,
packs the health report and computes the key check value. The gateway builds the same bytes in
`ws0/protocol.py`. `docs/protocol-design.md` sections 3 and 4 define the format.

This document is the source. `tools/tangle.py` generates `ws_frame.c` from the code chunks below.
The repository also holds the generated file, so the build, the static analysers, the fuzzer and the
host tests read ordinary C. Edit this file, then regenerate and check:

```sh
python3 tools/tangle.py firmware/common/ws_frame.lit.md                            # write ws_frame.c
python3 tools/tangle.py --check firmware/common/ws_frame.lit.md                    # committed .c == tangle
python3 tools/tangle.py --weave /tmp/ws_frame.html firmware/common/ws_frame.lit.md # render
```

A chunk is a fenced ` ```c {#name} ` block. A line `<<name>>` inside a chunk includes chunk
`name`. Chunks appear in reading order. The root chunk (section 8) puts them in C order.

## 1. Guarantees

| Property | Guarantee | Checked by |
|---|---|---|
| Range | the code refuses a station, counter, kind or length that its field cannot hold. It never truncates | `test_counter_and_station_limits`, `fuzz_reply`, `obs_ok` in `App/selftest.c` |
| Refusal | every refusal after the `out` check leaves all `out_cap` bytes of `out` zero | `test_counter_and_station_limits`, `fuzz_reply` |
| Agreement | a sealed frame equals `ws0/protocol.py` `seal()` and the design document's construction byte for byte | `test_known_answer_vectors`, `test_vectors_follow_the_spec`, `test_random_agreement_both_directions` |
| Opening | only an authentic 33-byte ACK or NACK for the caller's station opens. The function writes the outputs only then | `test_reply_rejections`, `fuzz_reply`, `reply_ok` in `App/selftest.c` |
| Health report | `ws_diag_pack` writes exactly the bytes of `ws0/protocol.py` `DIAG` | `test_diag_plaintext_matches_python`, `test_diagnostic_frame_agreement` |
| Key check value | the first 3 bytes of AES-128-ECB(key, zero block). ECB is the electronic codebook mode | `test_key_check_value` |

The tests named here are in `tests/test_frame.py` unless the table names another file.

## 2. Frame layout

Every frame is a clear header, a ciphertext and a tag. Every integer is big-endian. The header is
8 bytes (`WS_HEADER_LEN`). CCM also authenticates the header as the additional authenticated data
(AAD). The ciphertext of n bytes and the 8-byte tag (`WS_TAG_LEN`) follow the header. The diagram
shows the header bits, most significant bit first:

```mermaid
packet-beta
0-3: "version (5)"
4-7: "kind"
8-23: "station (u16)"
24-63: "counter (u40)"
```

| Offset | Bytes | Field | Constant (`ws_frame.h`) |
|---:|---:|---|---|
| 0 | 1 | version 5 in bits 7–4, kind in bits 3–0 | `WS_FRAME_BYTE0(kind)` |
| 1 | 2 | station, 1–65535 | `WS_STATION_BYTES`, `WS_STATION_MAX` |
| 3 | 5 | transmission counter, 1 to 2^40 − 1 | `WS_COUNTER_OFF`, `WS_COUNTER_BYTES`, `WS_COUNTER_MAX` |
| 8 | n | CCM ciphertext of the kind's plaintext | |
| 8 + n | 8 | CCM tag, M = 8 | `WS_TAG_LEN` |

| Kind | Value | Direction | Plaintext | Frame |
|---|---:|---|---|---:|
| `WS_KIND_OBS` | 1 | node to gateway | observation (`ws_obs.c`) | 16 + n |
| `WS_KIND_ACK` | 2 | gateway to node | reply, 17 B (section 5) | 33 |
| `WS_KIND_NACK` | 3 | gateway to node | reply, 17 B (section 5) | 33 |
| `WS_KIND_DIAG` | 4 | node to gateway | health report, 32 B (section 7) | 48 |

A frame is at most `WS_FRAME_MAX` (255) bytes, one LoRa payload. The header and tag take
`WS_FRAME_OVERHEAD` (16), which leaves at most 239 plaintext bytes.

The file's own constants size the key, the AES block and the nonce:

```c {#constants}
#define KEY_BITS (WS_KEY_LEN * CHAR_BIT)
#define AES_BLOCK_LEN 16
/* CCM nonce: kind u8, station u32, counter u64. */
#define NONCE_STATION_BYTES 4
#define NONCE_COUNTER_BYTES 8
#define NONCE_LEN (1 + NONCE_STATION_BYTES + NONCE_COUNTER_BYTES)
_Static_assert(NONCE_LEN == 13, "CCM with a 2-byte length field takes a 13-byte nonce (15 - L)");
```

A CCM nonce of 13 bytes leaves 2 bytes for the CCM message-length field (15 − 13). Two bytes count
up to 65535 plaintext bytes, more than a 255-byte frame needs.

## 3. Header, nonce and AAD

### Layout

`header` writes the 8 header bytes (section 2) and the 13 nonce bytes from the same three integers.
The nonce bits, most significant bit first:

```mermaid
packet-beta
0-7: "kind (u8)"
8-39: "station (u32)"
40-103: "counter (u64)"
```

The nonce holds the kind as a whole byte, without the version. It widens the station to 4 bytes
and the counter to 8 bytes with leading zeros. `ws0/protocol.py` builds the same nonce with
`NONCE.pack(kind, station, counter)`.

The AAD is the 8 header bytes. CCM authenticates them in the clear, so a changed version, kind,
station or counter fails the tag.

### Why the nonce is built from the integers

The nonce is a function of (kind, station, counter) only. `header` never copies header bytes into
it, for two reasons:

- The nonce does not depend on how the header packs its fields. A change to the header widths
  cannot change which triples give which nonces.
- `header` writes each integer into a field that holds it. The 5-byte header field would truncate a
  counter of 2^40 or more. `seal_ok` refuses such a counter before `header` runs (section 4). On
  the reply path the counter comes from 5 frame bytes, so it always fits.

```c {#header}
/* Writes the header (also the AAD) and the nonce. The nonce comes from the integers, not from
 * the header bytes. The callers refuse a counter that the 5-byte field cannot hold. The nonce
 * must not depend on how the header packs the fields. */
static void header(uint8_t h[WS_HEADER_LEN], uint8_t nonce[NONCE_LEN], uint8_t kind, uint32_t station, uint64_t counter) {
 uint8_t *p = ws_write_u8(h, WS_FRAME_BYTE0(kind));
 p = ws_write_be(p, station, WS_STATION_BYTES);
 (void)ws_write_be(p, counter, WS_COUNTER_BYTES);
 p = ws_write_u8(nonce, kind);
 p = ws_write_be(p, station, NONCE_STATION_BYTES);
 (void)ws_write_be(p, counter, NONCE_COUNTER_BYTES);
}
```

The cursor writers (`ws_be.h`) return the position after each field, so the layout is the order of
the calls.

### Nonce uniqueness

Under one key, the code must seal each (kind, station, counter) triple at most once. `ws_seal_kind`
keeps no state. It trusts the caller for uniqueness and checks only the range.

| Side | Kinds | Counter source | Durable before use |
|---|---|---|---|
| Node | OBS, DIAG | `store_next_counter` (`App/node_store.c`), called by `App/tx_exchange.c` before each seal | reserves blocks of 256 counters in the flash meta log before it returns one |
| Gateway | ACK, NACK | `Nonces.next` (`ws0/protocol.py`) | commits the new counter to its SQLite database in an immediate transaction before it returns it |

On the node, the counter reaches flash before the seal:

```mermaid
sequenceDiagram
    participant X as App/tx_exchange.c
    participant S as node_store.c
    participant F as flash meta log
    participant W as ws_frame.c
    X->>S: store_next_counter
    alt the reserved block is used up
        S->>F: meta_append CTR, reserved + 256
        F-->>S: programmed
    end
    S-->>X: counter
    X->>W: ws_seal_kind with the counter
    W-->>X: frame
```

The two sides use separate counter spaces. The kind byte in the nonce keeps them apart. For
example, node counter 5 sealed as OBS and gateway counter 5 sealed as ACK give different nonces.
OBS and DIAG share the node's counter. ACK and NACK share the gateway's counter. Thus no allocator
issues a counter value twice within one space.

A counter must be durable before use. Otherwise a reset between seal and reservation lets the next
boot issue the same counter again. A repeated counter is fatal for CCM. CCM encrypts in counter
mode, and its keystream depends only on the key and the nonce. Two frames under one nonce share
keystream. The exclusive OR (XOR) of their ciphertexts is the XOR of their plaintexts. A known
plaintext of one frame then reveals the other. `docs/protocol-design.md` section 3.2 counts nonce
reuse as a total loss of security.

The version is in the AAD but not in the nonce. Protocol version 5 therefore uses a new key
(`docs/protocol-design.md` section 3.2). No counter used under the previous format meets that key.

## 4. Sealing

### Refusals

`seal_ok` decides what `ws_seal_kind` may seal. The checks short-circuit in order, so the code
computes `plain_len + WS_FRAME_OVERHEAD` only for a `plain_len` that cannot overflow.

```c {#seal-ok}
/* Returns 1 if ws_seal_kind can seal these arguments: a plaintext that fits the frame and the
 * output, a valid station and counter, and a kind that the node or the gateway seals. */
static int seal_ok(uint32_t station, uint8_t kind, uint64_t counter, const uint8_t *plain, uint32_t plain_len, uint32_t out_cap) {
 if(plain_len>WS_FRAME_MAX-WS_FRAME_OVERHEAD || plain_len+WS_FRAME_OVERHEAD>out_cap || (!plain && plain_len)) return 0;
 if(station==0 || station>WS_STATION_MAX || counter==0 || counter>WS_COUNTER_MAX) return 0;
 return kind>=WS_KIND_OBS && kind<=WS_KIND_DIAG;
}
```

| Condition | Return | `out` afterwards |
|---|---|---|
| `out` is NULL | `WS_FRAME_EINVAL` (-1) | no buffer |
| `plain_len` above 239 (`WS_FRAME_MAX − WS_FRAME_OVERHEAD`) | `WS_FRAME_EINVAL` | `out_cap` zero bytes |
| `plain_len + 16` above `out_cap` | `WS_FRAME_EINVAL` | `out_cap` zero bytes |
| `plain` is NULL and `plain_len` is not 0 | `WS_FRAME_EINVAL` | `out_cap` zero bytes |
| station 0 or above 65535 | `WS_FRAME_EINVAL` | `out_cap` zero bytes |
| counter 0 or above 2^40 − 1 | `WS_FRAME_EINVAL` | `out_cap` zero bytes |
| kind not 1–4 | `WS_FRAME_EINVAL` | `out_cap` zero bytes |
| Mbed TLS `setkey` or `encrypt_and_tag` fails | `WS_FRAME_ECRYPTO` (-4) | `out_cap` zero bytes |

`seal_ok` refuses counter 0 because neither allocator issues it. Both start at 1.

The zeroed output protects a caller that ignores the return code. A refused call leaves no stale
frame from an earlier call in `out`. A failed cipher call leaves no header with a partial
ciphertext. A zero buffer starts with byte 0, which is version 0. The receiving bridge (the RX
bridge) and the gateway drop it. The wipe covers `out_cap` bytes, so `out_cap` must be the real
size of `out`.

### Seal

`ws_seal_kind` writes the header into `out`. Then it encrypts `plain` into `out` after the header
and writes the tag after the ciphertext. The AAD is the first 8 bytes of `out`, the header that the
function just wrote.

```mermaid
flowchart TD
    N{"out is NULL?"} -- yes --> R1["return WS_FRAME_EINVAL"]
    N -- no --> S{"seal_ok?"}
    S -- no --> Z1["zero out_cap bytes of out, return WS_FRAME_EINVAL"]
    S -- yes --> H["header: out bytes 0-7 and the nonce"]
    H --> K["setkey, then encrypt_and_tag: ciphertext at out + 8, tag at out + 8 + plain_len"]
    K --> FR["mbedtls_ccm_free"]
    FR --> C{"Mbed TLS returned 0?"}
    C -- no --> Z2["zero out_cap bytes of out, return WS_FRAME_ECRYPTO"]
    C -- yes --> L["return plain_len + 16"]
```

```c {#seal-kind}
int ws_seal_kind(const uint8_t key[WS_KEY_LEN], uint32_t station, uint8_t kind, uint64_t counter,
 const uint8_t *plain, uint32_t plain_len, uint8_t *out, uint32_t out_cap) {
 uint8_t nonce[NONCE_LEN]; mbedtls_ccm_context ccm; int rc;
 uint32_t len=plain_len+WS_FRAME_OVERHEAD;
 if(!out) return WS_FRAME_EINVAL;
 /* Every refusal wipes the whole output buffer. A caller that ignores the result then cannot
    send a stale or half-built frame. */
 if(!seal_ok(station,kind,counter,plain,plain_len,out_cap)) {
  mbedtls_platform_zeroize(out,out_cap);
  return WS_FRAME_EINVAL;
 }
 header(out,nonce,kind,station,counter);
 mbedtls_ccm_init(&ccm);
 rc=mbedtls_ccm_setkey(&ccm,MBEDTLS_CIPHER_ID_AES,key,KEY_BITS);
 if(!rc) rc=mbedtls_ccm_encrypt_and_tag(&ccm,plain_len,nonce,NONCE_LEN,out,WS_HEADER_LEN,
  plain,out+WS_HEADER_LEN,out+WS_HEADER_LEN+plain_len,WS_TAG_LEN);
 mbedtls_ccm_free(&ccm);
 if(rc) { mbedtls_platform_zeroize(out,out_cap); return WS_FRAME_ECRYPTO; }
 return (int)len;
}
```

`mbedtls_ccm_free` clears the key schedule in `ccm` on both paths. The code uses
`mbedtls_platform_zeroize`, not `memset`. The compiler may delete a `memset` of memory that nothing
reads again.

## 5. Opening a reply

### Reply plaintext

ACK and NACK carry the same 17-byte plaintext (`WS_REPLY_PLAIN_LEN`, `docs/protocol-design.md`
section 4). The plaintext bits, most significant bit first:

```mermaid
packet-beta
0-31: "epoch (u32)"
32-63: "seq (u32)"
64-95: "word (u32)"
96-135: "echo (u40)"
```

| Offset | Bytes | Field | ACK | NACK |
|---:|---:|---|---|---|
| 0 | 4 | epoch | of the record answered | of the record answered |
| 4 | 4 | seq | of the record answered | of the record answered |
| 8 | 4 | word | host UTC, or 0 when the gateway measured its own clock as wrong | reason: 1 `WS_NACK_COLLISION`, 2 `WS_NACK_INVALID` |
| 12 | 5 | echo | the observation counter answered | the observation counter answered |

The header counter of a reply is the gateway's counter. `echo` is the node's counter of the frame
that the reply answers.

```c {#reply-unpack}
/* The reply plaintext: epoch u32, seq u32, word u32 (UTC or NACK reason), echo u40. */
static void reply_unpack(const uint8_t plain[WS_REPLY_PLAIN_LEN], uint32_t *epoch, uint32_t *seq, uint32_t *word, uint64_t *echo) {
 const uint8_t *p = ws_read_be32(plain, epoch);
 p = ws_read_be32(p, seq);
 p = ws_read_be32(p, word);
 (void)ws_read_be(p, echo, WS_COUNTER_BYTES);
}
```

### Checks

`ws_open_reply` runs its checks in this order and stops at the first failure:

```mermaid
flowchart TD
    A{"1. len is 33 (WS_ACK_FRAME_LEN)?"} -- no --> E1["WS_FRAME_EINVAL (-1)"]
    A -- yes --> B{"2. ws_frame_kind: frame not NULL, version 5, kind ACK or NACK?"}
    B -- no --> E2["WS_FRAME_EHEADER (-2)"]
    B -- yes --> C{"3. caller station in 1-65535?"}
    C -- no --> E1
    C -- yes --> D{"4. frame bytes 0-2 equal the rebuilt header?"}
    D -- no --> E2
    D -- yes --> F{"5. CCM decrypts and the tag verifies?"}
    F -- no --> E3["WS_FRAME_EAUTH (-3)"]
    F -- yes --> OK["write the outputs, return WS_FRAME_OK (0)"]
```

Step 3 checks an argument, not the frame, so it returns `WS_FRAME_EINVAL`. Step 4 rebuilds the
header from the frame's kind, the caller's station and the frame's counter. It compares bytes 0–2
(version, kind and station, `WS_COUNTER_OFF` bytes). Step 5 uses the frame's 8 header bytes as the
AAD.

Steps 1–4 need no key and run no cipher. A reply for another station fails at step 4. Step 4 does
not compare the counter bytes. `ws_open_reply` reads them from the frame and encodes them again, so
they match by construction. The nonce for step 5 comes from the same `header` call. It holds the
node's own station, so the tag can verify only for a frame sealed for this station.

A failed `mbedtls_ccm_setkey` also returns `WS_FRAME_EAUTH`. The caller cannot tell it from a bad
tag.

On success the function writes `kind`, `counter`, `epoch`, `seq`, `word` and `echo`. On failure it
writes none of them. It zeroes the plaintext buffer on every path that reaches the cipher.

```c {#open-reply}
int ws_open_reply(const uint8_t key[WS_KEY_LEN], uint32_t station, const uint8_t *frame, uint32_t len,
 uint8_t *kind, uint64_t *counter, uint32_t *epoch, uint32_t *seq, uint32_t *word, uint64_t *echo) {
 uint8_t expect[WS_HEADER_LEN], nonce[NONCE_LEN], plain[WS_REPLY_PLAIN_LEN]; mbedtls_ccm_context ccm; int rc;
 if(len!=WS_ACK_FRAME_LEN) return WS_FRAME_EINVAL;
 int k=ws_frame_kind(frame,len);
 if(k!=WS_KIND_ACK && k!=WS_KIND_NACK) return WS_FRAME_EHEADER;
 if(station==0 || station>WS_STATION_MAX) return WS_FRAME_EINVAL;   /* the caller's station, not the frame's */
 uint64_t ctr=ws_get_be64(frame+WS_COUNTER_OFF,WS_COUNTER_BYTES);
 header(expect,nonce,(uint8_t)k,station,ctr);
 if(memcmp(expect,frame,WS_COUNTER_OFF)) return WS_FRAME_EHEADER; /* version, kind, station */
 mbedtls_ccm_init(&ccm);
 rc=mbedtls_ccm_setkey(&ccm,MBEDTLS_CIPHER_ID_AES,key,KEY_BITS);
 if(!rc) rc=mbedtls_ccm_auth_decrypt(&ccm,WS_REPLY_PLAIN_LEN,nonce,NONCE_LEN,frame,WS_HEADER_LEN,
  frame+WS_HEADER_LEN,plain,frame+WS_HEADER_LEN+WS_REPLY_PLAIN_LEN,WS_TAG_LEN);
 mbedtls_ccm_free(&ccm);
 if(!rc) { *kind=(uint8_t)k; *counter=ctr; reply_unpack(plain,epoch,seq,word,echo); }
 mbedtls_platform_zeroize(plain,sizeof plain);
 return rc?WS_FRAME_EAUTH:WS_FRAME_OK;
}
```

## 6. Key check value

`ws_key_check` encrypts one zero block with AES-128-ECB under the key. It returns the first 3 bytes
(`WS_KCV_LEN`). The node and the gateway compute the value from the same key. Equal values show
equal keys, and the key itself stays hidden. The function zeroes the whole AES block before it
returns, so only those 3 bytes leave it.

| Key | Check value |
|---|---|
| `00 01 02 … 0f` (the self-test key) | `c6a13b` (FIPS-197 AES-128 vector) |

Users:

- `store_config_write` and `store_config_load` (`App/node_store.c`) store the value with the key
  and compare it on load. A mismatch means that the stored key changed after it was written.
- `App/tx_console.c` prints the value as `kcv=` in `#status`, for comparison with the gateway's
  value.

The function returns the Mbed TLS code. It writes `out` only when that code is 0.

```c {#key-check}
int ws_key_check(const uint8_t key[WS_KEY_LEN], uint8_t out[WS_KCV_LEN]) {
 uint8_t block[AES_BLOCK_LEN]; mbedtls_aes_context aes; int rc;
 mbedtls_aes_init(&aes);
 rc=mbedtls_aes_setkey_enc(&aes,key,KEY_BITS);
 if(!rc) { const uint8_t zero[AES_BLOCK_LEN]={0}; rc=mbedtls_aes_crypt_ecb(&aes,MBEDTLS_AES_ENCRYPT,zero,block); }
 mbedtls_aes_free(&aes);
 if(!rc) memcpy(out,block,WS_KCV_LEN);
 mbedtls_platform_zeroize(block,sizeof block);   /* only 3 bytes of AES(key, 0) may leave */
 return rc;
}
```

## 7. Health report

`ws_diag_pack` writes the 32-byte health report plaintext (kind `WS_KIND_DIAG`,
`WS_DIAG_PLAIN_LEN`) from a `ws_diag_t`. The order of the writes sets the offsets. The plaintext
bits, most significant bit first:

```mermaid
packet-beta
0-31: "epoch (u32)"
32-63: "uptime (u32)"
64-79: "pending (u16)"
80-111: "lost (u32)"
112-127: "torn (u16)"
128-143: "abandoned (u16)"
144-159: "no_ack (u16)"
160-175: "rejects (u16)"
176-183: "reset_cause"
184-191: "link"
192-223: "build (u32)"
224-231: "rssi (i8)"
232-239: "snr (i8)"
240-247: "crashes"
248-255: "energy"
```

| Offset | Bytes | `ws_diag_t` field | Contents |
|---:|---:|---|---|
| 0 | 4 | `epoch` | boot epoch |
| 4 | 4 | `uptime` | seconds since boot |
| 8 | 2 | `pending` | journal records not yet acknowledged |
| 10 | 4 | `lost` | journal lost total |
| 14 | 2 | `torn` | torn slots |
| 16 | 2 | `abandoned` | abandoned total |
| 18 | 2 | `no_ack` | missed ACKs since boot |
| 20 | 2 | `rejects` | rejected replies since boot |
| 22 | 1 | `reset_cause` | reset cause code |
| 23 | 1 | `link` | link state |
| 24 | 4 | `build` | first 4 bytes of the release commit hash |
| 28 | 1 | `rssi` | received signal strength (RSSI) of the last authentic ACK, signed dBm |
| 29 | 1 | `snr` | signal-to-noise ratio (SNR) of the last authentic ACK, signed dB |
| 30 | 1 | `crashes` | crash record count |
| 31 | 1 | `energy` | energy state (`docs/protocol-design.md` section 5.2) |

`ws0/protocol.py` unpacks the same bytes with `struct.Struct('>IIHIHHHHBBIbbBB')`.

- Each `ws_diag_t` field has its wire width, so the function truncates nothing. The caller clamps
  the counts. The design saturates 16-bit counters at `0xFFFF`.
- `rssi` and `snr` are `int8_t`. The cast to `uint8_t` writes their two's-complement byte.
  `WS_SIGNAL_NONE` (`INT8_MIN`) goes out as `0x80`. The gateway reads it as −128, "none yet".

```c {#diag-pack}
/* Field order and widths: docs/protocol-design.md section 4 and ws0/protocol.py DIAG. */
void ws_diag_pack(const ws_diag_t *d, uint8_t out[WS_DIAG_PLAIN_LEN]) {
 uint8_t *p = ws_write_be32(out, d->epoch);
 p = ws_write_be32(p, d->uptime);
 p = ws_write_be16(p, d->pending);
 p = ws_write_be32(p, d->lost);
 p = ws_write_be16(p, d->torn);
 p = ws_write_be16(p, d->abandoned);
 p = ws_write_be16(p, d->no_ack);
 p = ws_write_be16(p, d->rejects);
 p = ws_write_u8(p, d->reset_cause);
 p = ws_write_u8(p, d->link);
 p = ws_write_be32(p, d->build);
 p = ws_write_u8(p, (uint8_t)d->rssi);
 p = ws_write_u8(p, (uint8_t)d->snr);
 p = ws_write_u8(p, d->crashes);
 (void)ws_write_u8(p, d->energy);
}
```

## 8. The file

The generated file orders the chunks for C. The order is: includes, constants, the header and nonce
builder, the seal path, the reply path, the key check value and the health report.

```c {#ws_frame.c}
#include "ws_frame.h"
#include <string.h>
#include "ws_be.h"
#include "mbedtls/aes.h"
#include "mbedtls/ccm.h"
#include "mbedtls/platform_util.h"

<<constants>>

<<header>>

<<seal-ok>>

<<seal-kind>>

<<reply-unpack>>

<<open-reply>>

<<key-check>>

<<diag-pack>>
```

## 9. Tests

`tests/test_frame.py` builds `ws_frame.c` as a host library and calls it through `ctypes`. It
compares the C output with `ws0/protocol.py`. It also compares it with a frame built directly from
the design document with the `AESCCM` class of the `cryptography` library.

| Test | What it checks |
|---|---|
| `test_vectors_follow_the_spec` | the OBS, ACK and NACK known-answer vectors follow the design document's construction |
| `test_known_answer_vectors` | C and Python seal and open the vectors to the same bytes and values |
| `test_random_agreement_both_directions` | 300 random keys, stations and counters: C seals what Python seals, and C opens what Python seals |
| `test_counter_and_station_limits` | the C code refuses station 0 and 65536, counter 0, 2^40 and 2^64 − 1, kinds 0, 5 and 15, and a 256-byte frame. After a station or counter refusal the C buffer is all zero (`fuzz_reply` checks it for every refusal) |
| `test_reply_rejections` | a wrong tag, station, key, kind, length or version fails. A NACK with its kind byte changed to ACK fails the tag |
| `test_diagnostic_frame_agreement` | a sealed health report frame matches Python, and `unseal` in `ws0/protocol.py` does not accept it as an observation |
| `test_diag_plaintext_matches_python` | `ws_diag_pack` equals `DIAG.pack` for zeros, extremes and 200 random reports |
| `test_key_check_value` | the check value equals AES-ECB of a zero block, `c6a13b` for the self-test key |
| `test_selftest_vectors` (`FirmwareTables`) | the byte arrays in `App/selftest.c` are the design document's frames |

`firmware/fuzz/fuzz_reply.c` passes arbitrary bytes to `ws_open_reply`. `tests/test_fuzz.py`
(`test_reply`) runs it. Only the two genuine self-test frames may open. The fuzzer then seals with
a station, counter, kind and plaintext that it chooses. The station and the counter are biased to 0,
1, each limit and one past it. The kind is 0 to 5, so two invalid kinds occur.
A value out of range must return a negative code. It must also leave all of `out` zero, including
8 bytes past any frame. An accepted value must give the design document's header and length. An
ACK or NACK for station 1 with a 17-byte plaintext must open to the same values.

`selftest_kat` (`App/selftest.c`) is the known-answer test. It runs on the TX board at boot
(`App/app_tx.c`). It seals the observation vector and checks that `ws_seal_kind` refuses counter
2^40. It tries to open the ACK, a tampered ACK and the NACK. `#status` reports the result as `kat=`.

```sh
.venv/bin/python -m unittest tests.test_frame tests.test_fuzz tests.test_tangle
```
