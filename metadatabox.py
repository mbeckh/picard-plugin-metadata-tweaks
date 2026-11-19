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
from picard.extension_points import script_variables
from picard.util import titlecase

from picard.ui.metadatabox import (
    MetadataBox,
    TagDiff,
)

from . import monkey, options


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

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

    top_tags_set = set(top_tags)
    clear_existing_tags = setting['clear_existing_tags']

    for file in files:
        orig_metadata = file.orig_metadata
        new_metadata = file.metadata

        for name in options.get_all_additional_variables() & (set(orig_metadata) | set(new_metadata)):
            if name in tag_diff.status:  # TagDiff.tag_names is not yet set
                continue

            tv = ALL_TAGS.tagvar_from_name(name)
            readonly = tv.is_read_only if tv else False  # is_read_only includes preserved
            removable = not readonly

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
                elif not clear_existing_tags and not new_values:
                    new_values = list(orig_values or [''])

            removed = name in new_metadata.deleted_tags
            tag_diff.add(
                name,
                old=orig_values,
                new=new_values,
                removable=removable,
                removed=removed,
                readonly=readonly,
                top_tags=top_tags_set,
            )


def _longest_common_prefix(names: Iterable[str], sep: str = '_') -> str:
    """Tries to find the longest common delimited prefix in a number of strings.

    Args:
        names: The names to check. Leading separators are ignored in comparison.
        sep: Parts separator, defaults to underscore.

    Returns:
        The longest common prefix without any leading separator.
    """
    if not names:
        return ''

    split_names = [name.lstrip(sep).split(sep) for name in names]
    common_parts: list[str] = []

    for parts in zip(*split_names, strict=False):
        if all(part == parts[0] for part in parts[1:]):
            common_parts.append(parts[0])
        else:
            break

    return sep.join(common_parts)


def _beautify_variable_name(name: str) -> str:
    """Tries to get a human friendly name for a variable in case none was provided.

    Args:
        name: Variable name.

    Returns:
        A human friendly name for the UI.
    """
    name_plain = options.tag_plain(name)

    # get plugin id of variable (if any)
    ep_variables = script_variables.ext_point_script_variables
    plugin_id = [var.plugin_id for var in ep_variables if var.name == name_plain]
    if plugin_id:
        # strip common prefix of plugin (if any)
        prefix = _longest_common_prefix(var.name for var in ep_variables if var.plugin_id == plugin_id[0])
    else:
        prefix = ''

    # finally, replace underscores and capitalize
    display_name = name_plain[len(prefix) :].replace('_', ' ').strip()
    if not display_name:
        display_name = name_plain.replace('_', ' ').strip()

    return titlecase(display_name)


@monkey.patch(script_variables, script_variables.get_plugin_variable_title)
def _monkey_script_variables_get_plugin_variable_title(wrapped: Callable[[str], str | None], name: str) -> str | None:
    if _enabled:
        name_for_ui = options.tag_for_ui(name)
        return wrapped(name_for_ui) or _beautify_variable_name(name)
    return wrapped(name)


def enable(api: PluginApi) -> None:
    """Add the patches (called from main module)."""
    global _api, _enabled
    _api = api

    _enabled = True


def disable() -> None:
    """Remove the patches (called from main module)."""
    global _api, _enabled

    _enabled = False
    monkey.unpatch_module(__name__)
    del _api
