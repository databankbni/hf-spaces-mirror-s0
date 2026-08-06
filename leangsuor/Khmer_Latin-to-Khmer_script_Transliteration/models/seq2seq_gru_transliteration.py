"""
Character-Level Seq2Seq GRU for Khmer Latin → Khmer Script Transliteration
===========================================================================

Architecture Overview
---------------------

    ┌─────────────────────────────────────────────────────────────┐
    │                        ENCODER                              │
    │  Roman chars → Embedding(128) → GRU(256) → hidden state h  │
    └─────────────────────────────────────────────────────────────┘
                              ↓
                     (single hidden state)
                              ↓
    ┌─────────────────────────────────────────────────────────────┐
    │                        DECODER                              │
    │  Khmer chars → Embedding(128) → GRU(256) → Dense(softmax)  │
    │                     (init with encoder state)               │
    └─────────────────────────────────────────────────────────────┘

GRU vs LSTM
~~~~~~~~~~~~
    The key structural difference is that GRU carries a **single** hidden
    state h, while LSTM maintains two (h and c).  GRU uses 2 gates
    (reset, update) instead of LSTM's 3 (input, forget, output), yielding
    ~25 % fewer parameters for the same hidden dimension.

Data Preparation Pipeline
-------------------------
    1. LOAD DATA       – JSON dict → parallel lists khmer_script[], khmer_latin[]
    2. BUILD VOCAB     – unique chars → char2idx / idx2char  (0 = padding)
    3. SPECIAL TOKENS  – target side only: \\t (start), \\n (end)
    4. ENCODE          – chars → integer indices
    5. PAD / TRUNCATE  – 0-pad to max_src_len / max_tgt_len
    6. SPLIT           – 95 % train, 5 % val  (random_state=42)

Hyperparameters
~~~~~~~~~~~~~~~
    embed_dim       128
    latent_dim      256
    epochs          50
    batch_size      256
    optimizer       Adam
    loss            sparse_categorical_crossentropy
"""

import configparser
import itertools
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.callbacks import Callback, EarlyStopping, ModelCheckpoint

from translating_khmer_latin_to_khmer_script.export import save_config_yaml


# ======================================================================
# Config loader
# ======================================================================

def load_config(config_path="config.ini"):
    """Load configuration from INI file, including [gru] array settings."""
    config = configparser.ConfigParser()

    defaults = {
        "data_path": "data/processed/complete/khmer_roman_grouped_patched.json",
        "base_output_dir": "outputs",
        "embed_dim": 128,
        "latent_dim": 256,
        "batch_sizes": [64, 128, 256],
        "embed_dims": [64, 128, 256],
        "latent_dims": [128, 256, 512],
        "epochs": 50,
        "batch_size": 256,
        "val_split": 0.05,
        "random_state": 42,
        "verbose": 1,
        "save_every_epoch": True,
    }

    def _int_list(s):
        return [int(x.strip()) for x in s.split(",")]

    if os.path.exists(config_path):
        config.read(config_path)

        if "paths" in config:
            defaults["base_output_dir"] = config.get("paths", "base_output_dir", fallback=defaults["base_output_dir"])

        if "model" in config:
            defaults["embed_dim"] = config.getint("model", "embed_dim", fallback=defaults["embed_dim"])
            defaults["latent_dim"] = config.getint("model", "latent_dim", fallback=defaults["latent_dim"])

        if "training" in config:
            defaults["epochs"]       = config.getint("training", "epochs", fallback=defaults["epochs"])
            defaults["batch_size"]   = config.getint("training", "batch_size", fallback=defaults["batch_size"])
            defaults["val_split"]    = config.getfloat("training", "val_split", fallback=defaults["val_split"])
            defaults["random_state"] = config.getint("training", "random_state", fallback=defaults["random_state"])

        if "logging" in config:
            defaults["verbose"]          = config.getint("logging", "verbose", fallback=defaults["verbose"])
            defaults["save_every_epoch"] = config.getboolean("logging", "save_every_epoch", fallback=defaults["save_every_epoch"])

        if "gru" in config:
            g = config["gru"]
            defaults["data_path"] = g.get("data_path", defaults["data_path"])
            defaults["epochs"]    = g.getint("epochs", defaults["epochs"])
            if g.get("batch_sizes"):
                defaults["batch_sizes"] = _int_list(g["batch_sizes"])
            if g.get("embed_dims"):
                defaults["embed_dims"]  = _int_list(g["embed_dims"])
            if g.get("latent_dims"):
                defaults["latent_dims"] = _int_list(g["latent_dims"])

        print(f"Loaded configuration from: {config_path}")
    else:
        print(f"Config file not found: {config_path}, using defaults.")

    return defaults


