# M466 Compressor - Limiter: plugin

The Ward-Beck M466 Compressor - Limiter (1976|9) as a **VST3 / CLAP plugin** with its front panel, and
as the DSP the **Ward-Beck Audio Tap** runs as an insert.

| Control | Range | What it does |
|---|---|---|
| INS | in / out | insert in; out is a hard bypass |
| COMP | in / out | compressor in (red LED: taking 1 dB or more) |
| COMP THLD | −20 … 0 dB | compressor threshold (panel dB: 0 = −20 dBFS) |
| SLOPE | 1.5, 2, 3, 5, 10 :1 | compression ratio |
| RLS (green) | 0.1 … 5 s | compressor release (attack 10 ms) |
| D S | in / out | de-esser: the detector hears only DS-NG's band, and the compressor release halves (WBS manual) |
| DS-NG | 1 … 8 kHz | de-esser centre |
| LIM | in / out | 50:1 limiter, 50 µs attack (red LED: 1 dB or more) |
| LIMIT THLD | 0 … +20 dB | limiter threshold (panel dB) |
| RLS (yellow) | 0.1 … 5 s | limiter release |
| LIMIT 6 / 12 | lamps | the limiter is taking 6 / 12 dB or more |
| SENS | −8 … +10 dB | level into the detector and the gain element |
| GR / VU | | the readout under the badge: gain reduction, or output peak |

Knobs: drag up / down (Shift = fine), scroll to nudge, double-click for the default.

## Build

```bash
cargo xtask bundle wbs-m466 --release        # target/bundled/wbs-m466.vst3 and wbs-m466.clap
cargo run --release --features standalone --bin wbs-m466-standalone   # the panel in a window (JACK, or --backend dummy)
cargo test --no-default-features             # the DSP's tests
```

Copy `wbs-m466.vst3` to `~/.vst3` (Linux), `%COMMONPROGRAMFILES%\VST3` (Windows) or
`~/Library/Audio/Plug-Ins/VST3` (macOS); `wbs-m466.clap` to the matching `CLAP` folder.

The panel kit comes from [Ward-Beck-Plugin-Core](https://github.com/WardBeckSystems/Ward-Beck-Plugin-Core).
Inside a WBSps.ca checkout, `WBSps.ca/.cargo/config.toml` points the build at the local copy instead.
Linux builds need the X11/XCB and JACK development files (`libx11-xcb-dev`, `libjack-jackd2-dev`), or
the shims in Plugin Core's `build-shims/linux`.

**Sources.** The signal path is ported from the WBS VST suite (`M466_Compressor_Limiter`), whose controls
follow the M466 front panel photo (R002 - M466.jpg). The panel layout follows a concept rendering
(`Ward-Beck-Plugin-Core/art/concept-rack-gemini.svg`, drawn there as "M456"), *inferred*, not a factory drawing.

Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
