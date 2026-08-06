"""
Export utilities for generating a unified, timestamped output directory structure.

Every model run produces:

    outputs/<DDMMYYYY-HHMMSS>/<model-name>/
        checkpoints/   – weight files (.h5, .keras) or serialised model (.pkl)
        evaluation/    – vocab configs, raw prediction outputs
        metrics/       – loss history, BLEU scores, model statistics (JSON)
        plots/         – training-curve images (PNG)
        config.yaml    – YAML snapshot of model + training hyperparameters

Usage
-----
    from translating_khmer_latin_to_khmer_script.export import (
        make_run_dir, make_model_dirs, save_config_yaml
    )

    run_dir = make_run_dir("outputs")              # call once per run
    paths   = make_model_dirs(run_dir, "seq2seq_gru")
    save_config_yaml({"model": {...}}, paths["config_yaml"])
"""

import os
from datetime import datetime


def make_run_dir(base_dir: str = "outputs") -> str:
    """Create ``base_dir/DDMMYYYY-HHMMSS/`` and return its absolute path.

    Parameters
    ----------
    base_dir:
        Parent directory under the project root (default: ``outputs``).

    Returns
    -------
    str
        Path to the newly created run directory.
    """
    stamp = datetime.now().strftime("%d%m%Y-%H%M%S")
    path = os.path.join(base_dir, stamp)
    os.makedirs(path, exist_ok=True)
    return path


def make_model_dirs(run_dir: str, model_name: str) -> dict:
    """Create the standard four subdirectories for *model_name* inside *run_dir*.

    Parameters
    ----------
    run_dir:
        Timestamped run directory returned by :func:`make_run_dir`.
    model_name:
        Short identifier, e.g. ``"seq2seq_gru"`` or ``"fuzzy_ngram_greedy_backoff"``.

    Returns
    -------
    dict with keys:
        ``root``, ``checkpoints``, ``evaluation``, ``metrics``, ``plots``,
        ``config_yaml``  (path string, *not* a directory – file is created by caller).
    """
    root = os.path.join(run_dir, model_name)
    dirs = {
        "root": root,
        "checkpoints": os.path.join(root, "checkpoints"),
        "evaluation": os.path.join(root, "evaluation"),
        "metrics": os.path.join(root, "metrics"),
        "plots": os.path.join(root, "plots"),
        "config_yaml": os.path.join(root, "config.yaml"),
    }
    for key, path in dirs.items():
        if key != "config_yaml":
            os.makedirs(path, exist_ok=True)
    return dirs


def save_config_yaml(config_dict: dict, yaml_path: str) -> None:
    """Serialise *config_dict* to a human-readable YAML file.

    Parameters
    ----------
    config_dict:
        Nested dict with model / training / data settings.
    yaml_path:
        Destination file path (``paths["config_yaml"]`` from :func:`make_model_dirs`).
    """
    import yaml  # PyYAML – listed in requirements.txt

    with open(yaml_path, "w", encoding="utf-8") as fh:
        yaml.dump(
            config_dict,
            fh,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
