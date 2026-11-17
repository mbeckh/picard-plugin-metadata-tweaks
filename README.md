# Metadata Tweaks
![Latest Version](https://img.shields.io/github/v/tag/mbeckh/picard-plugin-metadata-tweaks?sort=semver&filter=v*&style=flat-square&label=latest)
![Supports](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmbeckh%2Fpicard-plugin-metadata-tweaks%2Frefs%2Fheads%2Fmain%2F.works_with.yml&query=%24.picard.from&prefix=picard+%3E%3D&style=flat-square&label=supports&color=orange)
![Tested with](https://img.shields.io/badge/dynamic/yaml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmbeckh%2Fpicard-plugin-metadata-tweaks%2Frefs%2Fheads%2Fmain%2F.works_with.yml&query=%24.picard.latest&prefix=picard+%3C%3D&style=flat-square&label=tested+with&color=green)

A plugin for [MusicBrainz Picard](https://picard.musicbrainz.org) to manage metadata and timestamps of the tagging workflow.

## What it Does

The plugins adds more tags, sets file times and provides a way for calculated tag values using a script executed even after manual changes in the UI.

### Variables and Tags
File creation and modification timestamps, relative directory name (to move target), filename with extension and file size are added to the meta data view.

The plugin adds the following variables and ID3 tags:

| Variable | ID3 Tag |
| --- | --- |
| `category` | `TCAT` |
| `encodingtime` | `TDEN` |
| `taggingtime` | `TDTG` |
| `produced` | `TPRO` |
| `radiostationname` | `TRSN` |
| `radiostationowner` | `TRSO` |
| `~reldirname` | - |
| `~filename_and_extension` | - |

> [!TIP]
> The rather uncommon tags related to internet radio stations can be used to make data available for iTunes.

### Scripting
A script can be configured to run after any meta data updates, even those made in the UI. This makes it possible to have the value of a tag calculated based on the values of other tags and keep that in sync even when the tags are updated in the UI.

The plugin also adds three scripting functions:
* `$to_utc(date[, default])`\
  Converts a date with optional time from local time to UTC.
* `$from_utc(date[, default])`\
  Converts a date with optional time from UTC to local time.
* `$datediff(start, end[, unit=d])`\
  Calculates the difference in local time between two dates.

### Timestamps
#### File Creation and Modification Timestamps
The plugin optionally manages file creation and modification times in the tagging workflow. File creation time is available on Windows only.

Tf the global option to preserve timestamps is _not_ set, file creation and modification time can be set from a variable or tag.

#### Meta Data Updated Timestamps
The plugin also provides a way to set an updated modification timestamp (UTC) in a variable or tag. This variable or tag can then in turn be used to e.g. set the file timestamps.

The plugin takes care that all files saved in a single operation will get the same timestamp (down to the nanosecond).

#### Touch Timestamp
When the file creation and modification timestamps are set based on meta data or the option to preserve timestamps is set, a change to a does not change file meta data and might also not change the file size. In this case, backup tools might miss the change and not update the copy in the backup.

To account for this, an option to encode a touch timestamp in the file creation and modification timestamps is available. When set, this adds sub-second data with resolution of 0.1s to the file times.

> [!IMPORTANT]
> This plugin requires the [Monkey Plugin](https://github.com/mbeckh/picard-plugin-monkey/) as a prerequisite. Please install this plugin first.

This plugin modifies Picard _way beyond_ the level that was intended by the implementers of the official API. It relies heavily on internal and private implementation details and monkey patches its way across the Picard code base to achieve its goals.

> [!WARNING]
> **Even a minor update of Picard can break this plugin** until I'm able to supply an updated version. The plugin is typically tested with the latest version of Picard only.

## License

The code is released under the Apache License Version 2.0. Please see [LICENSE](LICENSE) for details and [NOTICE](NOTICE) for the required information when using picard-plugin-metadata-tweaks in your own work.
