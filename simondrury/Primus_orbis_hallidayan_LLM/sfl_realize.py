#!/usr/bin/env python3
"""
sfl_realize.py
Instantiation: meaning state -> lexical realization in language L.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

DIM = ["ideational", "field", "interpersonal", "tenor", "textual", "mode"]
DEFAULT_N_DIM = 6


@dataclass
class LexicalItem:
    form: str
    lang: str
    fingerprint: np.ndarray


class VocabularySpace:
    def __init__(self, lang: str, n_dim: int = DEFAULT_N_DIM):
        self.lang = lang
        self.n_dim = n_dim
        self._items: List[LexicalItem] = []

    def add(self, form: str, fingerprint: List[float]):
        fp = np.array(fingerprint, dtype=float)
        assert fp.shape == (self.n_dim,)
        self._items.append(LexicalItem(form=form, lang=self.lang, fingerprint=fp))

    def nearest(self, M_out: np.ndarray, k: int = 5) -> List[Tuple[str, float]]:
        dists = [
            (item.form, float(np.linalg.norm(item.fingerprint - M_out)))
            for item in self._items
        ]
        return sorted(dists, key=lambda x: x[1])[:k]

    def realize(self, M_out: np.ndarray) -> str:
        return self.nearest(M_out, k=1)[0][0]

    def __len__(self):
        return len(self._items)

    def __repr__(self):
        return f"VocabularySpace(lang={self.lang}, n_dim={self.n_dim}, items={len(self)})"


def build_pilot_en() -> VocabularySpace:
    v = VocabularySpace(lang="EN")
    v.add("hey", [-0.7, -0.5, 0.8, 0.9, 0.6, -0.6])
    v.add("hello", [-0.6, -0.4, 0.7, 0.8, 0.5, -0.5])
    v.add("please", [-0.2, 0.0, 0.9, 1.0, 0.4, -0.4])
    v.add("thank you", [0.1, 0.2, 1.0, 1.0, 0.5, -0.5])
    v.add("sorry", [-0.1, 0.0, 0.9, 1.0, 0.3, -0.5])
    v.add("print", [0.6, 0.8, 0.5, 0.6, 0.9, -0.6])
    v.add("run", [0.5, 0.7, 0.4, 0.5, 0.8, -0.6])
    v.add("write", [0.6, 0.7, 0.4, 0.6, 0.9, -0.5])
    v.add("show", [0.4, 0.6, 0.5, 0.6, 0.8, -0.5])
    v.add("for me", [0.4, 0.6, 0.9, 0.9, 1.0, -0.6])
    v.add("hello world", [0.8, 0.9, 0.3, 0.4, 0.9, -0.6])
    v.add("code", [0.7, 0.9, 0.2, 0.3, 0.8, -0.7])
    v.add("function", [0.8, 1.0, 0.1, 0.2, 0.9, -0.7])
    v.add("output", [0.6, 0.8, 0.2, 0.3, 0.8, -0.6])
    return v


def build_pilot_es() -> VocabularySpace:
    v = VocabularySpace(lang="ES")
    v.add("buenos dias", [-0.6, -0.3, 0.8, 0.7, 0.7, 0.4])
    v.add("hola", [-0.5, -0.4, 0.7, 0.8, 0.5, 0.3])
    v.add("por favor", [-0.2, 0.0, 0.9, 1.0, 0.4, 0.3])
    v.add("gracias", [0.1, 0.2, 1.0, 1.0, 0.5, 0.3])
    v.add("perdon", [-0.1, 0.0, 0.9, 1.0, 0.3, 0.3])
    v.add("hoy", [-0.1, 0.2, 0.3, 0.4, 0.6, 0.4])
    v.add("viernes", [0.2, 0.3, 0.2, 0.3, 0.7, 0.4])
    v.add("manana", [0.1, 0.2, 0.2, 0.3, 0.6, 0.4])
    v.add("CNN", [0.5, 1.0, 0.6, 0.2, 0.9, 0.8])
    v.add("noticias", [0.4, 0.9, 0.4, 0.3, 0.8, 0.7])
    v.add("importante", [0.6, 0.7, 0.7, 0.8, 0.8, 0.6])
    v.add("para mi", [0.5, 0.6, 0.8, 0.9, 0.7, 0.5])
    v.add("para muchos", [0.7, 0.8, 0.8, 0.8, 0.9, 0.6])
    v.add("dia", [0.3, 0.4, 0.4, 0.5, 0.6, 0.4])
    return v


def build_pilot_pt() -> VocabularySpace:
    v = VocabularySpace(lang="PT")
    v.add("ola", [-0.6, -0.4, 0.7, 0.8, 0.5, 0.4])
    v.add("bom dia", [-0.6, -0.3, 0.8, 0.7, 0.7, 0.5])
    v.add("por favor", [-0.2, 0.0, 0.9, 1.0, 0.4, 0.4])
    v.add("obrigado", [0.1, 0.2, 1.0, 1.0, 0.5, 0.4])
    v.add("desculpe", [-0.1, 0.0, 0.9, 1.0, 0.3, 0.4])
    v.add("hoje", [-0.1, 0.2, 0.3, 0.4, 0.6, 0.5])
    v.add("sexta-feira", [0.2, 0.3, 0.2, 0.3, 0.7, 0.5])
    v.add("imprimir", [0.6, 0.8, 0.5, 0.6, 0.9, -0.5])
    v.add("codigo", [0.7, 0.9, 0.2, 0.3, 0.8, -0.6])
    v.add("importante", [0.6, 0.7, 0.7, 0.8, 0.8, 0.6])
    v.add("noticias", [0.4, 0.9, 0.4, 0.3, 0.8, 0.7])
    v.add("para mim", [0.5, 0.6, 0.8, 0.9, 0.7, 0.5])
    v.add("para muitos", [0.7, 0.8, 0.8, 0.8, 0.9, 0.6])
    v.add("ola mundo", [0.8, 0.9, 0.3, 0.4, 0.9, -0.5])
    return v


def build_pilot_it() -> VocabularySpace:
    v = VocabularySpace(lang="IT")
    v.add("ciao", [-0.6, -0.4, 0.8, 0.9, 0.5, 0.3])
    v.add("buongiorno", [-0.6, -0.3, 0.7, 0.7, 0.7, 0.4])
    v.add("per favore", [-0.2, 0.0, 0.9, 1.0, 0.4, 0.3])
    v.add("grazie", [0.1, 0.2, 1.0, 1.0, 0.5, 0.3])
    v.add("scusa", [-0.1, 0.0, 0.9, 1.0, 0.3, 0.3])
    v.add("oggi", [-0.1, 0.2, 0.3, 0.4, 0.6, 0.4])
    v.add("venerdi", [0.2, 0.3, 0.2, 0.3, 0.7, 0.4])
    v.add("stampa", [0.6, 0.8, 0.5, 0.6, 0.9, -0.6])
    v.add("codice", [0.7, 0.9, 0.2, 0.3, 0.8, -0.7])
    v.add("importante", [0.6, 0.7, 0.7, 0.8, 0.8, 0.5])
    v.add("notizie", [0.4, 0.9, 0.4, 0.3, 0.8, 0.7])
    v.add("per me", [0.5, 0.6, 0.8, 0.9, 0.7, 0.4])
    v.add("per molti", [0.7, 0.8, 0.8, 0.8, 0.9, 0.6])
    v.add("ciao mondo", [0.8, 0.9, 0.3, 0.4, 0.9, -0.6])
    return v


def build_pilot_zh() -> VocabularySpace:
    v = VocabularySpace(lang="ZH")
    v.add("ni hao", [-0.5, -0.3, 0.7, 0.7, 0.6, 0.2])
    v.add("zao shang hao", [-0.5, -0.2, 0.7, 0.6, 0.7, 0.5])
    v.add("qing", [-0.2, 0.0, 0.8, 0.9, 0.5, 0.3])
    v.add("xie xie", [0.1, 0.2, 0.9, 0.9, 0.5, 0.3])
    v.add("duibuqi", [-0.1, 0.0, 0.8, 0.9, 0.3, 0.3])
    v.add("jintian", [-0.1, 0.2, 0.2, 0.3, 0.6, 0.6])
    v.add("xingqiwu", [0.2, 0.3, 0.1, 0.2, 0.7, 0.6])
    v.add("dayin", [0.6, 0.8, 0.4, 0.5, 0.9, 0.1])
    v.add("daima", [0.7, 0.9, 0.1, 0.2, 0.8, -0.2])
    v.add("zhongyao", [0.6, 0.7, 0.5, 0.6, 0.8, 0.6])
    v.add("xinwen", [0.4, 0.9, 0.3, 0.2, 0.8, 0.8])
    v.add("dui wo lai shuo", [0.5, 0.6, 0.7, 0.8, 0.7, 0.5])
    v.add("ni hao shijie", [0.8, 0.9, 0.2, 0.3, 0.9, 0.1])
    v.add("dajia", [0.7, 0.8, 0.7, 0.7, 0.9, 0.6])
    return v


def realize_trajectory(states: np.ndarray, vocab: VocabularySpace, k: int = 3) -> List[Dict]:
    results = []
    for t, state in enumerate(states):
        candidates = vocab.nearest(state, k=k)
        results.append({
            "step": t,
            "state": state.tolist(),
            "best": candidates[0][0],
            "candidates": candidates,
        })
    return results
