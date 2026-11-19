# 1993 - microCOM II - Assignment Software v3.20 - screen 06 - M7880 key assignment (emulated).png
Wiki page: [microCOM II](../../../PAGES/microCOM-II.md)


- **Year:** 1993 (program reads: Copyright 1991,92,93 WARD-BECK SYSTEMS)
- **Module:** microCOM II
- **Category:** MICRO SERIES
- **Note:** a picture made for the archive: the original MCOM.EXE v3.20 running unmodified in the mcom-tui 8086 emulator, its 80x25 text screen redrawn at 2160x1200. The demo setup (DIR, TD, AUD, FM, CAM1-4, IF01-02, PGM) was typed in for this picture; the date and time are from the day it was made. COM1 is connected to the simulated matrix frame.
- **Original file:** `WBSps.env/wbsPS-NOT UPLOADED/Microcom software/MCOM.EXE`
- **SHA-256:** `f0e1a60a0bfcc813b111a175014b9f61f4cdab183e09cefa24eb6cb6383129f9`
- **Size:** 156,782 bytes
- **Pages:** 1

## Full text

### Page 1

```text
   Define System    Data Transfer   Terminal Assignments    Utilities   Quit
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀┌─────────────────────┐▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
                                    │ Select Definition   │
                                    │ Assignment Edit     │
                      █▀█┌─────┬──────┬───────┬────────┐t │
                      █ █│ Bus#│ Code │Overlay│Terminal│t │
                      █ █├─────┼──────┼───────┼────────┤  │
                         │ 001 │ DIR  │       │M7880   │──┘
                    C O M│ 002 │ TD   │       │M7880   │ E M
                         │ 003 │ AUD  │       │M7880   │
           Station: DIR          Overlay:
           Bus No.: 001          Priority:   3
           Type:    M7880        Definition: TERMINAL
          ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
          █ KEYS ║ 1    2    3    4    5    6    A    B    C    D  █
          █══════╬════╤════╤════╤════╤════╤════╦════╤════╤════╤════█
          █ CODE ║TD  │AUD │FM  │CAM1│CAM2│CAM3║CAM4│IF01│IF02│GRP1█
          █ OVLY ║    │    │    │    │    │    ║    │    │    │    █
          █──────╫────┼────┼────┼────┼────┼────╫────┼────┼────┼────█
         @█ ATTR ║TL/ │TL/ │TL/ │TL/ │TL/ │TL/ ║TL/ │TL/ │TL/ │TL/ █rved
 [F1]=Help▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀ Selections
 Drive \ Path:  C:\MICROCOM                  Systems ID: 00   Status: ON-LINE
 Active Matrix: MCOMFILE   Size: 048 x 048           Active Terminal: TERMINAL
 Date: October 22, 2026    Time: 7:30 AM             Active Overlay : OVERLAY
  <F2> Select Code, <F3> Set Attribute, <F9> Upload, <F10> Save, <ESC> abort
```
