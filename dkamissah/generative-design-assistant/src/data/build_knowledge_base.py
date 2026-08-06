"""
Build the engineering knowledge base for the Generative Design Assistant.

Embeds a curated set of engineering standards, design principles,
and material specifications into a ChromaDB vector store.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import yaml
import re
from pathlib import Path
from loguru import logger
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings


ENGINEERING_DOCUMENTS = [
    {
        "id": "material_steel_001",
        "title": "High-Strength Steel Selection Criteria",
        "category": "materials",
        "text": """High-strength steel alloys (e.g. AHSS, UHSS) offer tensile strengths from 590 MPa to over 1500 MPa. 
        Key grades include DP600, DP800, TRIP780, and press-hardened steels like 22MnB5 (1500 MPa after hot stamping).
        Advantages: high strength-to-weight ratio, good formability in some grades, excellent crashworthiness.
        Limitations: springback issues, higher tooling wear, hydrogen embrittlement risk in ultra-high strength grades.
        Typical automotive applications: door reinforcements, B-pillars, bumper beams, roof rails.
        Weight savings vs. mild steel: 20-35% for equivalent structural performance.
        Cost premium: 1.5-3x compared to conventional mild steel."""
    },
    {
        "id": "material_aluminium_001",
        "title": "Aluminium Alloy Design Guidelines",
        "category": "materials",
        "text": """Aluminium alloys (series 5xxx, 6xxx, 7xxx) are widely used in automotive lightweighting.
        6061-T6: 276 MPa yield strength, excellent corrosion resistance, good weldability. Body panels, extrusions.
        7075-T6: 503 MPa yield strength, aerospace grade, limited weldability. Structural brackets, suspension.
        5182-H19: High formability, used for closures and door inners.
        Weight vs. steel: ~35% lighter for equivalent volume; requires 40-50% more material thickness for same stiffness.
        Joining challenges: resistance spot welding not standard; self-piercing rivets (SPR) and structural adhesive preferred.
        Thermal expansion coefficient 2x steel — requires design accommodation in mixed-material structures.
        Recyclability: >95% recyclable with minimal energy loss, strong sustainability case."""
    },
    {
        "id": "material_cfrp_001",
        "title": "Carbon Fibre Reinforced Polymer (CFRP) Engineering",
        "category": "materials",
        "text": """CFRP offers the highest specific stiffness and strength of structural materials.
        Typical properties: tensile strength 1500-3500 MPa, modulus 70-300 GPa, density 1.5-1.6 g/cm³.
        Weight savings: 50-60% vs. steel for equivalent structural performance.
        Manufacturing: autoclave, RTM, prepreg layup, wet compression moulding.
        Design principles: fibres must be aligned with principal stress directions; quasi-isotropic layups for multidirectional loading.
        Failure modes: delamination, fibre breakage, matrix cracking — requires specific damage tolerance design.
        Cost: 5-20x steel by weight; significant manufacturing complexity.
        Automotive applications: BMW i3/i8 life module, Ferrari/Lamborghini monocoques, high-performance structural components.
        Recyclability challenge: thermoset CFRP difficult to recycle; thermoplastic CFRP (TPC) emerging as sustainable alternative."""
    },
    {
        "id": "design_topology_001",
        "title": "Topology Optimisation Principles",
        "category": "design_methods",
        "text": """Topology optimisation (TO) is a mathematical method that optimises material distribution within a design space 
        subject to loads, constraints, and boundary conditions. Used to identify efficient load paths and organic structural forms.
        Common algorithms: SIMP (Solid Isotropic Material with Penalization), BESO (Bi-directional Evolutionary Structural Optimisation).
        Typical mass savings: 20-50% vs. conventional design while maintaining structural performance.
        Design workflow: define design space → apply loads/constraints → run TO → interpret results → engineering refinement → validation.
        Software: Altair OptiStruct, ANSYS Mechanical, Abaqus, nTopology.
        Manufacturing constraints: minimum member size, draw direction, overhang angle (for AM), symmetry constraints.
        BMW application: structural brackets, suspension components, engine mounts — often combined with additive manufacturing."""
    },
    {
        "id": "design_additive_001",
        "title": "Additive Manufacturing Design Guidelines (Metal AM)",
        "category": "design_methods",
        "text": """Metal additive manufacturing (AM) enables geometries impossible with conventional machining.
        Processes: SLM/LPBF (laser powder bed fusion), EBM (electron beam melting), DED (directed energy deposition).
        LPBF achievable tolerances: ±0.1-0.2mm; surface roughness Ra 5-20µm (pre-finish).
        Minimum wall thickness: 0.3-0.5mm (material dependent).
        Overhangs: requires support if angle > 45° from horizontal; design for self-supporting geometries where possible.
        Post-processing: stress relief, HIP (Hot Isostatic Pressing) for critical parts, CNC finishing of critical surfaces.
        Materials: Ti-6Al-4V (aerospace/medical), AlSi10Mg (lightweight structures), 316L SS, Inconel 718.
        Cost drivers: build time, support removal, post-processing, powder cost — competitive at low volumes and complex geometries.
        BMW Group: uses LPBF for individualised parts, racing components, and topology-optimised brackets in series production."""
    },
    {
        "id": "design_fea_001",
        "title": "Structural FEA Validation Requirements",
        "category": "validation",
        "text": """Finite Element Analysis (FEA) is the primary virtual validation method for structural components.
        Static analysis: verify stress < allowable (typically 0.7 × yield strength for safety factor 1.4).
        Modal analysis: natural frequencies must avoid excitation frequencies (engine orders, road inputs 0-50Hz typical).
        Fatigue: Woehler curve approach; typical automotive target life 200,000 km or 10^7 cycles.
        Crashworthiness: LS-DYNA explicit simulation; energy absorption, intrusion, and deceleration targets per regulations.
        Buckling: linear buckling factor > 3.0 for safety-critical components under compression.
        Mesh requirements: element size < 1/6 of smallest feature; hex elements preferred for accuracy.
        Correlation targets: frequency within ±5% of test, stress within ±10%.
        BMW validation process: virtual validation first → physical prototype testing → production validation."""
    },
    {
        "id": "design_lightweight_001",
        "title": "Automotive Lightweighting Strategy",
        "category": "design_methods",
        "text": """Automotive lightweighting targets CO2 reduction: every 100kg saved reduces CO2 by ~8-10g/km (WLTP).
        Primary strategies: material substitution, topology optimisation, function integration, joining technology optimisation.
        Multi-material design: combining steel, aluminium, CFRP, and plastics for optimal performance/cost/weight balance.
        BMW EfficientLightweight approach: intelligent material mix, load-path-optimised structures, manufacturing innovation.
        Mass targets: BEV platforms require aggressive lightweighting to offset battery weight (300-700kg).
        Cost-weight trade-off: cost penalty of €5-20 per kg saved depending on technology.
        Lifecycle assessment: must consider manufacturing energy, recyclability — lightweighting only beneficial if full lifecycle CO2 is reduced.
        Key regulations: Euro NCAP structural requirements, FMVSS, ECE-R regulations constrain design freedom."""
    },
    {
        "id": "design_tolerances_001",
        "title": "Geometric Tolerancing and Surface Finish Standards",
        "category": "standards",
        "text": """GD&T (Geometric Dimensioning and Tolerancing) per ISO 1101 / ASME Y14.5 defines form, orientation, location, and runout.
        Automotive body panel gaps: typically 3.0 ± 0.5mm; flush: ± 0.3mm.
        Machined surfaces: IT6-IT8 tolerance grade; Ra 0.8-3.2 µm for sealing surfaces.
        Press-formed panels: ±0.5mm dimensional tolerance; surface waviness < 0.3mm/300mm.
        Weld quality: ISO 5817 Grade B for structural welds; spatter and porosity limits defined.
        Corrosion protection: zinc coating 7-20 µm; e-coat thickness 15-25 µm; topcoat 40-60 µm total.
        Fasteners: ISO metric thread standards; tightening torques per VDI 2230.
        BMW specific: measurement per VDA 2006; CMM validation at 100% for safety parts, sampling for non-safety."""
    },
    {
        "id": "design_sustainability_001",
        "title": "Sustainable Design and Circular Economy Principles",
        "category": "sustainability",
        "text": """Sustainable design minimises environmental impact across the full product lifecycle.
        Circular economy principles: design for disassembly, recyclability, reuse of materials and components.
        BMW Group targets: 40% reduction in CO2 per vehicle by 2030 vs. 2019; 50% recycled content in new models by 2030.
        Recyclability by material: steel 90%+, aluminium 95%+, thermoplastic 80%+, thermoset CFRP <30%.
        Design for disassembly: avoid permanent joining (welding, overmoulding) between dissimilar materials where recyclability is required.
        Bio-based materials: natural fibre composites (kenaf, flax) for interior trim — lower CO2 than glass fibre, lighter weight.
        End-of-life vehicle (ELV) directive: 85% reuse/recycling, 95% recovery by mass required.
        LCA tools: SimaPro, GaBi — mandatory for BMW Tier 1 suppliers on new programmes."""
    },
    {
        "id": "design_manufacturing_001",
        "title": "Design for Manufacturing (DfM) Guidelines",
        "category": "standards",
        "text": """Design for Manufacturing ensures designs can be produced reliably and cost-effectively at scale.
        Stamping: minimum bend radius 1-2x material thickness; draw depth < 2x blank diameter; draft angles 3-7°.
        Injection moulding: wall thickness 2-4mm; draft angle minimum 1°; avoid sharp internal corners (R ≥ 0.5mm).
        Die casting: wall thickness 1.5-5mm; draft angles 1-3°; porosity acceptable if non-structural.
        Welding: accessibility for spot weld guns (min 30mm flange); laser welding requires tight fit-up < 0.1mm gap.
        Assembly: one-sided assembly preferred; poka-yoke features for anti-mistake; torque angles for bolted joints.
        Cost drivers in order: material → manufacturing process → assembly → logistics → quality.
        BMW APQP process: design freeze 30 months before SOP; tooling approval 18 months before SOP."""
    },
    {
        "id": "generative_design_001",
        "title": "Generative Design in Automotive Engineering",
        "category": "design_methods",
        "text": """Generative design uses AI/algorithms to automatically generate optimised design solutions from requirements.
        Key inputs: design space, loads and boundary conditions, manufacturing constraints, material options, optimisation objectives.
        Approaches: topology optimisation, genetic algorithms, parametric optimisation, ML-based surrogate models.
        BMW applications: topology-optimised CFRP roof struts (i8), AM brackets for race applications, structural nodes for space frame.
        Software: Autodesk Fusion 360 Generative Design, nTopology, Altair Inspire, Siemens NX.
        Integration with simulation: FEA validation of generated designs; automated mesh generation and solver setup.
        Digital twin: generated design validated in virtual environment before physical prototype.
        AI role: ML models predict performance of design variants, enabling rapid design space exploration (1000s of variants/hour vs. days manually)."""
    },
    {
        "id": "requirements_001",
        "title": "Engineering Requirements Capture and Management",
        "category": "process",
        "text": """Engineering requirements form the contractual basis for design development.
        Requirement types: functional (what it must do), performance (how well), interface (how it connects), constraint (what limits apply).
        SMART requirements: Specific, Measurable, Achievable, Relevant, Time-bound.
        Automotive requirements hierarchy: customer needs → system requirements → component requirements → manufacturing requirements.
        Tools: DOORS, Polarion, Jira for requirements management; traceability matrix links requirements to validation evidence.
        BMW V-model: requirements defined at left arm; validation evidence collected at right arm for each level.
        Common failure modes: ambiguous requirements, missing requirements, requirements conflicts, gold-plating.
        AI in requirements: NLP extraction of requirements from natural language documents; automated conflict detection."""
    },
]


def load_config(path="configs/config.yaml"):
    with open(path) as f:
        raw = f.read()
    raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ""), raw)
    return yaml.safe_load(raw)


def build_knowledge_base(config_path="configs/config.yaml"):
    cfg        = load_config(config_path)
    store_path = cfg["embeddings"]["vector_store_path"]
    collection = cfg["embeddings"]["collection_name"]
    model_name = cfg["embeddings"]["model"]

    Path(store_path).mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)

    texts = [d["text"] for d in ENGINEERING_DOCUMENTS]
    logger.info(f"Embedding {len(texts)} engineering documents...")
    embeddings = model.encode(texts, show_progress_bar=True).tolist()

    client = chromadb.PersistentClient(
        path=store_path,
        settings=Settings(anonymized_telemetry=False)
    )

    try:
        client.delete_collection(collection)
    except Exception:
        pass

    col = client.create_collection(
        name=collection,
        metadata={"hnsw:space": "cosine"}
    )

    col.add(
        ids        = [d["id"] for d in ENGINEERING_DOCUMENTS],
        embeddings = embeddings,
        documents  = texts,
        metadatas  = [{"title": d["title"], "category": d["category"]} for d in ENGINEERING_DOCUMENTS]
    )

    logger.success(f"Knowledge base built: {col.count()} documents in '{collection}'")
    return col


if __name__ == "__main__":
    build_knowledge_base()
