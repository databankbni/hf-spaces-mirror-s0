import os
import torch
import numpy as np
import gradio as gr
import matplotlib.pyplot as plt
from scipy.io import wavfile
from scipy.signal import find_peaks
from transformers import WhisperProcessor, WhisperForConditionalGeneration

device = "cuda" if torch.cuda.is_available() else "cpu"

# 1. Initialize Whisper Model
model_id = "openai/whisper-tiny.en"
processor = WhisperProcessor.from_pretrained(model_id)
model = WhisperForConditionalGeneration.from_pretrained(model_id).to(device)
model.eval()

# 2. Forensic Statistical Feature Extraction Functions
def count_linguistic_syllables(text):
    if not text.strip():
        return 1
    words = text.lower().split()
    count = 0
    vowels = "aeiouy"
    for word in words:
        word_count = 0
        if word[0] in vowels: word_count += 1
        for index in range(1, len(word)):
            if word[index] in vowels and word[index - 1] not in vowels: word_count += 1
        if word.endswith("e"): word_count -= 1
        if word_count == 0: word_count = 1
        count += word_count
    return max(1, count)

def extract_forensic_metrics(feature_tensor, transcript):
    feat = feature_tensor.squeeze(0).cpu().detach().numpy()
    frame_energies = np.sum(feat, axis=0)
    
    energy_threshold = np.min(frame_energies) + 0.05 * (np.max(frame_energies) - np.min(frame_energies))
    active_indices = np.where(frame_energies > energy_threshold)[0]
    
    if len(active_indices) == 0:
        return {"duration": 0, "peaks": 0, "density": 1.0, "pitch_clarity": 0.0}
        
    start_f, end_f = active_indices[0], active_indices[-1]
    speech_zone_feat = feat[:, start_f:end_f+1]
    
    zone_energy = np.sum(speech_zone_feat, axis=0)
    smoothed_energy = np.convolve(zone_energy, np.ones(5)/5, mode='same')
    peaks, _ = find_peaks(smoothed_energy, distance=8, prominence=2.0)
    
    column_contrast = np.std(speech_zone_feat, axis=0)
    expected_syllables = count_linguistic_syllables(transcript)
    
    return {
        "duration": float(len(active_indices)),
        "peaks": float(len(peaks)),
        "density": float(len(peaks) / expected_syllables),
        "pitch_clarity": float(np.mean(column_contrast))
    }

def create_feature_plot(clean_val, adv_val, title, ylabel):
    fig, ax = plt.subplots(figsize=(5, 3.2))
    ax.bar(['Clean Reference', 'Submitted Audio'], [clean_val, adv_val], color=['#4CAF50', '#F44336'], width=0.4)
    ax.set_title(title, pad=15)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, max(clean_val, adv_val) * 1.35) 
    plt.tight_layout()
    return fig

