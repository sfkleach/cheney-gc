"""
This is small program to demonstrate how Cheney-style garbage collection works.
It employs a simple abstract machine to help visualize the process.

The machine has a set of registers which are referenced by name. Each register 
holds a 64-bit word, modelled here as a Word. 

The machine also has a value stack which is used to store values. The stack
is modelled as a list of Values.

Finally the abstract machine also has a heap. Fundamentally this is a large
array of 64-bit word that are grouped into objects. The objects are vectors of
values and have this format:

    LENGTH a 64-bit unsigned number that describes the length of the object
    DATA a sequence of values that represent the data of the object.

"""

import argparse
from typing import List

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

LENGTH_OFFSET = 0
ELEMENTS_OFFSET = 1
OVERHEAD = 1

class Heap:

    def __init__(self, size):
        self._heap = [None] * size
        self._tip = 0
        self._scan_queue = 0

    def get(self, offset):
        return self._heap[offset]
    
    def put(self, offset, value):
        self._heap[offset] = value
        return value

    def gcScanNextObject(self, gc):
        gctrace = gc.gctrace()
        ok = self._scan_queue < self._tip
        if ok:
            offset = self._scan_queue
            length = self._heap[offset + LENGTH_OFFSET].value()
            gctrace.logScanNextObject(offset, length)
            with gctrace:
                self._scan_queue = offset + 2 + length
                for i in range(length):
                    delta = offset + 2 + i
                    self._heap[delta] = gc.forwardIfPointer(self._heap[delta])
        else:
            gctrace.logScanQueueEmpty()
        return ok

    def newHeap(self):
        return Heap(len(self._heap))

    def show(self):
        print(f"  Heap (tip = {self._tip})")
        offset = 0
        while offset < self._tip:
            start = self._heap[offset]
            length = self._heap[offset + LENGTH_OFFSET].value()
            data = self._heap[offset + ELEMENTS_OFFSET: offset + 2 + length]
            print(f"    {offset}: {length}, {data}")
            offset += OVERHEAD + length

    def checkCapacity(self, length):
        if self._tip + length > len(self._heap):
            raise GarbageCollectionNeededException()
        
    def pointer(self, offset):
        return Pointer(self, offset)

    def tipPointer(self):
        return Pointer(self, self._tip)

    def newObject(self, length, stack):
        self.checkCapacity(length + OVERHEAD)
        result = self.tipPointer()
        self.add(Data(length))
        self._heap[self._tip: self._tip + length] = stack[-length:]
        del stack[-length:]
        self._tip += length
        return result

    def explode(self, pointer: Pointer, stack: List[Word]):
        offset = pointer.offset()
        length = self._heap[offset + LENGTH_OFFSET].value()
        stack.extend(self._heap[offset + ELEMENTS_OFFSET: offset + ELEMENTS_OFFSET + length])

    def clone(self, pointer):
        return self.cloneToTargetHeap(pointer, self)

    def cloneToTargetHeap(self, pointer: Pointer, target_heap: 'Heap'):
        offset = pointer.offset()
        length = self._heap[offset + LENGTH_OFFSET].value()
        target_heap.checkCapacity(length + OVERHEAD)
        result = target_heap.tipPointer()
        target_heap.add(Data(length))
        for i in range(offset + ELEMENTS_OFFSET, offset + ELEMENTS_OFFSET + length):
            target_heap.add(self._heap[i])
        return result

    def add(self, value: Word):
        self._heap[self._tip] = value
        self._tip += 1

