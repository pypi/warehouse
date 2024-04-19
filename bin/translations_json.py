#!/usr/bin/env python3

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

import json
import pathlib

import polib

from warehouse.i18n import KNOWN_LOCALES

"""

"""

domain = "messages"
localedir = "warehouse/locale"
languages = [locale for locale in KNOWN_LOCALES]
cwd = pathlib.Path().cwd()
print("\nCreating messages.json files\n")

# look in each language file that is used by the app
for lang in languages:
    # read the .po file to find any .js file messages
    entries = []
    include_next = False

    po_path = cwd.joinpath(localedir, lang, 'LC_MESSAGES', 'messages.po')
    if not po_path.exists():
        continue
    po = polib.pofile(po_path)
    for entry in po.translated_entries():
        occurs_in_js = any(o.endswith('.js') for o, _ in entry.occurrences)
        if occurs_in_js:
            entries.append(entry)

    # if one or more translation messages from javascript files were found,
    # then write the json file to the same folder.
    result = {
        "locale": lang,
        "plural-forms": po.metadata['Plural-Forms'],
        "entries": {e.msgid: {
            "flags": e.flags,
            "msgctxt": e.msgctxt,
            "msgid": e.msgid,
            "msgid_plural": e.msgid_plural,
            "msgid_with_context": e.msgid_with_context,
            "msgstr": e.msgstr,
            "msgstr_plural": e.msgstr_plural,
            "prev_msgctxt": e.previous_msgctxt,
            "prev_msgid": e.previous_msgid,
            "prev_msgid_plural": e.previous_msgid_plural,
        } for e in entries},
    }
    json_path = po_path.with_suffix('.json')
    with json_path.open('w') as f:
        print(f"Writing messages to {json_path}")
        json.dump(result, f)