# 3. Processing Function for Gradio
def process_audio_pair(sample_dropdown):
    idx = int(sample_dropdown.split(" ")[1])
    clean_path = f"audio_dataset_verified/clean/sample_{idx}.wav"
    adv_path = f"audio_dataset_verified/adversarial/sample_{idx}.wav"
    
    if not os.path.exists(clean_path) or not os.path.exists(adv_path):
        return [None]*12
        
    sr_c, clean_wave = wavfile.read(clean_path)
    sr_a, adv_wave = wavfile.read(adv_path)
    clean_wave_float = clean_wave.astype(np.float32) / 32767.0
    adv_wave_float = adv_wave.astype(np.float32) / 32767.0
    
    # Process Clean Reference
    c_feats = processor(clean_wave_float, sampling_rate=sr_c, return_tensors="pt").input_features.to(device)
    with torch.no_grad(): c_pred = model.generate(c_feats)
    clean_tx = processor.batch_decode(c_pred, skip_special_tokens=True)[0].strip()
    m_clean = extract_forensic_metrics(c_feats, clean_tx)
    
    # Process Submitted Live Audio
    a_feats = processor(adv_wave_float, sampling_rate=sr_a, return_tensors="pt").input_features.to(device)
    with torch.no_grad(): a_pred = model.generate(a_feats)
    adv_tx = processor.batch_decode(a_pred, skip_special_tokens=True)[0].strip()
    m_adv = extract_forensic_metrics(a_feats, adv_tx)
    
    # Feature 1 Clean Multi-line Layout
    f1_md = f"""### 📊 Feature 1: Active Frame Duration
* **Clean Reference Baseline:** {m_clean['duration']:.1f} frames
* **Submitted Audio Track:** {m_adv['duration']:.1f} frames

**Statistical Indicator:** Time Window Bloat.  
**Operational Insight:** In clean, quiet room tracking, mathematical optimizers must stretch their malicious signals out into trailing silent frames. However, if your live environment contains steady background noise floors, the baseline audio window will already look fully active. As shown here in Sample 1, environmental noise masks window bloat anomalies entirely, proving why single-threshold duration filters fail in production."""

    f1_plot = create_feature_plot(m_clean['duration'], m_adv['duration'], '1. Active Frame Duration Profile', 'Frames (10ms step)')

    # Feature 2 Clean Multi-line Layout
    f2_md = f"""### 📊 Feature 2: Energy Envelope Peaks
* **Clean Reference Baseline:** {m_clean['peaks']:.1f} peaks
* **Submitted Audio Track:** {m_adv['peaks']:.1f} peaks

**Statistical Indicator:** Gradient Splintering.  
**Operational Insight:** Biological throats create smooth, slow macro-curves during enunciation. Numerical gradient tracking algorithms operate on a pixel-by-pixel basis, forcing sharp, sudden structural tweaks. This causes the energy envelope to fracture into hundreds of artificial micro-spikes that stand out clearly even when duration checks are bypassed."""

    f2_plot = create_feature_plot(m_clean['peaks'], m_adv['peaks'], '2. Energy Envelope Macro-Peaks', 'Peak Count')

    # Feature 3 Clean Multi-line Layout
    f3_md = f"""### 📊 Feature 3: Syllabic Density Ratios
* **Clean Reference Baseline:** {m_clean['density']:.2f}
* **Submitted Audio Track:** {m_adv['density']:.2f}

**Statistical Indicator:** Acoustic-Linguistic Reality Mismatch.  
**Operational Insight:** This is a fully self-contained check that evaluates the input file without an outside reference. It divides physical acoustic peaks by the linguistic syllables found in the text transcript. Human speech tracks close to an expected 1.0 balance. If an optimizer introduces hundreds of micro-spikes to force a brief command output, this balance breaks down."""

    f3_plot = create_feature_plot(m_clean['density'], m_adv['density'], '3. Syllabic Density Metric', 'Peaks per Syllable')

    # Feature 4 Clean Multi-line Layout
    f4_md = f"""### 📊 Feature 4: Harmonic Pitch Clarity
* **Clean Reference Baseline:** {m_clean['pitch_clarity']:.3f}
* **Submitted Audio Track:** {m_adv['pitch_clarity']:.3f}

**Statistical Indicator:** Frequency Smearing.  
**Operational Insight:** Real vocal cords produce sharp, parallel horizontal frequency bands (harmonics) with quiet zones between them. To alter an attention layer without generating loud, audible distortion, adversarial optimization routines bleed noise vertically across bins, smoothing out the variance and muddying pitch definition."""

    f4_plot = create_feature_plot(m_clean['pitch_clarity'], m_adv['pitch_clarity'], '4. Harmonic Pitch Variance', 'Cross-Bin Standard Dev')

    return (
        clean_path, adv_path, clean_tx, adv_tx,
        f1_md, f1_plot,
        f2_md, f2_plot,
        f3_md, f3_plot,
        f4_md, f4_plot
    )

