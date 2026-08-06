import gradio as gr
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel
from scipy.linalg import svd
from scipy import stats
import warnings
import random
warnings.filterwarnings('ignore')

# ============================================================
# CLASE SDMonitor — version corregida
# Cambios respecto a la version anterior:
#   1. Ademas del compuesto S, guarda coherencia/foco espectral/
#      isotropia POR SEPARADO para cada frase (desagregacion).
#   2. evaluate_corpus ahora calcula: media, desviacion estandar,
#      test t pareado, test de Wilcoxon (no parametrico, mas robusto
#      con N=50), y tamano de efecto (d de Cohen para muestras pareadas).
#   3. Sin estos numeros, un "Delta_S" negativo o positivo no dice
#      si es una diferencia real o ruido de muestreo -- ahora se
#      reporta el p-valor explicitamente.
#   4. NUEVO: los resultados del tab en ingles ahora se traducen a
#      claves/valores en ingles (antes el JSON salia en espanol en
#      ambas pestanas, lo cual confundia a los interesados de habla
#      inglesa). El tab en espanol sigue mostrando el JSON original
#      en espanol; el core de calculo (SDMonitor) no cambia.
# ============================================================
class SDMonitor:
    def __init__(self, model, tokenizer, max_length=128):
        self.model = model
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.model.eval()

    def _compute_components(self, text):
        """Devuelve las tres componentes por separado ademas del
        compuesto S, para poder ver de donde viene cualquier efecto."""
        try:
            inputs = self.tokenizer(
                text, return_tensors="pt", truncation=True,
                max_length=self.max_length, padding=True,
            )
            inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs, output_hidden_states=True)

            if not hasattr(outputs, 'hidden_states') or outputs.hidden_states is None:
                return None

            embeddings = outputs.hidden_states[-1][0].cpu().numpy()
            if embeddings.shape[0] < 2:
                return None

            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            emb_norm = embeddings / (norms + 1e-10)

            # Componente 1: coherencia local (coseno entre tokens consecutivos)
            sims = np.einsum("ij,ij->i", emb_norm[:-1], emb_norm[1:])
            local_coh = float(np.clip(np.mean(sims), -1.0, 1.0))

            # Componente 2: foco espectral (concentracion de varianza en
            # las primeras 5 direcciones principales via SVD)
            try:
                _, s, _ = svd(emb_norm, full_matrices=False)
                s_squared = s ** 2
                spectral_focus = float(np.sum(s_squared[:5]) / (np.sum(s_squared) + 0.1))
            except np.linalg.LinAlgError:
                spectral_focus = 0.0

            # Componente 3: isotropia real (via numero de condicion de
            # la matriz de Gram)
            gram = emb_norm @ emb_norm.T
            eig_vals = np.linalg.eigvalsh(gram)
            eig_vals = eig_vals[eig_vals > 1e-6]
            if len(eig_vals) > 0:
                condition_num = np.max(eig_vals) / (np.min(eig_vals) + 0.1)
                true_isotropy = float(1.0 / (1.0 + np.log(condition_num + 1)))
            else:
                true_isotropy = 0.0

            S = ((1 + local_coh) / 2) * spectral_focus * (1 - true_isotropy)

            return {
                "S": float(S),
                "coherence": local_coh,
                "spectral_focus": spectral_focus,
                "isotropy": true_isotropy,
            }
        except Exception as e:
            print(f"Error: {e}")
            return None

    def evaluate_corpus(self, coherent_list, broken_list):
        S_coh, S_bro = [], []
        coh_coh, coh_bro = [], []       # componente coherencia
        spec_coh, spec_bro = [], []     # componente foco espectral
        iso_coh, iso_bro = [], []       # componente isotropia
        errors = 0

        for coh_text, bro_text in zip(coherent_list, broken_list):
            r_coh = self._compute_components(coh_text)
            r_bro = self._compute_components(bro_text)

            if r_coh is not None and r_bro is not None:
                # Solo se guarda el par si AMBAS frases se procesaron
                # bien -- para que el test pareado tenga sentido (mismo
                # numero de observaciones en ambos lados, emparejadas
                # una a una en el mismo orden)
                S_coh.append(r_coh["S"]); S_bro.append(r_bro["S"])
                coh_coh.append(r_coh["coherence"]); coh_bro.append(r_bro["coherence"])
                spec_coh.append(r_coh["spectral_focus"]); spec_bro.append(r_bro["spectral_focus"])
                iso_coh.append(r_coh["isotropy"]); iso_bro.append(r_bro["isotropy"])
            else:
                errors += 1

        if len(S_coh) < 3:
            return {"Error": f"Muy pocas frases procesadas correctamente ({len(S_coh)}). "
                              f"Se necesitan al menos 3 pares para un test estadistico. Errores: {errors}"}

        S_coh_arr, S_bro_arr = np.array(S_coh), np.array(S_bro)
        diffs = S_coh_arr - S_bro_arr

        # Test t pareado (asume diferencias aprox. normales)
        t_stat, p_value_t = stats.ttest_rel(S_coh_arr, S_bro_arr)

        # Test de Wilcoxon (no parametrico, no asume normalidad --
        # mas confiable con N=50 y datos que pueden no ser gaussianos)
        try:
            w_stat, p_value_w = stats.wilcoxon(S_coh_arr, S_bro_arr)
        except ValueError:
            # Wilcoxon falla si todas las diferencias son cero
            w_stat, p_value_w = None, None

        # Tamano de efecto: d de Cohen para muestras pareadas
        # (diferencia media dividida por la desviacion estandar de
        # las diferencias -- indica si el efecto es grande o chico,
        # independientemente de si es "significativo")
        cohens_d = float(np.mean(diffs) / (np.std(diffs, ddof=1) + 1e-10))

        def interpretar_d(d):
            ad = abs(d)
            if ad < 0.2: return "insignificante"
            elif ad < 0.5: return "pequeno"
            elif ad < 0.8: return "mediano"
            else: return "grande"

        resultado = {
            "S_coherente": {
                "media": float(np.mean(S_coh_arr)),
                "desviacion_estandar": float(np.std(S_coh_arr, ddof=1)),
            },
            "S_roto": {
                "media": float(np.mean(S_bro_arr)),
                "desviacion_estandar": float(np.std(S_bro_arr, ddof=1)),
            },
            "Delta_S": float(np.mean(diffs)),
            "significancia_estadistica": {
                "test_t_pareado": {
                    "estadistico": float(t_stat),
                    "p_valor": float(p_value_t),
                    "es_significativo_al_5pct": bool(p_value_t < 0.05),
                },
                "test_wilcoxon": {
                    "estadistico": float(w_stat) if w_stat is not None else None,
                    "p_valor": float(p_value_w) if p_value_w is not None else None,
                    "es_significativo_al_5pct": bool(p_value_w < 0.05) if p_value_w is not None else None,
                },
                "tamano_efecto_cohen_d": cohens_d,
                "interpretacion_tamano_efecto": interpretar_d(cohens_d),
            },
            "componentes_desagregados": {
                "coherencia_local": {
                    "coherente_media": float(np.mean(coh_coh)),
                    "roto_media": float(np.mean(coh_bro)),
                },
                "foco_espectral": {
                    "coherente_media": float(np.mean(spec_coh)),
                    "roto_media": float(np.mean(spec_bro)),
                },
                "isotropia": {
                    "coherente_media": float(np.mean(iso_coh)),
                    "roto_media": float(np.mean(iso_bro)),
                },
            },
            "N_pares_validos": len(S_coh),
            "errores_de_procesamiento": errors,
        }
        return resultado


