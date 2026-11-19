# 1993 - microCOM II - Assignment Software v3.20 - screen 04 - Matrix Index Table (emulated).png
Wiki page: [microCOM II](../../../PAGES/microCOM-II.md)


- **Year:** 1993 (program reads: Copyright 1991,92,93 WARD-BECK SYSTEMS)
- **Module:** microCOM II
- **Category:** MICRO SERIES
- **Note:** a picture made for the archive: the original MCOM.EXE v3.20 running unmodified in the mcom-tui 8086 emulator, its 80x25 text screen redrawn at 2160x1200. The demo setup (DIR, TD, AUD, FM, CAM1-4, IF01-02, PGM) was typed in for this picture; the date and time are from the day it was made. COM1 is connected to the simulated matrix frame.
- **Original file:** `WBSps.env/wbsPS-NOT UPLOADED/Microcom software/MCOM.EXE`
- **SHA-256:** `ff4a7633a28386c9d88dce27811f93d78abbeb6e02d1d7b1a9e0b7e8e845cba4`
- **Size:** 177,086 bytes
- **Pages:** 1

## Full text

### Page 1

```text
   Define System    Data Transfer   Terminal Assignments    Utilities   Quit
▀▀▀┌─────────────────────┐▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
   │ Matrix Index Table  │
  ┌───┬────┬────┬─────────┬───────────────────────┬────────┐    ┌───────────┐
  │Bus│Mnem│Ovly│Attribute│                       │Terminal│    │Prefix Code│
  │ # │Code│Code│T│L│M│I│P│      Description      │  Type  │    │Pri Key Sec│
  ├───┼────┼────┼─┼─┼─┼─┼─┼───────────────────────┼────────┤    ├───────────┤
  │001│DIR │    │x│x│ │ │ │Director               │        │    │$0.. 1     │
  │002│TD  │    │x│x│ │ │ │Technical Director     │        │    │$1.. 2     │
  │003│AUD │    │x│x│ │ │ │Audio Mixer            │        │    │$2.. 3     │
  │004│FM  │    │x│x│ │ │ │Floor Manager          │        │    │     4     │
  │005│CAM1│    │x│x│ │ │ │Camera 1               │        │    │     5     │
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
 F2..Select Terminal  F3..Set Attributes  F4..Copy  F10..Save/End  ESC..Abort
```
