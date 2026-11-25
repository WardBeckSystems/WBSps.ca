# M462B Parametric EQ: plugin

The Ward-Beck M462B Parametric EQ (1974|7) as a **VST3 / CLAP plugin** with its front panel, and as the
DSP the **Ward-Beck Audio Tap** runs as an insert.

| Band | Frequency | Gain | Q |
|---|---|---|---|
| HF (red) | 3 … 16 kHz shelf | ±14 dB | |
| HMF (amber) | 800 Hz … 8 kHz bell | ±14 dB | 0.5 … 3 |
| LMF (yellow) | 150 Hz … 2 kHz bell | ±14 dB | 0.5 … 3 |
| LF (green) | 30 … 400 Hz shelf | ±14 dB | |

EQ IN at the foot (out = straight through). The class-A output driver adds a light, fixed saturation.

```bash
cargo xtask bundle wbs-m462b --release
cargo run --release --features standalone --bin wbs-m462b-standalone
cargo test --no-default-features
```

**Sources.** Signal path ported from the WBS VST suite (`M462B_Parametric_EQ`); panel positions from the suite's
layout, which follows the M462B photo (M462B.jpg).

Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
