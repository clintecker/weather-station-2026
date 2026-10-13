"""Shared skip rule for tests that compile firmware C on the host.

The gateway must run on macOS, Linux and Windows. The C firmware tests need a C compiler (`cc`),
which a Windows host usually lacks, so they skip there. CI sets WS_REQUIRE_CC=1 on Linux and
macOS so a missing compiler fails instead of silently skipping.
"""
import os
import shutil
import unittest

HAVE_CC = shutil.which('cc') is not None
REQUIRE_CC = os.environ.get('WS_REQUIRE_CC') == '1'

needs_cc = unittest.skipUnless(HAVE_CC or REQUIRE_CC, 'needs a C compiler (cc) to build firmware C for the host')
