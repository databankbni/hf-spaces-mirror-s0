from __future__ import annotations

import re


_RANK_POSITION = re.compile(
    r"(?:排(?:在|到|了)?(?:第)?几(?:名|位)?|"
    r"排(?:名)?(?:是|在)?多少|"
    r"位列(?:第)?几(?:名|位)?|位居(?:第)?几(?:名|位)?|"
    r"在第几(?:名|位)?|第几(?:名|位)|"
    r"排名(?:是|在|第)?(?:多少|几)|名次(?:是|在)?(?:多少|几)|"
    r"榜单(?:中|里|上)?(?:的)?(?:位置|名次)|排到哪里|"
    r"第\s*(?:\d+|[一二三四五六七八九十两]+)\s*(?:名|位|个)?\s*(?:是|有)?\s*(?:什么|哪|哪个).{0,4}(?:车|车系|车型)?)"
)
_RANK_CONTEXT = re.compile(r"榜|榜单|排行|排名|推荐(?:池|榜|名单)?|候选(?:池|名单)?|机会榜|前\s*\d+|top\s*\d+")
_WHY = re.compile(r"为什么|为何|为啥|怎么会|怎么|咋|什么原因")
_ABSENT = re.compile(r"不在|没在|未在|没进|未进|没有进|没上|未上|看不到|没看到|没出现|未出现|没被选中|未被选中|没选中|不见")
_ACQUISITION_ACTION = re.compile(r"收(?:车)?|做|碰|补库|进货|拿货|跟进|关注")
_JUDGEMENT = re.compile(
    r"(?:建议|推荐|适合|值得|该不该|要不要|能不能|可不可以|是否|好不好|行不行).{0,5}"
    r"(?:收(?:车)?|做|碰|补库|进货|拿货|跟进|关注)|"
    r"(?:收(?:车)?|做|碰|补库|进货|拿货).{0,5}(?:吗|么|不|好不好|行不行|合适吗|值得吗|建议吗)"
)
_EXPLICIT_PRICING = re.compile(
    r"估价|报价|多少钱|什么价|收车价|收多少钱|多少钱收|最高收|最高追|"
    r"卖车价|售车价|卖多少钱|挂牌价|建议售价|利润测算|同时估|批量估|"
    r"\d+(?:\.\d+)?\s*万.{0,8}(?:能不能|可不可以|是否|该不该|值不值).{0,4}(?:收|卖|出)"
)
_SCORE_EXPLANATION = re.compile(
    r"(?:机会分|选品分|综合分|推荐分|这个评分|该评分|分数).{0,10}(?:怎么|如何|为何|为什么|依据|来源|算|计算|构成)|"
    r"(?:怎么|如何|为何|为什么|依据什么).{0,14}(?:机会分|选品分|综合分|推荐分|这个评分|该评分|这个分数|该分数)|"
    r"(?:排序|排名|排位).{0,4}(?:依据|原因|逻辑)|"
    r"(?:为什么|为何|为啥|怎么会|咋).{0,12}(?:排(?:得|在)?(?:这么|那么)?(?:高|低|前|后)|排第|排名|名次|位置)|"
    r"(?:排(?:得|在)?(?:这么|那么)?(?:高|低|前|后)|排第|排名|名次).{0,12}(?:为什么|为何|为啥|原因|依据|具体数据)|"
    r"(?:这车|这个车|这台车|该车|它).{0,10}(?:真实收车转化|售车转化|收车转化|周转|毛利|亏损|经营数据|具体数据).{0,10}(?:多少|怎么样|如何|是什么|高不高|低不低)|"
    r"(?:这车|这个车|这台车|该车|它).{0,80}(?:真实收车转化|售车转化|收车转化|周转|毛利|亏损).{0,80}(?:分别(?:是|为)?多少|各是多少)"
)
_METHOD_EXPLANATION = re.compile(
    r"(?:选品|推荐|机会榜|风险榜|排序).{0,10}(?:逻辑|算法|公式|规则|口径|怎么计算|如何计算|怎么算|怎么排)|"
    r"(?:逻辑|算法|公式|规则).{0,10}(?:选品|推荐|机会榜|风险榜|排序)"
)
_EVIDENCE_EXPLANATION = re.compile(
    r"(?:选品|推荐|机会分|选品分|排序).{0,10}(?:证据|数据来源|用了哪些数据|哪些数据|可信度|依据)|"
    r"(?:证据|数据来源|用了哪些数据).{0,10}(?:选品|推荐|排序)|"
    r"(?:DSI|懂车帝|榜单|排行榜).{0,12}(?:参与|用于|作用|影响).{0,8}(?:选品|推荐|排序)"
)
_COMPARE_SELECTION = re.compile(
    r"(?:哪个|哪款|谁).{0,8}(?:更值得|更适合|更稳|风险更低|更好做|建议收)|"
    r"(?:对比|比较|横向|\bvs\b|\bor\b).{0,16}(?:收|做|风险|推荐|机会|周转|利润)|"
    r"(?:和|、).{0,16}(?:哪个|哪款|谁).{0,8}(?:值得|适合|稳|风险|做|收)"
)
_CITY_OPPORTUNITY = re.compile(
    r"(?:北京|上海|广州|深圳|重庆|成都|杭州|武汉|长春).{0,4}(?:和|、|对比|比).{0,4}"
    r"(?:北京|上海|广州|深圳|重庆|成都|杭州|武汉|长春).{0,12}(?:哪个城市|哪里|更适合|更好做|机会)"
)


def classify_selection_query_family(text: str, *, has_vehicle_entity: bool = False) -> str:
    """Classify reusable selection-question structures before module routing.

    These are semantic families rather than sentence-specific aliases.  They
    intentionally override the clicked UI module, but never override an
    explicit request for a concrete purchase/sale price.
    """

    value = str(text or "").strip()
    if not value or _EXPLICIT_PRICING.search(value):
        return ""
    if _RANK_POSITION.search(value):
        return "rank_lookup"
    if _WHY.search(value) and _ABSENT.search(value) and (_RANK_CONTEXT.search(value) or re.search(r"选中|入选", value)):
        return "explain_exclusion"
    if _ABSENT.search(value) and (_RANK_CONTEXT.search(value) or re.search(r"选中|入选", value)):
        return "explain_exclusion"
    if _CITY_OPPORTUNITY.search(value):
        return "city_opportunity"
    if _COMPARE_SELECTION.search(value):
        return "compare"
    if has_vehicle_entity and _JUDGEMENT.search(value) and _ACQUISITION_ACTION.search(value):
        return "series_judgement"
    if _SCORE_EXPLANATION.search(value):
        return "score_explanation"
    if _METHOD_EXPLANATION.search(value):
        return "method_explanation"
    if _EVIDENCE_EXPLANATION.search(value):
        return "evidence_request"
    return ""


def is_explicit_pricing_query(text: str) -> bool:
    return bool(_EXPLICIT_PRICING.search(str(text or "")))