# ---------- TRADUCCION ES -> EN PARA EL TAB EN INGLES ----------
# Traduce claves y algunos valores de cadena (no toca numeros/booleanos).
# El calculo interno (SDMonitor.evaluate_corpus) no cambia -- esto solo
# traduce el diccionario de salida antes de mostrarlo en el tab EN.
KEY_TRANSLATIONS = {
    "S_coherente": "S_coherent",
    "S_roto": "S_broken",
    "media": "mean",
    "desviacion_estandar": "std_dev",
    "Delta_S": "Delta_S",
    "significancia_estadistica": "statistical_significance",
    "test_t_pareado": "paired_t_test",
    "estadistico": "statistic",
    "p_valor": "p_value",
    "es_significativo_al_5pct": "significant_at_5pct",
    "test_wilcoxon": "wilcoxon_test",
    "tamano_efecto_cohen_d": "effect_size_cohens_d",
    "interpretacion_tamano_efecto": "effect_size_interpretation",
    "componentes_desagregados": "disaggregated_components",
    "coherencia_local": "local_coherence",
    "coherente_media": "coherent_mean",
    "roto_media": "broken_mean",
    "foco_espectral": "spectral_focus",
    "isotropia": "isotropy",
    "N_pares_validos": "N_valid_pairs",
    "errores_de_procesamiento": "processing_errors",
    "Error": "Error",
}