# ======================================================================
# Data loading — supports grouped {"romanization": [...]} or flat string
# ======================================================================

def load_data(data_path):
    """Load grouped or flat JSON and return parallel (roman, khmer) lists."""
    with open(data_path, encoding="utf-8") as f:
        raw = json.load(f)

    roman_list, khmer_list = [], []
    for item in raw:
        khmer  = item.get("khmer", "").strip()
        romans = item.get("romanization", "")
        if not khmer:
            continue
        if isinstance(romans, list):
            for r in romans:
                r = r.strip()
                if r:
                    roman_list.append(r)
                    khmer_list.append(khmer)
        elif isinstance(romans, str) and romans.strip():
            roman_list.append(romans.strip())
            khmer_list.append(khmer)

    print(f"Loaded {len(roman_list):,} (roman → khmer) pairs from {Path(data_path).name}")
    return roman_list, khmer_list


# ======================================================================
# Versioning helper
# ======================================================================

def _next_version_dir(base_output_dir, batch_size, embed_dim, latent_dim):
    """Return a new non-existing version directory for today's date."""
    date_str  = datetime.now().strftime("%d%m%Y")
    day_dir   = Path(base_output_dir) / date_str
    day_dir.mkdir(parents=True, exist_ok=True)
    version = 1
    while True:
        candidate = day_dir / f"gru_v{version}_bs{batch_size}_ed{embed_dim}_ld{latent_dim}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return str(candidate)
        version += 1


# ======================================================================
# Vocabulary helpers
# ======================================================================

def build_vocab(seqs):
    """Build character-level vocabulary from a list of strings.

    Returns
    -------
    char2idx : dict   char → int  (1-indexed; 0 reserved for padding)
    idx2char : dict   int → char
    """
    chars = sorted(set("".join(seqs)))
    char2idx = {c: i + 1 for i, c in enumerate(chars)}
    idx2char = {i: c for c, i in char2idx.items()}
    return char2idx, idx2char


def encode_src(seqs, char2idx, max_len):
    """Encode source (roman) sequences to padded integer arrays."""
    res = []
    for s in seqs:
        ids = [char2idx[c] for c in s if c in char2idx]
        if len(ids) > max_len:
            ids = ids[:max_len]
        else:
            ids += [0] * (max_len - len(ids))
        res.append(ids)
    return np.array(res, dtype="int32")


def encode_tgt(seqs, char2idx, max_len, start_idx, end_idx):
    """Encode target (Khmer) sequences with start/end tokens.

    Returns
    -------
    decoder_input  : np.ndarray  (N, max_len)      shifted right (<start> prefix)
    decoder_target : np.ndarray  (N, max_len, 1)    ground truth  (<end> suffix)
    """
    decoder_input = []
    decoder_target = []
    for s in seqs:
        seq_ids = [char2idx[c] for c in s if c in char2idx]
        in_ids = [start_idx] + seq_ids
        out_ids = seq_ids + [end_idx]
        if len(in_ids) > max_len:
            in_ids = in_ids[:max_len]
        else:
            in_ids += [0] * (max_len - len(in_ids))
        if len(out_ids) > max_len:
            out_ids = out_ids[:max_len]
        else:
            out_ids += [0] * (max_len - len(out_ids))
        decoder_input.append(in_ids)
        decoder_target.append(out_ids)
    decoder_input = np.array(decoder_input, dtype="int32")
    decoder_target = np.expand_dims(np.array(decoder_target, dtype="int32"), -1)
    return decoder_input, decoder_target


# ======================================================================
# Model builder
# ======================================================================

