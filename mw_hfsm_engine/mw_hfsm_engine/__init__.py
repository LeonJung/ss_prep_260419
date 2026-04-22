"""mw_hfsm_engine — self-built Hierarchical FSM engine for Robot Task Manager.

Public API:
- State, StateMachine, BehaviorSM: the three engine class types.
- register_state: decorator for late-binding registration.
- StateRegistry: ID → class resolver.
- Userdata: dict-like scope container.
- HfsmError, TransitionError, RegistryError: exceptions.
"""

from .exceptions import HfsmError, TransitionError, RegistryError, SelfIterationError
from .userdata import Userdata
from .state import State, StateRegistry, register_state
from .state_machine import StateMachine
from .behavior_sm import BehaviorSM
from .parallel import Parallel, Region
from .decorators import RetryDecorator
from .spec_loader import build_from_spec
from .observer import active_path, install_observer

__all__ = [
    'State',
    'StateMachine',
    'BehaviorSM',
    'Parallel',
    'Region',
    'RetryDecorator',
    'StateRegistry',
    'register_state',
    'Userdata',
    'HfsmError',
    'TransitionError',
    'RegistryError',
    'SelfIterationError',
    'build_from_spec',
    'active_path',
    'install_observer',
]
