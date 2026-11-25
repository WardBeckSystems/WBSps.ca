// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! Equaliser sections shared by the M462 family plugins: RBJ biquads (bell, shelves) per channel,
//! and the gentle op-amp saturation of the 4-126 front end. No plugin framework.

pub const MAX_CH: usize = 16;

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Shape {
    Bell,
    LowShelf,
    HighShelf,
}

/// One EQ section on every channel.
#[derive(Clone, Copy)]
pub struct Section {
    b: [f32; 3],
    a: [f32; 2],
    z: [[f32; 2]; MAX_CH],
    flat: bool,
}

impl Default for Section {
    fn default() -> Self {
        Section { b: [1.0, 0.0, 0.0], a: [0.0, 0.0], z: [[0.0; 2]; MAX_CH], flat: true }
    }
}

impl Section {
    /// RBJ cookbook coefficients; `q` is the bell's Q (shelves use slope 1).
    pub fn set(&mut self, shape: Shape, hz: f32, q: f32, gain_db: f32, rate: f32) {
        if gain_db.abs() < 0.01 {
            self.flat = true;
            return;
        }
        self.flat = false;
        let a = 10f32.powf(gain_db / 40.0);
        let w = std::f32::consts::TAU * hz.clamp(10.0, rate * 0.45) / rate;
        let (sn, cs) = w.sin_cos();
        let (b0, b1, b2, a0, a1, a2) = match shape {
            Shape::Bell => {
                let al = sn / (2.0 * q.max(0.1));
                (1.0 + al * a, -2.0 * cs, 1.0 - al * a, 1.0 + al / a, -2.0 * cs, 1.0 - al / a)
            }
            Shape::LowShelf | Shape::HighShelf => {
                let al = sn / 2.0 * (2.0f32).sqrt(); // slope S = 1
                let k = 2.0 * a.sqrt() * al;
                if shape == Shape::LowShelf {
                    (
                        a * ((a + 1.0) - (a - 1.0) * cs + k),
                        2.0 * a * ((a - 1.0) - (a + 1.0) * cs),
                        a * ((a + 1.0) - (a - 1.0) * cs - k),
                        (a + 1.0) + (a - 1.0) * cs + k,
                        -2.0 * ((a - 1.0) + (a + 1.0) * cs),
                        (a + 1.0) + (a - 1.0) * cs - k,
                    )
                } else {
                    (
                        a * ((a + 1.0) + (a - 1.0) * cs + k),
                        -2.0 * a * ((a - 1.0) + (a + 1.0) * cs),
                        a * ((a + 1.0) + (a - 1.0) * cs - k),
                        (a + 1.0) - (a - 1.0) * cs + k,
                        2.0 * ((a - 1.0) - (a + 1.0) * cs),
                        (a + 1.0) - (a - 1.0) * cs - k,
                    )
                }
            }
        };
        self.b = [b0 / a0, b1 / a0, b2 / a0];
        self.a = [a1 / a0, a2 / a0];
    }

    /// Transposed direct form II, one sample on channel `ch`.
    #[inline]
    pub fn run(&mut self, ch: usize, x: f32) -> f32 {
        if self.flat {
            return x;
        }
        let z = &mut self.z[ch];
        let y = self.b[0] * x + z[0];
        z[0] = self.b[1] * x - self.a[0] * y + z[1];
        z[1] = self.b[2] * x - self.a[1] * y;
        y
    }

    pub fn reset(&mut self) {
        self.z = [[0.0; 2]; MAX_CH];
    }

    pub fn ok(&mut self) {
        if self.z.iter().flatten().any(|v| !v.is_finite()) {
            self.reset();
        }
    }
}

/// The 4-126 op-amp front end: unity at low level, rounding off as it is driven (0 … 100 %).
#[inline]
pub fn saturate(x: f32, drive_pct: f32) -> f32 {
    if drive_pct <= 0.0 {
        return x;
    }
    let k = 1.0 + 3.0 * (drive_pct / 100.0).clamp(0.0, 2.0);
    let y = (k * x).tanh() / k;
    y + 0.02 * (drive_pct / 100.0) * y * y // a touch of second harmonic
}

/// Magnitude of a section at `hz` in dB (for tests and curves).
#[cfg(test)]
pub fn response_db(s: &Section, hz: f32, rate: f32) -> f32 {
    if s.flat {
        return 0.0;
    }
    let w = std::f32::consts::TAU * hz / rate;
    let (c1, s1, c2, s2) = (w.cos(), w.sin(), (2.0 * w).cos(), (2.0 * w).sin());
    let nr = s.b[0] + s.b[1] * c1 + s.b[2] * c2;
    let ni = -(s.b[1] * s1 + s.b[2] * s2);
    let dr = 1.0 + s.a[0] * c1 + s.a[1] * c2;
    let di = -(s.a[0] * s1 + s.a[1] * s2);
    10.0 * ((nr * nr + ni * ni) / (dr * dr + di * di)).log10()
}
