import argparse
from typing import Callable, Dict
import re

from gceventlogger import GCEventLogger
from machine import Machine

SCENARIOS: Dict[str, Callable[[Machine], None]] = {}

def Scenario():
    """Decorator to register a function as a scenario. The function name is used 
    as the scenario name.
    """
    def decorator(func):
        short_name = re.sub("scenario_?", "", func.__name__)
        SCENARIOS[short_name] = func
        return func
    return decorator

@Scenario()
def scenario0(mc):
    """Trivial scenario where the garbage collector is called before any allocation.
    """
    mc.LOAD_DATA('A', 10)  # Load a value into a register so it will show up in the output.  
    mc.show("Before")
    mc.garbageCollect("Manual GC")
    mc.show("After")

@Scenario()
def scenario10(mc):
    """Scenario with a single object and no garbage.
    """
    mc.STACK_LENGTH('L')
    mc.LOAD_DATA('A', 11)
    mc.PUSH('A')
    mc.LOAD_DATA('A', 22)
    mc.PUSH('A')
    mc.LOAD_DATA('A', 33)
    mc.PUSH('A')
    mc.STACK_DELTA('L')
    mc.NEW_VECTOR('T', 'L')
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

@Scenario()
def scenario20(mc):
    """Scenario with a pair of objects.
    """
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(10)
    mc.PUSH_DATA(11)
    mc.PUSH_DATA(12)
    mc.NEW_VECTOR_DELTA('T', 'L')
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(1)
    mc.PUSH_DATA(2)
    mc.PUSH_DATA(3)
    mc.PUSH('T')
    mc.STACK_DELTA('L')
    mc.NEW_VECTOR('T', 'L')
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

@Scenario()
def scenario30(mc):
    """Scenario with a single object that is repeatedly cloned to 
    create a large number of unreachable objects. These objects are
    then garbage collected.
    """
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(11)
    mc.PUSH_DATA(12)
    mc.PUSH_DATA(13)
    mc.STACK_DELTA('L')
    mc.NEW_VECTOR('T', 'L')
    for _ in range(60):
        mc.CLONE('T', 'T')
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

@Scenario()
def scenario40(mc):
    """Scenario with a large chain of objects. The root object has a single
    child, which has a single child, and so on.
    """
    mc.LOAD_DATA('L', 0)
    mc.NEW_VECTOR('CHAIN', 'L')
    mc.LOAD_DATA('L', 2)
    for i in range(10):
        mc.PUSH_DATA(i)
        mc.PUSH('CHAIN')
        mc.NEW_VECTOR('CHAIN', 'L')
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

@Scenario()
def scenario50(mc):
    """Scenario with a diamond shaped object graph. The root object
    has two children, each of which has a single child. 
    """
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(101)
    mc.PUSH_DATA(102)
    mc.PUSH_DATA(103)
    mc.NEW_VECTOR_DELTA('SharedGrandChild', 'L')
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(10)
    mc.PUSH('SharedGrandChild')
    mc.NEW_VECTOR_DELTA('Child1', 'L')
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(11)
    mc.PUSH('SharedGrandChild')
    mc.NEW_VECTOR_DELTA('Child2', 'L')
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(1)
    mc.PUSH('Child1')
    mc.PUSH('Child2')
    mc.NEW_VECTOR_DELTA('Root', 'L')
    mc.LOAD_DATA('SharedGrandChild', -1)
    mc.LOAD_DATA('Child1', -1)
    mc.LOAD_DATA('Child2', -1)
    mc.show('Before GC')
    mc.garbageCollect('Manual GC')
    mc.show('After GC')

@Scenario()
def scenario60(mc):
    """Scenario with two vectors that point to each other. A reference counting
    strategy cannot collect these objects.
    """
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(555)
    mc.PUSH_DATA(-1)    # Placeholder for the second vector.
    mc.NEW_VECTOR_DELTA('Vector1', 'L')
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(666)
    mc.PUSH('Vector1')
    mc.NEW_VECTOR_DELTA('Vector2', 'L')
    mc.SET_FIELD('Vector1', 1, 'Vector2')
    mc.LOAD_DATA('Vector1', -1)
    mc.LOAD_DATA('Vector2', -1)
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

@Scenario()
def scenario100(mc):
    """Scenario with a mixture of store that is unreachable, reachable and 
    shared.
    """
    mc.LOAD_DATA('A', 10)
    mc.LOAD_DATA('B', 20)
    mc.LOAD_DATA('C', 30)
    mc.STACK_LENGTH('L')
    mc.PUSH('A')
    mc.PUSH('B')
    mc.PUSH('C')
    mc.NEW_VECTOR_DELTA('T', 'L')
    mc.STACK_LENGTH('L')
    mc.CLONE('T', 'T')
    mc.PUSH('T')
    mc.PUSH('T')
    mc.NEW_VECTOR_DELTA('T', 'L')
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

def list_scenarios():
    print("Available scenarios:")
    for name in sorted(SCENARIOS.keys(), key=lambda x: int(x) if x.isdigit() else x):
        print(f" --scenario={name}")
        doc = SCENARIOS[name].__doc__
        if doc:
            print(f"   {doc}")
        else:
            print()

def main():
    argparser = argparse.ArgumentParser(description="Cheney-style garbage collector")
    argparser.add_argument("--scenario", default='0', help="Scenario to run")
    argparser.add_argument("--list", action='store_true', help="List the available scenarios")
    args = argparser.parse_args()
    if args.list:
        list_scenarios()
    else:
        gctrace = GCEventLogger()
        if args.scenario in SCENARIOS:
            scenario = SCENARIOS[args.scenario]
            scenario(Machine(gctrace))
        else:
            print(f"Invalid scenario '{args.scenario}' selected.")
            print()
            list_scenarios()

if __name__ == "__main__":
    main()
