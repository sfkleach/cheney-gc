"""
This is small program to demonstrate how Cheney-style garbage collection works.
It employs a simple abstract machine to help visualize the process.

The abstract machine has a heap, which is modelled as an array of abstract
Pointers or integers, which are intended to fit into a width of 64-bits.
The objects in the heap are vectors and have this format:

    KEY a 64-bit data field that describes the type of the object. In this
        simple machine this is not used in normal processing but is temporarily
        used by the garbage collector to mark the object as relocated.
    LENGTH a 64-bit unsigned number that describes the length of the object
    DATA a sequence of values that represent the data of the object

The machine also has a set of registers which divided into pointer resgiters
and data registers. The registers are referenced by name. Each set of registers
is modelled as a dictionary of strings to values.


"""

from typing import List

class OurException(Exception):
    pass

class Value:
    pass

class Pointer( Value ):
    """
    This class mimicks a 64-bit pointer aligned on an 8-byte boundary. It is 
    used to represent a pointer to a location in the heap. 

    IMPORTANT: Pointers may only point to the starting location of
    an object in the heap.
    """

    def __init__(self, heap, offset):
        self._heap = heap
        self._offset = offset

    def isInHeap(self, heap):
        return self._heap is heap
    
    def dereference(self) -> Value:
        return self._heap.get(self._offset)
    
    def update(self, new_value: Value):
        return self._heap.put(self._offset, new_value)

    def offset(self):
        return self._offset

    def __repr__(self):
        return f"Pointer({self._offset})"

class Data( Value ):
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

class Key( Value ):
    """
    This class represents a key value. In a more complex machine it would be
    used to describe the type of the object. In this simple machine it is only
    used by the garbage collector to mark it as relocated.
    """

    def __init__(self):
        pass

    def __repr__(self):
        return "Key()"

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

    def scan_next_object(self, gc):
        ok = self._scan_queue < self._tip
        if ok:
            offset = self._scan_queue
            length = self._heap[offset + 1].value()
            self._scan_queue = offset + 2 + length
            for i in range(length):
                delta = offset + 2 + i
                self._heap[delta] = gc.forwardIfPointer(self._heap[delta])
        return ok
    
    def forwardObjectIfNeeded(self, pointer: Pointer, new_heap):
        if pointer.isInHeap(self):
            p = pointer.dereference()
            if isinstance(p, Pointer) and p.isInHeap(new_heap):
                return p
            else:
                return pointer.update(self.cloneToTargetHeap(pointer, new_heap))
        else:
            raise OurException("Pointer not in current heap")

    def new_heap(self):
        return Heap(len(self._heap))
    
    def copy_back(self, new_heap: 'Heap'):
        self._heap = new_heap._heap
        self._tip = new_heap._tip

    def heap(self):
        return self._heap

    def show(self):
        print(f"  Heap (tip = {self._tip})")
        offset = 0
        while offset < self._tip:
            key = self._heap[offset]
            length = self._heap[offset + 1].value()
            data = self._heap[offset + 2: offset + 2 + length]
            print(f"    {offset}: {key}, {length}, {data}")
            offset += 2 + length

    def check_capacity(self, length):
        if self._tip + length >= len(self._heap):
            raise OurException("Out of memory")
        
    def pointer(self, offset):
        return Pointer(self, offset)

    def tip_pointer(self):
        return Pointer(self, self._tip)

    def new_object(self, length, stack):
        self.check_capacity(length)
        result = self.pointer(self._tip)
        self.add(Key())
        self.add(Data(length))
        self._heap[self._tip: self._tip + length] = stack[-length:]
        del stack[-length:]
        self._tip += length
        return result

    def init_object(self, length, value: Value):
        self.check_capacity(length + 2)
        result = self.tip_pointer()
        self.add( Key())
        self.add( Data(length))
        for _ in range(length):
            self.add(value)
        return result

    def explode(self, pointer: Pointer, stack: List[Value]):
        offset = pointer.offset()
        length = self._heap[offset + 1].value()
        stack.extend(self._heap[offset + 2: offset + 2 + length])

    def clone(self, pointer):
        return self.cloneToTargetHeap(pointer, self)

    def cloneToTargetHeap(self, pointer: Pointer, target_heap: 'Heap'):
        offset = pointer.offset()
        length = self._heap[offset + 1].value()
        self.check_capacity(length + 2)
        result = target_heap.tip_pointer()
        target_heap.add( Key() )
        target_heap.add(Data(length))
        for i in range(offset + 2, offset + 2 + length):
            target_heap.add(self._heap[i])
        return result

    def add(self, value: Value):
        self._heap[self._tip] = value
        self._tip += 1