def build_seq2seq_model(vocab_src, vocab_tgt, embed_dim=128, latent_dim=256):
    """Build encoder-decoder GRU model and return training + inference models.

    Unlike the LSTM variant the GRU carries only a single hidden state h
    (no cell state c), so the encoder produces one tensor and the decoder
    accepts one state input.

    Returns
    -------
    model          : training model   ([encoder_input, decoder_input] → decoder_output)
    encoder_model  : inference encoder (encoder_input → state_h)
    decoder_model  : inference decoder ([decoder_input, state_h] → [output, state_h])
    """
    # --- Encoder ---
    encoder_inputs = layers.Input(shape=(None,), name="encoder_input")
    encoder_embedding = layers.Embedding(
        vocab_src, embed_dim, mask_zero=True, name="encoder_embedding"
    )
    x = encoder_embedding(encoder_inputs)
    encoder_gru = layers.GRU(latent_dim, return_state=True, use_cudnn=False, name="encoder_gru")
    _encoder_outputs, state_h = encoder_gru(x)
    encoder_state = state_h

    # --- Decoder ---
    decoder_inputs = layers.Input(shape=(None,), name="decoder_input")
    decoder_embedding = layers.Embedding(
        vocab_tgt, embed_dim, mask_zero=True, name="decoder_embedding"
    )
    y = decoder_embedding(decoder_inputs)
    decoder_gru = layers.GRU(
        latent_dim, return_sequences=True, return_state=True, use_cudnn=False, name="decoder_gru"
    )
    decoder_outputs, _ = decoder_gru(y, initial_state=encoder_state)
    decoder_dense = layers.Dense(vocab_tgt, activation="softmax", name="decoder_dense")
    decoder_outputs = decoder_dense(decoder_outputs)

    # --- Training model ---
    model = models.Model([encoder_inputs, decoder_inputs], decoder_outputs)
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy")

    # --- Inference: encoder ---
    encoder_model = models.Model(encoder_inputs, encoder_state, name="encoder_model")

    # --- Inference: decoder ---
    decoder_state_input_h = layers.Input(shape=(latent_dim,), name="decoder_state_input")

    dec_emb2 = decoder_embedding(decoder_inputs)
    decoder_outputs2, state_h2 = decoder_gru(
        dec_emb2, initial_state=decoder_state_input_h
    )
    decoder_outputs2 = decoder_dense(decoder_outputs2)

    decoder_model = models.Model(
        [decoder_inputs, decoder_state_input_h],
        [decoder_outputs2, state_h2],
        name="decoder_model",
    )

    return model, encoder_model, decoder_model


# ======================================================================
# Callbacks: save inference models
# ======================================================================

class SaveInferenceModelsCallback(Callback):
    """Save encoder & decoder .keras files at the end of each epoch."""

    def __init__(self, encoder_model, decoder_model, save_dir):
        super().__init__()
        self.encoder_model = encoder_model
        self.decoder_model = decoder_model
        self.save_dir = save_dir

    def on_epoch_end(self, epoch, logs=None):
        val_loss = logs.get("val_loss", 0)
        enc_path = os.path.join(
            self.save_dir, f"encoder_model.{epoch + 1:02d}-{val_loss:.2f}.keras"
        )
        dec_path = os.path.join(
            self.save_dir, f"decoder_model.{epoch + 1:02d}-{val_loss:.2f}.keras"
        )
        self.encoder_model.save(enc_path)
        self.decoder_model.save(dec_path)
        print(f"\nSaved inference models: {enc_path}, {dec_path}")


class SaveBestInferenceModelsCallback(Callback):
    """Overwrite best_encoder_model.keras / best_decoder_model.keras whenever val_loss improves."""

    def __init__(self, encoder_model, decoder_model, save_dir):
        super().__init__()
        self.encoder_model = encoder_model
        self.decoder_model = decoder_model
        self.save_dir = save_dir
        self.best_val_loss = float("inf")

    def on_epoch_end(self, epoch, logs=None):
        val_loss = logs.get("val_loss", float("inf"))
        if val_loss < self.best_val_loss:
            self.best_val_loss = val_loss
            self.encoder_model.save(os.path.join(self.save_dir, "best_encoder_model.keras"))
            self.decoder_model.save(os.path.join(self.save_dir, "best_decoder_model.keras"))
            print(f"\n[Best] val_loss={val_loss:.4f} — saved best inference models (epoch {epoch + 1})")


