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

"""Plugin options page and patches for TagListEditor to support variables."""

from __future__ import annotations

from collections.abc import Generator
from functools import partial
from typing import TYPE_CHECKING, ClassVar, Protocol, cast, override

from picard.const.sys import IS_WIN
from picard.plugin3.api import (
    OptionsPage,
    PageOptionConfigs,
    PluginApi,
    t_,
)
from picard.tags import all_tag_vars

from picard.ui.options.interface_top_tags import InterfaceTopTagsOptionsPage
from picard.ui.widgets.completion_provider import CompletionChoicesProvider, CompletionMode
from picard.ui.widgets.editablelistview import AutocompleteItemDelegate
from picard.ui.widgets.taglisteditor import TagListEditor

from . import monkey
from .ui_compiled.ui_options import Ui_MetadataTweaksOptionsPage


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from PyQt6 import QtWidgets

_api: PluginApi
_enabled = False


class _EnhancedTagListDelegate(Protocol):
    _mt_completions: Iterable[str]


def with_system_variables(names: Iterable[str] | None = None) -> set[str]:
    """Adds variables required by plugin features.

    Args:
        names: A list of variable names, if empty, the list configured in the plugin is used.

    Returns:
        A set of all variables that should be treated like tags.
    """
    plugin_config = _api.plugin_config
    if names is None:
        additional_names = set(plugin_config['variables_show'])
    else:
        additional_names = set(names)

    if plugin_config['file_set_created']:
        additional_names.add('~file_created_timestamp')
    if plugin_config['file_set_modified']:
        additional_names.add('~file_modified_timestamp')

    return additional_names


def tag_for_ui(tag: str) -> str:
    """Coverts prefix from ~ to _.

    Args:
        tag: Tag to convert.

    Returns:
        Tag name to show in the UI.
    """
    return ('_' + tag[1:]) if tag.startswith('~') else tag


def tag_for_code(tag: str) -> str:
    """Coverts prefix from _ to ~.

    Args:
        tag: Tag to convert.

    Returns:
        Tag name suitable for use in code.
    """
    return ('~' + tag[1:]) if tag.startswith('_') else tag


def tag_plain(tag: str) -> str:
    """Coverts prefix from _ to ~.

    Args:
        tag: Tag to convert.

    Returns:
        Tag name suitable for use in code.
    """
    return tag[1:] if tag.startswith(('_', '~')) else tag