VALUE_TRANSLATIONS = {
    "insignificante": "negligible",
    "pequeno": "small",
    "mediano": "medium",
    "grande": "large",
}


def translate_result_to_english(obj):
    """Traduce recursivamente claves (siempre) y valores de texto
    conocidos (solo si estan en VALUE_TRANSLATIONS) de espanol a ingles."""
    if isinstance(obj, dict):
        return {
            KEY_TRANSLATIONS.get(k, k): translate_result_to_english(v)
            for k, v in obj.items()
        }
    if isinstance(obj, str):
        return VALUE_TRANSLATIONS.get(obj, obj)
    return obj


# ---------- FUNCION PARA GENERAR CORPUS ROTO ----------
def generate_broken(corpus, seed=42):
    random.seed(seed)
    broken = []
    for sent in corpus:
        words = sent.rstrip('.').split()
        shuffled = random.sample(words, len(words))
        broken.append(' '.join(shuffled) + '.')
    return broken


# ---------- CORPUS ESPAÑOL (50 frases) ----------
CORPUS_ES_COHERENT = [
    "La inteligencia artificial transforma nuestra comprensión del lenguaje.",
    "Los neurocientíficos estudian las conexiones sinápticas del cerebro humano.",
    "La fotosíntesis convierte la luz solar en energía química.",
    "Los átomos se organizan en estructuras cristalinas complejas.",
    "El ADN contiene las instrucciones genéticas de los organismos vivos.",
    "Las ondas electromagnéticas viajan a la velocidad de la luz.",
    "Los ecosistemas marinos mantienen el equilibrio del planeta.",
    "La gravedad mantiene a los planetas en órbita alrededor del sol.",
    "Las reacciones químicas liberan o absorben energía térmica.",
    "Los algoritmos de aprendizaje profundo procesan millones de datos.",
    "La mecánica cuántica desafía nuestra intuición sobre la realidad.",
    "El cambio climático es el desafío más urgente de nuestra generación.",
    "Las células madre ofrecen esperanza para enfermedades degenerativas.",
    "La teoría de la relatividad transformó nuestra comprensión del espacio.",
    "Los exoplanetas podrían albergar formas de vida desconocidas.",
    "El gato se sentó en la alfombra y comenzó a ronronear.",
    "Los niños juegan al fútbol en el parque cada tarde soleada.",
    "Mi abuela prepara el desayuno todas las mañanas temprano.",
    "El perro ladra cuando escucha ruidos extraños en la noche.",
    "Las flores del jardín necesitan agua todos los días.",
    "Mi hermano estudia medicina en la universidad de Santiago.",
    "El autobús llega puntualmente a las ocho de la mañana.",
    "La profesora explica la lección con mucha paciencia.",
    "Los pájaros cantan al amanecer desde los árboles cercanos.",
    "El cartero entrega las cartas en la tarde.",
    "El café de la mañana es el mejor momento del día.",
    "Mi hermana mayor vive en Barcelona desde hace años.",
    "El cine de barrio es un tesoro cultural que debemos preservar.",
    "Los viernes por la noche siempre salimos a cenar.",
    "La biblioteca municipal organiza actividades para niños.",
    "El tiempo fluye irreversiblemente hacia el futuro.",
    "La conciencia emerge de procesos neurales complejos.",
    "La belleza reside en la percepción subjetiva del observador.",
    "El conocimiento se construye a través de la experiencia acumulada.",
    "La libertad implica responsabilidad sobre nuestras decisiones.",
    "El significado surge del contexto y las relaciones semánticas.",
    "La verdad se revela mediante el método científico riguroso.",
    "La memoria transforma nuestras experiencias en narrativas coherentes.",
    "El lenguaje estructura nuestra forma de pensar el mundo.",
    "La razón nos permite distinguir lo real de lo aparente.",
    "La inteligencia artificial está redefiniendo los límites de la creatividad.",
    "El internet de las cosas conectará cada dispositivo del hogar.",
    "La computación cuántica resolverá problemas imposibles para las máquinas actuales.",
    "Los vehículos autónomos transformarán el transporte urbano.",
    "La impresión 3D permitirá construir casas en el espacio.",
    "El conocimiento científico siempre debe estar al servicio de la humanidad.",
    "La educación es la herramienta más poderosa para transformar sociedades.",
    "El aprendizaje continuo es clave para adaptarse al cambio tecnológico.",
    "La colaboración entre disciplinas genera las soluciones más innovadoras.",
    "La curiosidad es el motor más potente del conocimiento humano."
]

