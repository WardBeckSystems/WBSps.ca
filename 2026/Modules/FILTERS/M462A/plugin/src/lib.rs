// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! Ward-Beck M462A Equalizer Module (1976|9).
//!
//! `dsp` is the signal path on its own (used by the Ward-Beck Audio Tap). With the default feature `vst`
//! this crate is also a full VST3 / CLAP plugin whose editor is the M462A front panel.

pub mod dsp;
pub mod eq;

#[cfg(feature = "vst")]
mod editor;
#[cfg(feature = "vst")]
pub use plugin::*;

#[cfg(feature = "vst")]
mod plugin {
    use crate::dsp::{Settings, M462A};
    use nih_plug::prelude::*;
    use std::sync::Arc;

    fn gain(name: &str) -> FloatParam {
        FloatParam::new(name, 0.0, FloatRange::Linear { min: -14.0, max: 14.0 })
            .with_unit(" dB")
            .with_value_to_string(formatters::v2s_f32_rounded(1))
    }

    #[derive(Params)]
    pub struct Params462A {
        #[persist = "editor-state"]
        pub editor_state: Arc<wbs_panel::nih_plug_egui::EguiState>,
        #[id = "eqin"]
        pub eq_in: BoolParam,
        #[id = "lfg"]
        pub lf_gain: FloatParam,
        #[id = "lf150"]
        pub lf_150: BoolParam,
        #[id = "lfshelf"]
        pub lf_shelf: BoolParam,
        #[id = "midf"]
        pub mid_hz: FloatParam,
        #[id = "midq"]
        pub mid_q: FloatParam,
        #[id = "midg"]
        pub mid_gain: FloatParam,
        #[id = "hfg"]
        pub hf_gain: FloatParam,
        #[id = "hfshelf"]
        pub hf_10k: BoolParam,
        #[id = "sat"]
        pub drive: FloatParam,
    }

    impl Default for Params462A {
        fn default() -> Self {
            let d = Settings::default();
            Params462A {
                editor_state: crate::editor::default_state(),
                eq_in: BoolParam::new("EQ IN", d.eq_in),
                lf_gain: gain("LF GAIN"),
                lf_150: BoolParam::new("LF 150 Hz", d.lf_150),
                lf_shelf: BoolParam::new("LF SHELF", d.lf_shelf),
                mid_hz: FloatParam::new("MID FREQ", d.mid_hz, FloatRange::Skewed { min: 200.0, max: 7000.0, factor: FloatRange::skew_factor(-2.0) })
                    .with_value_to_string(formatters::v2s_f32_hz_then_khz(1))
                    .with_string_to_value(formatters::s2v_f32_hz_then_khz()),
                mid_q: FloatParam::new("MID Q", d.mid_q, FloatRange::Linear { min: 0.6, max: 2.5 }).with_value_to_string(formatters::v2s_f32_rounded(2)),
                mid_gain: gain("MID GAIN"),
                hf_gain: gain("HF GAIN"),
                hf_10k: BoolParam::new("HF SHELF 10 kHz", d.hf_10k),
                drive: FloatParam::new("OPAMP SAT", d.drive_pct, FloatRange::Linear { min: 0.0, max: 100.0 })
                    .with_unit(" %")
                    .with_value_to_string(formatters::v2s_f32_rounded(0)),
            }
        }
    }

    impl Params462A {
        pub fn settings(&self) -> Settings {
            Settings {
                eq_in: self.eq_in.value(),
                lf_gain_db: self.lf_gain.value(),
                lf_150: self.lf_150.value(),
                lf_shelf: self.lf_shelf.value(),
                mid_hz: self.mid_hz.value(),
                mid_q: self.mid_q.value(),
                mid_gain_db: self.mid_gain.value(),
                hf_gain_db: self.hf_gain.value(),
                hf_10k: self.hf_10k.value(),
                drive_pct: self.drive.value(),
            }
        }
    }

    pub struct Plugin {
        params: Arc<Params462A>,
        dsp: M462A,
    }

    impl Default for Plugin {
        fn default() -> Self {
            Plugin { params: Arc::new(Params462A::default()), dsp: M462A::new(48000.0) }
        }
    }

    impl nih_plug::prelude::Plugin for Plugin {
        const NAME: &'static str = "WBS M462A Equalizer";
        const VENDOR: &'static str = "Ward-Beck Systems";
        const URL: &'static str = "https://ward-beck.ca";
        const EMAIL: &'static str = "info@ward-beck.ca";
        const VERSION: &'static str = env!("CARGO_PKG_VERSION");
        const AUDIO_IO_LAYOUTS: &'static [AudioIOLayout] = &[
            AudioIOLayout { main_input_channels: NonZeroU32::new(2), main_output_channels: NonZeroU32::new(2), ..AudioIOLayout::const_default() },
            AudioIOLayout { main_input_channels: NonZeroU32::new(1), main_output_channels: NonZeroU32::new(1), ..AudioIOLayout::const_default() },
        ];
        type SysExMessage = ();
        type BackgroundTask = ();

        fn params(&self) -> Arc<dyn Params> {
            self.params.clone()
        }
        fn editor(&mut self, _e: AsyncExecutor<Self>) -> Option<Box<dyn Editor>> {
            crate::editor::create(self.params.clone())
        }
        fn initialize(&mut self, _l: &AudioIOLayout, c: &BufferConfig, _x: &mut impl InitContext<Self>) -> bool {
            self.dsp.set_sample_rate(c.sample_rate);
            true
        }
        fn reset(&mut self) {
            self.dsp.reset();
        }
        fn process(&mut self, buffer: &mut Buffer, _a: &mut AuxiliaryBuffers, _c: &mut impl ProcessContext<Self>) -> ProcessStatus {
            self.dsp.set(self.params.settings());
            self.dsp.process(buffer.as_slice());
            ProcessStatus::Normal
        }
    }

    impl ClapPlugin for Plugin {
        const CLAP_ID: &'static str = "ca.ward-beck.m462a";
        const CLAP_DESCRIPTION: Option<&'static str> = Some("Ward-Beck M462A Equalizer Module (1976): LF 50/150, sweep mid, HF shelf, 4-126 op-amp front end");
        const CLAP_MANUAL_URL: Option<&'static str> = Some("https://wardbecksystems.github.io/WBSps.ca/PAGES/M462A.html");
        const CLAP_SUPPORT_URL: Option<&'static str> = None;
        const CLAP_FEATURES: &'static [ClapFeature] = &[ClapFeature::AudioEffect, ClapFeature::Stereo, ClapFeature::Mono, ClapFeature::Equalizer];
    }

    impl Vst3Plugin for Plugin {
        const VST3_CLASS_ID: [u8; 16] = *b"WBS-M462A-Equal1";
        const VST3_SUBCATEGORIES: &'static [Vst3SubCategory] = &[Vst3SubCategory::Fx, Vst3SubCategory::Eq];
    }

    nih_export_clap!(Plugin);
    nih_export_vst3!(Plugin);
}
