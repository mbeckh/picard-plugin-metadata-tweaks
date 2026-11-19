# Copyright 2023-2026 Michael Beckh (mbeckh)
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

"""Automatically update timestamps in the tagging process."""

from __future__ import annotations

from datetime import (
    UTC,
    datetime,
)
import os
from pathlib import Path
import re
import threading
from typing import (
    TYPE_CHECKING,
    Protocol,
    cast,
)

from picard.const.sys import IS_WIN
from picard.coverart.providers import CoverArtProviderLocal
from picard.file import FileIdentity
from picard.metadata import MultiMetadataProxy, _changed_score  # ruff: ignore[import-private-name]
from picard.plugin3.api import (
    File,
    Metadata,
    PluginApi,
    Track,
)
from picard.script import (
    ScriptError,
    ScriptParser,
)
from picard.tagger import Tagger
from picard.util import (
    IterableFiles,
    iter_files_from_objects,
)

from . import datefunctions, extra_tags, metadatabox, monkey
from .options import MetadataTweaksOptionsPage


if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable


if IS_WIN or TYPE_CHECKING:
    from ctypes import FormatError as ctypes_FormatError, byref, get_last_error as ctypes_get_last_error, windll
    from ctypes.wintypes import (
        FILETIME,
        HANDLE,
    )

_api: PluginApi
_enabled = False


class _TimestampedFile(Protocol):
    _mt_timestamp: datetime


def _rel_dirname(directory: str, base: str) -> str:
    if IS_WIN and os.path.splitdrive(directory)[0] != os.path.splitdrive(base)[0]:
        return directory
    return os.path.relpath(directory, base)


def _file_post_load_processor(api: PluginApi, file: File) -> None:
    """Add calculated metadata."""
    orig_metadata = file.orig_metadata

    setting = api.global_config.setting
    if setting['move_files']:
        orig_metadata['~reldirname'] = _rel_dirname(orig_metadata['~dirname'], setting['move_files_to'])
    else:
        orig_metadata['~reldirname'] = orig_metadata['~dirname']
    orig_metadata['~filename_and_extension'] = orig_metadata['~filename'] + '.' + orig_metadata['~extension']


@monkey.patch(Metadata, Metadata._compare_weighted)
def _monkey_Metadata_compare_weighted(  # ruff: ignore[too-many-positional-arguments]
    wrapped: Callable[
        [
            Metadata,
            dict[str, str | list[str]],
            dict[str, str | list[str]],
            set[str],
            set[str] | None,
            set[str] | None,
            bool,
        ],
        list[tuple[float, int]],
    ],
    self: Metadata,
    store_a: dict[str, str | list[str]],
    store_b: dict[str, str | list[str]],
    ignored: set[str],
    deleted_a: set[str] | None = None,
    deleted_b: set[str] | None = None,
    penalize_removed: bool = False,  # ruff: ignore[boolean-default-value-positional-argument, boolean-type-hint-positional-argument]
) -> list[tuple[float, int]]:
    """Compare variables which are normally left out of comparison.

    Returns:
        Result of call to wrapped Metadata._compare_weighted.
    """
    parts = wrapped(self, store_a, store_b, ignored, deleted_a, deleted_b, penalize_removed)
    if _enabled:
        for name in ('~file_created_timestamp', '~file_modified_timestamp', '~reldirname', '~filename_and_extension'):
            if name in store_a or name in store_b:
                sa = store_a.get(name)
                sb = store_b.get(name)
                if sa != sb:
                    parts.append((_changed_score(name, sa, sb), self._CHANGE_DEFAULT_WEIGHT))

    return parts


@monkey.patch(File, File._tags_to_update)
def _monkey_File_tags_to_update(
    wrapped: Callable[[File, list[str]], Generator[str]], self: File, ignored_tags: list[str]
) -> Generator[str]:
    """Yield additional names which are normally left out for comparison."""
    yield from wrapped(self, ignored_tags)
    if _enabled:
        names = set(self.metadata) | set(self.orig_metadata)
        yield from names & {
            '~file_created_timestamp',
            '~file_modified_timestamp',
            '~reldirname',
            '~filename_and_extension',
        }