class TrainingProgressCallback(Callback):
    """Print training progress with loss values after each epoch."""

    def __init__(self, total_epochs, steps_per_epoch=None):
        super().__init__()
        self.total_epochs    = total_epochs
        self.steps_per_epoch = steps_per_epoch
        self.history = {"epoch": [], "loss": [], "val_loss": []}

    def on_epoch_begin(self, epoch, logs=None):
        print(f"\n{'='*60}")
        step_info = f"  |  steps: {self.steps_per_epoch}" if self.steps_per_epoch else ""
        print(f"Epoch {epoch + 1}/{self.total_epochs}{step_info}")
        print(f"{'='*60}")

    def on_epoch_end(self, epoch, logs=None):
        loss = logs.get("loss", 0)
        val_loss = logs.get("val_loss", 0)
        self.history["epoch"].append(epoch + 1)
        self.history["loss"].append(float(loss))
        self.history["val_loss"].append(float(val_loss))

        print(f"\n>>> Epoch {epoch + 1} Summary:")
        print(f"    Training Loss:   {loss:.4f}")
        print(f"    Validation Loss: {val_loss:.4f}")
        if epoch > 0:
            prev_loss = self.history["loss"][-2]
            prev_val_loss = self.history["val_loss"][-2]
            loss_delta = loss - prev_loss
            val_loss_delta = val_loss - prev_val_loss
            print(f"    Loss Change:     {loss_delta:+.4f} ({'↓' if loss_delta < 0 else '↑'})")
            print(f"    Val Loss Change: {val_loss_delta:+.4f} ({'↓' if val_loss_delta < 0 else '↑'})")

    def on_train_end(self, logs=None):
        print(f"\n{'='*60}")
        print("Training Complete!")
        print(f"{'='*60}")
        print(f"Final Training Loss:   {self.history['loss'][-1]:.4f}")
        print(f"Final Validation Loss: {self.history['val_loss'][-1]:.4f}")
        best_epoch = np.argmin(self.history["val_loss"]) + 1
        best_val_loss = min(self.history["val_loss"])
        print(f"Best Validation Loss:  {best_val_loss:.4f} (Epoch {best_epoch})")


# ======================================================================
# Training entry-point
# ======================================================================

