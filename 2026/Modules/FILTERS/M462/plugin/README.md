# M462 Equalizer: plugin

The Ward-Beck M462 Equalizer (1974|7) as a **VST3 / CLAP plugin** with its front panel, and as the DSP
the **Ward-Beck Audio Tap** runs as an insert.

| Control | Range | What it does |
|---|---|---|
| EQ | in / out | EQ in (red lamp); out = straight through |
| LF | ±15 dB | low band, 25 … 400 Hz (green); BELL in = bell, out = shelf |
| MF | ±15 dB | mid bell, 400 Hz … 5.4 kHz (yellow); Q switch: H narrow (2.5), L wide (0.7) |
| HF | ±15 dB | high band, 1.6 … 24 kHz (red); BELL in = bell, out = shelf |

```bash
cargo xtask bundle wbs-m462 --release        # target/bundled/wbs-m462.vst3 and wbs-m462.clap
cargo run --release --features standalone --bin wbs-m462-standalone
cargo test --no-default-features
```

**Sources.** *Inferred*: the M462's panel and ranges are not in the archive. Panel, ranges and switches follow
the concept rendering (`Ward-Beck-Plugin-Core/art/concept-rack-gemini.svg`, drawn there as "M582C").

Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
