#ifndef SELFTEST_H
#define SELFTEST_H
/* The TX boot self-test (also the KAT console command): draft-5 known answers for the observation
 * encoder and seal, the ACK and NACK opener (with a tampered tag that must fail), and the counter
 * limit. 1 if every check passes; a board that fails it does not transmit. */
int selftest_kat(void);
#endif
