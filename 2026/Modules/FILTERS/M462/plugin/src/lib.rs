// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
//! Ward-Beck M462 Equalizer (1974|7).
//!
//! `dsp` is the signal path on its own (used by the Ward-Beck Audio Tap). With the default feature `vst`
//! this crate is also a full VST3 / CLAP plugin whose editor is the M462 front panel.

pub mod dsp;
pub mod eq;

#[cfg(feature = "vst")]
mod editor;
#[cfg(feature = "vst")]
pub use plugin::*;

#[cfg(feature = "vst")]
mod plugin {
    use crate::dsp::{Settings, M462};
    use nih_plug::prelude::*;
    use std::sync::Arc;

    fn freq(name: &str, v: f32, lo: f32, hi: f32) -> FloatParam {
        FloatParam::new(name, v, FloatRange::Skewed { min: lo, max: hi, factor: FloatRange::skew_factor(-1.5) })
            .with_value_to_string(formatters::v2s_f32_hz_then_khz(1))
            .with_string_to_value(formatters::s2v_f32_hz_then_khz())
    }
    fn gain15(name: &str) -> FloatParam {
        FloatParam::new(name, 0.0, FloatRange::Linear { min: -15.0, max: 15.0 })
            .with_unit(" dB")
            .with_value_to_string(formatters::v2s_f32_rounded(1))
    }

    #[derive(Params)]
    pub struct Params462 {
        #[persist = "editor-state"]
        pub editor_state: Arc<wbs_panel::nih_plug_egui::EguiState>,
        #[id = "eqin"]
        pub eq_in: BoolParam,
        #[id = "lfbell"]
        pub lf_bell: BoolParam,
        #[id = "lff"]
        pub lf_hz: FloatParam,
        #[id = "lfg"]
        pub lf_gain: FloatParam,
        #[id = "mfq"]
        pub mf_q_high: BoolParam,
        #[id = "mff"]
        pub mf_hz: FloatParam,
        #[id = "mfg"]
        pub mf_gain: FloatParam,
        #[id = "hfbell"]
        pub hf_bell: BoolParam,
        #[id = "hff"]
        pub hf_hz: FloatParam,
        #[id = "hfg"]
        pub hf_gain: FloatParam,
    }

    impl Default for Params462 {
        fn default() -> Self {
            let d = Settings::default();
            Params462 {
                editor_state: crate::editor::default_state(),
                eq_in: BoolParam::new("EQ", d.eq_in),
                lf_bell: BoolParam::new("LF BELL", d.lf_bell),
                lf_hz: freq("LF FREQ", d.lf_hz, 25.0, 400.0),
                lf_gain: gain15("LF"),
                mf_q_high: BoolParam::new("Q H / L", d.mf_q_high),
                mf_hz: freq("MF FREQ", d.mf_hz, 400.0, 5400.0),
                mf_gain: gain15("MF"),
                hf_bell: BoolParam::new("HF BELL", d.hf_bell),
                hf_hz: freq("HF FREQ", d.hf_hz, 1600.0, 24000.0),
                hf_gain: gain15("HF"),
            }
        }
    }

    impl Params462 {
        pub fn settings(&self) -> Settings {
            Settings {
                eq_in: self.eq_in.value(),
                lf_bell: self.lf_bell.value(),
                lf_hz: self.lf_hz.value(),
                lf_gain_db: self.lf_gain.value(),
                mf_q_high: self.mf_q_high.value(),
                mf_hz: self.mf_hz.value(),
                mf_gain_db: self.mf_gain.value(),
                hf_bell: self.hf_bell.value(),
                hf_hz: self.hf_hz.value(),
                hf_gain_db: self.hf_gain.value(),
            }
        }
    }

    pub struct Plugin {
        params: Arc<Params462>,
        dsp: M462,
    }

    impl Default for Plugin {
        fn default() -> Self {
            Plugin { params: Arc::new(Params462::default()), dsp: M462::new(48000.0) }
        }
    }

    impl nih_plug::prelude::Plugin for Plugin {
        const NAME: &'static str = "WBS M462 Equalizer";
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
        const CLAP_ID: &'static str = "ca.ward-beck.m462";
        const CLAP_DESCRIPTION: Option<&'static str> = Some("Ward-Beck M462 Equalizer (1974): sweepable LF, MF and HF with shape and Q switches");
        const CLAP_MANUAL_URL: Option<&'static str> = Some("https://wardbecksystems.github.io/WBSps.ca/PAGES/M462.html");
        const CLAP_SUPPORT_URL: Option<&'static str> = None;
        const CLAP_FEATURES: &'static [ClapFeature] = &[ClapFeature::AudioEffect, ClapFeature::Stereo, ClapFeature::Mono, ClapFeature::Equalizer];
    }

    impl Vst3Plugin for Plugin {
        const VST3_CLASS_ID: [u8; 16] = *b"WBS-M462-Equaliz";
        const VST3_SUBCATEGORIES: &'static [Vst3SubCategory] = &[Vst3SubCategory::Fx, Vst3SubCategory::Eq];
    }

    nih_export_clap!(Plugin);
    nih_export_vst3!(Plugin);
}
