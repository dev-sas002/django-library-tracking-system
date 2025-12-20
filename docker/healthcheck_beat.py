#!/usr/bin/env python3
"""Healthcheck for the Celery beat container.

Deliberately does not use ``pgrep``: ``procps`` is not installed in the
``python:*-slim`` base image, so a pgrep-based check reports the container
unhealthy even while beat is running perfectly.

Scanning ``/proc`` needs no extra package. Reads are guarded because a process
can exit between ``listdir`` and ``open``, and that race must not be reported as
a failing scheduler.
"""

import os
import sys


def beat_is_running():
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        try:
            with open(f'/proc/{entry}/cmdline', 'rb') as handle:
                cmdline = handle.read()
        except OSError:
            continue  # the process went away, or we may not read it
        if b'beat' in cmdline and b'celery' in cmdline:
            return True
    return False


if __name__ == '__main__':
    sys.exit(0 if beat_is_running() else 1)