def train(
    dict_path,
    run_dir="outputs",
    model_name="seq2seq_gru",
    embed_dim=128,
    latent_dim=256,
    epochs=50,
    batch_size=256,
    val_split=0.05,
    random_state=42,
):
    """End-to-end training: load data → build model → fit → save artefacts.

    Parameters
    ----------
    dict_path : str
        Path to grouped JSON (roman ↔ khmer pairs, supports list romanizations).
    run_dir : str
        Final versioned output directory, e.g.
        ``outputs/27052026/gru_v1_bs64_ed64_ld128``.
        Subdirectories (checkpoints/, evaluation/, metrics/, plots/) are
        created directly inside it.
    model_name : str
        Logical name used in config YAML and print output.
    """
    # ---- 1. Load data ------------------------------------------------
    roman_list, khmer_list = load_data(dict_path)
    khmer_latin  = roman_list
    khmer_script = khmer_list

    # ---- 2. Build vocabularies ---------------------------------------
    src_char2idx, src_idx2char = build_vocab(khmer_latin)
    tgt_char2idx, tgt_idx2char = build_vocab(khmer_script)

    start_token, end_token = "\t", "\n"
    next_idx = len(tgt_char2idx) + 1
    tgt_char2idx[start_token] = next_idx
    tgt_idx2char[next_idx] = start_token
    next_idx += 1
    tgt_char2idx[end_token] = next_idx
    tgt_idx2char[next_idx] = end_token

    start_token_idx = tgt_char2idx[start_token]
    end_token_idx = tgt_char2idx[end_token]

    max_src_len = max(len(s) for s in khmer_latin)
    max_tgt_len = max(len(s) for s in khmer_script) + 2  # + start + end

    # ---- 3. Encode ---------------------------------------------------
    X = encode_src(khmer_latin, src_char2idx, max_src_len)
    decoder_input_data, decoder_target_data = encode_tgt(
        khmer_script, tgt_char2idx, max_tgt_len, start_token_idx, end_token_idx
    )

    # ---- 4. Train / val split ----------------------------------------
    indices = np.arange(len(X))
    train_idx, val_idx = train_test_split(
        indices, test_size=val_split, random_state=random_state
    )
    X_train, X_val = X[train_idx], X[val_idx]
    dec_in_train, dec_in_val = decoder_input_data[train_idx], decoder_input_data[val_idx]
    dec_tgt_train, dec_tgt_val = decoder_target_data[train_idx], decoder_target_data[val_idx]

    num_train = len(X_train)
    steps_per_epoch = math.ceil(num_train / batch_size)
    print(f"Training samples: {num_train}, Validation samples: {len(X_val)}")
    print(f"Steps per epoch:  {steps_per_epoch}")

    vocab_src = len(src_char2idx) + 1
    vocab_tgt = len(tgt_char2idx) + 1

    # ---- 5. Build model ----------------------------------------------
    model, encoder_model, decoder_model = build_seq2seq_model(
        vocab_src, vocab_tgt, embed_dim, latent_dim
    )

    # ---- 6. Prepare export dirs & save vocab config ------------------
    ckpt_dir = os.path.join(run_dir, "checkpoints")
    eval_dir = os.path.join(run_dir, "evaluation")
    metr_dir = os.path.join(run_dir, "metrics")
    plot_dir = os.path.join(run_dir, "plots")
    cfg_yaml = os.path.join(run_dir, "config.yaml")
    for d in (ckpt_dir, eval_dir, metr_dir, plot_dir):
        os.makedirs(d, exist_ok=True)
    paths = {
        "root": run_dir,
        "checkpoints": ckpt_dir,
        "evaluation": eval_dir,
        "metrics": metr_dir,
        "plots": plot_dir,
        "config_yaml": cfg_yaml,
    }

    print(f"\n{'='*60}")
    print("Output Directory Structure:")
    print(f"{'='*60}")
    print(f"  Root:        {paths['root']}")
    print(f"  Checkpoints: {paths['checkpoints']}")
    print(f"  Evaluation:  {paths['evaluation']}")
    print(f"  Metrics:     {paths['metrics']}")
    print(f"  Plots:       {paths['plots']}")
    print(f"  Config:      {paths['config_yaml']}")
    print(f"{'='*60}\n")

    vocab_config = {
        "src_char2idx": src_char2idx,
        "src_idx2char": {int(k): v for k, v in src_idx2char.items()},
        "tgt_char2idx": tgt_char2idx,
        "tgt_idx2char": {int(k): v for k, v in tgt_idx2char.items()},
        "start_token_idx": int(start_token_idx),
        "end_token_idx": int(end_token_idx),
        "max_src_len": int(max_src_len),
        "max_tgt_len": int(max_tgt_len),
        "latent_dim": int(latent_dim),
    }
    with open(os.path.join(paths["evaluation"], "vocab_config.json"), "w", encoding="utf-8") as f:
        json.dump(vocab_config, f, ensure_ascii=False, indent=2)

    # ---- 7. Callbacks ------------------------------------------------
    checkpoint_cb = ModelCheckpoint(
        filepath=os.path.join(
            paths["checkpoints"], "weights.{epoch:02d}-{val_loss:.2f}.weights.h5"
        ),
        save_weights_only=True,
        save_best_only=False,
        verbose=1,
    )
    best_checkpoint_cb = ModelCheckpoint(
        filepath=os.path.join(paths["checkpoints"], "best_weights.weights.h5"),
        save_weights_only=True,
        save_best_only=True,
        monitor="val_loss",
        verbose=1,
    )
    save_inference_cb = SaveInferenceModelsCallback(
        encoder_model, decoder_model, paths["checkpoints"]
    )
    best_inference_cb = SaveBestInferenceModelsCallback(
        encoder_model, decoder_model, paths["checkpoints"]
    )
    progress_cb = TrainingProgressCallback(total_epochs=epochs, steps_per_epoch=steps_per_epoch)
    early_stop_cb = EarlyStopping(monitor="val_loss", patience=10, restore_best_weights=False, verbose=1)

    print(f"\n{'='*60}")
    print("Training Configuration:")
    print(f"{'='*60}")
    print(f"  Embedding Dim:   {embed_dim}")
    print(f"  Latent Dim:      {latent_dim}")
    print(f"  Epochs:          {epochs}")
    print(f"  Batch Size:      {batch_size}")
    print(f"  Source Vocab:    {vocab_src}")
    print(f"  Target Vocab:    {vocab_tgt}")
    print(f"  Max Source Len:  {max_src_len}")
    print(f"  Max Target Len:  {max_tgt_len}")
    print(f"{'='*60}\n")

    # ---- 8. Fit ------------------------------------------------------
    print("\nStarting training...\n")
    history = model.fit(
        [X_train, dec_in_train],
        dec_tgt_train,
        validation_data=([X_val, dec_in_val], dec_tgt_val),
        epochs=epochs,
        batch_size=batch_size,
        callbacks=[checkpoint_cb, best_checkpoint_cb, save_inference_cb, best_inference_cb, progress_cb, early_stop_cb],
        verbose=1,
    )

    # ---- 9. Save artefacts ------------------------------------------
    history_dict = {
        "loss": [float(v) for v in history.history["loss"]],
        "val_loss": [float(v) for v in history.history["val_loss"]],
        "epochs": list(range(1, len(history.history["loss"]) + 1)),
        "best_epoch": int(np.argmin(history.history["val_loss"]) + 1),
        "best_val_loss": float(min(history.history["val_loss"])),
        "final_loss": float(history.history["loss"][-1]),
        "final_val_loss": float(history.history["val_loss"][-1]),
        "config": {
            "embed_dim": embed_dim,
            "latent_dim": latent_dim,
            "batch_size": batch_size,
            "epochs": epochs,
            "val_split": val_split,
        },
    }
    history_path = os.path.join(paths["metrics"], "training_history.json")
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history_dict, f, indent=2)
    print(f"\nSaved training history to: {history_path}")

    # Save final inference models
    final_enc_path = os.path.join(paths["checkpoints"], "encoder_model.keras")
    final_dec_path = os.path.join(paths["checkpoints"], "decoder_model.keras")
    encoder_model.save(final_enc_path)
    decoder_model.save(final_dec_path)

    # ---- 10. Loss curve plot ----------------------------------------
    import matplotlib.pyplot as plt

    plt.figure(figsize=(8, 5))
    plt.plot(history_dict["epochs"], history_dict["loss"], label="train")
    plt.plot(history_dict["epochs"], history_dict["val_loss"], label="val")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.title("GRU Training Loss")
    plt.legend()
    plt.tight_layout()
    plot_path = os.path.join(paths["plots"], "loss_curve.png")
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"Saved loss curve to: {plot_path}")

    # ---- 11. Config YAML --------------------------------------------
    model_config = {
        "model": {
            "name": model_name,
            "architecture": "encoder_decoder_gru",
            "embed_dim": embed_dim,
            "latent_dim": latent_dim,
        },
        "training": {
            "epochs": epochs,
            "batch_size": batch_size,
            "val_split": val_split,
            "random_state": random_state,
            "optimizer": "adam",
            "loss": "sparse_categorical_crossentropy",
        },
        "data": {"path": dict_path},
    }
    save_config_yaml(model_config, paths["config_yaml"])
    print(f"Saved config to: {paths['config_yaml']}")

    print(f"\n{'='*60}")
    print("Training Summary:")
    print(f"{'='*60}")
    print(f"  Final Training Loss:   {history_dict['final_loss']:.4f}")
    print(f"  Final Validation Loss: {history_dict['final_val_loss']:.4f}")
    print(f"  Best Validation Loss:  {history_dict['best_val_loss']:.4f} (Epoch {history_dict['best_epoch']})")
    print(f"\nSaved to: {paths['root']}")
    print(f"  checkpoints/ – weight files + .keras inference models")
    print(f"  evaluation/  – vocab_config.json")
    print(f"  metrics/     – training_history.json")
    print(f"  plots/       – loss_curve.png")
    print(f"  config.yaml")
    print(f"{'='*60}\n")

    return model, encoder_model, decoder_model, vocab_config


