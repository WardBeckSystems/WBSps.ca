# M462A Equalizer Module: plugin

The Ward-Beck M462A Equalizer Module (1976|9) as a **VST3 / CLAP plugin** with its front panel, and as
the DSP the **Ward-Beck Audio Tap** runs as an insert.

| Control | Range | What it does |
|---|---|---|
| HF | ±14 dB | high shelf; SHELF in = 10 kHz, out = 3 kHz |
| MID FREQ / GAIN / Q | 200 Hz … 7 kHz, ±14 dB, Q 0.6 … 2.5 | sweepable mid bell |
| LF | ±14 dB | low section; 50 / 150 picks the turnover, LF SHELF in = shelf, out = bell |
| OPAMP SAT | 0 … 100 % | the 4-126 op-amp front end, rounding off as it is driven |
| EQ IN | in / out | out = straight through |

```bash
cargo xtask bundle wbs-m462a --release
cargo run --release --features standalone --bin wbs-m462a-standalone
cargo test --no-default-features
```

**Sources.** Signal path ported from the WBS VST suite (`M462A_Channel_EQ`); panel positions from the suite's
layout, which follows the M462A photo (M462A.jpg) and the M436L recall drawing.

Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