class GarbageCollector:

    def __init__(self, registers, value_stack, heap, gctrace):
        self._registers = registers
        self._value_stack = value_stack
        self._heap = heap
        self._new_heap = heap.newHeap()
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

    def forwardIfPointer(self, value):
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

    def collectGarbage(self):
        with self._gctrace("GARBAGE COLLECTION"):
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
        self._registers = {}
        self._heap = Heap(100)
        self._value_stack = []
        self._gctrace = gctrace

    def garbageCollect(self, msg):
        self._heap = GarbageCollector(self._registers, self._value_stack, self._heap, self._gctrace).collectGarbage()

    def show(self, msg):
        print(f"Machine state: {msg}")
        print("  Registers")
        for k, v in self._registers.items():
            print(f"    {k}: {v}")
        print("  Stack (top to bottom)")
        for i in reversed(range(len(self._value_stack))):
            print(f"    {i}: {self._value_stack[i]}")
        self._heap.show()
        print()

    def LOAD(self, register, value):
        self._registers[register] = Data(value)

    def PUSH(self, register):
        self._value_stack.append(self._registers[register])

    def POP(self, register):
        self._registers[register] = self._value_stack.pop()

    def STACK_LENGTH(self, register):
        self._registers[register] = Data(len(self._value_stack))

    def STACK_DELTA(self, register):
        n = len(self._value_stack) - self._registers[register].value()
        self._registers[register] = Data(n)

    def NEW_OBJECT(self, len_register, obj_register, try_gc=True):
        try:
            length = self._registers[len_register].value()
            self._registers[obj_register] = self._heap.newObject(length, self._value_stack)
        except GarbageCollectionNeededException:
            if try_gc:
                self.garbageCollect("Automatic GC")
                self.NEW_OBJECT(len_register, obj_register, try_gc=False) 
            else:
                raise OurException("Out of memory")

    def LENGTH(self, obj_register, len_register):
        self._registers[len_register] = self._heap.get(self._registers[obj_register].offset() + 1)

    def EXPLODE(self, obj_register):
        self._heap.explode(self._registers[obj_register], self._value_stack)

    def FIELD(self, obj_register, index, value_register):
        length = self._heap.get(self._registers[obj_register].offset() + LENGTH_OFFSET).value()
        if index < 0 or index >= length:
            raise OurException("Index out of range")
        offset = self._registers[obj_register].offset() + ELEMENTS_OFFSET + index
        self._registers[value_register] = self._heap.get(offset)

    def CLONE(self, obj_register, clone_register, try_gc=True):
        try:
            self._registers[clone_register] = self._heap.clone(self._registers[obj_register])
        except GarbageCollectionNeededException:
            if try_gc:
                self.garbageCollect("Automatic GC")
                self.CLONE(obj_register, clone_register, try_gc=False) 
            else:
                raise OurException("Out of memory")

def scenario1(mc):
    mc.LOAD('A', 10)
    mc.LOAD('B', 20)
    mc.LOAD('C', 30)
    mc.PUSH('A')
    mc.STACK_LENGTH('L')
    mc.PUSH('A')
    mc.PUSH('B')
    mc.PUSH('C')
    mc.STACK_DELTA('L')
    mc.show("Before")
    mc.NEW_OBJECT('L', 'R')
    mc.show("After")
    mc.STACK_LENGTH('L')
    mc.CLONE('R', 'R')
    mc.show("Clone")
    mc.PUSH('R')
    mc.PUSH('R')
    mc.STACK_DELTA('L')
    mc.NEW_OBJECT('L', 'R')
    mc.show("Finally")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

def scenario2(mc):
    mc.STACK_LENGTH('L')
    mc.LOAD('A', 11)
    mc.PUSH('A')
    mc.LOAD('A', 22)
    mc.PUSH('A')
    mc.LOAD('A', 33)
    mc.PUSH('A')
    mc.STACK_DELTA('L')
    mc.NEW_OBJECT('L', 'R')
    for i in range(60):
        mc.CLONE('R', 'R')
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

SCENARIOS = [scenario1, scenario2]

def main():
    argparser = argparse.ArgumentParser(description="Cheney-style garbage collector")
    argparser.add_argument("--scenario", type=int, default=1, help="Scenario to run")
    argparser.add_argument("--gctrace", action='store_true', help="Trace the garbage collection process")
    args = argparser.parse_args()
    gctrace = GCEventLogger() if args.gctrace else Null()
    try:
        scenario = SCENARIOS[args.scenario - 1]
        scenario(Machine(gctrace))
    except IndexError:
        print("Invalid scenario selected")

if __name__ == "__main__":
    main()
