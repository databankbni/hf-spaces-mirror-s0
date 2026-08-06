"""
Answer domain — PromptPolicy Strategy pattern.

Design notes:
- PromptPlan is a frozen value object.  It carries everything ``generate_answer``
  needs to build the final system prompt and cap token usage.
- PromptPolicy is a Protocol (structural subtyping): any class with a ``build_plan``
  method is a valid policy.  No ABC inheritance required.
- PromptPolicyRegistry is closed for modification, open for extension: new policies
  are added via ``registry.register(...)``; ``generate_answer`` and the route never
  need editing.
- ProseTutorPolicy reproduces today's SYSTEM_PROMPT + _TIER_CONFLICT_NOTE + 1024 cap
  verbatim so the answer/eval contract is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Value object — resolved plan returned by every policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromptPlan:
    """Immutable resolved prompt configuration for a single generation call."""

    system_prompt: str
    max_tokens: int
    formatting: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Strategy interface
# ---------------------------------------------------------------------------

@runtime_checkable
class PromptPolicy(Protocol):
    """Narrow interface: a policy maps a query context to a PromptPlan."""

    def build_plan(
        self,
        *,
        subject: str | None,
        question_type: str | None,
        persona: str | None,
        tier_conflict: bool,
        weak_context: bool = False,
    ) -> PromptPlan:
        ...


# ---------------------------------------------------------------------------
# The one live policy: ProseTutorPolicy
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "Sən Azərbaycan məktəb şagirdlərinə kömək edən bir müəllimsən.\n"
    "Sənə verilən kontekst parçaları Azərbaycan dövlət kurikulumuna uyğun dərsliklərdən götürülüb.\n"
    "Yalnız verilən kontekstə əsaslanaraq cavab ver.\n"
    "Kontekstdən kənar məlumat əlavə etmə.\n"
    "Cavabını Azərbaycan dilində yaz, aydın və qısa şəkildə.\n"
    "Cavabın sonunda [N] formatında sitat göstər (N - kontekst parçasının nömrəsi)."
)

_TIER_CONFLICT_NOTE = (
    "\n\nDiqqət: Bu cavab üçün həm rəsmi dərslik, həm də köməkçi mənbə parçaları tapıldı. "
    "Ziddiyyət olduqda rəsmi dərslik mənbəsinə üstünlük ver və bu fərqi şagirdə bildir."
)

# The exact phrase the tutor must emit when the retrieved context does not answer
# the question. Single source of truth: the grounding contract instructs the model
# to write it, the keyless path returns it, and the faithfulness eval detects it.
INSUFFICIENT_CONTEXT_MESSAGE = (
    "Bu sual üzrə dərslikdə kifayət qədər məlumat tapılmadı. "
    "Sualı daha konkret mövzu və ya dövr adı ilə yenidən yazın."
)

# Faithfulness contract — appended to EVERY policy's system prompt. This is the
# core defence against the live failure mode (GRO-111): retrieval returns chunks
# that are superficially similar but about a different topic (e.g. a question about
# Europe's highest peak retrieving Azerbaijan's), and the model "answers from
# context" by substituting the wrong subject. The contract forbids that substitution.
# GRO-111 v2 — VALIDATED against live Gemini (A/B on the real failing cases,
# 2026-06-07): the first version over-refused in-corpus reasoning questions
# (it told the model to refuse unless the context answered "directly", which the
# model read as "verbatim"). This version distinguishes "same topic → reason and
# answer" from "different topic → refuse", which a tutor must do. Measured result:
# GEO-climate REFUSE→ANSWER, MATH-domain REFUSE→ANSWER, GEO-Europe stays REFUSE.
_GROUNDING_CONTRACT = (
    "\n\nDOĞRULUQ VƏ ƏHATƏ QAYDASI:\n"
    "Əgər kontekst sualla EYNİ mövzudadırsa, ondan istifadə edərək addım-addım izah et və "
    "nəticə çıxar — cavab birbaşa yazılmasa belə, kontekstdəki anlayış və faktlardan məntiqlə "
    "nəticə çıxarmaq sənin vəzifəndir (sən müəllimsən, məsələni həll et).\n"
    "Sual tam siyahı tələb edirsə (məsələn «sadalayın», «adlandırın», «hansılardır»), "
    "kontekstdə olan bütün maddələri siyahı kimi tam yaz; yarımçıq buraxma.\n"
    "Kontekst sualın mövzusu ilə eyni fənndirsə (məsələn, hər ikisi alkanlar haqqındadır), "
    "amma tam siyahı parçalanmada aydın deyilsə, ümumi imtina mesajını VERMƏ — kontekstdə "
    "olan maddələri yaz və çatışmayanları qeyd et.\n"
    "YALNIZ kontekst tamam BAŞQA mövzudadırsa (sual başqa ölkə/qitə/dövr/şəxs haqqındadır, "
    "kontekst isə fərqli bir şeydən bəhs edir), cavab uydurma və yalnız bunu yaz: "
    f"«{INSUFFICIENT_CONTEXT_MESSAGE}»"
)

# Extra directive threaded in when retrieval similarity is weak (top score below the
# weak-context threshold). It does NOT hard-refuse — borderline-but-on-topic questions
# (e.g. a broad definition query) should still be answered — it makes the model verify
# relevance before answering. The hard refuse stays the model's call via _GROUNDING_CONTRACT.
_WEAK_CONTEXT_DIRECTIVE = (
    "\n\nXƏBƏRDARLIQ: Tapılan kontekst sualla yalnız zəif uyğunluq təşkil edir. "
    "Cavab verməzdən əvvəl kontekstin sualı həqiqətən əhatə etdiyini bir daha yoxla; "
    "əhatə etmirsə, yuxarıdakı doğruluq qaydasına əməl et."
)


def _finalize(base_prompt: str, *, tier_conflict: bool, weak_context: bool) -> str:
    """Compose a policy's final system prompt: base + grounding + optional directives.

    Order is deliberate and shared by every policy (DRY): the grounding contract is
    always present; the weak-context warning is added only on weak retrieval; the
    tier-conflict note stays LAST so existing ``endswith(_TIER_CONFLICT_NOTE)`` tests
    and the source-precedence guidance remain valid.
    """
    prompt = base_prompt + _GROUNDING_CONTRACT
    if weak_context:
        prompt += _WEAK_CONTEXT_DIRECTIVE
    if tier_conflict:
        prompt += _TIER_CONFLICT_NOTE
    return prompt


_MAX_TOKENS = 1024


class ProseTutorPolicy:
    """
    Azerbaijani prose tutor — the sole active policy in CP4.

    Reproduces today's SYSTEM_PROMPT + optional _TIER_CONFLICT_NOTE + max_tokens=1024
    exactly, so the answer/eval contract is byte-equivalent.
    """

    def build_plan(
        self,
        *,
        subject: str | None,
        question_type: str | None,
        persona: str | None,
        tier_conflict: bool,
        weak_context: bool = False,
    ) -> PromptPlan:
        system = _finalize(_SYSTEM_PROMPT, tier_conflict=tier_conflict, weak_context=weak_context)
        return PromptPlan(system_prompt=system, max_tokens=_MAX_TOKENS)


_MATH_SYSTEM_PROMPT = (
    "Sən Azərbaycan məktəb şagirdlərinə riyaziyyat fənnindən kömək edən bir müəllimsən.\n"
    "Sənə verilən kontekst parçaları Azərbaycan DİM kurikulumuna uyğun riyaziyyat dərsliyindən götürülüb.\n"
    "Kontekst parçaları LaTeX formatında riyazi ifadələr ($...$) ehtiva edə bilər — onları dəyişmədən saxla.\n"
    "Yalnız verilən kontekstə əsaslanaraq cavab ver.\n"
    "Kontekstdən kənar məlumat əlavə etmə.\n"
    "Cavabını Azərbaycan dilində yaz, aydın və addım-addım şəkildə.\n"
    "Riyazi ifadələri LaTeX formatında ($...$) yaz.\n"
    "Cavabın sonunda [N] formatında sitat göstər (N - kontekst parçasının nömrəsi)."
)

_MATH_MAX_TOKENS = 2048  # math solutions are longer than prose answers


class MathTutorPolicy:
    """
    Math subject tutor — CP7 seam.

    Replaces ProseTutorPolicy for subject='mathematics'. Declares the math
    system prompt (LaTeX-aware, step-by-step) and a higher token cap.
    The full MathSolverPolicy (equation solving, discriminant fix) is CP13.
    """

    def build_plan(
        self,
        *,
        subject: str | None,
        question_type: str | None,
        persona: str | None,
        tier_conflict: bool,
        weak_context: bool = False,
    ) -> PromptPlan:
        prompt = _finalize(_MATH_SYSTEM_PROMPT, tier_conflict=tier_conflict, weak_context=weak_context)
        return PromptPlan(system_prompt=prompt, max_tokens=_MATH_MAX_TOKENS)


# ---------------------------------------------------------------------------
# CP13 — MathSolverPolicy: the discriminant fix
# ---------------------------------------------------------------------------
# The live math bug (eval case `math-discr-1`: "x² − mx + 11 > 0 bütün həqiqi x
# üçün …") returned a wrong answer because the model skipped the discriminant
# sign analysis. This policy makes the method explicit and non-skippable.

_MATH_SOLVER_METHOD = (
    "\n\nMÜHÜM — kvadrat ifadələrlə bağlı məsələlərdə bu addımları AT­LAMA:\n"
    "1) Kvadrat tənlik/bərabərsizlik $ax^2+bx+c$ üçün diskriminantı hesabla: "
    "$D = b^2 - 4ac$.\n"
    "2) Köklər (lazım olduqda): $x = \\dfrac{-b \\pm \\sqrt{D}}{2a}$.\n"
    "3) İşarə analizi — bərabərsizlik bütün həqiqi $x$ üçün doğru olmalıdırsa:\n"
    "   • $ax^2+bx+c > 0\\ \\forall x \\iff a > 0$ VƏ $D < 0$;\n"
    "   • $ax^2+bx+c < 0\\ \\forall x \\iff a < 0$ VƏ $D < 0$;\n"
    "   • bərabər ($\\ge 0$ / $\\le 0$) hallarda $D \\le 0$ götür.\n"
    "4) Diskriminantın işarəsini nəticə çıxarmadan ƏVVƏL yoxla; təxmin etmə.\n"
    "5) Tam ədədlərin sayı soruşulursa, alınan intervalı dəqiq say."
)


class MathSolverPolicy(MathTutorPolicy):
    """
    CP13 math policy — extends the CP7 math tutor with explicit equation-solving
    and discriminant sign-analysis guidance.

    Subclasses ``MathTutorPolicy`` so existing ``isinstance(..., MathTutorPolicy)``
    checks (CP7 registry-integration test) stay valid while the prompt evolves.
    Keeps the same LaTeX-aware base prompt and the 2048-token cap; appends the
    step-by-step solver method (and the tier-conflict note when relevant).
    """

    def build_plan(
        self,
        *,
        subject: str | None,
        question_type: str | None,
        persona: str | None,
        tier_conflict: bool,
        weak_context: bool = False,
    ) -> PromptPlan:
        prompt = _finalize(
            _MATH_SYSTEM_PROMPT + _MATH_SOLVER_METHOD,
            tier_conflict=tier_conflict,
            weak_context=weak_context,
        )
        return PromptPlan(system_prompt=prompt, max_tokens=_MATH_MAX_TOKENS)


# ---------------------------------------------------------------------------
# GRO-111 — HistoryTutorPolicy (subject="azerbaycan_tarixi")
# ---------------------------------------------------------------------------
# The corpus is the Azerbaijani-history textbook. History answers hinge on precise
# dates, actors, places and cause→effect, so the prompt asks for those explicitly.

_HISTORY_SYSTEM_PROMPT = (
    "Sən Azərbaycan məktəb şagirdlərinə «Azərbaycan tarixi» fənnindən kömək edən bir müəllimsən.\n"
    "Sənə verilən kontekst parçaları Azərbaycan DİM kurikulumuna uyğun «Azərbaycan tarixi» "
    "dərsliyindən götürülüb.\n"
    "Yalnız verilən kontekstə əsaslanaraq cavab ver, kontekstdən kənar məlumat əlavə etmə.\n"
    "Tarixi hadisəni izah edərkən dəqiq tarixi (il/əsr), iştirak edən şəxsləri, yer adlarını "
    "və səbəb-nəticə əlaqəsini göstər.\n"
    "Cavabını Azərbaycan dilində, aydın və qısa yaz.\n"
    "Cavabın sonunda [N] formatında sitat göstər (N - kontekst parçasının nömrəsi)."
)

_HISTORY_MAX_TOKENS = 1024


class HistoryTutorPolicy:
    """Azerbaijani-history tutor — dates/actors/places/causality emphasis."""

    def build_plan(
        self,
        *,
        subject: str | None,
        question_type: str | None,
        persona: str | None,
        tier_conflict: bool,
        weak_context: bool = False,
    ) -> PromptPlan:
        prompt = _finalize(_HISTORY_SYSTEM_PROMPT, tier_conflict=tier_conflict, weak_context=weak_context)
        return PromptPlan(system_prompt=prompt, max_tokens=_HISTORY_MAX_TOKENS)


# ---------------------------------------------------------------------------
# GRO-111 — GeographyTutorPolicy (subject="geography")
# ---------------------------------------------------------------------------
# The corpus is Azerbaijan-focused geography. The live failure (a "Europe's highest
# peak" question answered with Azerbaijan's Bazardüzü) is a scope error, so this
# prompt carries an explicit out-of-scope guard ON TOP of the shared grounding contract.

_GEOGRAPHY_SYSTEM_PROMPT = (
    "Sən Azərbaycan məktəb şagirdlərinə coğrafiya fənnindən kömək edən bir müəllimsən.\n"
    "Sənə verilən kontekst parçaları Azərbaycan DİM kurikulumuna uyğun coğrafiya dərsliyindən "
    "götürülüb — bu dərslik əsasən AZƏRBAYCANIN coğrafiyasını əhatə edir.\n"
    "Yalnız verilən kontekstə əsaslanaraq cavab ver, kontekstdən kənar məlumat əlavə etmə.\n"
    "Yer adlarını, koordinatları, relyef formalarını və təbii xüsusiyyətləri dəqiq göstər.\n"
    "DİQQƏT — ƏHATƏ DAİRƏSİ: Sual Azərbaycandan kənar bir ərazi (məsələn, Avropa, dünya, "
    "başqa bir ölkə və ya qitə) haqqındadırsa və kontekstdə həmin yerə dair konkret məlumat "
    "yoxdursa, Azərbaycana aid bənzər faktı (məsələn, Azərbaycanın ən hündür zirvəsini) "
    "cavab kimi VERMƏ — bu, yanlış cavabdır.\n"
    "Cavabını Azərbaycan dilində, aydın və qısa yaz.\n"
    "Cavabın sonunda [N] formatında sitat göstər (N - kontekst parçasının nömrəsi)."
)

_GEOGRAPHY_MAX_TOKENS = 1024


class GeographyTutorPolicy:
    """Azerbaijan-geography tutor — places/coordinates/relief + out-of-scope guard."""

    def build_plan(
        self,
        *,
        subject: str | None,
        question_type: str | None,
        persona: str | None,
        tier_conflict: bool,
        weak_context: bool = False,
    ) -> PromptPlan:
        prompt = _finalize(_GEOGRAPHY_SYSTEM_PROMPT, tier_conflict=tier_conflict, weak_context=weak_context)
        return PromptPlan(system_prompt=prompt, max_tokens=_GEOGRAPHY_MAX_TOKENS)


# ---------------------------------------------------------------------------
# CP13 — MultipleChoicePolicy (question_type="mcq")
# ---------------------------------------------------------------------------

_MCQ_SYSTEM_PROMPT = (
    "Sən Azərbaycan məktəb şagirdlərinə kömək edən bir müəllimsən.\n"
    "Sual çoxvariantlı (test) sualdır.\n"
    "Yalnız verilən kontekstə əsaslanaraq cavab ver, kontekstdən kənar məlumat əlavə etmə.\n"
    "Əvvəlcə düzgün variantı aydın göstər (məsələn: «Düzgün cavab: B»),\n"
    "sonra 1-2 cümlə ilə qısa əsaslandırma ver.\n"
    "Cavabını Azərbaycan dilində yaz.\n"
    "Cavabın sonunda [N] formatında sitat göstər (N - kontekst parçasının nömrəsi)."
)

_MCQ_MAX_TOKENS = 512  # MCQ answers are short: the option + a brief justification


class MultipleChoicePolicy:
    """Concise option-focused policy for multiple-choice questions."""

    def build_plan(
        self,
        *,
        subject: str | None,
        question_type: str | None,
        persona: str | None,
        tier_conflict: bool,
        weak_context: bool = False,
    ) -> PromptPlan:
        prompt = _finalize(_MCQ_SYSTEM_PROMPT, tier_conflict=tier_conflict, weak_context=weak_context)
        return PromptPlan(
            system_prompt=prompt,
            max_tokens=_MCQ_MAX_TOKENS,
            formatting={"question_type": "mcq"},
        )


# ---------------------------------------------------------------------------
# CP13 — ExamCoachPersonaPolicy (persona="coach")
# ---------------------------------------------------------------------------
# A persona is a *standalone* policy in the current single-policy registry: the
# registry resolves to exactly one PromptPolicy, so a persona cannot yet be
# layered on top of a subject prompt. Subject always wins when both are set (see
# resolution order in PromptPolicyRegistry.resolve). Full persona×subject
# composition needs a PromptPlan-composition layer — a deliberate future seam,
# out of CP13 scope. This concrete persona proves the registry dimension works.

_COACH_SYSTEM_PROMPT = (
    "Sən Azərbaycan DİM imtahanına hazırlaşan şagirdlərə dəstək olan, "
    "həvəsləndirici bir imtahan məşqçisisən.\n"
    "Yalnız verilən kontekstə əsaslanaraq cavab ver, kontekstdən kənar məlumat əlavə etmə.\n"
    "Cavabını aydın, addım-addım və ruhlandırıcı tonda yaz, lakin qısa saxla.\n"
    "İmtahan üçün faydalı məsləhət və ya yaddaqalan qeyd əlavə et.\n"
    "Cavabını Azərbaycan dilində yaz.\n"
    "Cavabın sonunda [N] formatında sitat göstər (N - kontekst parçasının nömrəsi)."
)

_COACH_MAX_TOKENS = 1024


class ExamCoachPersonaPolicy:
    """Encouraging DİM exam-coach persona (subject-agnostic)."""

    def build_plan(
        self,
        *,
        subject: str | None,
        question_type: str | None,
        persona: str | None,
        tier_conflict: bool,
        weak_context: bool = False,
    ) -> PromptPlan:
        prompt = _finalize(_COACH_SYSTEM_PROMPT, tier_conflict=tier_conflict, weak_context=weak_context)
        return PromptPlan(
            system_prompt=prompt,
            max_tokens=_COACH_MAX_TOKENS,
            formatting={"persona": "coach"},
        )


# ---------------------------------------------------------------------------
# Registry — closed for modification, open for extension
# ---------------------------------------------------------------------------

class PromptPolicyRegistry:
    """
    Resolves a (subject, question_type, persona) triple to a PromptPolicy.

    Extension example — to add a math policy in CP13:
    ::
        registry = PromptPolicyRegistry()
        registry.register(
            subject="riyaziyyat",
            question_type=None,
            persona=None,
            policy=MathSolverPolicy(),
        )

    Resolution order: exact (subject, question_type, persona) match →
    (subject, None, None) catch-all → global default.  Always falls back to
    ProseTutorPolicy so there is no KeyError path.
    """

    def __init__(self) -> None:
        self._policies: dict[tuple[str | None, str | None, str | None], PromptPolicy] = {}
        self._default: PromptPolicy = ProseTutorPolicy()

    def register(
        self,
        policy: PromptPolicy,
        *,
        subject: str | None = None,
        question_type: str | None = None,
        persona: str | None = None,
    ) -> None:
        self._policies[(subject, question_type, persona)] = policy

    def set_default(self, policy: PromptPolicy) -> None:
        self._default = policy

    def resolve(
        self,
        subject: str | None,
        question_type: str | None,
        persona: str | None,
    ) -> PromptPolicy:
        """Resolve the most specific registered policy for the given dimensions.

        Specificity order (first registered match wins), then the default:

        1. ``(subject, question_type, persona)`` — exact triple
        2. ``(subject, question_type, None)`` — subject + question type
        3. ``(subject, None, persona)`` — subject + persona
        4. ``(subject, None, None)`` — subject catch-all
        5. ``(None, question_type, None)`` — question type across all subjects (MCQ)
        6. ``(None, None, persona)`` — persona across all subjects
        7. ``self._default``

        ``question_type`` ranks above ``persona`` because it shapes the answer
        structure, whereas persona only adjusts tone. The order is a strict
        generalisation of the CP4/CP7 two-tier lookup (1 → 4 → default), so every
        previously-registered policy resolves exactly as before.
        """
        candidates = (
            (subject, question_type, persona),
            (subject, question_type, None),
            (subject, None, persona),
            (subject, None, None),
            (None, question_type, None),
            (None, None, persona),
        )
        seen: set[tuple[str | None, str | None, str | None]] = set()
        for key in candidates:
            if key in seen:
                continue
            seen.add(key)
            policy = self._policies.get(key)
            if policy is not None:
                return policy
        return self._default


# Module-level singleton — generate_answer imports this
_registry = PromptPolicyRegistry()


def get_registry() -> PromptPolicyRegistry:
    """Return the shared policy registry."""
    return _registry

# Subject policies — keyed by canonical subject id (see query.domain.canonical_subject).
# CP13 upgrades the math seam from the CP7 MathTutorPolicy placeholder to the full
# MathSolverPolicy (discriminant fix). MathSolverPolicy IS-A MathTutorPolicy, so the
# CP7 registry-integration assertion (isinstance MathTutorPolicy) still holds.
_registry.register(MathSolverPolicy(), subject="mathematics")
# GRO-111: History & Geography get their own subject prompts (were generic prose).
_registry.register(HistoryTutorPolicy(), subject="azerbaycan_tarixi")
_registry.register(GeographyTutorPolicy(), subject="geography")

# Question-type policies — apply across subjects via resolution tier 5.
_registry.register(MultipleChoicePolicy(), question_type="mcq")

# Persona policies — apply to subject-less requests via resolution tier 6.
_registry.register(ExamCoachPersonaPolicy(), persona="coach")
