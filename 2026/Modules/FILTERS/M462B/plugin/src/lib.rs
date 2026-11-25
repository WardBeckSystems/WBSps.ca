// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! Ward-Beck M462B Parametric EQ (1974|7).
//!
//! `dsp` is the signal path on its own (used by the Ward-Beck Audio Tap). With the default feature `vst`
//! this crate is also a full VST3 / CLAP plugin whose editor is the M462B front panel.

pub mod dsp;
pub mod eq;

#[cfg(feature = "vst")]
mod editor;
#[cfg(feature = "vst")]
pub use plugin::*;

#[cfg(feature = "vst")]
mod plugin {
    use crate::dsp::{Settings, M462B};
    use nih_plug::prelude::*;
    use std::sync::Arc;

    fn gain(name: &str) -> FloatParam {
        FloatParam::new(name, 0.0, FloatRange::Linear { min: -14.0, max: 14.0 })
            .with_unit(" dB")
            .with_value_to_string(formatters::v2s_f32_rounded(1))
    }

    fn freq(name: &str, v: f32, lo: f32, hi: f32) -> FloatParam {
        FloatParam::new(name, v, FloatRange::Skewed { min: lo, max: hi, factor: FloatRange::skew_factor(-1.5) })
            .with_value_to_string(formatters::v2s_f32_hz_then_khz(1))
            .with_string_to_value(formatters::s2v_f32_hz_then_khz())
    }
    fn q(name: &str, v: f32) -> FloatParam {
        FloatParam::new(name, v, FloatRange::Linear { min: 0.5, max: 3.0 }).with_value_to_string(formatters::v2s_f32_rounded(2))
    }

    #[derive(Params)]
    pub struct Params462B {
        #[persist = "editor-state"]
        pub editor_state: Arc<wbs_panel::nih_plug_egui::EguiState>,
        #[id = "eqin"]
        pub eq_in: BoolParam,
        #[id = "lff"]
        pub lf_hz: FloatParam,
        #[id = "lfg"]
        pub lf_gain: FloatParam,
        #[id = "lmff"]
        pub lmf_hz: FloatParam,
        #[id = "lmfq"]
        pub lmf_q: FloatParam,
        #[id = "lmfg"]
        pub lmf_gain: FloatParam,
        #[id = "hmff"]
        pub hmf_hz: FloatParam,
        #[id = "hmfq"]
        pub hmf_q: FloatParam,
        #[id = "hmfg"]
        pub hmf_gain: FloatParam,
        #[id = "hff"]
        pub hf_hz: FloatParam,
        #[id = "hfg"]
        pub hf_gain: FloatParam,
    }

    impl Default for Params462B {
        fn default() -> Self {
            let d = Settings::default();
            Params462B {
                editor_state: crate::editor::default_state(),
                eq_in: BoolParam::new("EQ IN", d.eq_in),
                lf_hz: freq("LF FREQ", d.lf_hz, 30.0, 400.0),
                lf_gain: gain("LF GAIN"),
                lmf_hz: freq("LMF FREQ", d.lmf_hz, 150.0, 2000.0),
                lmf_q: q("LMF Q", d.lmf_q),
                lmf_gain: gain("LMF GAIN"),
                hmf_hz: freq("HMF FREQ", d.hmf_hz, 800.0, 8000.0),
                hmf_q: q("HMF Q", d.hmf_q),
                hmf_gain: gain("HMF GAIN"),
                hf_hz: freq("HF FREQ", d.hf_hz, 3000.0, 16000.0),
                hf_gain: gain("HF GAIN"),
            }
        }
    }

    impl Params462B {
        pub fn settings(&self) -> Settings {
            Settings {
                eq_in: self.eq_in.value(),
                lf_hz: self.lf_hz.value(),
                lf_gain_db: self.lf_gain.value(),
                lmf_hz: self.lmf_hz.value(),
                lmf_q: self.lmf_q.value(),
                lmf_gain_db: self.lmf_gain.value(),
                hmf_hz: self.hmf_hz.value(),
                hmf_q: self.hmf_q.value(),
                hmf_gain_db: self.hmf_gain.value(),
                hf_hz: self.hf_hz.value(),
                hf_gain_db: self.hf_gain.value(),
            }
        }
    }

    pub struct Plugin {
        params: Arc<Params462B>,
        dsp: M462B,
    }

    impl Default for Plugin {
        fn default() -> Self {
            Plugin { params: Arc::new(Params462B::default()), dsp: M462B::new(48000.0) }
        }
    }

    impl nih_plug::prelude::Plugin for Plugin {
        const NAME: &'static str = "WBS M462B Parametric EQ";
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
        const CLAP_ID: &'static str = "ca.ward-beck.m462b";
        const CLAP_DESCRIPTION: Option<&'static str> = Some("Ward-Beck M462B Parametric EQ (1974): four bands, two of them fully parametric");
        const CLAP_MANUAL_URL: Option<&'static str> = Some("https://wardbecksystems.github.io/WBSps.ca/PAGES/M462B.html");
        const CLAP_SUPPORT_URL: Option<&'static str> = None;
        const CLAP_FEATURES: &'static [ClapFeature] = &[ClapFeature::AudioEffect, ClapFeature::Stereo, ClapFeature::Mono, ClapFeature::Equalizer];
    }

    impl Vst3Plugin for Plugin {
        const VST3_CLASS_ID: [u8; 16] = *b"WBS-M462B-Param1";
        const VST3_SUBCATEGORIES: &'static [Vst3SubCategory] = &[Vst3SubCategory::Fx, Vst3SubCategory::Eq];
    }

    nih_export_clap!(Plugin);
    nih_export_vst3!(Plugin);
}