def _save_file_times_to_metadata(metadata: Metadata | MultiMetadataProxy) -> None:
    setting = _api.global_config.setting
    if setting['preserve_timestamps']:
        return

    plugin_config = _api.plugin_config
    if IS_WIN and plugin_config['file_set_created']:
        set_created_from = plugin_config['file_set_created_from']
        if set_created_from:
            created = datefunctions.from_utc(metadata[set_created_from], raise_exception=False)
            if created:
                created = datetime.fromisoformat(created).replace(tzinfo=None).isoformat(sep=' ', timespec='seconds')
                metadata['~file_created_timestamp'] = created
    if plugin_config['file_set_modified']:
        set_modified_from = plugin_config['file_set_modified_from']
        if set_modified_from:
            modified = datefunctions.from_utc(metadata[set_modified_from], raise_exception=False)
            if modified:
                modified = datetime.fromisoformat(modified).replace(tzinfo=None).isoformat(sep=' ', timespec='seconds')
                metadata['~file_modified_timestamp'] = modified


@monkey.patch(File, File.update, priority=-10)
def _update_calculated_metadata(
    wrapped: Callable[[File, bool, bool], None],
    self: File,
    signal=True,  # ruff: ignore[boolean-default-value-positional-argument, missing-type-function-argument]
    update_selection=True,  # ruff: ignore[boolean-default-value-positional-argument, missing-type-function-argument]
) -> None:
    """Update timestamps and metadata from script. Must run after all metadata has been updated."""
    if not _enabled:
        wrapped(self, signal, update_selection)
        return

    setting = _api.global_config.setting
    plugin_config = _api.plugin_config

    new_metadata = self.metadata
    orig_metadata = self.orig_metadata
    metadata = MultiMetadataProxy(new_metadata, orig_metadata)

    # Reset update timestamp
    if plugin_config['metadata_set_timestamp']:
        set_timestamp_to = plugin_config['metadata_set_timestamp_to']
        metadata[set_timestamp_to] = orig_metadata[set_timestamp_to]

    # set file times
    _save_file_times_to_metadata(metadata)

    move_files = setting['move_files']
    base_dir = setting['move_files_to'] if move_files else None
    rename_files = setting['rename_files']

    new_name = (
        os.path.split(self.make_filename(self.filename, metadata, setting)) if move_files or rename_files else None
    )
    metadata['~reldirname'] = (
        _rel_dirname(new_name[0], base_dir) if move_files and new_name and base_dir else metadata['~dirname']
    )
    metadata['~filename_and_extension'] = (
        new_name[1] if rename_files and new_name else metadata['~filename'] + '.' + metadata['~extension']
    )

    if plugin_config['metadata_script']:
        script_name = plugin_config['metadata_script_name']
        if script_name:
            script = '\n'.join([
                text for _pos, name, _enabled, text in setting['list_of_scripts'] if name == script_name
            ])

            parser = ScriptParser()
            try:
                parser.eval(script, cast('Metadata', metadata))
            except ScriptError:
                _api.logger.exception("Failed to run tagger script %s on track", script_name)
            metadata.strip_whitespace()

    wrapped(self, signal, update_selection)


def _get_timestamp_name() -> str | None:
    plugin_config = _api.plugin_config

    if not plugin_config['metadata_set_timestamp']:
        return None
    return plugin_config['metadata_set_timestamp_to']


