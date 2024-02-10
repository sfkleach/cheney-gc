"""
This is small program to demonstrate how Cheney-style garbage collection works.
It employs a simple abstract machine to help visualize the process.

The machine has a set of registers which are referenced by name. Each register
holds a 64-bit word, modelled here as a Word.

The machine also has a value stack which is used to store values. The stack
is modelled as a list of Values.

Finally the abstract machine also has a heap. Fundamentally this is a large
array of 64-bit word that are grouped into objects. The objects are vectors of
values.
"""

from typing import List, Dict
from null import Null
from gceventlogger import GCEventLogger

class OurException(Exception):
    """Used to signal a runtime error in the machine."""
    pass

class GarbageCollectionNeededException(Exception):
    """Used to signal that the heap is full and garbage collection is needed."""
    pass

class Word:
    """
    This is the base class for all values in the machine. It is intended to
    represent a 64-bit word value. And it is used to represent both pointers and
    data. In practice a few bits would need to be reserved to distinguish between
    pointers and data, but this is not implemented here.
    """
    pass

class Pointer( Word ):
    """
    This class mimicks a 64-bit pointer aligned on an 8-byte boundary. It is
    used to represent a pointer to a location in the heap.

    IMPORTANT: Pointers may only point to the starting location of
    an object in the heap. They are not allowed to point to the middle of an
    object.
    """

    def __init__(self, heap, offset):
        self._heap = heap
        self._offset = offset

    def isInHeap(self, heap):
        return self._heap is heap

    def dereference(self) -> Word:
        return self._heap.get(self._offset)

    def update(self, new_value: Word):
        return self._heap.put(self._offset, new_value)

    def offset(self):
        return self._offset

    def __repr__(self):
        return f"Pointer({self._offset})"

class Data( Word ):
    """
    This class represents an integer data value. It is used to represent
    any value that is not a pointer.
    """

    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value

    def __repr__(self):
        return f"Data({self._value})"


# These constants describe the layout of the objects in the heap. In this simple
# model the only objects that are supported are vectors of values. The layout
# is as follows:
#
#     LENGTH a 64-bit unsigned number that describes the length of the object.
#         This is at an offset of 0 from the start of the object. It constitutes
#         an overhead of 1 word.
#
#     DATA a sequence of values that represent the data of the object.
#         These start at an offset of 1 from the start of the object. The nth
#         element of the vector is at an offset of n + 1 from the start of the
#         object.
#
# These constants simplify evolving this package into a more complicated model.

VECTOR_LENGTH_OFFSET = 0
VECTOR_ELEMENTS_OFFSET = 1
VECTOR_OVERHEAD = 1

class Heap:
    """
    This class represents the heap of the abstract machine. It is a large
    array of 64-bit words. It is used to store objects. The objects are
    vectors of values.
    """

    def __init__(self, size):
        self._store = [None] * size
        self._tip = 0
        self._scan_queue = 0

    def get(self, offset):
        return self._store[offset]

    def put(self, offset, value):
        self._store[offset] = value
        return value

    def gcScanNextObject(self, gc):
        gctrace = gc.gctrace()
        ok = self._scan_queue < self._tip
        if ok:
            offset = self._scan_queue
            length = self._store[offset + VECTOR_LENGTH_OFFSET].value()
            gctrace.logScanNextObject(offset, length)
            with gctrace:
                self._scan_queue = offset + VECTOR_OVERHEAD + length
                for i in range(length):
                    delta = offset + VECTOR_OVERHEAD + i
                    self._store[delta] = gc.forwardIfPointer(self._store[delta])
        else:
            gctrace.logScanQueueEmpty()
        return ok

    def newHeap(self):
        return Heap(len(self._store))

    def show(self):
        print(f"  Heap (tip = {self._tip})")
        offset = 0
        while offset < self._tip:
            length = self._store[offset + VECTOR_LENGTH_OFFSET].value()
            data = self._store[offset + VECTOR_ELEMENTS_OFFSET: offset + VECTOR_ELEMENTS_OFFSET + length]
            print(f"    {offset}: {data}")
            offset += VECTOR_OVERHEAD + length

    def checkCapacity(self, length):
        if self._tip + length > len(self._store):
            raise GarbageCollectionNeededException()

    def pointer(self, offset):
        return Pointer(self, offset)

    def tipPointer(self):
        return Pointer(self, self._tip)

    def newObject(self, length, stack):
        # print('BEFORE', self._tip, self._store)
        self.checkCapacity(length + VECTOR_OVERHEAD)
        result = self.tipPointer()
        self.add(Data(length))
        self._store[self._tip: self._tip + length] = stack[-length:]
        del stack[-length:]
        self._tip += length
        # print('AFTER', self._tip, self._store)
        return result

    def explode(self, pointer: Pointer, stack: List[Word]):
        offset = pointer.offset()
        length = self._store[offset + VECTOR_LENGTH_OFFSET].value()
        stack.extend(self._store[offset + VECTOR_ELEMENTS_OFFSET: offset + VECTOR_ELEMENTS_OFFSET + length])

    def clone(self, pointer):
        return self.cloneToTargetHeap(pointer, self)

    def cloneToTargetHeap(self, pointer: Pointer, target_heap: 'Heap'):
        offset = pointer.offset()
        length = self._store[offset + VECTOR_LENGTH_OFFSET].value()
        target_heap.checkCapacity(length + VECTOR_OVERHEAD)
        result = target_heap.tipPointer()
        target_heap.add(Data(length))
        for i in range(offset + VECTOR_ELEMENTS_OFFSET, offset + VECTOR_ELEMENTS_OFFSET + length):
            target_heap.add(self._store[i])
        return result

    def add(self, value: Word):
        self._store[self._tip] = value
        self._tip += 1

