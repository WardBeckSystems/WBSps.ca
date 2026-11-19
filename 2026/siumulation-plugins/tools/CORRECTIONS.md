# Correction pass: facts later plugins proved wrong in earlier ones

ROOT = `/home/anthony/Documents/GitProjects/WBSps.ca/2026` (simulator: `siumulation.html`, plugins in `siumulation-plugins/`).
ARCHIVE = `/home/anthony/Downloads/WBS shuffler/WBS - DATA SHUFFLER` (product folders, read only).

For each item:
1. Read the **source** plugin's Findings tab and the archive files it cites, and confirm the fact yourself.
2. Change the **target** plugin as little as you can. Fix the model (constants, logic, labels) and its Findings/Software text.
3. Add a line to the target's Findings: `Corrected 2026|59: … (see <source plugin>)`.
4. Keep everything else unchanged. Follow `tools/BUILD_BRIEF.md` rules: inferred tags, privacy, no new files except `<id>-` assets, and no subagents.

After each target: run `node --check`, then load it alone (`file://ROOT/siumulation.html?load=<file>&plugin=<id>#<tab>`) in headless Chrome with `--virtual-time-budget=15000` and look at every tab. Use a `_test_<id>.html` copy in ROOT to catch runtime errors, and delete the copy afterwards.