@monkey.patch(File, File.update, priority=10)  # run last
def _monkey_File_update(
    wrapped: Callable[[File, bool, bool], None],
    self: File,
    signal: bool = True,  # ruff: ignore[boolean-default-value-positional-argument, boolean-type-hint-positional-argument]
    update_selection: bool = True,  # ruff: ignore[boolean-default-value-positional-argument, boolean-type-hint-positional-argument]
) -> None:
    """Hook into update to update timestamp of metadata change."""
    if not _enabled:
        wrapped(self, signal, update_selection)
        return

    def update_timestamp() -> bool:
        set_timestamp_to = _get_timestamp_name()
        if not set_timestamp_to:
            return False

        # Update timestamp
        timestamp = datetime.now(UTC).isoformat(sep=' ', timespec='seconds')
        self.metadata[set_timestamp_to] = timestamp

        # file times might depend on tagging date
        _save_file_times_to_metadata(self.metadata)

        parent = self.parent_item
        if not isinstance(parent, Track) or not self.orig_metadata['~file_modified_timestamp']:
            # not an album or no file
            return True
        track = cast('Track', parent)
        album = track.album
        if not album:
            return True

        # all tracks of the album should get the same timestamp
        for file in album.iterfiles():
            if (
                file.state != File.State.CHANGED
                or file is self
                or file.metadata[set_timestamp_to] == timestamp
                or not isinstance(file.parent_item, Track)
            ):
                continue
            file.metadata[set_timestamp_to] = timestamp
            _save_file_times_to_metadata(file.metadata)
            if signal:
                file.update_item(update_selection=False)

        return True

    wrapped(self, signal and False, update_selection and False)

    if self.state == File.State.CHANGED and (update_timestamp() or signal):
        self.update_item(update_selection=update_selection)


@monkey.patch(Track, Track.update)
def _monkey_Track_update(
    wrapped: Callable[[Track, bool], None],
    self: Track,
    signal: bool = True,  # ruff: ignore[boolean-default-value-positional-argument, boolean-type-hint-positional-argument]
) -> None:
    """Run script on tracks."""
    if _enabled:
        plugin_config = _api.plugin_config
        if plugin_config['metadata_script']:
            script_name = plugin_config['metadata_script_name']
            if script_name:
                setting = _api.global_config.setting
                script = '\n'.join([
                    text for _pos, name, _enabled, text in setting['list_of_scripts'] if name == script_name
                ])

                metadata = MultiMetadataProxy(self.metadata, self.orig_metadata)
                parser = ScriptParser()
                try:
                    parser.eval(script, cast('Metadata', metadata))
                except ScriptError:
                    _api.logger.exception("Failed to run tagger script %s on track", script_name)
                metadata.strip_whitespace()
                signal = True

    wrapped(self, signal)


#
# Use a common timestamp for encoding current date in file times.
#
_tagger_lock = threading.Lock()


@monkey.patch(Tagger, Tagger.save)
def _monkey_Tagger_save(
    wrapped: Callable[[Tagger, Iterable[IterableFiles]], None], self: Tagger, objects: Iterable[IterableFiles]
) -> None:
    files = None
    if _enabled:
        plugin_config = _api.plugin_config
        touch_file = plugin_config['file_touch']
        if touch_file:
            files = list(iter_files_from_objects(objects, save=True))

    if files:
        now = datetime.now(UTC)
        with _tagger_lock:
            for file in files:
                if hasattr(file, '_mt_timestamp'):
                    _api.logger.error("Timestamp already set for file: %r", file)
                cast('_TimestampedFile', file)._mt_timestamp = now

    wrapped(self, objects)

    if files:
        with _tagger_lock:
            for file in files:
                if not hasattr(file, '_mt_timestamp'):
                    _api.logger.error("Timestamp not set for file: %r", file)
                else:
                    del cast('_TimestampedFile', file)._mt_timestamp


#
# Call Windows API to set file times
#


if IS_WIN:
    # 116444736000000000 = 1970-01-01 as FILETIME value
    _EPOCH_AS_FILETIME = 116444736000000000
    # 10000000 = 100s of nanoseconds
    _HUNDREDS_OF_NANOSECONDS = 10000000
    _TOUCH_VERSION = 0

    def _epoch_to_filetime(epoch: float) -> FILETIME:
        # Convert Unix timestamp to Windows FileTime using some magic numbers
        timestamp = int((epoch * _HUNDREDS_OF_NANOSECONDS) + _EPOCH_AS_FILETIME)
        return FILETIME(timestamp & 0xFFFFFFFF, timestamp >> 32)

    def _code_into(filetime: FILETIME, coded_value: int) -> None:
        timestamp = filetime.dwLowDateTime + (filetime.dwHighDateTime << 32)
        timestamp = (
            round(timestamp / _HUNDREDS_OF_NANOSECONDS) * _HUNDREDS_OF_NANOSECONDS
            + coded_value % _HUNDREDS_OF_NANOSECONDS
        )
        filetime.dwLowDateTime = timestamp & 0xFFFFFFFF
        filetime.dwHighDateTime = timestamp >> 32