class GarbageCollector:
    """
    This class is responsible for performing garbage collection. It is given
    privileged access to the registers, value stack and heap of the machine.
    """

    def __init__(self, machine, gctrace):
        self._registers = machine._Machine__registers
        self._value_stack = machine._Machine__value_stack
        self._heap = machine._Machine__heap
        self._new_heap = self._heap.newHeap()
        self._gctrace = gctrace

    def gctrace(self):
        return self._gctrace

    def _visitRegisters(self):
        for k, v in self._registers.items():
            if isinstance(v, Pointer):
                self._gctrace.logVisitRegister(k, v)
                self._registers[k] = self.forwardIfPointer(v)

    def _visitValueStack(self):
        for i, x in enumerate(self._value_stack):
            self._value_stack[i] = self.forwardIfPointer(x)

    def forwardIfPointer(self, value: Word):
        if not isinstance(value, Pointer):
            return value

        pointer: Pointer = value
        p = pointer.dereference()
        if isinstance(p, Pointer) and p.isInHeap(self._new_heap):
            # Already forwarded.
            self._gctrace.logAlreadyForwarded(pointer, p)
            return p
        else:
            # Need to forward.
            new_pointer = self._heap.cloneToTargetHeap(pointer, self._new_heap)
            self._gctrace.logForwardObject(pointer, new_pointer)
            return pointer.update(new_pointer)

    def collectGarbage(self, message):
        with self._gctrace(f"GARBAGE COLLECTION: {message}"):
            with self._gctrace("INITIAL PHASE: Visit roots"):
                self._visitRegisters()
                self._visitValueStack()
            with self._gctrace("MAIN PHASE: Scanning objects in the scan-queue (new-heap)"):
                while self._new_heap.gcScanNextObject(self):
                    pass
        self._gctrace.logFinish()
        return self._new_heap


class Machine:

    def __init__(self, gctrace: GCEventLogger | Null):
        self.__registers: Dict[str, Word] = {}
        self.__heap: Heap = Heap(100)
        self.__value_stack: List[Word] = []
        self._gctrace = gctrace

    def garbageCollect(self, msg):
        self.__heap = GarbageCollector(self, self._gctrace).collectGarbage(msg)

    def show(self, msg):
        print(f"Machine state: {msg}")
        print("  Registers")
        for k, v in self.__registers.items():
            print(f"    {k}: {v}")
        print("  Stack (top to bottom)")
        for i in reversed(range(len(self.__value_stack))):
            print(f"    {i}: {self.__value_stack[i]}")
        self.__heap.show()
        print()

    def LOAD(self, register, value):
        self.__registers[register] = Data(value)

    def PUSH(self, register):
        self.__value_stack.append(self.__registers[register])

    def PUSH_DATA(self, value):
        self.__value_stack.append(Data(value))

    def POP(self, register):
        self.__registers[register] = self.__value_stack.pop()

    def STACK_LENGTH(self, register):
        # print('STACK LENGTH', len(self.__value_stack))
        self.__registers[register] = Data(len(self.__value_stack))

    def STACK_DELTA(self, register):
        # print('STACK DELTA', len(self.__value_stack))
        n = len(self.__value_stack) - self.__registers[register].value()
        self.__registers[register] = Data(n)

    def _new_object(self, length, obj_register, try_gc=True):
        try:
            self.__registers[obj_register] = self.__heap.newObject(length, self.__value_stack)
        except GarbageCollectionNeededException as exc:
            if try_gc:
                self.garbageCollect("Automatic GC")
                self._new_object(length, obj_register, try_gc=False)
            else:
                raise OurException("Out of memory") from exc

    def NEW_OBJECT(self, len_register, obj_register, try_gc=True):
        length = self.__registers[len_register].value()
        self._new_object(length, obj_register, try_gc)

    def NEW_OBJECT_DELTA(self, length_register, obj_register, try_gc=True):
        length = len(self.__value_stack) - self.__registers[length_register].value()
        self._new_object(length, obj_register, try_gc)

    def LENGTH(self, obj_register, len_register):
        self.__registers[len_register] = self.__heap.get(self.__registers[obj_register].offset() + VECTOR_LENGTH_OFFSET)

    def EXPLODE(self, obj_register):
        self.__heap.explode(self.__registers[obj_register], self.__value_stack)

    def FIELD(self, target_register, obj_register, index ):
        length = self.__heap.get(self.__registers[obj_register].offset() + VECTOR_LENGTH_OFFSET).value()
        if index < 0 or index >= length:
            raise OurException("Index out of range")
        offset = self.__registers[obj_register].offset() + VECTOR_ELEMENTS_OFFSET + index
        self.__registers[target_register] = self.__heap.get(offset)

    def SET_FIELD(self, obj_register, index, value_register):
        length = self.__heap.get(self.__registers[obj_register].offset() + VECTOR_LENGTH_OFFSET).value()
        if index < 0 or index >= length:
            raise OurException("Index out of range")
        offset = self.__registers[obj_register].offset() + VECTOR_ELEMENTS_OFFSET + index
        print('OFFSET', offset)
        self.__heap.put(offset, self.__registers[value_register])

    def CLONE(self, obj_register, clone_register, try_gc=True):
        try:
            self.__registers[clone_register] = self.__heap.clone(self.__registers[obj_register])
        except GarbageCollectionNeededException as exc:
            if try_gc:
                self.garbageCollect("Automatic GC")
                self.CLONE(obj_register, clone_register, try_gc=False)
            else:
                raise OurException("Out of memory") from exc