# ======================================================================
# Inference
# ======================================================================

class Seq2SeqGRUTransliterator:
    """Load saved GRU encoder/decoder models and transliterate roman → Khmer.

    Parameters
    ----------
    model_dir : str
        Root directory for this model, e.g.
        ``outputs/03042026-143052/seq2seq_gru``.
        Expects the new export layout:
        ``model_dir/evaluation/vocab_config.json`` and
        ``model_dir/checkpoints/encoder_model.keras``.
    """

    def __init__(self, model_dir):
        vocab_path = os.path.join(model_dir, "evaluation", "vocab_config.json")
        with open(vocab_path, encoding="utf-8") as f:
            vc = json.load(f)

        self.src_char2idx = vc["src_char2idx"]
        self.tgt_idx2char = {int(k): v for k, v in vc["tgt_idx2char"].items()}
        self.start_token_idx = vc["start_token_idx"]
        self.end_token_idx = vc["end_token_idx"]
        self.max_src_len = vc["max_src_len"]
        self.max_tgt_len = vc["max_tgt_len"]

        ckpt_dir = os.path.join(model_dir, "checkpoints")
        enc_path = os.path.join(ckpt_dir, "best_encoder_model.keras")
        dec_path = os.path.join(ckpt_dir, "best_decoder_model.keras")
        if not os.path.exists(enc_path):
            enc_path = os.path.join(ckpt_dir, "encoder_model.keras")
            dec_path = os.path.join(ckpt_dir, "decoder_model.keras")
        # Load on CPU — avoids cuDNN mask restriction for single-sample inference
        with tf.device("/CPU:0"):
            self.encoder_model = tf.keras.models.load_model(enc_path)
            self.decoder_model = tf.keras.models.load_model(dec_path)
        print(f"Loaded GRU models from {enc_path}")

    def _encode_word(self, word):
        norm = word.strip().lower()
        ids = [self.src_char2idx[c] for c in norm if c in self.src_char2idx]
        if len(ids) > self.max_src_len:
            ids = ids[: self.max_src_len]
        else:
            ids += [0] * (self.max_src_len - len(ids))
        return ids

    def predict_word(self, roman_word):
        """Greedy autoregressive decoding for a single word."""
        seq = self._encode_word(roman_word)
        X_in = np.array([seq], dtype="int32")

        with tf.device("/CPU:0"):
            state_h = self.encoder_model(X_in, training=False)
            target_seq = tf.constant([[self.start_token_idx]], dtype="int32")
            decoded_chars = []

            while True:
                output_tokens, state_h = self.decoder_model(
                    [target_seq, state_h], training=False
                )
                sampled_idx = int(output_tokens[0, -1, :].numpy().argmax())

                if sampled_idx in (self.end_token_idx, 0) or len(decoded_chars) >= self.max_tgt_len:
                    break

                decoded_chars.append(self.tgt_idx2char.get(sampled_idx, ""))
                target_seq = tf.constant([[sampled_idx]], dtype="int32")

        return "".join(decoded_chars)

    def transliterate_sentence(self, roman_sentence):
        """Transliterate a space-separated roman sentence word-by-word."""
        words = roman_sentence.split()
        out = []
        for w in words:
            pred = self.predict_word(w)
            out.append(pred if pred else f"[{w}]")
        return " ".join(out)