# ---------- CORPUS INGLÉS (50 frases) ----------
CORPUS_EN_COHERENT = [
    "Artificial intelligence is transforming our understanding of language.",
    "Neuroscientists study the synaptic connections of the human brain.",
    "Photosynthesis converts sunlight into chemical energy.",
    "Atoms organize into complex crystalline structures.",
    "DNA contains the genetic instructions of all living organisms.",
    "Electromagnetic waves travel at the speed of light.",
    "Marine ecosystems maintain the planet's delicate balance.",
    "Gravity keeps planets in orbit around the sun.",
    "Chemical reactions release or absorb thermal energy.",
    "Deep learning algorithms process millions of data points.",
    "Quantum mechanics challenges our intuition about reality.",
    "Climate change is the most urgent challenge of our generation.",
    "Stem cells offer hope for degenerative diseases.",
    "The theory of relativity transformed our understanding of space.",
    "Exoplanets may harbor unknown forms of life.",
    "The cat sat on the carpet and began to purr.",
    "Children play soccer in the park every sunny afternoon.",
    "My grandmother prepares breakfast early every morning.",
    "The dog barks when it hears strange noises at night.",
    "The flowers in the garden need water every day.",
    "My brother studies medicine at the University of Santiago.",
    "The bus arrives punctually at eight in the morning.",
    "The teacher explains the lesson with great patience.",
    "The birds sing at dawn from the nearby trees.",
    "The mailman delivers the letters in the afternoon.",
    "Morning coffee is the best moment of the day.",
    "My older sister has lived in Barcelona for years.",
    "The neighborhood cinema is a cultural treasure we must preserve.",
    "On Friday nights we always go out for dinner.",
    "The public library organizes activities for children.",
    "Time flows irreversibly toward the future.",
    "Consciousness emerges from complex neural processes.",
    "Beauty resides in the subjective perception of the observer.",
    "Knowledge is constructed through accumulated experience.",
    "Freedom implies responsibility for our decisions.",
    "Meaning arises from context and semantic relationships.",
    "Truth is revealed through rigorous scientific method.",
    "Memory transforms our experiences into coherent narratives.",
    "Language structures our way of thinking about the world.",
    "Reason allows us to distinguish the real from the apparent.",
    "Artificial intelligence is redefining the boundaries of creativity.",
    "The Internet of Things will connect every device in the home.",
    "Quantum computing will solve problems impossible for current machines.",
    "Autonomous vehicles will transform urban transportation.",
    "3D printing will enable the construction of houses in space.",
    "Scientific knowledge must always serve humanity.",
    "Education is the most powerful tool for transforming societies.",
    "Continuous learning is key to adapting to technological change.",
    "Collaboration across disciplines generates the most innovative solutions.",
    "Yes, curiosity is the most powerful engine of human knowledge."
]

