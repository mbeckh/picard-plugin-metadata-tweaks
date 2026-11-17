# Copyright 2026 Michael Beckh (mbeckh)
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

"""Patch MetadataBox to show addtional values."""

from __future__ import annotations

from typing import TYPE_CHECKING

from picard.const.tags import ALL_TAGS

from picard.ui.metadatabox import (
    MetadataBox,
    TagDiff,
)

from . import monkey


if TYPE_CHECKING:
    from collections.abc import Callable

    from picard.config import Config
    from picard.file import File
    from picard.metadata import Metadata
    from picard.plugin3.api import PluginApi


_api: PluginApi
_enabled = False


def _format_size(metadata: Metadata) -> list[str]:
    return [
        _api.trn('variable.filesize.format', "{size:n} Byte", "{size:n} Bytes", size=int(size))
        for size in metadata.getall('~filesize')
    ]


@monkey.patch(MetadataBox, MetadataBox._add_files_to_tag_diff)
def _monkey_MetadataBox_add_files_to_tag_diff(  # ruff: ignore[too-many-positional-arguments]
    wrapped: Callable[[MetadataBox, set[File], TagDiff, Config, list[str]], None],
    self: MetadataBox,
    files: set[File],
    tag_diff: TagDiff,
    config: Config,
    top_tags: list[str],
) -> None:
    """Add additional variables to metadata box."""
    wrapped(self, files, tag_diff, config, top_tags)

    if not _enabled:
        return

    setting = config.setting
    plugin_config = _api.plugin_config
    for file in files:
        orig_metadata = file.orig_metadata
        new_metadata = file.metadata

        for name in (
            '~file_created_timestamp',
            '~file_modified_timestamp',
            '~reldirname',
            '~filename_and_extension',
            '~filesize',
        ):
            if name in orig_metadata or name in new_metadata:
                tv = ALL_TAGS.tagvar_from_name(name)
                readonly = tv.is_read_only if tv else False

                if name == '~filesize':
                    orig_values = _format_size(orig_metadata)
                    new_values = _format_size(new_metadata)
                else:
                    orig_values = file.format_specific_metadata(orig_metadata, name, setting)
                    new_values = file.format_specific_metadata(new_metadata, name, setting)
                    if name == '~file_created_timestamp':
                        readonly = readonly or plugin_config['file_set_created']
                    elif name == '~file_modified_timestamp':
                        readonly = readonly or plugin_config['file_set_modified']
                tag_diff.add(name, old=orig_values, new=new_values, removable=False, readonly=readonly)


def enable(api: PluginApi) -> None:
    """Add the patches (called from main module)."""
    global _api, _enabled
    _api = api

    _enabled = True


def disable() -> None:
    """Remove the patches (called from main module)."""
    global _api, _enabled

    _enabled = False
    del _api