class GarbageCollector:

    def __init__(self, registers, value_stack, heap):
        self._registers = registers
        self._value_stack = value_stack
        self._heap = heap
        self._new_heap = heap.new_heap()

    def visitRegisters(self):
        for k, v in self._registers.items():
            print(f"Check register {k} with value {v}")
            if isinstance(v, Pointer):
               self._registers[k] = self.forwardIfPointer(v)

    def visitValueStack(self):
        for i, x in enumerate(self._value_stack):
            self._value_stack[i] = self.forwardIfPointer(x)

    def run(self):
        self.visitRegisters()
        self.visitValueStack()

        while self._new_heap.scan_next_object(self):
            pass

        return self._new_heap

    def forwardIfPointer(self, value):
        if isinstance(value, Pointer):
            return self._heap.forwardObjectIfNeeded(value, self._new_heap)
        else:
            return value


class Procedure:

    def __init__(self, codelist, labels):
        self._codelist = codelist
        self._labels = labels

    def __len__(self):
        return len(self._codelist)

    def __getitem__(self, index):
        return self._codelist[index]

    def lookup(self, label):
        return self._labels[label]


class Machine:

    def __init__(self, procedure):
        self._registers = {}
        self._heap = Heap(100)
        self._value_stack = []
        self._pc = 0
        self._procedure = procedure

    def garbage_collect(self):
        print("Garbage collecting...")
        self._heap = GarbageCollector(self._registers, self._value_stack, self._heap).run()

    def run(self):
        N = len(self._procedure)
        while self._pc < N:
            instruction, args = self._procedure[self._pc]
            print(f'Call {instruction} on {args}')
            getattr(self, instruction)(*args)

    def register(self, name):
        return self._registers[name]

    def show(self):
        print("  Registers")
        for k, v in self._registers.items():
            print(f"    {k}: {v}")
        print("  Stack (top to bottom)")
        for i in reversed(range(len(self._value_stack))):
            print(f"    {i}: {self._value_stack[i]}")
        self._heap.show()

    def SHOW(self, message):
        print(message)
        self.show()
        self._pc += 1

    def LOAD(self, register, value):
        self._registers[register] = Data(value)
        self._pc += 1

    def PUSH(self, register):
        self._value_stack.append(self._registers[register])
        self._pc += 1

    def POP(self, register):
        self._registers[register] = self._value_stack.pop()
        self._pc += 1

    def STACK_LENGTH(self, register):
        self._registers[register] = Data(len(self._value_stack))
        self._pc += 1

    def STACK_DIFF(self, register):
        n = len(self._value_stack) - self._registers[register].value()
        self._registers[register] = Data(n)
        self._pc += 1

    def NEW_OBJECT(self, len_register, obj_register):
        length = self._registers[len_register].value()
        self._registers[obj_register] = self._heap.new_object(length, self._value_stack)
        self._pc += 1

    def LENGTH(self, obj_register, len_register):
        self._registers[len_register] = self._heap.heap()[self._registers[obj_register].offset() + 1]
        self._pc += 1

    def EXPLODE(self, obj_register):
        self._heap.explode(self._registers[obj_register], self._value_stack)
        self._pc += 1

    def FIELD(self, obj_register, index, value_register):
        length = self._heap.heap()[self._registers[obj_register].offset() + 1].value()
        if index < 0 or index >= length:
            raise OurException("Index out of range")
        offset = self._registers[obj_register].offset() + 2 + index
        self._registers[value_register] = self._heap.heap()[offset]
        self._pc += 1

    def CLONE(self, obj_register, clone_register):
        self._registers[clone_register] = self._heap.clone(self._registers[obj_register])
        self._pc += 1

    def JUMP(self, label):
        self._pc = self._procedure.lookup(label)

    def JUMP_IF(self, register, label):
        if self._registers[register].value():
            self._pc = self._procedure.lookup(label)
        else:
            self._pc += 1

    def GARBAGE_COLLECT(self):
        self.garbage_collect()
        self._pc += 1

class CodePlanter:

    def __init__(self):
        self._codelist = []
        self._labels = {}

    def __call__(self, instruction, *args):
        self._codelist.append((instruction, args))

    def LABEL(self, label):
        self._labels[label] = len(self._codelist)

    def new_procedure(self):
        return Procedure(self._codelist, self._labels)


def main():
    cp = CodePlanter()
    cp('LOAD', 'A', 10)
    cp('LOAD', 'B', 20)
    cp('LOAD', 'C', 30)
    cp('PUSH', 'A')
    cp('STACK_LENGTH', 'L')
    cp('PUSH', 'A')
    cp('PUSH', 'B')
    cp('PUSH', 'C')
    cp('STACK_DIFF', 'L')
    cp('SHOW', "Before")
    cp('NEW_OBJECT', 'L', 'R')
    cp('SHOW', "After")
    cp('STACK_LENGTH', 'L')
    cp('CLONE', 'R', 'R')
    cp('SHOW', "Clone")
    cp('PUSH', 'R')
    cp('PUSH', 'R')
    cp('STACK_DIFF', 'L')
    cp('NEW_OBJECT', 'L', 'R')
    cp('SHOW', "Finally")
    cp('GARBAGE_COLLECT')
    cp('SHOW', "After GC")
    proc = cp.new_procedure()
    m = Machine(proc)
    m.run()