| # | Target | Correction | Source of truth |
|---|---|---|---|
| 1 | d8208.js | PIC clock is 6.144 MHz (24.576 MHz ÷ 4 from the CPLD), not 3.58 MHz; the 3.58 MHz crystal belongs to the unused genlock chip. Rescale pass timings. | d8205.js, d8200.js (`d8200_top.rpt`) |
| 2 | d8210-d8212.js | MF8210 slot pitch is 1.260 in, not the inferred 1.2 in. | mfxx.js |
| 3 | d6204a.js | Calibration is analog: a 74HC4053 switches R66 6K49 / R73 8K06 / R75 16K2 in the output stage (+24/+22/+16 dBu), not FPGA gain. The DIP map from the netlist is SW1/SW2 cal, SW3 tone, SW7 OFF = DIP sets power-up defaults, SW8 ON = DashBoard lockout, SW4–6 unused. "Calibration: Disabled" mutes both pairs. | d6204.js |
| 4 | d6207a-docs.js | The compressed flag is active-high in the VHDL, so the two register-map documents are wrong, not the code. Program-mode codes: the manual's table rows agree with the MIB; only its MSB/LSB captions and the Mode2/Mode3 names are swapped. | d6207a.js |
| 5 | rav-24.js | The CPLD is an EPM7128SLC84-6, not EPM7256S (EPM7256S is only the first entry in the candidate-device list in `avs24.rpt`). | avs.js |
| 6 | rd69-vidbuddy-madibuddy.js | The VIDBuddy battery is about 11 Wh (450 mA charge × 2.0 h from the label and manual), not 21.6 Wh. Recompute the battery-life comparison. | avb-vid-buddy.js |
| 7 | pod15a.js | The real POD15A issue 3 netlist and BOM are in the obsolete POD15 folder. Replace the guessed circuit with the real one (ERROR = no-sync one-shot CD4538, ISL5002 on EL2244 footprint, outputs driven in pairs, differential input with BNC shell = IN−, issue 3 dropped issue 1's terminator switch). | pod15.js |
| 8 | pod11a.js | The POD11A manual is in the obsolete POD11 folder: BS1 ON = peak hold OFF, PPM decay 1.5 s or 3 s per 24 dB, peak LED above −3 dBFS, 30–96 kHz input, 41 LEDs per bar. The SLM-1 *analog* code it used as a stand-in is POD3A's own (CAL steps 0/+4/+8/+12 dBu). POD11A's firmware is most likely the digital SLM-1 master in `#SLM #SERIES …/SLM-1/sharc/slm-1-v1.0x` (inferred, from the 2004 functional diagram titled "POD11A AES/EBU MONITOR" with an "SLM1D Input"). Rebase the model on the manual and the digital SLM-1 code. | pod11.js, pod3a.js, slm.js |
| 9 | pod12a.js | The POD12A firmware is archived: the MCU is V020000 in the obsolete POD12 folder (`POD12 - #Engineering/…/#V020000/`, v100 in `RD77/Software/Atmel/backup1/v100`), and the FPGA is the D6201A project in `RD77/Software/FPGA/v100`. SRC takes INPUT A and outputs it on INPUT B's clock, enabled only when B is locked (not a fixed 48 kHz). The clock-steering loop is idle; the EQ is a second receiver input (0x80/0x89). Model from the real code. | pod12.js |
| 10 | pod13a.js | The POD13A firmware is archived in the obsolete POD13 folder: Atmel V100 (`POD13 - SOFTWARE #atmel/…#v100/`, ATmega128, `v100w.c`, bug: `DEBOUNCE_fs2` compares `pfs` instead of `pfs2`) and Lattice V100 (`POD13 - #SOFTWARE #lattice2/v100/pod13a.vhd`, `.jed`). `dec2_4.vhd` makes the unused 4th CAL setting switch all gains off, which is the test sheet's "Up/Up = Mute". Model from the real code. | pod13.js |
| 11 | pod23.js | The POD22 master that pod23 could not find is `Software/554265/pod22v1.asm` in the obsolete POD22 folder (Nov 2004, "Pod 22 communicating with 2 POD23s"). Use it for the 2003 link model if it fits, and update the Findings. | pod22.js |
| 12 | pod2.js | The POD9 slave button: in POD9 V102 the RA1 read is commented out (the button does nothing) and `SPI_master` forces slave on at every SPI exchange. Toggling works only in the 16F73 build. Make the POD9 side default to V102 behaviour, with the 16F73 build as an option. | pod9.js |
| 13 | ama4.js | The PIC clock is 4.9152 MHz, not 4 MHz. AES termination: bit 7 of the saved selection = 75/110 Ω for all four inputs; ama4 has the sense backwards. | ams4.js |
| 14 | demux4.js | Host poll from the AMS4 is about every 0.37 s, not the guessed 100 ms (for the AMS4 host build). | ams4.js |
| 15 | ams4.js | The DEMUX-1 reply is 0xE0–0xE3 once probed (0x00–0x03 otherwise), about 6.3 ms after the command, not 0xC0 at 1–2 ms. The first reply after power-up is immediate. | demux1.js |
| 16 | dms1.js | The same DEMUX-1 reply facts as #15. Also the DMS1 front-panel pass is 115–182 cycles (median 120–144), not the assumed 150. | demux1.js, dms.js |
| 17 | ams8e.js | Qualify the claim that a CE30 image won't configure a CE40: EP4CE30 and EP4CE40 share the JTAG IDCODE 0x020F40DD, the 9,534,304-bit image and all 484 pin roles; nothing archived shows a difference the configuration hardware could detect. | rd10-cycloneiv.js |
| 18 | ams81.js | `wait_ms` is about 164 µs per "ms" (counted from the `.lis`), so the SDI-relock Dolby freeze is about 247 ms, not 1.5 s, and the boot delay is about 0.74 s, not 4.5 s. Also: the FPGA lock register reads 1 = no lock through NOT gates (inst65/73/74/75), which answers ams81's open question on lock polarity. | rd60-ams81a-iss5.js, rd66-mlc8-ams8e1-iss5.js |
| 19 | ams16.js | The master folder's v700 front panel is one save behind the shipped build. RD23's `v200w.c` shows "06AV0000", the version on the 30 Oct 2012 test report; the master copy matches RD23's `v200w._c` backup. Switch the model to the shipped RD23 copy, or offer both, and note it. | rd23-ams16-3g.js |
