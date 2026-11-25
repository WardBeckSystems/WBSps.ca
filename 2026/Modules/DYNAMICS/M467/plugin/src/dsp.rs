// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! M467 Noise Gate signal path, free of any plugin framework (the Audio Tap uses this alone).
//!
//! Ported from the WBS VST suite (2030.env/vst/M467_Noise_Gate): per channel, the key is high-passed
//! (80 Hz, 18 dB/octave) and envelope-followed (1 ms attack, 0.2 ms with FAST, release RLS); the gate's
//! gain follows a soft S-curve between −ATTEN and unity around THLD, slewed over 1 ms so it never clicks.
//! The edgewise VU reads the output (300 ms, 0 VU = −20 dBFS RMS). Panel dB are dBFS + 20.

/// Every control on the front panel.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Settings {
    /// NG: gate in (out = straight through)
    pub gate: bool,
    /// THLD: −50 … 0 dB (panel)
    pub thld_db: f32,
    /// ATTEN: 0 … 50 dB, how far the closed gate turns the signal down
    pub atten_db: f32,
    /// RLS: 0.1 … 5 s
    pub rls_s: f32,
    /// The lever: fast (0.2 ms) attack
    pub fast: bool,
    /// COMP TIE: 0 = OUT, 1, 2 (the console's compressor link; kept as set)
    pub comp_tie: u8,
}