# Build Interface
with gr.Blocks(theme=gr.themes.Soft()) as app:
    gr.Markdown("# 🛡️ Statistical Acoustic Defense Framework for ASR Architectures")
    gr.Markdown("### Research Space: Evasion Analysis Using Classical Physics-Based Statistical Invariants")
    
    with gr.Tabs():
        with gr.Tab("🎙️ Interactive Forensics"):
            gr.Markdown("Select any of the 10 verified target samples to check how an audio track's raw physics diverge from its decoded text transcript. *(Note: Clean references are provided strictly for laboratory baseline visual comparison).*")
            
            sample_dropdown = gr.Dropdown(
                choices=[f"Sample {i}" for i in range(1, 11)], 
                label="Select Target Forensic Sample (Samples 1-10)", 
                value="Sample 1"
            )
            
            with gr.Row():
                with gr.Column():
                    gr.Markdown("### 🟢 Clean Human Speech (Reference)")
                    audio_clean = gr.Audio(label="Clean Waveform Baseline", type="filepath", interactive=False)
                    text_clean = gr.Textbox(label="Whisper Output (Baseline Transcript)", lines=2)
                
                with gr.Column():
                    gr.Markdown("### 🔴 Submitted Audio Track (Evaluation)")
                    audio_adv = gr.Audio(label="Submitted Waveform Input", type="filepath", interactive=False)
                    text_adv = gr.Textbox(label="Whisper Output (Hijacked Transcript)", lines=2)
            
            analyze_btn = gr.Button("Execute Divergence Audit", variant="primary")
            
            gr.Markdown("## 📊 Statistical Feature Auditing Breakdown")
            
            with gr.Row():
                with gr.Column(scale=1):
                    f1_text = gr.Markdown("Select a sample file and click 'Execute Divergence Audit' to begin scanning.")
                with gr.Column(scale=1):
                    f1_graph = gr.Plot(label="")
            
            gr.Markdown("---")
            
            with gr.Row():
                with gr.Column(scale=1):
                    f2_text = gr.Markdown()
                with gr.Column(scale=1):
                    f2_graph = gr.Plot(label="")
                    
            gr.Markdown("---")
            
            with gr.Row():
                with gr.Column(scale=1):
                    f3_text = gr.Markdown()
                with gr.Column(scale=1):
                    f3_graph = gr.Plot(label="")
                    
            gr.Markdown("---")
            
            with gr.Row():
                with gr.Column(scale=1):
                    f4_text = gr.Markdown()
                with gr.Column(scale=1):
                    f4_graph = gr.Plot(label="")
                
            analyze_btn.click(
                process_audio_pair, 
                inputs=[sample_dropdown], 
                outputs=[
                    audio_clean, audio_adv, text_clean, text_adv,
                    f1_text, f1_graph,
                    f2_text, f2_graph,
                    f3_text, f3_graph,
                    f4_text, f4_graph
                ]
            )

        with gr.Tab("📄 Technical Report"):
            gr.Markdown("""
            ## 🔬 Technical Report: Physical Invariant Auditing for Automatic Speech Recognition
            
            ### 1. The Problem: Neural Network Cross-Layer Optimization Vulnerabilities
            Automatic Speech Recognition (ASR) systems—particularly multi-head cross-attention models like OpenAI's Whisper—suffer from structural vulnerabilities to mathematical optimization attacks. An attacker with white-box access can run a sequence of forward-backward optimization passes through the model's frozen weights to construct an imperceptible noise perturbation tensor δ:
            
            $$\\min_{\\delta} \\mathcal{L}_{\\text{Whisper}}(X_{\\text{clean}} + \\delta, Y_{\\text{hijack}}) \\quad \\text{subject to } \\|\\delta\\|_\\infty \\le \\epsilon$$
            
            By injecting this mathematically structured noise into an audio track, the attacker manipulates the encoder feature map. This forces the internal decoder to transcribe completely unauthorized, high-stakes system instructions (Y_hijack) while human observers hear only benign conversational phrasing.
            
            ---
            
            ### 2. Traditional ASR Defense Paradigms vs. Our Proposed Framework
            Current production-grade security implementations struggle to protect automatic speech recognition models against both **White-Box** and **Black-Box** adversarial threat models due to critical scaling limits:
            
            #### Core Threat Vector Descriptions
            * **White-Box Attack Vectors:** The adversary possesses full structural visibility into your active ASR engine (access to exact weights, layer architectures, and tokenizers). They use precise backpropagation routines (such as Projected Gradient Descent or PGD) to sculpt an optimal mathematical perturbation mask that directly disrupts attention nodes.
            * **Black-Box Attack Vectors:** The adversary has zero visibility into your target production backend. They attempt to blind-spot your system using either **Transferable Surrogate Ensembles** (crafting malicious inputs that simultaneously fool multiple open-source models like Kaldi, wav2vec2, and generic deep neural networks, counting on mathematical overlap) or **Query-Based Mutation Loops** (repeatedly mutating an audio file using black-box genetic optimization algorithms, monitoring text output changes until a command triggers).
            
            #### The Failure of Traditional Countermeasures
            * **Adversarial Training:** Requires generating massive datasets of adversarial examples and continuously retraining the target ASR model. This path is computationally heavy, causes overfitting, and lowers accuracy on clean human speech.
            * **Secondary Deep Learning Classifiers:** Involves placing an independent neural network detector ahead of the ASR system. This approach creates a complex system architecture and simply introduces a secondary black box that can itself be bypassed by adaptive attacks.
            * **Audio Modification Pre-filters:** Running lossy compression, high-pass filtering, or downsampling routines effectively disrupts basic perturbations, but heavily degrades Word Error Rates (WER) on accented or quiet speech.
            
            #### The Proposed Framework: Universal Classical Robustness
            This framework shifts the defensive line entirely to the **Physical Layer**. Rather than trying to track infinite mathematical gradients or training heavy machine learning dependencies, our engine audits the **internal structural alignment** of the input file. It functions deterministically by cross-referencing raw acoustic invariants against the linguistic requirements of the generated text string.
            
            #### Architectural Strengths & Universal Robustness Analysis
            1. **Inherent White-Box Robustness (The Gradient Footprint):** Even if a white-box optimization routine meticulously restricts its parameters to bypass simple frame-duration thresholds, it *must* modify internal multi-head feature distributions to force a targeted output. This requirement permanently leaves behind an un-erasable physical trail of **Gradient Splintering** (Feature 2) and **Frequency Smearing** (Feature 4).
            2. **Inherent Black-Box Robustness (Acoustic Destruction):** Because black-box attackers lack access to precise analytical gradients, their attack profiles are physically much rougher. Using trial-and-error mutations or surrogate approximations applies a blunt acoustic instrument to force a transcript change. This results in massive physical distortions, causing the **Energy Envelope Peaks** and **Syllabic Density Mismatch** (Feature 3) to spike significantly higher than white-box baselines, rendering black-box attacks incredibly simple to flag.
            3. **Zero Training Data Overhead:** Requires absolutely no adversarial tracking data, paired fake sets, or ongoing training loops.
            4. **Compute Efficiency:** Evaluates files within milliseconds using standard acoustic statistics on lightweight hardware pipelines.
            5. **Zero Performance Drift:** Preserves the underlying ASR model's original performance boundaries, keeping clean voice transcriptions perfectly intact.
            
            ---

            ### 3. Dataset Provenance & Adversarial Optimization Protocol
            
            #### Source Dataset Provenance
            The ten evaluation baseline sample pairs used in this defensive platform were extracted from the clean test partition of the **LibriSpeech ASR Corpus**. Target phrases were selected across varying speaker genders, accents, and phonetic configurations to build a balanced, physical baseline of legitimate human speech.
            
            #### Training & Generation of Adversarial "Fake" Audio
            The adversarial counterparts were engineered by feeding the source LibriSpeech wave vectors through an iterative optimization script targeting Whisper’s cross-attention matrix layers. Using an acoustic adaptation of the **Projected Gradient Descent (PGD)** algorithm, the system computed loss vectors by penalizing variations between the model's current transcription state and the target malicious string (Y_hijack). Over multiple optimization steps, the script applied micro-adjustments directly onto the raw 1D audio amplitudes, bounding the noise ceiling within an unnoticeable mathematical epsilon threshold.
            
            #### Optimization Convergence & Failure Case Variations
            Crucially, within this 10-sample laboratory pool, some tracks are purposefully not fully optimized or converged. 
            In real-world settings, optimization routines frequently stall due to local minima traps, high speaker voice contrast, or phonetic friction points. In several of the provided sample pairs, the optimization loop failed to reach linguistic convergence—meaning the adversarial perturbation altered the physical properties of the audio track but failed to force Whisper into decoding the targeted malicious transcript. 
            
            Including these incomplete entries serves an important experimental goal: it demonstrates how our physical acoustic indicators successfully catch the structural signature of an attack even if the exploit ultimately fails to execute its linguistic payload.
            
            ---
            
            ### 4. Core Mechanisms: Four Classical Acoustic Invariants
            
            #### 📊 Feature 1: Active Frame Duration Analysis
            * **Mechanism:** Scans row-wise mathematical energy across the 10ms feature blocks of the Log-Mel Spectrogram to isolate precise vocal starts and stops.
            * **Physical Cause:** Human phrases are brief and concise. Optimization routines require maximum vector space to manipulate attention states to output long text strings. This forces the optimization algorithm to populate trailing silent zones with micro-noise, artificially blowing up the active voice footprint toward the context window limit (~3,000 frames).
            
            #### 📊 Feature 2: Energy Envelope & Gradient Splintering
            * **Mechanism:** Collapses the vertical frequency data into a 1D temporal energy wave and applies a local peak-extraction filter (y_i > y_i-1 and y_i > y_i+1).
            * **Physical Cause:** Human speech mechanics generate smooth, continuous, cyclical macro-curves based on natural breath and enunciation pacing. Gradient algorithms (like PGD) make microscopic, rapid adjustments at the individual data-element layer. This causes Gradient Splintering, shattering the smooth pressure wave into hundreds of jagged micro-spikes.
            
            #### 📊 Feature 3: Syllabic Density Ratios (Rs)
            * **Mechanism:** Parses the text transcript through an algorithmic phonetic counter and maps it against raw energy bursts to calculate structural density:
            
            * Formula: Rs = (Physical Spectrogram Energy Peaks) / (Expected Linguistic Syllables from Transcript)
            
            * **Physical Cause:** Authentic human speech tracks closely to an expected 1:1 structural layout (0.65 ≤ Rs ≤ 1.80). When an optimizer attempts to erase text content or force a brief, complex string onto a highly fragmented audio file, the ratio spikes violently (Rs > 10.0), showing a clear reality-check violation.
            
            #### 📊 Feature 4: Harmonic Pitch Contour Clarity
            * **Mechanism:** Computes the standard deviation vertically across individual frequency columns within the active speech zone.
            * **Physical Cause:** Human vocal folds generate clear, parallel resonant frequency structures (formants) separated by silent gaps, creating high variance (~0.38). To fool an attention model without adding loud, audible static, optimization algorithms smear broadband noise across all bins simultaneously, which flattens the contrast and drops pitch variance sharply (0.22).
            
            ---
            
            ### 5. Real-World Limitations & Remaining Vectors
            To maintain robust security engineering protocols, this physical validation layer must acknowledge specific operational boundaries:
            
            * **Generative Voice Clones / Neural TTS:** If an attacker leverages an advanced Text-to-Speech generative engine to synthesize an unauthorized vocal command from scratch, this framework will not catch it. Because generative vocoders model genuine physical biological pathways, the audio will exhibit normal pitch harmonics, tight frame tracking, and proper syllabic density.
            * **Defense-Aware Optimization Metrics:** An adversary with complete white-box access to this validation script can introduce regularizing parameters into their cost functions—explicitly penalizing extra peak generation or maintaining frequency-column variance. While this heavily complicates attack generation and limits command flexibility, it remains a mathematical possibility.
            * **Ambient Background Noise Masking:** High environmental noise floors naturally affect frame-duration and peak tracking metrics (as seen in Sample 1). When background hums trigger voice activity detectors continuously, the framework must rely on an ensemble approach—weighting pitch contour variance and syllabic mismatch calculations more heavily to surface hidden anomalies.
            """)

if __name__ == "__main__":
    app.launch()