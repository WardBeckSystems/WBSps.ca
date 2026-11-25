# M467 Noise Gate: plugin

The Ward-Beck M467 Noise Gate (1976) as a **VST3 / CLAP plugin** with its front panel and edgewise VU,
and as the DSP the **Ward-Beck Audio Tap** runs as an insert.

| Control | Range | What it does |
|---|---|---|
| NG | in / out | gate in; the red lamp is lit while the gate is holding the signal down |
| THLD | −50 … 0 dB | where the gate opens (panel dB: 0 = −20 dBFS) |
| ATTEN | 0 … 50 dB | how far the closed gate turns the signal down |
| RLS | 0.1 … 5 s | release |
| FAST (lever) | off / on | 0.2 ms attack instead of 1 ms |
| GATE | lamp | green while the gate is open |
| COMP TIE OUT / 1 / 2 | interlocked | ties the gate to a compressor link bus on the console; kept as set (no link here) |
| VU | −20 … +3 | the output, 300 ms, 0 VU = −20 dBFS RMS |

The key is high-passed at 80 Hz (18 dB/octave) so rumble doesn't hold the gate open; the gain moves on a
soft curve and is slewed over 1 ms so it never clicks.

## Build

```bash
cargo xtask bundle wbs-m467 --release        # target/bundled/wbs-m467.vst3 and wbs-m467.clap
cargo run --release --features standalone --bin wbs-m467-standalone   # the panel in a window
cargo test --no-default-features             # the DSP's tests
```

**Sources.** The signal path is ported from the WBS VST suite (`M467_Noise_Gate`). The panel layout follows
a concept rendering (`Ward-Beck-Plugin-Core/art/concept-rack-gemini.svg`, drawn there as "M407"); the
FAST lever and COMP TIE are *inferred* from that rendering, not a factory drawing.

Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
