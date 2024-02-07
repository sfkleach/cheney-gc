class GCEventLogger:

    def __init__(self):
        self._level = 0
        self._scan_count = 0

    def __enter__(self):
        self._level += 1
    
    def __exit__(self, exc_type, exc_value, traceback):
        self._level -= 1

    def __call__(self, message):
        self._tab()
        print(message)
        return self

    def _tab(self):
        print("  " * self._level, end="")

    def logVisitRegister(self, name, value):
        self._tab()
        print(f"Register {name} has pointer: {value}")

    def logForwardObject(self, pointer, new_pointer):
        self._tab()
        print(f"Object copied to end of scan_queue: {pointer} -> {new_pointer}")

    def logAlreadyForwarded(self, pointer, new_pointer):
        self._tab()
        print(f"Already forwarded: {pointer} -> {new_pointer}")

    def logScanNextObject(self, offset, length):
        self._tab()
        self._scan_count += 1
        print(f"{self._scan_count}: Scanning object at {offset} with length {length}")
        return self

    def logScanQueueEmpty(self):
        self._tab()
        print(f"#: Scan queue empty")

    def logFinish(self):
        print()
