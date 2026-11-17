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

"""Add some more tags and variables to Picard and change configuration of some existing ones."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from picard.const.tags import ALL_TAGS
from picard.formats.id3 import ID3File
from picard.plugin3.api import PluginApi, t_
from picard.tags import TagVar


if TYPE_CHECKING:

    class _MonkeyID3File(ID3File):
        """Helper for type checking."""

        _ID3File__translate: MappingProxyType[str, str]
        _ID3File__rtranslate: MappingProxyType[str, str]


# Make some more standard tags available.
ADDITIONAL_STANDARD_TAGS = {
    'TCAT': TagVar(
        'category',
        shortdesc=t_('tag.category.name', "Category"),
        longdesc=t_('tag.category.desc', "The (podcast) category of this track (iTunes extension)."),
        is_from_mb=False,
        is_populated_by_picard=False,
        is_filterable=True,
    ),
    'TDEN': TagVar(
        'encodingtime',
        shortdesc=t_('tag.encodingtime.name', "Encoding Time"),
        longdesc=t_('tag.encodingtime.desc', "A timestamp describing when the audio was encoded."),
        is_from_mb=False,
        is_populated_by_picard=False,
        is_filterable=True,
    ),
    'TDTG': TagVar(
        'taggingtime',
        shortdesc=t_('tag.taggingtime.name', "Tagging Time"),
        longdesc=t_('tag.taggingtime.desc', "A timestamp describing then the audio was tagged."),
        is_from_mb=False,
        is_populated_by_picard=False,
        is_filterable=True,
    ),
    'TPRO': TagVar(
        'produced',
        shortdesc=t_('tag.produced.name', "Produced Notice"),
        longdesc=t_(
            'tag.produced.desc',
            "The production copyright holder of the original sound, not the audio file itself. The string must begin with a year and a space.",
        ),
        is_populated_by_picard=False,
        is_multi_value=True,
        is_filterable=True,
    ),
    'TRSN': TagVar(
        'radiostationname',
        shortdesc=t_('tag.radiostationname.name', "Radio Station Name"),
        longdesc=t_(
            'tag.radiostationname.desc', "The name of the internet radio station from which the audio is streamed."
        ),
        is_from_mb=False,
        is_populated_by_picard=False,
        is_multi_value=True,
        is_filterable=True,
    ),
    'TRSO': TagVar(
        'radiostationowner',
        shortdesc=t_('tag.radiostationowner.name', "Radio Station Owner"),
        longdesc=t_(
            'tag.radiostationowner.desc',
            "The name of the owner of the internet radio station from which the audio is streamed.",
        ),
        is_from_mb=False,
        is_populated_by_picard=False,
        is_multi_value=True,
        is_filterable=True,
    ),
}

ADDITIONAL_VARIABLES = (
    TagVar(
        'reldirname',
        shortdesc=t_('variable.reldirname.name', "Relative Directory"),
        longdesc=t_('variable.reldirname.desc', "The path of the file relative to the target folder."),
        is_preserved=True,
        is_read_only=True,
        is_hidden=True,
        is_tag=False,
        is_calculated=True,
        is_file_info=True,
        is_from_mb=False,
        is_populated_by_picard=False,
        is_filterable=True,
    ),
    TagVar(
        'filename_and_extension',
        shortdesc=t_('variable.filename_and_extension.name', "File"),
        longdesc=t_('variable.filename_and_extension.desc', "The filename including the extension."),
        is_preserved=True,
        is_read_only=True,
        is_hidden=True,
        is_tag=False,
        is_calculated=True,
        is_file_info=True,
        is_from_mb=False,
        is_populated_by_picard=False,
        is_filterable=True,
    ),
)


# PATCH: Mapping stored in picard.formats.id3.ID3File.__translate
# PATCH: Mapping stored in picard.formats.id3.ID3File.__rtranslate
# PATCH: List of tags in picard.const.tags.ALL_TAGS
def enable(api: PluginApi) -> None:
    """Patch internal structures (called by main module).

    Raises:
        ValueError: If tag to add is already present.
    """
    id3_file_class = cast('_MonkeyID3File', ID3File)

    translate = dict(id3_file_class._ID3File__translate.items())
    rtranslate = dict(id3_file_class._ID3File__rtranslate.items())

    for tag, tv in ADDITIONAL_STANDARD_TAGS.items():
        if tag in translate or tv.name in rtranslate:
            raise ValueError(f"Tag {tag} already present")
        translate[tag] = tv.name
        rtranslate[tv.name] = tag

    id3_file_class._ID3File__translate = MappingProxyType(translate)
    id3_file_class._ID3File__rtranslate = MappingProxyType(rtranslate)

    # translation
    for tv in (*ADDITIONAL_STANDARD_TAGS.values(), *ADDITIONAL_VARIABLES):
        if tv._shortdesc:
            tv._shortdesc = api.tr(tv._shortdesc)
        if tv._longdesc:
            tv._longdesc = api.tr(tv._longdesc)

    # make created and modified timestamps editable
    for name in ('~file_created_timestamp', '~file_modified_timestamp'):
        tv = ALL_TAGS.tagvar_from_name(name)
        if tv:
            tv.is_preserved = False

    ALL_TAGS.extend(ADDITIONAL_STANDARD_TAGS.values())
    ALL_TAGS.extend(ADDITIONAL_VARIABLES)


def disable() -> None:
    """Unpatch internal structures (called by main module)."""
    id3_file_class = cast('_MonkeyID3File', ID3File)

    translate = dict(id3_file_class._ID3File__translate.items())
    rtranslate = dict(id3_file_class._ID3File__rtranslate.items())

    for tag, tv in ADDITIONAL_STANDARD_TAGS.items():
        del translate[tag]
        del rtranslate[tv.name]

    id3_file_class._ID3File__translate = MappingProxyType(translate)
    id3_file_class._ID3File__rtranslate = MappingProxyType(rtranslate)

    for tv in (*ADDITIONAL_STANDARD_TAGS.values(), *ADDITIONAL_VARIABLES):
        ALL_TAGS.remove(tv)

    # undo patch
    for name in ('~file_created_timestamp', '~file_modified_timestamp'):
        tv = ALL_TAGS.tagvar_from_name(name)
        if tv:
            tv.is_preserved = True
