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

"""Plugin options page."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, ClassVar, override

from picard.const.sys import IS_WIN
from picard.plugin3.api import (
    OptionsPage,
    PageOptionConfigs,
    t_,
)

from .ui_compiled.ui_options import Ui_MetadataTweaksOptionsPage


if TYPE_CHECKING:
    from PyQt6 import QtWidgets


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
