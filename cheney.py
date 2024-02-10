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
    mc.LOAD('A', 10)  # Load a value into a register so it will show up in the output.  
    mc.show("Before")
    mc.garbageCollect("Manual GC")
    mc.show("After")

@Scenario()
def scenario1(mc):
    """Scenario with a single object and no garbage.
    """
    mc.STACK_LENGTH('L')
    mc.LOAD('A', 11)
    mc.PUSH('A')
    mc.LOAD('A', 22)
    mc.PUSH('A')
    mc.LOAD('A', 33)
    mc.PUSH('A')
    mc.STACK_DELTA('L')
    mc.NEW_OBJECT('L', 'R')
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

@Scenario()
def scenario2(mc):
    """Scenario with a pair of objects.
    """
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(10)
    mc.PUSH_DATA(11)
    mc.PUSH_DATA(12)
    # mc.STACK_DELTA('L')
    mc.NEW_OBJECT_DELTA('L', 'R')
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(1)
    mc.PUSH_DATA(2)
    mc.PUSH_DATA(2)
    mc.PUSH('R')
    mc.STACK_DELTA('L')
    mc.NEW_OBJECT('L', 'R')
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

@Scenario()
def scenario10(mc):
    """Scenario with a single object that is repeatedly cloned to 
    create a large number of unreachable objects. These objects are
    then garbage collected.
    """
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(11)
    mc.PUSH_DATA(12)
    mc.PUSH_DATA(13)
    mc.STACK_DELTA('L')
    mc.NEW_OBJECT('L', 'R')
    for _ in range(60):
        mc.CLONE('R', 'R')
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

@Scenario()
def scenario20(mc):
    """Scenario with a large chain of objects. The root object has a single
    child, which has a single child, and so on.
    """
    mc.LOAD('L', 0)
    mc.NEW_OBJECT('L', 'CHAIN')
    mc.LOAD('L', 2)
    for i in range(10):
        mc.PUSH_DATA(i)
        mc.PUSH('CHAIN')
        mc.NEW_OBJECT('L', 'CHAIN')
    mc.show("Before GC")
    mc.garbageCollect("Manual GC")
    mc.show("After GC")

@Scenario()
def scenario30(mc):
    """Scenario with a diamond shaped object graph. The root object
    has two children, each of which has a single child. 
    """
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(100)
    mc.PUSH_DATA(102)
    mc.PUSH_DATA(103)
    mc.NEW_OBJECT_DELTA('L', 'SharedGrandChild')
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(10)
    mc.PUSH('SharedGrandChild')
    mc.NEW_OBJECT_DELTA('L', 'Child1')
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(20)
    mc.PUSH('SharedGrandChild')
    mc.NEW_OBJECT_DELTA('L', 'Child2')
    mc.STACK_LENGTH('L')
    mc.PUSH_DATA(1)
    mc.PUSH('Child1')
    mc.PUSH('Child2')
    mc.NEW_OBJECT_DELTA('L', 'Root')
    mc.LOAD('SharedGrandChild', -1)
    mc.LOAD('Child1', -1)
    mc.LOAD('Child2', -1)
    mc.show('Before GC')
    mc.garbageCollect('Manual GC')
    mc.show('After GC')

@Scenario()
def scenario31(mc):
    """Scenario with a mixture of store that is unreachable, reachable and 
    shared.
    """
    mc.LOAD('A', 10)
    mc.LOAD('B', 20)
    mc.LOAD('C', 30)
    mc.STACK_LENGTH('L')
    mc.PUSH('A')
    mc.PUSH('B')
    mc.PUSH('C')
    mc.NEW_OBJECT_DELTA('L', 'R')
    mc.STACK_LENGTH('L')
    mc.CLONE('R', 'R')
    mc.PUSH('R')
    mc.PUSH('R')
    mc.NEW_OBJECT_DELTA('L', 'R')
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
        try:
            scenario = SCENARIOS[args.scenario]
            scenario(Machine(gctrace))
        except KeyError:
            print(f"Invalid scenario '{args.scenario}' selected.")
            print()
            list_scenarios()

if __name__ == "__main__":
    main()
