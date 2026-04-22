"""Userdata container — scoped dict passed through state hierarchy.

Phase 1: minimal dict wrapper with attribute access.  Phase 2 may add
explicit scope separation (in vs out, parent vs child) and remapping.
"""

from __future__ import annotations

from typing import Any, Iterable


class Userdata:
    """Dict-backed container supporting both subscript and attribute access.

    `state.execute(userdata)` reads/writes keys through subscript or attribute.
    Values are arbitrary Python objects — convert to/from ROS messages at the
    boundary layer (skill server or action client), not inside states.
    """

    def __init__(self, initial: dict | None = None):
        self._data: dict[str, Any] = dict(initial) if initial else {}

    # subscript access
    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    # attribute access as sugar
    def __getattr__(self, key: str) -> Any:
        if key.startswith('_'):
            raise AttributeError(key)
        try:
            return self._data[key]
        except KeyError as err:
            raise AttributeError(key) from err

    def __setattr__(self, key: str, value: Any) -> None:
        if key.startswith('_'):
            super().__setattr__(key, value)
        else:
            self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def update(self, other: dict | 'Userdata') -> None:
        if isinstance(other, Userdata):
            self._data.update(other._data)
        else:
            self._data.update(other)

    def keys(self) -> Iterable[str]:
        return self._data.keys()

    def to_dict(self) -> dict[str, Any]:
        """Return a copy of the underlying dict (for serialization / snapshot)."""
        return dict(self._data)

    def __repr__(self) -> str:
        return f'Userdata({self._data!r})'