class MetadataTweaksOptionsPage(OptionsPage):
    """Plugin options page."""

    NAME = 'metadata_tweaks'
    TITLE = t_('ui.metadata_tweaks.title', "Metadata Tweaks")
    PARENT = 'plugins'

    OPTIONS: ClassVar[PageOptionConfigs] = {
        'metadata_set_timestamp': {'widgets': ['metadata_set_timestamp']},
        'metadata_set_timestamp_to': {'widgets': ['metadata_set_timestamp_to']},
        'metadata_script': {'widgets': ['metadata_script']},
        'metadata_script_name': {'widgets': ['metadata_script_name']},
        'file_set_created': {'widgets': ['file_set_created']},
        'file_set_created_from': {'widgets': ['file_set_created_from']},
        'file_set_modified': {'widgets': ['file_set_modified']},
        'file_set_modified_from': {'widgets': ['file_set_modified_from']},
        'file_touch': {'widgets': ['file_touch']},
        'variables_show': {'widgets': ['variables_show']},
    }

    @override
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.ui = Ui_MetadataTweaksOptionsPage()
        self.ui.setupUi(self)

        self.ui.metadata_set_timestamp.toggled.connect(self.ui.metadata_set_timestamp_to.setEnabled)
        self.ui.metadata_script.toggled.connect(self.ui.metadata_script_name.setEnabled)
        self.ui.file_set_created.toggled.connect(self.ui.file_set_created_from.setEnabled)
        self.ui.file_set_modified.toggled.connect(self.ui.file_set_modified_from.setEnabled)

        self.ui.metadata_set_timestamp_to.addItems(['encodingtime', 'taggingtime'])

        self.ui.file_set_created_from.addItems(['date', 'encodingtime', 'originaldate', 'releasedate', 'taggingtime'])
        self.ui.file_set_modified_from.addItems(['date', 'encodingtime', 'originaldate', 'releasedate', 'taggingtime'])

        completions_provider = CompletionChoicesProvider()
        builtin_variables = {*(tv.script_name() for tv in all_tag_vars() if tv.is_hidden)}
        variables = {
            *(
                name.strip('%')
                for name in completions_provider.build_choices(CompletionMode.VARIABLE, set(), builtin_variables, {})
            )
        }

        self.ui.variables_show.ui.tag_list_view.setItemDelegate(AutocompleteItemDelegate(sorted(variables)))

    @override
    def load(self) -> None:
        setting = self.api.global_config.setting
        plugin_config = self.api.plugin_config

        self.ui.metadata_script_name.clear()
        self.ui.metadata_script_name.addItems([
            name for _pos, name, _enabled, text in setting['list_of_scripts'] if text
        ])

        self.ui.metadata_set_timestamp.setChecked(plugin_config['metadata_set_timestamp'])
        self.ui.metadata_set_timestamp_to.setCurrentText(plugin_config['metadata_set_timestamp_to'])
        self.ui.metadata_script.setChecked(plugin_config['metadata_script'])
        self.ui.metadata_script_name.setCurrentText(plugin_config['metadata_script_name'])

        self.ui.file_set_created.setChecked(plugin_config['file_set_created'])
        self.ui.file_set_created_from.setCurrentText(plugin_config['file_set_created_from'])
        self.ui.file_set_modified.setChecked(plugin_config['file_set_modified'])
        self.ui.file_set_modified_from.setCurrentText(plugin_config['file_set_modified_from'])
        self.ui.file_touch.setChecked(plugin_config['file_touch'])

        self.ui.variables_show.update(plugin_config['variables_show'])
        self.ui.variables_show.set_user_sortable(False)

        self.ui.metadata_set_timestamp_to.setEnabled(self.ui.metadata_set_timestamp.isChecked())

        self.ui.metadata_script_name.setEnabled(self.ui.metadata_script.isChecked())

        self.ui.file_set_created.setEnabled(IS_WIN and not setting['preserve_timestamps'])
        self.ui.file_set_modified.setEnabled(not setting['preserve_timestamps'])

        self.ui.file_set_created_from.setEnabled(
            self.ui.file_set_created.isEnabled() and self.ui.file_set_created.isChecked()
        )
        self.ui.file_set_modified_from.setEnabled(
            self.ui.file_set_modified.isEnabled() and self.ui.file_set_modified.isChecked()
        )

        page = self.dialog.get_page('tags')
        page.ui.preserve_timestamps.toggled.connect(partial(self._update_file_options, page.ui.preserve_timestamps))

        # notify in case of updates
        model = self.ui.variables_show.ui.tag_list_view.model()
        if model:
            model.dataChanged.connect(self._update_top_tags)
            self._update_top_tags()

    @override
    def save(self) -> None:
        plugin_config = self.api.plugin_config

        plugin_config['metadata_set_timestamp'] = self.ui.metadata_set_timestamp.isChecked()
        plugin_config['metadata_set_timestamp_to'] = self.ui.metadata_set_timestamp_to.currentText()

        plugin_config['metadata_script'] = self.ui.metadata_script.isChecked()
        plugin_config['metadata_script_name'] = self.ui.metadata_script_name.currentText()

        plugin_config['file_set_created'] = self.ui.file_set_created.isChecked()
        plugin_config['file_set_created_from'] = self.ui.file_set_created_from.currentText()
        plugin_config['file_set_modified'] = self.ui.file_set_modified.isChecked()
        plugin_config['file_set_modified_from'] = self.ui.file_set_modified_from.currentText()
        plugin_config['file_touch'] = self.ui.file_touch.isChecked()
        plugin_config['variables_show'] = list(self.ui.variables_show.tags)

    def _update_file_options(self, source: QtWidgets.QCheckBox) -> None:
        self.ui.file_set_created.setEnabled(IS_WIN and not source.isChecked())
        self.ui.file_set_modified.setEnabled(not source.isChecked())
        self.ui.file_touch.setEnabled(IS_WIN)

        self.ui.file_set_created_from.setEnabled(
            self.ui.file_set_created.isEnabled() and self.ui.file_set_created.isChecked()
        )
        self.ui.file_set_modified_from.setEnabled(
            self.ui.file_set_modified.isEnabled() and self.ui.file_set_modified.isChecked()
        )

    def _update_top_tags(self: MetadataTweaksOptionsPage) -> None:
        top_tags_page = self.dialog.get_page('interface_top_tags')

        delegate = cast('AutocompleteItemDelegate', top_tags_page.ui.top_tags_list.ui.tag_list_view.itemDelegate())
        completions = cast('_EnhancedTagListDelegate', delegate)._mt_completions
        # add current selection and default
        additional_names = with_system_variables(self.ui.variables_show.tags)
        delegate._completions = sorted({*completions, *map(tag_for_ui, additional_names)})


#
# Patches for TagListEditor
#


@monkey.patch(TagListEditor, TagListEditor.tags)
def _monkey_TagListEditor_tags(
    wrapped: Callable[[TagListEditor], Generator[str]], self: TagListEditor
) -> Generator[str]:
    result = wrapped(self)

    if not isinstance(result, Generator):
        name = type(result).__name__
        raise TypeError(f"tags is expected to be an iterator but is of type {name}")

    yield from map(tag_for_code, result) if _enabled else result


@monkey.patch(TagListEditor, TagListEditor.update)
def _monkey_TagListEditor_update(
    wrapped: Callable[[TagListEditor, Iterable[str]], None], self: TagListEditor, tags: Iterable[str]
) -> None:
    if _enabled:
        tags = [*map(tag_for_ui, tags)]
    wrapped(self, tags)


@monkey.patch(InterfaceTopTagsOptionsPage, InterfaceTopTagsOptionsPage.__init__)
def _monkey_InterfaceTopTagsOptionsPage_init(
    wrapped: Callable[[InterfaceTopTagsOptionsPage, QtWidgets.QWidget | None], None],
    self: InterfaceTopTagsOptionsPage,
    parent: QtWidgets.QWidget | None = None,
) -> None:
    wrapped(self, parent)

    if _enabled:
        delegate = cast('AutocompleteItemDelegate', self.ui.top_tags_list.ui.tag_list_view.itemDelegate())
        completions = delegate._completions
        cast('_EnhancedTagListDelegate', delegate)._mt_completions = completions
        # add current selection and default
        additional_names = with_system_variables()
        delegate._completions = sorted({*completions, *map(tag_for_ui, additional_names)})


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
