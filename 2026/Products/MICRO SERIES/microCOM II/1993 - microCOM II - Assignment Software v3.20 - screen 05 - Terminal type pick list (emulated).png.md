# 1993 - microCOM II - Assignment Software v3.20 - screen 05 - Terminal type pick list (emulated).png
Wiki page: [microCOM II](../../../PAGES/microCOM-II.md)


- **Year:** 1993 (program reads: Copyright 1991,92,93 WARD-BECK SYSTEMS)
- **Module:** microCOM II
- **Category:** MICRO SERIES
- **Note:** a picture made for the archive: the original MCOM.EXE v3.20 running unmodified in the mcom-tui 8086 emulator, its 80x25 text screen redrawn at 2160x1200. The demo setup (DIR, TD, AUD, FM, CAM1-4, IF01-02, PGM) was typed in for this picture; the date and time are from the day it was made. COM1 is connected to the simulated matrix frame.
- **Original file:** `WBSps.env/wbsPS-NOT UPLOADED/Microcom software/MCOM.EXE`
- **SHA-256:** `0ee81d9b056b92ac96ac4cbb7ab9f13c7bf8e35bd22c26058609acf41838ab0d`
- **Size:** 183,763 bytes
- **Pages:** 1

## Full text

### Page 1

```text
   Define System    Data Transfer   Terminal Assignments    Utilities   Quit
▀▀▀┌─────────────────────┐▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
   │ Matrix Index Table  │
  ┌───┬────┬────┬─────────┬───────────────────────┬────────┐    ┌───────────┐
  │Bus│Mnem│Ovly│Attribute│                       │Terminal│    │Prefix Code│
  │ # │Code│Code│T│L│M│I│P│      Description      │  Type  ┌────────┐Key Sec│
  ├───┼────┼────┼─┼─┼─┼─┼─┼───────────────────────┼────────│        ↑───────┤
  │001│DIR │    │x│x│ │ │ │Director               │        │M7880   │ 1     │
  │002│TD  │    │x│x│ │ │ │Technical Director     │        │M7880/81│ 2     │
  │003│AUD │    │x│x│ │ │ │Audio Mixer            │        │M7880B  │ 3     │
  │004│FM  │    │x│x│ │ │ │Floor Manager          │        │M7880D  ↓ 4     │
  │005│CAM1│    │x│x│ │ │ │Camera 1               │        └────────┘ 5     │
  │006│CAM2│    │x│x│ │ │ │Camera 2               │        │    │     6     │
  │007│CAM3│    │x│x│ │ │ │Camera 3               │        │    │     7     │
  │008│CAM4│    │x│x│ │ │ │Camera 4               │        │    │     8 IF..│
  │009│IF01│    │x│x│ │ │ │Anchor Earpiece        │        │    │     9     │
  │010│IF02│    │x│x│ │ │ │Host Earpiece          │        │    └───────────┘
  │011│PGM │    │x│x│ │ │ │Program Feed           │        │
  │012│$012│    │x│x│ │ │ │Default Mnemonics      │        │
  └───┴────┴────┴─┴─┴─┴─┴─┴───────────────────────┴────────┘hts reserved
 [F1]=Help  [ENTER]=Select  [F10]=Save  [ESC]=Abort  [CURSOR]=Browse Selections
 Drive \ Path:  C:\MICROCOM                  Systems ID: 00   Status: ON-LINE
 Active Matrix: MCOMFILE   Size: 048 x 048           Active Terminal: TERMINAL
 Date: October 22, 2026    Time: 7:29 AM             Active Overlay : OVERLAY
 F2..Select TerminSelect a Terminal Type for current Bus!Save/End  ESC..Abort
```