# ======================================================================
# Evaluation helpers
# ======================================================================

def normalize_roman_token(token):
    """Lowercase and strip non-alphanumeric characters."""
    token = token.strip()
    token = re.sub(r"[^A-Za-z0-9]+", "", token)
    return token.lower()


def corpus_bleu(references, hypotheses, max_n=4):
    """Word-level corpus BLEU score."""
    weights = [1.0 / max_n] * max_n
    clipped_counts = [0] * max_n
    total_counts = [0] * max_n
    ref_len = 0
    hyp_len = 0

    for ref, hyp in zip(references, hypotheses):
        ref_toks = ref.split()
        hyp_toks = hyp.split()
        ref_len += len(ref_toks)
        hyp_len += len(hyp_toks)

        for n in range(1, max_n + 1):
            ref_ngrams = {}
            for i in range(len(ref_toks) - n + 1):
                ng = tuple(ref_toks[i : i + n])
                ref_ngrams[ng] = ref_ngrams.get(ng, 0) + 1

            hyp_ngrams = {}
            for i in range(len(hyp_toks) - n + 1):
                ng = tuple(hyp_toks[i : i + n])
                hyp_ngrams[ng] = hyp_ngrams.get(ng, 0) + 1

            total_counts[n - 1] += max(len(hyp_toks) - n + 1, 0)
            for ng, count in hyp_ngrams.items():
                clipped_counts[n - 1] += min(count, ref_ngrams.get(ng, 0))

    p_ns = []
    for i in range(max_n):
        if total_counts[i] == 0 or clipped_counts[i] == 0:
            p_ns.append(0.0)
        else:
            p_ns.append(clipped_counts[i] / total_counts[i])

    if hyp_len == 0:
        return 0.0
    bp = 1.0 if hyp_len > ref_len else math.exp(1 - ref_len / hyp_len)

    if not any(p > 0 for p in p_ns):
        return 0.0
    s = sum(w * math.log(p) for w, p in zip(weights, p_ns) if p > 0)
    return bp * math.exp(s)