def _set_file_times(
    filepath: str,
    created_epoch: float | None,
    modified_epoch: float | None,
    touch_datetime: datetime | None,
) -> None:
    """Set file times.

    Codes the touch_datetime into sub-seconds precision (Windows only).
    https://stackoverflow.com/questions/4996405/how-do-i-change-the-file-creation-date-of-a-windows-file

    Raises:
        OSError: If an error happens in the OS calls.
    """
    if IS_WIN:
        if created_epoch is None and modified_epoch is None and not touch_datetime:
            return

        filetime_created = _epoch_to_filetime(created_epoch) if created_epoch is not None else None
        filetime_modified = _epoch_to_filetime(modified_epoch) if modified_epoch is not None else None

        # Call Win32 API to modify the file creation date
        # 256: FILE_WRITE_ATTRIBUTES
        # 0: no sharing
        # 3: OPEN_EXISTING
        # 128: FILE_ATTRIBUTE_NORMAL
        h_file = windll.kernel32.CreateFileW(filepath, 256, 0, None, 3, 128, None)
        if h_file == HANDLE(-1).value:  # INVALID_HANDLE_VALUE
            last_error = ctypes_get_last_error()
            raise OSError(0, ctypes_FormatError(last_error), filepath, last_error)
        try:
            if touch_datetime:
                if filetime_created is None or filetime_modified is None:
                    # read current value if none provided
                    filetime_current_created = FILETIME() if filetime_created is None else None
                    filetime_current_modified = FILETIME() if filetime_modified is None else None
                    if not windll.kernel32.GetFileTime(
                        h_file,
                        filetime_current_created and byref(filetime_current_created),
                        None,
                        filetime_current_modified and byref(filetime_current_modified),
                    ):
                        last_error = ctypes_get_last_error()
                        raise OSError(0, ctypes_FormatError(last_error), filepath, last_error)

                    # Set created time and modified_time if not passed as an argument
                    filetime_created = (
                        cast('FILETIME', filetime_current_created) if filetime_created is None else filetime_created
                    )
                    filetime_modified = (
                        cast('FILETIME', filetime_current_modified) if filetime_modified is None else filetime_modified
                    )

                now = touch_datetime
                # each value of coded may use up to 7 digits (i.e. the number of zeros in HUNDREDS_OF_NANOSECONDS)
                coded_date = _TOUCH_VERSION * 1000000 + (now.year % 100) * 10000 + now.month * 100 + now.day
                coded_time = now.hour * 100000 + now.minute * 1000 + now.second * 10 + (now.microsecond // 100000) % 10

                _api.logger.debug(
                    'Created (%d, %d): %r', filetime_created.dwHighDateTime, filetime_created.dwLowDateTime, filepath
                )
                _api.logger.debug(
                    'Modified (%d, %d): %r', filetime_modified.dwHighDateTime, filetime_modified.dwLowDateTime, filepath
                )

                # Code current time into sub-second precision of created and modified time
                # version, year, month and day are saved into created time
                _code_into(filetime_created, coded_date)
                # hours, minutes, seconds and tenths of a second are saved into modified time
                _code_into(filetime_modified, coded_time)

                _api.logger.debug(
                    'Created (coded %d) (%d, %d): %r',
                    coded_date,
                    filetime_created.dwHighDateTime,
                    filetime_created.dwLowDateTime,
                    filepath,
                )
                _api.logger.debug(
                    'Modified (coded %d) (%d, %d): %r',
                    coded_time,
                    filetime_modified.dwHighDateTime,
                    filetime_modified.dwLowDateTime,
                    filepath,
                )
            if not windll.kernel32.SetFileTime(
                h_file,
                filetime_created and byref(filetime_created),
                None,
                filetime_modified and byref(filetime_modified),
            ):
                last_error = ctypes_get_last_error()
                raise OSError(0, ctypes_FormatError(last_error), filepath, last_error)
        finally:
            windll.kernel32.CloseHandle(h_file)
    elif modified_epoch is None:
        return
    else:
        os.utime(filepath, times=(modified_epoch, modified_epoch))


def _get_touch_timestamp(file: File) -> datetime | None:
    plugin_config = _api.plugin_config
    if not plugin_config['file_touch']:
        return None

    if not hasattr(file, '_mt_timestamp'):
        raise ValueError("File has no touch timestamp.")
    return cast('_TimestampedFile', file)._mt_timestamp


def _set_file_timestamps(file: File) -> None:
    """Set file times on save.

    Raises:
        ValueError: If the file has no touch timestamp.
        OSError: If setting the file timestamps fails.
    """
    filepath = file.filename

    st = Path(filepath).stat()

    # set timestamps
    setting = _api.global_config.setting
    preserve_timestamps = setting['preserve_timestamps']
    plugin_config = _api.plugin_config
    touch_timestamp = _get_touch_timestamp(file)

    metadata = file.metadata

    if preserve_timestamps:
        if touch_timestamp:
            _set_file_times(filepath, int(st.st_birthtime), int(st.st_mtime), touch_timestamp)
    else:
        set_created = IS_WIN and plugin_config['file_set_created']
        set_modified = plugin_config['file_set_modified']

        if set_created or set_modified or touch_timestamp:
            created_str = metadata['~file_created_timestamp'] if set_created else None
            created_epoch = int(datetime.fromisoformat(created_str).astimezone().timestamp()) if created_str else None

            modified_str = metadata['~file_modified_timestamp'] if set_modified else None
            modified_epoch = (
                int(datetime.fromisoformat(modified_str).astimezone().timestamp()) if modified_str else None
            )

            _set_file_times(filepath, created_epoch, modified_epoch, touch_timestamp)

    file._file_identity = FileIdentity(filepath)
    file._update_filesystem_metadata(file.orig_metadata)


# Rename cover


def _get_cover_types(string: str) -> tuple[str, list[str]]:
    found = {x.lower() for x in CoverArtProviderLocal._types_split_re.split(string) if x}
    types = list(found.intersection(CoverArtProviderLocal._known_types))

    if not types:
        return '', []
    if 'front' in types:
        return 'front', types
    return types[0], types


def _get_min_dates_in_folder(
    current_dir: Path, cover_path: Path, *, set_created: bool, set_modified: bool
) -> tuple[int | None, int | None]:
    if not set_created and not set_modified:
        raise ValueError("Must either set created or modified timestamp.")

    extensions = _api.tagger.format_registry.supported_extensions()
    min_createdat = None
    min_modifiedat = None
    min_created_file = None
    min_modified_file = None

    for root, _dirs, files in current_dir.walk():
        for filepath in filter(lambda path: path.suffix in extensions, map(root.joinpath, files)):
            st = filepath.stat()
            if set_created:
                createdat = int(st.st_birthtime)
                if min_createdat is None or createdat < min_createdat:
                    min_createdat = createdat
                    min_created_file = filepath
            if set_modified:
                modifiedat = int(st.st_mtime)
                if min_modifiedat is None or modifiedat < min_modifiedat:
                    min_modifiedat = modifiedat
                    min_modified_file = filepath

    if min_createdat is not None and min_created_file:
        _api.logger.debug(
            "File created time for %r based on %r",
            os.path.relpath(cover_path, current_dir),
            os.path.relpath(min_created_file, current_dir),
        )
    if min_modifiedat is not None and min_modified_file:
        _api.logger.debug(
            "File modified time for %r based on %r",
            os.path.relpath(cover_path, current_dir),
            os.path.relpath(min_modified_file, current_dir),
        )

    return (min_createdat, min_modifiedat)


def _set_cover_timestamps(file: File) -> None:
    setting = _api.global_config.setting
    if setting['preserve_timestamps']:
        return

    plugin_config = _api.plugin_config
    set_created = IS_WIN and plugin_config['file_set_created']
    set_modified = plugin_config['file_set_modified']

    if not set_created and not set_modified:
        return

    pattern_thumbnail = plugin_config['cover_thumbnail_regex']
    pattern_unprocessed = plugin_config['cover_unprocessed_regex']
    naming_format = plugin_config['cover_unprocessed_name']

    if not pattern_thumbnail and (not pattern_unprocessed or not naming_format):
        return

    regex_unprocessed = re.compile(pattern_unprocessed, re.IGNORECASE) if pattern_unprocessed else None
    regex_thumbnail = re.compile(pattern_thumbnail, re.IGNORECASE) if pattern_thumbnail else None
    min_dates = None

    current_dir = Path(file.filename).parent
    for root, _dirs, files in current_dir.walk():
        for filename in files:
            if (not regex_unprocessed or not regex_unprocessed.search(filename)) and (
                not regex_thumbnail or not regex_thumbnail.search(filename)
            ):
                continue

            cover_path = root / filename

            if min_dates is None:
                min_dates = _get_min_dates_in_folder(
                    current_dir, cover_path, set_created=set_created, set_modified=set_modified
                )
            st = cover_path.stat()
            if (set_created and min_dates[0] != int(st.st_birthtime)) or (
                set_modified and min_dates[1] != int(st.st_mtime)
            ):
                _set_file_times(str(cover_path), min_dates[0], min_dates[1], _get_touch_timestamp(file))


def _file_post_save_processor(_api: PluginApi, file: File) -> None:
    """Update timestamps after saving."""
    _set_file_timestamps(file)
    _set_cover_timestamps(file)


def enable(api: PluginApi) -> None:
    """Enable plugin and set up submodules."""
    global _api, _enabled

    _api = api
    _enabled = True

    datefunctions.enable(api)
    extra_tags.enable(api)
    metadatabox.enable(api)

    api.plugin_config.register_option(
        'metadata_script',
        default=False,
        title=api.tr('options.metadata_script', "Run script after any updates"),
        in_profile=True,
    )
    api.plugin_config.register_option(
        'metadata_script_name',
        default='',
        title=api.tr('options.metadata_script_name', "Name of script to calculate metadata"),
        in_profile=True,
    )

    api.plugin_config.register_option(
        'file_set_created',
        default=False,
        title=api.tr('options.file_set_created', "Set file created time"),
        in_profile=True,
    )
    api.plugin_config.register_option(
        'file_set_created_from',
        default='encodingtime',
        title=api.tr('options.file_set_created_from', "Name of variable to use for file created time"),
        in_profile=True,
    )
    api.plugin_config.register_option(
        'file_set_modified',
        default=False,
        title=api.tr('options.file_set_modified', "Set file last modified time"),
        in_profile=True,
    )
    api.plugin_config.register_option(
        'file_set_modified_from',
        default='taggingtime',
        title=api.tr('options.file_set_modified_from', "Name of variable to use for file last modified time"),
        in_profile=True,
    )
    api.plugin_config.register_option(
        'metadata_set_timestamp',
        default=False,
        title=api.tr('options.metadata_set_timestamp', "Set current tagging timestamp to metadate variable"),
        in_profile=True,
    )
    api.plugin_config.register_option(
        'metadata_set_timestamp_to',
        default='taggingtime',
        title=api.tr('options.metadata_set_timestamp_to', "Name of metadata variable for tagging timestamp"),
        in_profile=True,
    )

    api.plugin_config.register_option(
        'file_touch',
        default=False,
        title=api.tr('options.file_touch', "Encode update timestamp in file times"),
        in_profile=True,
    )

    api.register_file_post_load_processor(_file_post_load_processor, 100)
    api.register_file_post_save_processor(_file_post_save_processor, -100)

    api.register_options_page(MetadataTweaksOptionsPage)


def disable() -> None:
    """Disable plugin and tear down submodules."""
    global _api, _enabled

    metadatabox.disable()
    extra_tags.disable()
    datefunctions.disable()

    monkey.unpatch_module(__name__)

    _enabled = False
    del _api
