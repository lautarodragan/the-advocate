"""Names of the RPG Maker 2000 event command codes.

The table is `event_codes.json`, which comes from liblcf and is not edited by
hand; where from and with which command is in `tools/rpgmaker/README.md`.
Here it is only loaded, with the keys turned back into numbers —JSON only has
text keys—.

Codes not in the table are exported as a bare number.
"""

import json
import os

TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "event_codes.json")

with open(TABLE, encoding="utf-8") as _handle:
    EVENT_CODES = {int(code): name
                   for code, name in json.load(_handle).items()}

del _handle