def char_corpus_bleu(references, hypotheses, max_n=4):
    """Character-level corpus BLEU score (spaces removed)."""
    weights = [1.0 / max_n] * max_n
    clipped_counts = [0] * max_n
    total_counts = [0] * max_n
    ref_len = 0
    hyp_len = 0

    for ref, hyp in zip(references, hypotheses):
        ref_toks = [c for c in ref if not c.isspace()]
        hyp_toks = [c for c in hyp if not c.isspace()]
        ref_len += len(ref_toks)
        hyp_len += len(hyp_toks)

        for n in range(1, max_n + 1):
            ref_ngrams = {}
            for i in range(len(ref_toks) - n + 1):
                ng = tuple(ref_toks[i : i + n])
                ref_ngrams[ng] = ref_ngrams.get(ng, 0) + 1

            hyp_ngrams = {}
            for i in range(len(hyp_toks) - n + 1):
                ng = tuple(hyp_toks[i : i + n])
                hyp_ngrams[ng] = hyp_ngrams.get(ng, 0) + 1

            total_counts[n - 1] += max(len(hyp_toks) - n + 1, 0)
            for ng, count in hyp_ngrams.items():
                clipped_counts[n - 1] += min(count, ref_ngrams.get(ng, 0))

    p_ns = []
    for i in range(max_n):
        if total_counts[i] == 0 or clipped_counts[i] == 0:
            p_ns.append(0.0)
        else:
            p_ns.append(clipped_counts[i] / total_counts[i])

    if hyp_len == 0:
        return 0.0
    bp = 1.0 if hyp_len > ref_len else math.exp(1 - ref_len / hyp_len)

    if not any(p > 0 for p in p_ns):
        return 0.0
    s = sum(w * math.log(p) for w, p in zip(weights, p_ns) if p > 0)
    return bp * math.exp(s)


# ======================================================================
# Main entry point
# ======================================================================

if __name__ == "__main__":
    import argparse

    cfg = load_config("config.ini")

    parser = argparse.ArgumentParser(
        description="Train GRU Seq2Seq model for Khmer Latin → Khmer Script transliteration"
    )
    parser.add_argument("--config", type=str, default="config.ini")
    parser.add_argument("--data",   type=str, default=None, help="Override data path")
    parser.add_argument("--output", type=str, default=None, help="Override base output dir")
    parser.add_argument("--epochs",     type=int,   default=None)
    parser.add_argument("--val-split",  type=float, default=None)
    args = parser.parse_args()

    if args.config != "config.ini":
        cfg = load_config(args.config)

    data_path       = args.data   if args.data   is not None else cfg["data_path"]
    base_output_dir = args.output if args.output is not None else cfg["base_output_dir"]
    epochs          = args.epochs    if args.epochs    is not None else cfg["epochs"]
    val_split       = args.val_split if args.val_split is not None else cfg["val_split"]

    batch_sizes = cfg["batch_sizes"]
    embed_dims  = cfg["embed_dims"]
    latent_dims = cfg["latent_dims"]

    combos = list(itertools.product(batch_sizes, embed_dims, latent_dims))
    print("\n" + "=" * 60)
    print("GRU Seq2Seq — Multi-Version Training")
    print("=" * 60)
    print(f"Data:        {data_path}")
    print(f"Base output: {base_output_dir}")
    print(f"Epochs:      {epochs}")
    print(f"Versions:    {len(combos)}  (batch_sizes×embed_dims×latent_dims)")
    print("=" * 60 + "\n")

    for bs, ed, ld in combos:
        run_dir = _next_version_dir(base_output_dir, bs, ed, ld)
        print(f"\n{'#'*60}")
        print(f"  bs={bs}  ed={ed}  ld={ld}  →  {run_dir}")
        print(f"{'#'*60}\n")
        train(
            dict_path=data_path,
            run_dir=run_dir,
            model_name="seq2seq_gru",
            embed_dim=ed,
            latent_dim=ld,
            epochs=epochs,
            batch_size=bs,
            val_split=val_split,
        )
