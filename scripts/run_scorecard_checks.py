"""Isolated unittest adapter for root or backend import directories.

Reads test names on stdin. Emits outcomes only, without tracebacks or credentials.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import unittest

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path.cwd() / "tests"))

if os.getenv("SCORECARD_OFFLINE") == "1":
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
    def guarded(original):
        def connect(self, address):
            # Windows asyncio uses loopback socket pairs internally.
            if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
                raise RuntimeError("External network access is disabled for offline evaluations")
            return original(self, address)
        return connect
    socket.socket.connect = guarded(original_connect)
    socket.socket.connect_ex = guarded(original_connect_ex)


class Outcomes(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.rows.append({"test": test.id(), "status": "passed"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.rows.append({"test": test.id(), "status": "failed", "error_type": err[0].__name__})

    def addError(self, test, err):
        super().addError(test, err)
        self.rows.append({"test": test.id(), "status": "error", "error_type": err[0].__name__})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.rows.append({"test": test.id(), "status": "skipped"})

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.rows.append({"test": test.id(), "status": "failed" if issubclass(err[0], test.failureException) else "error", "error_type": err[0].__name__})

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.rows.append({"test": test.id(), "status": "skipped"})

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.rows.append({"test": test.id(), "status": "failed", "error_type": "UnexpectedSuccess"})


if __name__ == "__main__":
    tests = json.load(sys.stdin)
    result = Outcomes()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        suite = unittest.TestLoader().loadTestsFromNames(tests)
        suite.run(result)
    print(json.dumps(result.rows))