impl Default for Settings {
    fn default() -> Self {
        Settings { gate: true, thld_db: -10.0, atten_db: 40.0, rls_s: 0.5, fast: false, comp_tie: 0 }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Meters {
    /// GATE lamp: open
    pub open: bool,
    /// The gate is turning the signal down by this much (dB, ≥ 0)
    pub atten_db: f32,
    /// Output VU (−20 … +3)
    pub vu: f32,
}

/// Biquad (direct form I).
#[derive(Clone, Copy, Default)]
struct Biquad {
    b: [f32; 3],
    a: [f32; 2],
    x: [f32; 2],
    y: [f32; 2],
}

impl Biquad {
    fn run(&mut self, v: f32) -> f32 {
        let o = self.b[0] * v + self.b[1] * self.x[0] + self.b[2] * self.x[1] - self.a[0] * self.y[0] - self.a[1] * self.y[1];
        self.x = [v, self.x[0]];
        self.y = [o, self.y[0]];
        o
    }
}

/// The key's 18 dB/octave high-pass: a 2nd-order (Q 1) and a 1st-order section.
#[derive(Clone, Copy, Default)]
struct KeyHpf {
    bq: Biquad,
    a1: f32,
    x1: f32,
    y1: f32,
}

impl KeyHpf {
    fn new(hz: f32, rate: f32) -> Self {
        let w = std::f32::consts::TAU * hz / rate;
        let alpha = w.sin() / 2.0; // Q = 1
        let c = w.cos();
        let a0 = 1.0 + alpha;
        let bq = Biquad { b: [(1.0 + c) / 2.0 / a0, -(1.0 + c) / a0, (1.0 + c) / 2.0 / a0], a: [-2.0 * c / a0, (1.0 - alpha) / a0], ..Default::default() };
        let k = (w / 2.0).tan();
        KeyHpf { bq, a1: (k - 1.0) / (k + 1.0), x1: 0.0, y1: 0.0 }
    }
    fn run(&mut self, v: f32) -> f32 {
        let s = self.bq.run(v);
        // first-order high-pass: y = (x − x1)/(1+k) − a1·y1, written in its bilinear form
        let y = 0.5 * (1.0 - self.a1) * (s - self.x1) - self.a1 * self.y1;
        self.x1 = s;
        self.y1 = y;
        y
    }
}

const MAX_CH: usize = 16;
const KEY_HZ: f32 = 80.0;

pub struct M467 {
    rate: f32,
    s: Settings,
    env: [f32; MAX_CH],
    gain: [f32; MAX_CH],
    key: [KeyHpf; MAX_CH],
    vu_ms: f32,
    pub meters: Meters,
}

impl M467 {
    pub fn new(sample_rate: f32) -> Self {
        let mut m = M467 { rate: sample_rate, s: Settings::default(), env: [0.0; MAX_CH], gain: [1.0; MAX_CH], key: [KeyHpf::default(); MAX_CH], vu_ms: 0.0, meters: Meters::default() };
        m.reset();
        m
    }

    pub fn set_sample_rate(&mut self, sample_rate: f32) {
        self.rate = sample_rate;
        self.reset();
    }

    pub fn reset(&mut self) {
        self.env = [0.0; MAX_CH];
        self.gain = [1.0; MAX_CH];
        self.key = [KeyHpf::new(KEY_HZ, self.rate); MAX_CH];
        self.vu_ms = 0.0;
        self.meters = Meters { vu: -20.0, open: true, ..Meters::default() };
    }

    pub fn settings(&self) -> Settings {
        self.s
    }

    pub fn set(&mut self, s: Settings) {
        self.s = s;
    }

    pub fn process(&mut self, chans: &mut [&mut [f32]]) {
        let frames = chans.iter().map(|c| c.len()).min().unwrap_or(0);
        if frames == 0 {
            return;
        }
        let s = self.s;
        let coef = |sec: f32| 1.0 - (-1.0 / (sec.max(1e-6) * self.rate)).exp();
        let att = coef(if s.fast { 0.0002 } else { 0.001 });
        let rls = (-1.0 / (s.rls_s.max(0.01) * self.rate)).exp();
        let slew = coef(0.001);
        let floor = 10f32.powf(-s.atten_db.abs() / 20.0);
        let thld_dbfs = s.thld_db - 20.0;
        let n = chans.len().min(MAX_CH);
        let mut gain_sum = 0.0;
        for (ch, data) in chans.iter_mut().enumerate().take(n) {
            for v in data.iter_mut().take(frames) {
                let k = self.key[ch].run(*v).abs();
                if k > self.env[ch] {
                    self.env[ch] += att * (k - self.env[ch]);
                } else {
                    self.env[ch] *= rls;
                }
                let target = if s.gate {
                    let diff = if self.env[ch] > 1e-6 { 20.0 * self.env[ch].log10() - thld_dbfs } else { -100.0 };
                    floor + (1.0 - floor) / (1.0 + (-diff * 0.75).exp())
                } else {
                    1.0
                };
                self.gain[ch] += slew * (target - self.gain[ch]);
                *v *= self.gain[ch];
            }
            gain_sum += self.gain[ch];
        }
        // Output VU: mean square over 300 ms
        let vu_c = coef(0.3);
        for i in 0..frames {
            let sq = chans.iter().take(n).map(|c| c[i] * c[i]).sum::<f32>() / n as f32;
            self.vu_ms += vu_c * (sq - self.vu_ms);
        }
        if !self.vu_ms.is_finite() {
            self.reset();
        }
        let g = gain_sum / n as f32;
        let rms = self.vu_ms.max(0.0).sqrt();
        self.meters = Meters {
            open: !s.gate || g > floor + 0.15 * (1.0 - floor),
            atten_db: if g > 1e-6 { (-20.0 * g.log10()).max(0.0) } else { 120.0 },
            vu: if rms > 1e-7 { (20.0 * rms.log10() + 20.0).clamp(-30.0, 6.0) } else { -30.0 },
        };
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sine(db_fs: f32, n: usize) -> Vec<f32> {
        let a = 10f32.powf(db_fs / 20.0);
        (0..n).map(|i| a * (std::f32::consts::TAU * 1000.0 * i as f32 / 48000.0).sin()).collect()
    }
    fn peak(v: &[f32]) -> f32 {
        v.iter().fold(0.0f32, |m, x| m.max(x.abs()))
    }

    #[test]
    fn loud_passes_quiet_is_attenuated() {
        let mut m = M467::new(48000.0);
        let mut loud = sine(-10.0, 48000); // panel +10, above THLD −10
        m.process(&mut [&mut loud[..]]);
        assert!(m.meters.open);
        assert!((peak(&loud[40000..]) - 10f32.powf(-0.5)).abs() < 0.01);

        let mut quiet = sine(-60.0, 96000); // panel −40, below THLD
        m.process(&mut [&mut quiet[..]]);
        assert!(!m.meters.open);
        let out = 20.0 * peak(&quiet[90000..]).log10();
        assert!(out < -60.0 - 35.0, "closed gate takes about ATTEN 40 dB, got {out}");
    }

    #[test]
    fn gate_out_passes_everything() {
        let mut m = M467::new(48000.0);
        m.set(Settings { gate: false, ..Settings::default() });
        let mut quiet = sine(-60.0, 4800);
        let orig = quiet.clone();
        m.process(&mut [&mut quiet[..]]);
        assert_eq!(quiet, orig);
    }

    #[test]
    fn vu_reads_zero_at_nominal() {
        let mut m = M467::new(48000.0);
        m.set(Settings { gate: false, ..Settings::default() });
        // −20 dBFS RMS sine = peak −17 dBFS
        let mut s = sine(-17.0, 96000);
        m.process(&mut [&mut s[..]]);
        assert!(m.meters.vu.abs() < 0.5, "0 VU, got {}", m.meters.vu);
    }
}
