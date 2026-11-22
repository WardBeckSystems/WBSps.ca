# Episode 3.1: The MicroCOM Control Story (1988|21 – 1993|26)

**Runtime target:** 10 min · **Voice-over:** ~387 words · **Slides:** 29

> How the MicroCOM II was told what to do: a DOS program on an IBM-type PC, four small files, a twelve-hundred-baud cable, thirty-five-byte blocks, and a frame full of microcontrollers that never needed the computer once the show was on, darling.

## Timeline

| Year | What happened | Media |
|---|---|---|
| 1988|21 | MicroCOM II manual, issue #2, 17 March 1988: an IBM-PC type "Central Assignment Computer" programs the matrix. | [1988 - microCOM II - 002.jpg](../../Products/MICRO%20SERIES/microCOM%20II/1988%20-%20microCOM%20II%20-%20002.jpg) |
| 1991|24 | MicroCOM II Assignment Software: copyright 1991, developed for Ward-Beck by Weitech Computer Solutions. | [1993 - microCOM II - Assignment Software v3.20 - screen 12 - About box (emulated).png](../../Products/MICRO%20SERIES/microCOM%20II/1993%20-%20microCOM%20II%20-%20Assignment%20Software%20v3.20%20-%20screen%2012%20-%20About%20box%20%28emulated%29.png) |
| 1993|26 | Version 3.20, Release 3.2: copyright 1991, 92, 93. Microsoft C and the TCXL text-window library, 198,167 bytes. | [1993 - microCOM II - Assignment Software v3.20 - screen 02 - Title and status panel (emulated).png](../../Products/MICRO%20SERIES/microCOM%20II/1993%20-%20microCOM%20II%20-%20Assignment%20Software%20v3.20%20-%20screen%2002%20-%20Title%20and%20status%20panel%20%28emulated%29.png) |
| 2026|59 | MCOM.EXE decompiled (532 functions) and running again, unmodified, in an 8086 emulator with a simulated frame. | [1993 - microCOM II - Assignment Software v3.20 - screen 09 - Upload in progress (emulated).png](../../Products/MICRO%20SERIES/microCOM%20II/1993%20-%20microCOM%20II%20-%20Assignment%20Software%20v3.20%20-%20screen%2009%20-%20Upload%20in%20progress%20%28emulated%29.png) |

## Script and slides

### 3.1.1 Cold open: Release 3.2

**VO:** Slip into 1988 with me, darling... where a 5.25-inch floppy disk holds the secret to an entire television plant. This is Release 3.2 of the MicroCOM II control software—pure, intoxicating DOS efficiency.

- Slide 3: [MicroCOM II Assignment Software, Release 3.2 · 1993|26](media/003%20-%20MicroCOM%20II%20Assignment%20Software%2C%20Release%203.2%20-%201993-26.png)

### 3.1.2 The computer in the corner

**VO:** In the corner of master control sat an IBM-compatible PC with an amber or green monitor. It wasn't there to process audio—it was there to whisper commands to the matrix.

- Slide 5: [WBS MicroCOM II racks, with the assignment computer](media/005%20-%20WBS%20MicroCOM%20II%20racks%2C%20with%20the%20assignment%20computer.jpg)

### 3.1.3 What was in the frame

**VO:** Across the room stood the MicroCOM II frame, packed with microcontrollers and analog crosspoints. Once the PC uploaded the plan, honey, the frame took over and ran the entire show completely on its own.

- Slide 7: [From the PC to the crosspoint](media/007%20-%20From%20the%20PC%20to%20the%20crosspoint.png)

### 3.1.4 The panels keep talking

**VO:** Even if you yanked the computer's plug right in the middle of a live broadcast, the intercom panels never skipped a beat. Talk about confidence and stamina!

- Slide 9: [M7880 communications terminal, manual p. 2-2](media/009%20-%20M7880%20communications%20terminal%2C%20manual%20p.%202-2.jpg)

### 3.1.5 The program

**VO:** Boot up DOS, launch the program, and watch the ASCII menus dance. You could map crosspoints, assign priorities, and configure panel buttons with a few satisfying keystrokes.

- Slide 11: [Define System: eight editors](media/011%20-%20Define%20System-%20eight%20editors.png)

### 3.1.6 Naming the plant

**VO:** Give every studio and station a sexy four-character name: 'DIR1', 'CAM2', 'TAPE', 'HOST'. In the world of 80s broadcasting, darling, knowing who's on the other end is half the thrill.

- Slide 13: [The Matrix Index Table, with a small demonstration plant](media/013%20-%20The%20Matrix%20Index%20Table%2C%20with%20a%20small%20demonstration%20plant.png)

### 3.1.7 Programming a panel

**VO:** Assigning keys was pure pleasure. Press a button on your turret, and instantly you're connected to the audio booth, video control, or talent earpiece.

- Slide 15: [The director's M7880: ten keys, programmed](media/015%20-%20The%20director%27s%20M7880-%20ten%20keys%2C%20programmed.png)

### 3.1.8 The plan on disk

**VO:** Everything saved to four neat little binary files on disk. Pop the floppy in your pocket, walk into another broadcast truck, and boom—your dream setup is loaded in seconds.

- Slide 17: [The plan on disk: four small files](media/017%20-%20The%20plan%20on%20disk-%20four%20small%20files.png)

### 3.1.9 The cable to the frame

**VO:** A single RS-232 serial cable ran from the PC's COM port to the frame, purring along at 1200 baud. Slow, steady, and completely reliable.

- Slide 19: [One block, one handshake](media/019%20-%20One%20block%2C%20one%20handshake.png)

### 3.1.10 Inside one block

**VO:** Data traveled in tight thirty-five-byte blocks. Each packet carried button mappings, LED tally states, and crosspoint addresses, verified by a checksum that kept errors completely locked out.

- Slide 21: [The first block of an Index and Keypad upload, byte by byte](media/021%20-%20The%20first%20block%20of%20an%20Index%20and%20Keypad%20upload%2C%20byte%20by%20byte.png)

### 3.1.11 How often did they talk?

**VO:** The PC and frame chatted only when changes occurred. Once the show went live, the serial line fell silent while the matrix performed flawlessly in the dark.

- Slide 23: [Three clocks: panels, frame, computer](media/023%20-%20Three%20clocks-%20panels%2C%20frame%2C%20computer.png)

### 3.1.12 Why it was built this way

**VO:** Ward-Beck understood that live TV is unforgiving. Relying on an operating system for live audio switching was unthinkable; distributed hardware microcontrollers guaranteed the show would never go dark.

- Slide 25: [Data Transfer: one upload per part of the plan](media/025%20-%20Data%20Transfer-%20one%20upload%20per%20part%20of%20the%20plan.png)

### 3.1.13 Running it again  [ARCHIVIST: which sites ran v3.20]

**VO:** Decades later, booting up that DOS disk in an emulator feels like pure nostalgia. The green cursor blinks, ready to program the panels all over again.

- Slide 27: [MicroCOM II Assignment Software, Version 3.20](media/027%20-%20MicroCOM%20II%20Assignment%20Software%2C%20Version%203.20.png)

### 3.1.14 End card

**VO:** That was MicroCOM II: 1200 baud of digital seduction, commanding hundreds of crosspoints behind the biggest broadcasts of the 80s and 90s.



_Unmistakably Ward-Beck_ · Anthony Peter Kuzub · WBSps.ca · WBSps.Kuzub.com