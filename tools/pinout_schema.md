# Pinout picture JSON (`wbs-pinout/1`)

Every pinout picture of a module (connector layouts, rear views, pin-out pages, plug
connections, strapping drawings) gets one JSON beside it:

    <module repo>/PINOUTS/<picture file name without extension>.pinout.json

It says what **that picture** shows, nothing more: read by eye from the drawing, never
copied from another file. The module's `RTO.json` and its KiCad symbol
(`KICAD/<code>.kicad_sym`) are built from these files and the RTO-144 sheet
(`tools/pinout_build.py`): inputs on the symbol's left, outputs on the right, inserts as
a send / return pair of their own, power on top, grounds at the bottom.

```json
{
  "schema": "wbs-pinout/1",
  "picture": "1974 - M462 - 462-04-004 - CONNECTOR REAR VIEW.jpg",
  "module": "M462",
  "applies_to": ["M462", "M462A", "M462B"],
  "pinout": true,
  "drawing": {"number": "462-04-004", "title": "M462, M462A, M462B EQUALIZER MODULE CONNECTOR REAR VIEW",
              "date": "1974-10", "issue": null, "drawn": "DM"},
  "connectors": [
    {"name": "P1", "kind": "edge", "contacts": 22, "rows": "A-Z opposite 1-22", "view": "rear",
     "part": null}
  ],
  "pins": [
    {"connector": "P1", "pin": "1", "also": "A", "as_drawn": "+  (INPUT)", "signal": "INPUT +",
     "kind": "in", "port": "INPUT", "polarity": "+"},
    {"connector": "P1", "pin": "3", "also": "C", "as_drawn": "INPUT SHIELD", "signal": "INPUT SHIELD",
     "kind": "shield", "port": "INPUT", "polarity": "shield"},
    {"connector": "P1", "pin": "19", "also": "W", "as_drawn": "-25 VOLTS", "signal": "-25 V",
     "kind": "power", "port": null, "polarity": null}
  ],
  "ports": [
    {"name": "INPUT",  "dir": "in",  "pins": {"+": "P1-1", "-": "P1-2", "shield": "P1-3"}},
    {"name": "OUTPUT", "dir": "out", "pins": {"+": "P1-15", "-": "P1-16"}}
  ],
  "inserts": [],
  "straps": [],
  "unread": [],
  "confidence": "high",
  "notes": ""
}
```

## Fields

- `pinout`: false when the picture turns out not to be a pinout (say why in `notes`; leave
  `pins` empty).
- `applies_to`: every model the title block or text names.
- `connectors[].name`: as drawn (P1, P2, J4 …); "P1" when the drawing names none and there
  is one connector. `rows`: how the contacts are labelled ("1-22", "A-Z opposite 1-22",
  "1-15 single row").
- `pins[]`: one per contact the picture labels (skip contacts drawn blank).
  - `pin`: the contact as the drawing numbers it. A row drawn with both a letter and a number
    (A | 1): the number in `pin`, the letter in `also`, and say in `notes` whether the label
    belongs to both sides or one.
  - `as_drawn`: the words beside the contact, exactly (brackets and arrows as text).
  - `signal`: a clean name, UPPER CASE, with polarity: "INPUT +", "LEFT OUT -", "+24 V",
    "COMMON", "N/C".
  - `kind`: one of `in` · `out` · `insert_send` · `insert_return` · `power` · `ground` ·
    `shield` · `control_in` · `control_out` · `bus` · `strap` · `nc` · `other`.
  - `port`: the port the contact belongs to (null for power, ground, N/C).
  - `polarity`: `+` · `-` · `shield` · `L` · `R` · null.
- `ports[]`: each balanced / unbalanced signal once: `dir` `in` · `out` · `insert_send` ·
  `insert_return` · `control_in` · `control_out` · `bus` · `bidir`; `pins` maps polarity to
  "<connector>-<pin>".
- `inserts[]`: **an insert is special: always a pair.** `{"name": "INSERT", "send": "<port
  name>", "return": "<port name>", "normalled": true|false|null, "note": ""}`. The send is
  the module's output to the outboard gear (dir `insert_send`), the return its input back
  (dir `insert_return`). EQ / compressor / fader inserts, "insert out / insert in",
  "send / return", "pre-fader out / fader return" count.
- `straps[]`: jumpers and strap options: `{"name", "pins": ["P2-Z", "P2-W"], "note"}`.
- `unread[]`: anything on the picture that could not be read, in words.
- `confidence`: `high` (clean drawing, every label read), `medium` (some guessed), `low`
  (poor scan, much guessed).
