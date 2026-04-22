"""mw_hsm_engine — self-built Hierarchical FSM engine for Robot Task Manager.

Public API:
- State, StateMachine, BehaviorSM: the three engine class types.
- register_state: decorator for late-binding registration.
- StateRegistry: ID → class resolver.
- Userdata: dict-like scope container.
- HsmError, TransitionError, RegistryError: exceptions.
"""

from .exceptions import HsmError, TransitionError, RegistryError, SelfIterationError
from .userdata import Userdata
from .state import State, StateRegistry, register_state
from .state_machine import StateMachine
from .behavior_sm import BehaviorSM

__all__ = [
    'State',
    'StateMachine',
    'BehaviorSM',
    'StateRegistry',
    'register_state',
    'Userdata',
    'HsmError',
    'TransitionError',
    'RegistryError',
    'SelfIterationError',
]
