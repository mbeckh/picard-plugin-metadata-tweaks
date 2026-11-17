# Copyright 2023-2026 Michael Beckh
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Functions for both Python and Picard script to convert between timezones."""

from __future__ import annotations

from datetime import (
    UTC,
    datetime,
)
from enum import Enum
from typing import TYPE_CHECKING, overload


if TYPE_CHECKING:
    from picard.plugin3.api import (
        PluginApi,
        ScriptParser,
    )


_api: PluginApi


class _Conversion(Enum):
    TO_UTC = True
    FROM_UTC = False


_PATTERN_DATE = "2006-01-02"
_PATTERN_DATE_HOUR = "2006-01-02 03"
_PATTERN_DATE_HOUR_MINUTE = "2006-01-02 03:04"


def _convert_utc(datestr: str, conversion: _Conversion) -> str:
    """Convert datetime string to and from UTC.

    Returns:
        The converted string in ISO format.
    """
    if not datestr:
        return datestr

    dt = datetime.fromisoformat(datestr)

    length = len(datestr)
    if length <= len(_PATTERN_DATE):
        # no time conversion
        return dt.date().isoformat()
    if length <= len(_PATTERN_DATE_HOUR):
        ts = 'hours'
    elif length <= len(_PATTERN_DATE_HOUR_MINUTE):
        ts = 'minutes'
    else:
        ts = 'seconds'
    if conversion == _Conversion.TO_UTC:
        dt = dt.astimezone().astimezone(UTC).replace(tzinfo=None)
    elif conversion == _Conversion.FROM_UTC:
        dt = dt.replace(tzinfo=UTC).astimezone()
    return dt.isoformat(sep=' ', timespec=ts)


@overload
def to_utc(datestr: str, default: str, *, raise_exception: bool = True) -> str: ...


@overload
def to_utc(datestr: str, default: None = None, *, raise_exception: bool = True) -> str | None: ...


def to_utc(datestr: str, default: str | None = None, *, raise_exception: bool = True) -> str | None:
    """Convert a timestamp in string format from local time to UTC.

    Returns:
        The converted timestamp.

    Raises:
        ValueError: If both default and raise_exception are supplied.
    """
    if default is not None and raise_exception:
        raise ValueError("to_utc supports either default or exception.")
    try:
        return _convert_utc(datestr, _Conversion.TO_UTC)
    except Exception:
        if raise_exception:
            raise
        _api.logger.exception("Error converting %r to UTC", datestr)
    return default


@overload
def from_utc(datestr: str, default: str, *, raise_exception: bool = True) -> str: ...


@overload
def from_utc(datestr: str, default: None = None, *, raise_exception: bool = True) -> str | None: ...


def from_utc(datestr: str, default: str | None = None, *, raise_exception: bool = True) -> str | None:
    """Convert a timestamp in string format from UTC to local time.

    Returns:
        The converted timestamp.

    Raises:
        ValueError: If both default and raise_exception are supplied.
    """
    if default is not None and raise_exception:
        raise ValueError("to_utc supports either default or exception.")
    try:
        return _convert_utc(datestr, _Conversion.FROM_UTC)
    except Exception:
        if raise_exception:
            raise
        _api.logger.exception("Error converting %r to local time", datestr)
    return default


# Wrappers and functions for script


def _script_to_utc(_parser: ScriptParser, datestr: str = '', default: str = '') -> str:
    return to_utc(datestr, default, raise_exception=False)


def _script_from_utc(_parser: ScriptParser, datestr: str = '', default: str = '') -> str:
    return from_utc(datestr, default, raise_exception=False)


def _script_datediff(_parser: ScriptParser, from_str: str = '', to_str: str = '', unit: str = 'd') -> str:
    if unit != 'd':
        raise ValueError('datediff currently only supports days as unit.')

    if not from_str or not to_str or len(from_str) < len(_PATTERN_DATE) or len(to_str) < len(_PATTERN_DATE):
        return ''
    try:
        from_dt = datetime.fromisoformat(from_str).astimezone().astimezone(UTC)
        to_dt = datetime.fromisoformat(to_str).astimezone().astimezone(UTC)

        return str((to_dt - from_dt).days)
    except Exception:
        _api.logger.exception("Error calculating date difference of %r and %r", from_str, to_str)
    return ''


def enable(api: PluginApi) -> None:
    """Add the functions (called from main module)."""
    global _api

    _api = api
    _api.register_script_function(
        _script_to_utc,
        name='to_utc',
        documentation=api.tr('help.script.to_utc', "Converts a date with optional time from local time to UTC."),
        signature=api.tr('help.script.to_utc.signature', "$to_utc(date[, default])"),
    )
    _api.register_script_function(
        _script_from_utc,
        name='from_utc',
        documentation=api.tr('help.script.from_utc', "Converts a date with optional time from UTC to local time."),
        signature=api.tr('help.script.from_utc.signature', "$from_utc(date[, default])"),
    )
    _api.register_script_function(
        _script_datediff,
        name='datediff',
        documentation=api.tr('help.script.datediff', "Calculates the difference in local time between two dates."),
        signature=api.tr('help.script.datediff.signature', "$datediff(start, end[, unit=d])"),
    )


def disable() -> None:
    """Clear internal structures (called from main module)."""
    global _api

    del _api
