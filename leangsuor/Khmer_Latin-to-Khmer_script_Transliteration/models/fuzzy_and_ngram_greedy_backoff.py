"""
Fuzzy N-gram Contextual Predictor for Khmer Latin → Khmer Script Transliteration
=================================================================================

Architecture Overview
---------------------

    INPUT: Roman Sentence ("krong siemrab mean chonosangsay")
                            ↓
    1. TOKENIZATION & PREPROCESSING
       - Lowercase, normalize whitespace, split by space
                            ↓
    2. CANDIDATE GENERATION
       - Exact Matching:  Lookup in word_mappings dictionary
       - Fuzzy Matching:  SequenceMatcher similarity ≥ threshold (0.4–0.5)
                            ↓
    3. CONTEXT SCORING
       - N-gram context     (bigram / trigram language models)
       - Co-occurrence      (word neighbourhood within window=3)
       - Contextual mapping (roman_context, roman_word) → khmer counts
                            ↓
    4. BEAM SEARCH DECODING
       - Maintain top-k hypotheses scored by base_score × context_boost
                            ↓
    OUTPUT: Khmer Sentence ("ក្រុង សៀមរាប មាន ជនសង្ស័យ")

Scoring formula
~~~~~~~~~~~~~~~
    final_score = base_score × context_boost × ngram_score

    base_score   = similarity × weight   (exact ×20, fuzzy ×1)
    context_boost = 1 + context_score × 0.5   (up to 50 % boost)
    ngram_score  = 1 + P(khmer | khmer_context)   (Khmer n-gram LM; applied
                   only when the source word has NO exact match, else 1.0)

Data sources
~~~~~~~~~~~~
    dict_token_merged.json      → word_mappings (vocabulary for fuzzy matching)
    khmer_roman_part1/2.json    → n-grams, contextual mappings, co-occurrence

Hyperparameters
~~~~~~~~~~~~~~~
    max_ngram              3       Maximum n-gram order
    fuzzy_threshold_base   0.5     Min similarity without context
    fuzzy_threshold_context 0.4    Min similarity with context
    beam_size              3       Beam width for decoding
"""

import json
import os
import pickle
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import numpy as np


