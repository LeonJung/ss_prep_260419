"""Reference SubJob implementations.

Importing the package is enough to register every example SubJob via
@register_state, so the HFSM executor can pick them up with:

    ros2 launch mw_bringup navigate_test.launch.py \\
        subjob_modules:="['mw_hfsm_examples']"
"""

from .visit_three_points import VisitThreePoints

__all__ = ['VisitThreePoints']