CORPUS_ES_BROKEN = generate_broken(CORPUS_ES_COHERENT)
CORPUS_EN_BROKEN = generate_broken(CORPUS_EN_COHERENT)

print("Loading DistilBERT model...")
MODEL_NAME = "distilbert-base-uncased"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME)
monitor = SDMonitor(model, tokenizer)


def analyze_corpus_es():
    return monitor.evaluate_corpus(CORPUS_ES_COHERENT, CORPUS_ES_BROKEN)

def analyze_corpus_en():
    resultado = monitor.evaluate_corpus(CORPUS_EN_COHERENT, CORPUS_EN_BROKEN)
    return translate_result_to_english(resultado)


# ---------- TEXTOS BILINGUES ----------
INTRO_ES = """
# 🌐 Monitor de Inversión de Fase de Densidad Semántica (v2 — con test estadístico)
**ΔS = S(coherente) − S(roto)**

⚠️ **Convención de signo:** en el marco de Corpus Density Conjecture de este
proyecto, **ΔS < 0** (el texto ROTO obtiene mayor densidad que el coherente)
se etiqueta `STABLE_MANIFOLD`, y **ΔS > 0** se etiqueta `ENTROPIC_DRIFT`.
Esta convención es específica de este marco teórico y es contraria a la
intuición habitual — léela con esa aclaración en mente, no asumas que
"STABLE" significa "el modelo distingue bien lo coherente de lo roto".

Cada frase "rota" reordena aleatoriamente las mismas palabras de su frase
coherente correspondiente — mismo vocabulario, misma longitud, solo cambia
el orden sintáctico. Esto aísla la variable de estructura gramatical de
cualquier otro factor (tema, longitud, léxico).

**En esta versión:** se reporta desviación estándar, un test t
pareado, un test de Wilcoxon (no paramétrico, más robusto), el tamaño de
efecto (d de Cohen), y las tres componentes (coherencia, foco espectral,
isotropía) por separado — para saber si el resultado es estadísticamente
real y de dónde viene, no solo un promedio suelto.

**Modelo:** DistilBERT (ligero, rápido) · **Corpus:** 50 frases
"""

INTRO_EN = """
# 🌐 Semantic Density Phase Inversion Monitor (v2 — with statistical testing)
**ΔS = S(coherent) − S(broken)**

⚠️ **Sign convention:** under this project's Corpus Density Conjecture
framework, **ΔS < 0** (the BROKEN text scores higher density than the
coherent one) is labeled `STABLE_MANIFOLD`, and **ΔS > 0** is labeled
`ENTROPIC_DRIFT`. This convention is specific to this theoretical framework
and runs counter to normal intuition — read it with that caveat in mind;
don't assume "STABLE" means "the model tells coherent and broken text apart
well."

Each "broken" sentence randomly reshuffles the same words from its
corresponding coherent sentence — same vocabulary, same length, only the
syntactic order changes. This isolates grammatical structure from every
other factor (topic, length, lexicon).

**In this version:** the report includes standard deviation, a paired
t-test, a Wilcoxon test (non-parametric, more robust), effect size
(Cohen's d), and the three components (coherence, spectral focus,
isotropy) reported separately — so you can tell whether the result is
statistically real and where it comes from, not just a loose average.

**Model:** DistilBERT (lightweight, fast) · **Corpus:** 50 sentences
"""