class KhmerFuzzyContextualPredictor:
    def __init__(
        self, max_ngram=3, fuzzy_threshold_base=0.5, fuzzy_threshold_context=0.4
    ):
        self.word_mappings = defaultdict(list)  # roman -> [(khmer, freq), ...]
        self.khmer_vocab = set()
        self.roman_vocab = set()
        self.max_ngram = max_ngram

        self.fuzzy_threshold_base = fuzzy_threshold_base
        self.fuzzy_threshold_context = fuzzy_threshold_context

        # Context models
        self.roman_ngrams = defaultdict(Counter)  # n-gram -> Counter(next_word)
        self.khmer_ngrams = defaultdict(Counter)  # n-gram -> Counter(next_word)
        self.contextual_mappings = defaultdict(
            self._default_dict_factory
        )  # roman_context -> roman_word -> khmer_word

        # Co-occurrence statistics
        self.cooccurrence = defaultdict(Counter)  # roman_word -> Counter(context_words)

    def _default_dict_factory(self):
        """Factory function for nested defaultdict to make it pickle-compatible"""
        return defaultdict(Counter)

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------

    def preprocess_text(self, text):
        """Clean and normalize text"""
        text = re.sub(r"\s+", " ", str(text).strip())
        return text.lower()

    def tokenize(self, text):
        """Simple tokenization by splitting on spaces"""
        return text.split()

    def build_ngrams(self, words, n):
        """Build n-grams from word list"""
        if len(words) < n:
            return []
        return [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]

    # ------------------------------------------------------------------
    # Vocabulary & context building
    # ------------------------------------------------------------------

    def build_vocabulary(self, sentence_data, token_data=None):
        """Build vocabulary and context models.

        Parameters
        ----------
        sentence_data : list[dict]
            Sentence-level pairs (khmer_roman_part1/2.json).
            Used for n-grams, contextual mappings, and co-occurrence.
        token_data : list[dict], optional
            Word-level pairs (dict_token_merged.json).
            Used for building word_mappings (fuzzy matching vocabulary).
        """
        print("Building vocabulary and context models...")

        # Step 1: Build word_mappings from token_data
        if token_data is not None:
            print("Building word mappings from token dictionary data...")
            for token in token_data:
                khmer_word = self.preprocess_text(token.get("khmer", ""))
                if not khmer_word:
                    continue
                romans = token.get("romanization", "")
                roman_variants = (
                    [self.preprocess_text(r) for r in romans]
                    if isinstance(romans, list)
                    else [self.preprocess_text(romans)]
                )
                roman_variants = [r for r in roman_variants if r]
                if not roman_variants:
                    continue
                self.khmer_vocab.add(khmer_word)
                for roman_word in roman_variants:
                    self.roman_vocab.add(roman_word)
                    self.word_mappings[roman_word].append(khmer_word)
        else:
            print(
                "Warning: No token_data provided. Word mappings will only come from sentence alignment."
            )

        # Step 2: Build n-grams, contextual mappings, and co-occurrence from sentence_data
        print("Building n-gram models from sentence data...")
        for item in sentence_data:
            khmer_text = self.preprocess_text(item["khmer"])
            roman_text = self.preprocess_text(
                item.get("romanization") or item.get("roman", "")
            )

            khmer_words = self.tokenize(khmer_text)
            roman_words = self.tokenize(roman_text)

            self.khmer_vocab.update(khmer_words)
            self.roman_vocab.update(roman_words)

            # Positional alignment as supplementary word mappings
            min_len = min(len(khmer_words), len(roman_words))
            for i in range(min_len):
                self.word_mappings[roman_words[i]].append(khmer_words[i])

            # Context models for different n-gram sizes
            for n in range(2, self.max_ngram + 1):
                roman_ngs = self.build_ngrams(roman_words, n)
                for ngram in roman_ngs:
                    self.roman_ngrams[ngram[:-1]][ngram[-1]] += 1

                khmer_ngs = self.build_ngrams(khmer_words, n)
                for ngram in khmer_ngs:
                    self.khmer_ngrams[ngram[:-1]][ngram[-1]] += 1

                if roman_ngs and khmer_ngs:
                    for i in range(min(len(roman_ngs), len(khmer_ngs))):
                        roman_context = roman_ngs[i][:-1]
                        roman_word = roman_ngs[i][-1]
                        khmer_word = khmer_ngs[i][-1]
                        context_key = " ".join(roman_context)
                        self.contextual_mappings[context_key][roman_word][
                            khmer_word
                        ] += 1

            # Co-occurrence statistics (window = 3)
            for i, roman_word in enumerate(roman_words):
                window_size = 3
                start = max(0, i - window_size)
                end = min(len(roman_words), i + window_size + 1)
                for j in range(start, end):
                    if i != j:
                        self.cooccurrence[roman_word][roman_words[j]] += 1

        # Convert word mappings to frequency-sorted lists
        for roman_word in self.word_mappings:
            word_counts = Counter(self.word_mappings[roman_word])
            self.word_mappings[roman_word] = word_counts.most_common()

        print(
            f"Vocabulary built: {len(self.khmer_vocab)} Khmer words, {len(self.roman_vocab)} Roman words"
        )
        print(f"Word mappings: {len(self.word_mappings)} entries")
        print(f"Roman n-grams: {len(self.roman_ngrams)} entries")
        print(f"Contextual mappings: {len(self.contextual_mappings)} contexts")

    # ------------------------------------------------------------------
    # Similarity & context scoring
    # ------------------------------------------------------------------

    def similarity(self, word1, word2):
        """Calculate similarity between two words using SequenceMatcher.

        similarity = 2 * M / T
        where M = matching chars, T = total chars in both strings.
        """
        return SequenceMatcher(None, word1, word2).ratio()

    # Saturation constant for the context score: larger evidence saturates the
    # boost toward (but never reaching) its ceiling, keeping it graded, monotone,
    # and bounded in [0, 1) so the downstream boost stays within +50%.
    CONTEXT_SATURATION_K = 5.0

    def get_context_score(self, roman_word, context_words, khmer_candidate):
        """Graded context-compatibility score for a candidate, given ROMAN context.

        Accumulates raw evidence — co-occurrence counts plus contextual-mapping
        counts — then applies a saturating transform ``s / (s + k)`` so weak and
        strong context support are distinguished (rather than collapsing to a
        binary 0/1 ratio). Contextual mappings back off from the longest available
        roman context to shorter ones, taking the longest match (context
        shortening), mirroring :meth:`predict_next_word`.
        """
        if not context_words:
            return 0.0

        evidence = 0.0

        # Co-occurrence between the roman word and each roman context word.
        cooc = self.cooccurrence.get(roman_word)
        if cooc:
            for ctx_word in context_words:
                evidence += cooc.get(ctx_word, 0)

        # Contextual mappings with backoff: try the longest roman context first,
        # then progressively shorter ones; stop at the first (longest) match.
        max_ctx = min(len(context_words), self.max_ngram - 1)
        for n in range(max_ctx, 0, -1):
            context_key = " ".join(context_words[-n:])
            mapping = self.contextual_mappings.get(context_key)
            if mapping and roman_word in mapping and khmer_candidate in mapping[roman_word]:
                evidence += mapping[roman_word][khmer_candidate] * 2
                break

        return evidence / (evidence + self.CONTEXT_SATURATION_K)

    def get_ngram_score(self, khmer_candidate, khmer_context):
        """Khmer n-gram language-model factor for a candidate.

        Returns a multiplier in [1, 2] based on the conditional probability
        ``P(khmer_candidate | preceding khmer words)`` estimated from
        :attr:`khmer_ngrams`. 1.0 is neutral (no LM evidence); the factor rises
        toward 2.0 as the candidate becomes more likely given the Khmer history.
        Backs off from the longest available khmer context to shorter ones,
        using the first (longest) context that contains the candidate.

        Used only as a backoff aid when the source word has no exact match; see
        :meth:`predict_word_with_context`.
        """
        if not khmer_context:
            return 1.0

        max_ctx = min(len(khmer_context), self.max_ngram - 1)
        for n in range(max_ctx, 0, -1):
            context_tuple = tuple(khmer_context[-n:])
            counter = self.khmer_ngrams.get(context_tuple)
            if counter and khmer_candidate in counter:
                total = sum(counter.values())
                if total > 0:
                    return 1.0 + counter[khmer_candidate] / total
        return 1.0

    # ------------------------------------------------------------------
    # Candidate generation & prediction
    # ------------------------------------------------------------------

    def find_candidates_with_context(
        self, roman_word, context_words=None, threshold=None, max_candidates=10
    ):
        """Find candidate Khmer words considering context"""
        candidates = []
        roman_word = roman_word.lower()

        if context_words is None:
            context_words = []
        if threshold is None:
            threshold = self.fuzzy_threshold_base

        # Exact match
        if roman_word in self.word_mappings:
            for khmer_word, freq in self.word_mappings[roman_word][:max_candidates]:
                context_score = self.get_context_score(
                    roman_word, context_words, khmer_word
                )
                candidates.append((khmer_word, 1.0, freq, "exact", context_score))

        # Fuzzy matching
        fuzzy_matches = []
        for vocab_roman in self.word_mappings:
            sim = self.similarity(roman_word, vocab_roman)
            if sim >= threshold and vocab_roman != roman_word:
                for khmer_word, freq in self.word_mappings[vocab_roman]:
                    context_score = self.get_context_score(
                        vocab_roman, context_words, khmer_word
                    )
                    fuzzy_matches.append(
                        (khmer_word, sim, freq, "fuzzy", context_score)
                    )

        fuzzy_matches.sort(
            key=lambda x: (x[1] * (x[2] / 10) * (1 + x[4])), reverse=True
        )
        candidates.extend(fuzzy_matches[:max_candidates])
        return candidates[:max_candidates]

    def predict_word_with_context(
        self, roman_word, context_words=None, top_k=5, khmer_context=None
    ):
        """Predict top-k Khmer words considering context.

        ``khmer_context`` is the sequence of preceding KHMER words already
        decoded (supplied by beam search). It feeds the Khmer n-gram LM factor,
        which is applied ONLY when the source word has no exact match — i.e. a
        pure fuzzy backoff — so that the language model helps disambiguate when
        the dictionary cannot. When an exact match exists, the LM stays neutral.
        """
        candidates = self.find_candidates_with_context(
            roman_word,
            context_words,
            threshold=self.fuzzy_threshold_context,
            max_candidates=20,
        )
        if not candidates:
            return []

        # Only back off to the n-gram LM when there is no exact dictionary hit.
        has_exact = any(c[3] == "exact" for c in candidates)

        scored_candidates = []
        for khmer_word, similarity, frequency, match_type, context_score in candidates:
            if match_type == "exact":
                base_score = similarity * 20
            else:
                base_score = similarity * 1

            context_boost = 1 + (context_score * 0.5)
            ngram_score = (
                1.0 if has_exact else self.get_ngram_score(khmer_word, khmer_context)
            )
            final_score = base_score * context_boost * ngram_score

            scored_candidates.append(
                (
                    khmer_word,
                    final_score,
                    similarity,
                    frequency,
                    match_type,
                    context_score,
                )
            )

        seen = set()
        unique_candidates = []
        for candidate in sorted(scored_candidates, key=lambda x: x[1], reverse=True):
            if candidate[0] not in seen:
                seen.add(candidate[0])
                unique_candidates.append(candidate)

        return unique_candidates[:top_k]

    def predict_sentence_contextual(self, roman_sentence):
        """Predict Khmer words for each token in a sentence with contextual information"""
        roman_words = self.tokenize(self.preprocess_text(roman_sentence))
        predictions = {}

        for i, roman_word in enumerate(roman_words):
            context_size = min(self.max_ngram - 1, i)
            context_words = (
                roman_words[max(0, i - context_size) : i] if context_size > 0 else []
            )

            predictions[roman_word] = {
                "position": i,
                "context": context_words,
                "predictions": self.predict_word_with_context(
                    roman_word, context_words, top_k=3
                ),
            }

        return predictions

    def predict_next_word(self, roman_context, top_k=5):
        """Predict next word given Roman context"""
        context_tuple = tuple(roman_context)

        if context_tuple in self.roman_ngrams:
            return self.roman_ngrams[context_tuple].most_common(top_k)

        for n in range(len(roman_context) - 1, 0, -1):
            shorter_context = tuple(roman_context[-n:])
            if shorter_context in self.roman_ngrams:
                return self.roman_ngrams[shorter_context].most_common(top_k)

        return []

    # ------------------------------------------------------------------
    # Beam search translation
    # ------------------------------------------------------------------

    def translate_with_beam_search(self, roman_sentence, beam_size=3, verbose=False):
        """Use beam search for better contextual translation.

        When ``verbose`` is True, prints a step-by-step trace of the decoding:
        the Roman context for each source word, every surviving hypothesis with
        its Khmer context, the ranked candidates with their score breakdown
        (final score, similarity, match type, context score, log-prob added),
        and the beam after pruning. Useful for interpreting why a particular
        Khmer word was chosen.
        """
        roman_words = self.tokenize(self.preprocess_text(roman_sentence))
        beam = [{"translation": [], "score": 0.0, "roman_processed": 0}]

        if verbose:
            print("=" * 70)
            print(f"Input : {' '.join(roman_words)}")
            print(f"Tokens: {roman_words}  (beam_size={beam_size})")
            print("=" * 70)

        for i, roman_word in enumerate(roman_words):
            new_beam = []

            # Context is the preceding ROMAN source tokens (the keys the context
            # tables are built from). It depends only on the source position, not
            # on the hypothesis, so compute it once per step.
            context = roman_words[max(0, i - (self.max_ngram - 1)) : i]

            if verbose:
                print(
                    f"\nStep {i + 1}/{len(roman_words)}  "
                    f"source={roman_word!r}  roman_context={context}"
                )

            for h_idx, hypothesis in enumerate(beam):
                # Preceding KHMER words decoded on this hypothesis, for the
                # n-gram LM backoff (used only when there is no exact match).
                khmer_context = hypothesis["translation"][-(self.max_ngram - 1) :]
                candidates = self.predict_word_with_context(
                    roman_word, context, top_k=beam_size, khmer_context=khmer_context
                )

                if verbose:
                    so_far = " ".join(hypothesis["translation"]) or "∅"
                    print(
                        f"  Hypothesis #{h_idx} (cum_score={hypothesis['score']:.3f}): "
                        f"{so_far}"
                    )
                    print(f"    khmer_context={khmer_context}")
                    if not candidates:
                        print(
                            f"    no candidates → keep source {roman_word!r} "
                            f"(penalty -1.0)"
                        )

                if not candidates:
                    new_beam.append(
                        {
                            "translation": hypothesis["translation"] + [roman_word],
                            "score": hypothesis["score"] - 1.0,
                            "roman_processed": i + 1,
                        }
                    )
                else:
                    for rank, (
                        khmer_word,
                        score,
                        similarity,
                        frequency,
                        match_type,
                        context_score,
                    ) in enumerate(candidates, start=1):
                        logp = np.log(score + 1e-10)
                        if verbose:
                            print(
                                f"      {rank}. {khmer_word:<12} "
                                f"final={score:7.3f}  sim={similarity:.3f}  "
                                f"match={match_type:<5}  ctx={context_score:.3f}  "
                                f"+logp={logp:.3f}"
                            )
                        new_beam.append(
                            {
                                "translation": hypothesis["translation"] + [khmer_word],
                                "score": hypothesis["score"] + logp,
                                "roman_processed": i + 1,
                            }
                        )

            new_beam.sort(key=lambda x: x["score"], reverse=True)
            beam = new_beam[:beam_size]

            if verbose:
                print(f"  --- beam after prune (top {len(beam)}) ---")
                for b_idx, hyp in enumerate(beam):
                    print(
                        f"    {b_idx}. {' '.join(hyp['translation'])}  "
                        f"cum_score={hyp['score']:.3f}"
                    )

        if verbose:
            print("\n" + "=" * 70)
            best = " ".join(beam[0]["translation"]) if beam else " ".join(roman_words)
            print(f"Output: {best}")
            print("=" * 70)

        if beam:
            return beam[0]["translation"]
        return roman_words

    # ------------------------------------------------------------------
    # Persistence (pickle)
    # ------------------------------------------------------------------

    def save_model_pickle(self, filepath):
        """Save the trained model using pickle"""
        model_data = {
            "word_mappings": dict(self.word_mappings),
            "khmer_vocab": self.khmer_vocab,
            "roman_vocab": self.roman_vocab,
            "max_ngram": self.max_ngram,
            "roman_ngrams": dict(self.roman_ngrams),
            "khmer_ngrams": dict(self.khmer_ngrams),
            "contextual_mappings": {
                k: dict(v) for k, v in self.contextual_mappings.items()
            },
            "cooccurrence": dict(self.cooccurrence),
        }
        with open(filepath, "wb") as f:
            pickle.dump(model_data, f)
        print(f"Model saved to {filepath}")

    def load_model_pickle(self, filepath):
        """Load a trained model from pickle"""
        with open(filepath, "rb") as f:
            model_data = pickle.load(f)

        self.word_mappings = defaultdict(list, model_data["word_mappings"])
        self.khmer_vocab = model_data["khmer_vocab"]
        self.roman_vocab = model_data["roman_vocab"]
        self.max_ngram = model_data["max_ngram"]
        self.roman_ngrams = defaultdict(Counter, model_data["roman_ngrams"])
        self.khmer_ngrams = defaultdict(Counter, model_data["khmer_ngrams"])
        self.contextual_mappings = defaultdict(self._default_dict_factory)
        for k, v in model_data["contextual_mappings"].items():
            self.contextual_mappings[k] = defaultdict(Counter, v)
        self.cooccurrence = defaultdict(Counter, model_data["cooccurrence"])
        print(f"Model loaded from {filepath}")

    # ------------------------------------------------------------------
    # Persistence (JSON)
    # ------------------------------------------------------------------

    def save_model(self, filepath):
        """Save the trained model as JSON"""
        model_data = {
            "word_mappings": dict(self.word_mappings),
            "khmer_vocab": list(self.khmer_vocab),
            "roman_vocab": list(self.roman_vocab),
            "max_ngram": self.max_ngram,
            "roman_ngrams": {str(k): dict(v) for k, v in self.roman_ngrams.items()},
            "khmer_ngrams": {str(k): dict(v) for k, v in self.khmer_ngrams.items()},
            "contextual_mappings": {
                k: {k2: dict(v2) for k2, v2 in v.items()}
                for k, v in self.contextual_mappings.items()
            },
            "cooccurrence": {k: dict(v) for k, v in self.cooccurrence.items()},
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(model_data, f, ensure_ascii=False, indent=2)
        print(f"Enhanced model saved to {filepath}")

    def load_model(self, filepath):
        """Load a trained model from JSON"""
        with open(filepath, "r", encoding="utf-8") as f:
            model_data = json.load(f)

        self.word_mappings = defaultdict(list, model_data["word_mappings"])
        self.khmer_vocab = set(model_data["khmer_vocab"])
        self.roman_vocab = set(model_data["roman_vocab"])
        self.max_ngram = model_data.get("max_ngram", 3)

        self.roman_ngrams = defaultdict(Counter)
        for k, v in model_data.get("roman_ngrams", {}).items():
            self.roman_ngrams[eval(k)] = Counter(v)

        self.khmer_ngrams = defaultdict(Counter)
        for k, v in model_data.get("khmer_ngrams", {}).items():
            self.khmer_ngrams[eval(k)] = Counter(v)

        self.contextual_mappings = defaultdict(self._default_dict_factory)
        for k, v in model_data.get("contextual_mappings", {}).items():
            for k2, v2 in v.items():
                self.contextual_mappings[k][k2] = Counter(v2)

        self.cooccurrence = defaultdict(Counter)
        for k, v in model_data.get("cooccurrence", {}).items():
            self.cooccurrence[k] = Counter(v)

        print(f"Enhanced model loaded from {filepath}")

    def export(self, run_dir, model_name="fuzzy_ngram_greedy_backoff"):
        """Save model artefacts to the standardised export directory structure.

        Parameters
        ----------
        run_dir : str
            Timestamped run directory from
            :func:`~translating_khmer_latin_to_khmer_script.export.make_run_dir`.
        model_name : str
            Subdirectory name inside *run_dir* (default: ``fuzzy_ngram_greedy_backoff``).

        Returns
        -------
        dict
            Paths dict returned by :func:`~translating_khmer_latin_to_khmer_script.export.make_model_dirs`.
        """
        from translating_khmer_latin_to_khmer_script.export import (
            make_model_dirs,
            save_config_yaml,
        )

        paths = make_model_dirs(run_dir, model_name)

        # checkpoints – serialise the full model
        checkpoint_path = os.path.join(paths["checkpoints"], "model.pkl")
        with open(checkpoint_path, "wb") as f:
            pickle.dump(self, f)
        print(f"Saved model checkpoint to: {checkpoint_path}")

        # checkpoints – serialise the Roman and Khmer n-gram models separately
        roman_ngram_path = os.path.join(paths["checkpoints"], "roman_ngrams.pkl")
        with open(roman_ngram_path, "wb") as f:
            pickle.dump(dict(self.roman_ngrams), f)
        print(f"Saved Roman n-grams to: {roman_ngram_path}")

        khmer_ngram_path = os.path.join(paths["checkpoints"], "khmer_ngrams.pkl")
        with open(khmer_ngram_path, "wb") as f:
            pickle.dump(dict(self.khmer_ngrams), f)
        print(f"Saved Khmer n-grams to: {khmer_ngram_path}")

        # metrics – vocabulary and n-gram statistics
        metrics = {
            "vocab_size": len(self.word_mappings),
            "khmer_vocab_size": len(self.khmer_vocab),
            "roman_vocab_size": len(self.roman_vocab),
            "bigram_count": sum(len(v) for v in self.roman_ngrams.values()),
            "trigram_count": sum(
                len(v)
                for k, v in self.roman_ngrams.items()
                if isinstance(k, tuple) and len(k) == 2
            ),
        }
        metrics_path = os.path.join(paths["metrics"], "model_stats.json")
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)
        print(f"Saved model stats to: {metrics_path}")

        # config.yaml
        config = {
            "model": {
                "name": model_name,
                "type": "statistical",
                "algorithm": "fuzzy_ngram_greedy_backoff",
            },
            "hyperparameters": {
                "max_ngram": self.max_ngram,
                "fuzzy_threshold_base": self.fuzzy_threshold_base,
                "fuzzy_threshold_context": self.fuzzy_threshold_context,
                "beam_size": 3,
            },
        }
        save_config_yaml(config, paths["config_yaml"])
        print(f"Saved config to: {paths['config_yaml']}")

        return paths