FOOTER_ES = """
---
**Cómo leer el p-valor:** si `p_valor < 0.05` en el test t o en Wilcoxon,
la diferencia entre coherente y roto es estadísticamente significativa
(poco probable que sea ruido de muestreo con N=50). Si `p_valor >= 0.05`,
la diferencia observada podría deberse simplemente al azar de qué 50
frases se eligieron, y no debe interpretarse como un efecto real todavía.

**Referencia:** Cerda Seguel, D. (2026). The Stone Guest: Harmonic
Quantization of Semantic Phase Transitions in Large Language Models
(Version 2.0). Zenodo. https://doi.org/10.5281/zenodo.20820598
"""

FOOTER_EN = """
---
**How to read the p-value:** if `p_value < 0.05` on the t-test or the
Wilcoxon test, the difference between coherent and broken is statistically
significant (unlikely to be sampling noise with N=50). If `p_value >= 0.05`,
the observed difference could simply be due to chance in which 50 sentences
were picked, and shouldn't yet be interpreted as a real effect.

**Reference:** Cerda Seguel, D. (2026). The Stone Guest: Harmonic
Quantization of Semantic Phase Transitions in Large Language Models
(Version 2.0). Zenodo. https://doi.org/10.5281/zenodo.20820598
"""

# ---------- INTERFAZ BILINGÜE ----------
with gr.Blocks(title="Semantic Density Monitor v2", theme=gr.themes.Soft()) as demo:

    # El primer gr.Tab() declarado es el que Gradio abre por defecto al
    # cargar la pagina -- English va primero para que sea el idioma
    # por defecto, y Espanol queda como pestana secundaria.
    with gr.Tab("🇬🇧 English"):
        gr.Markdown(INTRO_EN)
        with gr.Row():
            with gr.Column():
                btn_en = gr.Button("📊 Run analysis (EN)", variant="primary")
                gr.Markdown("**Estimated time:** ~5-10 seconds")
            with gr.Column():
                output_en = gr.JSON(label="Results (EN)")
        btn_en.click(analyze_corpus_en, inputs=[], outputs=output_en)

        with gr.Accordion("📖 View full corpus (50 sentences)", open=False):
            gr.Markdown("### Coherent sentences")
            for i, sent in enumerate(CORPUS_EN_COHERENT, 1):
                gr.Markdown(f"{i}. {sent}")
            gr.Markdown("### Broken sentences")
            for i, sent in enumerate(CORPUS_EN_BROKEN, 1):
                gr.Markdown(f"{i}. {sent}")

        gr.Markdown(FOOTER_EN)

    with gr.Tab("🇪🇸 Español"):
        gr.Markdown(INTRO_ES)
        with gr.Row():
            with gr.Column():
                btn_es = gr.Button("📊 Ejecutar análisis (ES)", variant="primary")
                gr.Markdown("**Tiempo estimado:** ~5-10 segundos")
            with gr.Column():
                output_es = gr.JSON(label="Resultados (ES)")
        btn_es.click(analyze_corpus_es, inputs=[], outputs=output_es)

        with gr.Accordion("📖 Ver corpus completo (50 frases)", open=False):
            gr.Markdown("### Frases coherentes")
            for i, sent in enumerate(CORPUS_ES_COHERENT, 1):
                gr.Markdown(f"{i}. {sent}")
            gr.Markdown("### Frases rotas")
            for i, sent in enumerate(CORPUS_ES_BROKEN, 1):
                gr.Markdown(f"{i}. {sent}")

        gr.Markdown(FOOTER_ES)

demo.launch()