from __future__ import annotations

import re
from typing import Any

from .selection_query_semantics import classify_selection_query_family


DETAIL_ROUTE_MAP = {
    "clarify.missing_scope": "clarify_then_selection",
    "selection.recommend_scope": "selection_analyze_service",
    "selection.risk_scope": "selection_analyze_service",
    "selection.compare": "selection_analyze_service",
    "selection.price_band_opportunity": "selection_analyze_service",
    "selection.low_price_opportunity": "selection_analyze_service",
    "selection.city_opportunity": "selection_analyze_service",
    "selection.entity_resolution": "entity_resolution_then_selection",
    "selection.handoff_pricing": "pricing_handoff_or_clarify",
    "selection.explain_exclusion": "selection_explain_service",
    "selection.rank_lookup": "selection_analyze_service",
    "selection.series_judgement": "selection_analyze_service",
    "selection.explain_rank_score": "selection_analyze_service",
    "selection.evidence_request": "selection_evidence_service",
    "selection.data_quality": "selection_data_quality_service",
    "selection.signal_rule_explain": "selection_signal_explain",
    "selection.signal_ablation": "selection_strategy_lab",
    "selection.backtest_metric": "selection_strategy_lab",
    "selection.baseline_question": "selection_metrics_explain",
    "selection.total_profit_scale": "selection_strategy_lab",
    "selection.policy_newcar_effect": "daily_event_policy_tool",
    "selection.export_report": "selection_export_service",
    "selection.sort_filter": "selection_analyze_service",
    "selection.followup_refine": "selection_analyze_service",
    "selection.followup_signal_adjust": "selection_strategy_lab",
    "selection.followup_contextual_qa": "contextual_selection_qa",
    "selection.feedback_rewrite": "selection_response_refiner",
    "selection.module_boundary_qa": "selection_qa",
    "selection.constraint_handling": "clarify_or_refuse_unsafe_business_logic",
    "selection.safety_business_integrity": "refuse_or_correct_business_integrity",
    "selection.robust_nlu": "entity_resolution_then_selection",
    "selection_qa_translation": "selection_qa_translation",
    "policy_search_or_policy_tool": "policy_search_or_policy_tool",
    "product_feedback_ui": "product_feedback_ui",
    "data_schema_review": "data_schema_review",
    "out_of_scope.news": "out_of_scope.news",
    "out_of_scope.writing": "out_of_scope.writing",
    "out_of_scope.consumer_recommendation": "out_of_scope.consumer_recommendation",
    "out_of_scope.lead_contact": "out_of_scope.lead_contact",
    "out_of_scope.outbound_call": "out_of_scope.outbound_call",
    "out_of_scope.image_generation": "out_of_scope.image_generation",
}


TASK_INTENT_MAP = {
    "clarify.missing_scope": "clarify_selection_scope",
    "selection.recommend_scope": "recommend_models",
    "selection.risk_scope": "identify_risky_models",
    "selection.compare": "compare_series",
    "selection.price_band_opportunity": "recommend_price_band",
    "selection.low_price_opportunity": "low_price_opportunity",
    "selection.city_opportunity": "recommend_city_opportunity",
    "selection.entity_resolution": "series_judgement",
    "selection.handoff_pricing": "selection_to_pricing",
    "selection.explain_exclusion": "explain_selection_reason",
    "selection.rank_lookup": "lookup_selection_rank",
    "selection.series_judgement": "series_judgement",
    "selection.explain_rank_score": "explain_selection_score",
    "selection.evidence_request": "show_selection_evidence",
    "selection.data_quality": "explain_data_quality",
    "selection.signal_rule_explain": "explain_signal_rule",
    "selection.signal_ablation": "run_signal_ablation",
    "selection.backtest_metric": "show_backtest_metrics",
    "selection.baseline_question": "explain_baseline",
    "selection.total_profit_scale": "explain_total_profit_scale",
    "selection.policy_newcar_effect": "explain_policy_newcar_effect",
    "selection.export_report": "export_selection_report",
    "selection.sort_filter": "sort_filter_selection_result",
    "selection.followup_refine": "refine_selection_scope",
    "selection.followup_signal_adjust": "adjust_selection_signals",
    "selection.followup_contextual_qa": "answer_contextual_selection_question",
    "selection.feedback_rewrite": "rewrite_selection_response",
    "selection.module_boundary_qa": "explain_module_boundary",
    "selection.constraint_handling": "handle_selection_constraints",
    "selection.safety_business_integrity": "refuse_unsafe_selection_request",
    "selection.robust_nlu": "recommend_models",
    "selection_qa_translation": "translate_selection_qa",
}


def classify_selection_detail_intent(
    text: str,
    *,
    slots: dict[str, Any] | None = None,
    internal_intent: str = "",
    has_context: bool = False,
) -> dict[str, Any]:
    text = str(text or "").strip()
    slots = slots or {}
    normalized = text.lower()
    intent = _classify(text, normalized, slots=slots, internal_intent=internal_intent, has_context=has_context)
    return build_selection_detail_contract(intent, internal_intent=internal_intent)


def build_selection_detail_contract(intent: str, *, internal_intent: str = "") -> dict[str, Any]:
    """Build the stable execution contract for deterministic or LLM detail intents."""
    intent = str(intent or "").strip() or "selection.recommend_scope"
    if intent not in DETAIL_ROUTE_MAP:
        intent = "selection.recommend_scope"
    return {
        "selection_detail_intent": intent,
        "selection_route": DETAIL_ROUTE_MAP.get(intent, "selection_analyze_service"),
        "selection_task_intent": TASK_INTENT_MAP.get(intent, _task_from_internal(internal_intent)),
        "selection_action": _action_for_intent(intent),
        "selection_required_context": _required_context(intent),
    }


def _classify(text: str, normalized: str, *, slots: dict[str, Any], internal_intent: str, has_context: bool) -> str:
    if re.search(r"写一封|邮件|周报|作文|文案", text):
        return "out_of_scope.writing"
    if re.search(r"生成图片|画图|做图|海报", text):
        return "out_of_scope.image_generation"
    if re.search(r"自动.*打电话|给车主打电话|外呼", text):
        return "out_of_scope.outbound_call"
    if re.search(r"真实车源联系方式|联系方式|电话|微信", text):
        return "out_of_scope.lead_contact"
    if re.search(r"个人消费者|自用|家用.*买|我想买", text) and not re.search(r"收车|业务|库存", text):
        return "out_of_scope.consumer_recommendation"
    if re.search(r"汽车新闻|今天.*新闻|行业新闻有哪些", text) and not re.search(r"日报|选品|收车", text):
        return "out_of_scope.news"
    if re.search(r"字段够不够|表字段|schema|数据表", normalized):
        return "data_schema_review"
    if re.search(r"购车补贴|最新政策|查一下.*政策", text) and not re.search(r"选品|推荐|收车|二手车", text):
        return "policy_search_or_policy_tool"

    semantic_family = classify_selection_query_family(text, has_vehicle_entity=_has_entity(slots))
    # 品牌组/车型组只是实体别名；只要句子明确在比较，就必须执行比较，
    # 不能停在“已识别 BBA/两田一产”这种实体解析结果。
    if semantic_family == "compare":
        return "selection.compare"

    # A named vehicle/brand followed by a broad judgement question is a
    # concrete selection judgement, not a generic market greeting.
    if _has_entity(slots) and re.search(r"(?:怎么样|值不值得做|适不适合收|建议主动补库吗)", text):
        return "selection.series_judgement"

    # Exclusion questions must win over the English/typo robustness branch;
    # otherwise “tesla model y 为啥没被选中” becomes a generic recommendation.
    if re.search(r"列表里没有|前\s*30.*(?:看不到|没有)|(?<!有)没有.*推荐|没进.*推荐|没进榜|不在.*榜|不在.*推荐|没出现|为什么没有|为啥.*不在|没被选中|没有被推荐", text, flags=re.I):
        return "selection.explain_exclusion"

    if re.search(r"(?:风险榜|避免榜).{0,12}(?:公式|怎么算|计算|排序逻辑|按什么排)", text):
        return "selection.signal_rule_explain"

    if re.search(r"\d+\s*[-~—至到]\s*\d+\s*w|tesla|zeekr7x|bba|问届|m03|新能源\s*suv\s*风险榜\s*top|model\s*3\s*or\s*y|岚图\s*free", text):
        return "selection.robust_nlu"
    if "BYD" in text:
        return "selection.robust_nlu"

    if has_context and re.search(r"(?:这个车|该车|它).*(?:如果|假设).*(?:会排|能排|排第几|排名)", text):
        return "selection.followup_contextual_qa"
    if semantic_family == "rank_lookup":
        return "selection.rank_lookup"
    if semantic_family == "score_explanation":
        return "selection.explain_rank_score"

    if re.search(r"编一个|删掉样本|样本不足.*删|不要.*证据|没有数据也|直接说.*第一|包装成达标|proxy说成真实|没有.*编|没有.*代替|没有DSI.*热门榜代替|不要转定价|别写风险", text):
        return "selection.safety_business_integrity"
    if re.search(r"推荐\s*10\s*个|强行|别管数据|100%赚钱|所有城市所有车系|别筛条件|忽略回测|只要高利润|周转慢无所谓|转化为0|成交周期长但利润低|成交2辆也给我重点关注|最优推荐", text, flags=re.I):
        return "selection.constraint_handling"
    if re.fullmatch(r"\s*(?:什么车值得收|帮我选品|给我推荐几个车|哪些别碰|最近行情好的给我|新能源现在能不能做|SUV推荐一下|重庆有什么机会|我要稳一点的?|\d+(?:\.\d+)?\s*万(?:左右|上下|以内|以下|以上)?\s*(?:推荐|能做吗?)?)\s*[？?]?\s*", text):
        return "clarify.missing_scope"
    if re.search(r"列表里没有|前\s*30.*(?:看不到|没有)|(?<!有)没有.*推荐|没进.*推荐|没进榜|不在.*榜|不在.*推荐|没出现|为什么没有|为啥.*不在|没被选中|没有被推荐", text):
        return "selection.explain_exclusion"
    if re.search(r"导出这次回测指标", text):
        return "selection.backtest_metric"
    if re.search(r"日报/政策有没有影响.*推荐|排行榜有没有参与排序", text, flags=re.I):
        return "selection.evidence_request"
    if re.search(r"导出|导成\s*excel|生成.*(?:ppt|报告|prompt)|一页PPT|打包|给JSON|json格式|前端要用|保存成规则|给领导看的.*报告|给Codex", text, flags=re.I):
        return "selection.export_report"
    if re.search(r"baseline|基线|全量平均|筛选后的|包含避免组|跟谁比|推荐组是跟谁比|全量.*子集|筛选范围.*变", normalized):
        return "selection.baseline_question"
    if re.search(r"政策|补贴|新车|新款|上市|以旧换新", text) and re.search(r"选品|推荐|收车|二手|排序|展示|回测|去掉|准新车|老款|不参与", text):
        return "selection.policy_newcar_effect"
    if re.search(r"选中率太低.*业务规模|业务规模怎么办|总利润和利润率冲突|保守过滤器|只挑少量", text):
        return "selection.total_profit_scale"
    if re.search(r"总利润保留率是多少|平均利润高但总利润低|选中率太低|Top\s*20%|同容量结果|回测|达标|四项指标|推荐组|避免组|经营效果|指标是多少", text, flags=re.I):
        return "selection.backtest_metric"
    if has_context and re.search(r"去掉\s*dsi|只用排行榜|不要日报|日报影响|信号.*调整|只看行情状态机|排行榜里的降价榜|全信号的新增|dsi加进去后|误推|政策单独", normalized):
        return "selection.followup_signal_adjust"
    if has_context and re.search(r"那如果只看利润|换成售车转化排序|刚才第|为什么你说它|那它|上面那个|差在哪", text):
        return "selection.followup_contextual_qa"
    if has_context and re.search(r"把样本少于|按总利润排序.*不按机会分|只看重庆本地|扩大到全国|把混动也加上|只看SUV|价格带改成|不要特斯拉|样本少于\s*10|不按机会分", text, flags=re.I):
        return "selection.followup_refine"
    if re.search(r"按总利润贡献排|按.*总利润.*排|低价机会放前面|只看避坑|只看强推荐", text):
        return "selection.sort_filter"

    if re.search(r"导出这次回测指标", text):
        return "selection.backtest_metric"
    if re.search(r"证明\s*dsi.*报告怎么跑", normalized):
        return "selection.signal_ablation"
    if re.search(r"导出|导成\s*excel|生成.*(?:ppt|报告|prompt)|一页PPT|打包|给JSON|json格式|前端要用|保存成规则|给领导看的.*报告|给Codex", text, flags=re.I):
        return "selection.export_report"
    if re.search(r"这个结果.*demo|业务员看不懂|模型词|理由.*业务员|卡片|空话|太AI|重写|别漏|放到后面|以后遇到|看不懂机会分|暂无风险|领导会问总利润", text, flags=re.I):
        return "selection.feedback_rewrite"
    if re.search(r"选品和行情|选品和定价|热度榜|模块.*区别|为什么选品|选品结果能不能|推荐收是不是|避坑是不是|低价机会是不是|Agent里LLM|为什么还要进单车定价", text, flags=re.I):
        return "selection.module_boundary_qa"
    if re.search(r"如果不用日报|政策新车对选品.*帮助|排行榜.*总利润下降|证明\s*dsi|只要行情\+日报|全用是不是更强|ablation|策略对照|market_only|market_daily|full_signal|增益|排行榜反而总利润下降", normalized):
        return "selection.signal_ablation"
    if re.search(r"DSI高|热门榜|降价榜|城市榜|销量榜|排行榜.*(?:规则|火|变差|效果|加进去|命中|导致)|DSI弱|DSI缺失.*不能上榜|热门榜.*该收|信号.*规则|销量榜和热门榜|风险还是机会", text, flags=re.I):
        return "selection.signal_rule_explain"
    if re.search(r"日报/政策有没有影响.*推荐|内部行情.*DSI.*榜单.*日报|数据来源|证据.*可信度|证据|展开|分别是什么结论|有没有数据来源|强风险标签|排行榜有没有参与排序", text, flags=re.I):
        return "selection.evidence_request"
    if re.search(r"总利润和利润率冲突|保守过滤器|总利润|业务规模|利润保留率|只挑少量", text):
        return "selection.total_profit_scale"
    if has_context and re.search(r"按总利润排序.*不按机会分|不按机会分|把低价机会也算进去", text):
        return "selection.followup_refine"
    if re.search(r"按.*总利润.*排|总利润贡献排|只看避坑|低价机会放前面|只看强推荐|只看样本|样本量大于|过滤|隐藏|小样本隐藏", text):
        return "selection.sort_filter"
    if has_context and re.search(r"那它|刚才|第\s*\d|这个车如果|它和|为什么把它|结论和之前|上面那个|为什么你说它|差在哪", text):
        return "selection.followup_contextual_qa"
    if re.search(r"重庆和成都|成都和重庆|北京和上海|上海和北京|哪个城市|城市.*适合|同样车系.*排序|区域|本地|扩大到全国|城市机会|只适合看纯电|15万以内能做|15-25万SUV机会|机会怎么样|适合补库吗|全国看.*本地看", text):
        return "selection.city_opportunity"
    if re.search(r"DSI缺失|排行榜匹配不上|数据质量|数据覆盖|覆盖率|映射|车型库|样本太少|字段|price[_ ]?band|匹配不上|英文和中文|中文和英文|同一个|是不是同一个", text, flags=re.I):
        return "selection.data_quality"
    if re.search(r"推荐\s*10\s*个|强行|别管数据|100%赚钱|所有城市所有车系|别筛条件|忽略回测|只要高利润|周转慢无所谓|转化为0|成交周期长但利润低|成交2辆也给我重点关注|最优推荐", text, flags=re.I):
        return "selection.constraint_handling"
    if re.search(r"(?:找到|锁定|有了).{0,8}具体车.{0,12}(?:怎么|如何).{0,8}(?:定价|收车价)", text):
        return "selection.module_boundary_qa"
    if re.search(r"具体这台车.*多少钱|进入单车定价|只知道车系|不补六要素|先估个大概|最高追到|能多少钱收|能收多少|收车价|估价|报价|出多少钱|带到估价", text):
        return "selection.handoff_pricing"
    if re.search(r"BBA里面|两田一产|新势力|大众新能源|比亚迪宋|宝马5(?!系)|毛豆Y|这个FREE|问界现在|特斯拉怎么样", text, flags=re.I):
        return "selection.entity_resolution"
    if re.search(r"横向比较|谁风险更低|谁更适合做|谁更稳|怎么排|哪个更|哪个更值得|哪个更可信|对比|比较|vs| or |和.*哪个|前\s*\d+.*比较", text, flags=re.I):
        return "selection.compare"
    if re.search(r"样本可信度|小样本惩罚|排序依据|前十车系|前五|排名靠前|在前\s*\d*|机会分|凭什么|成交\s*\d+\s*(?:辆|台).*(?:高|分|重点|样本不足|才)|为什么.*排|周转.*为啥.*重点|排第一", text):
        return "selection.explain_rank_score"
    if _has_entity(slots) and re.search(
        r"为什么.*(?:不建议|不推荐|暂缓|别碰|不能主动收)|"
        r"(?:不建议|不推荐|暂缓|别碰|不能主动收).*(?:为什么|原因|依据|具体数据)|"
        r"为什么.*(?:这么|那么).*(?:低|后)",
        text,
    ):
        return "selection.explain_exclusion"
    if re.search(r"别碰|暂缓|风险最高|库存.*风险|周转.*风险|不要收|不建议收|不建议主动|避坑|容易亏|别追价|转化差|周转.*慢|补库.*谨慎", text):
        return "selection.risk_scope"
    if re.search(r"低价|捡漏|只能低价|不是推荐收.*低价|不能正常价|低于市场价|明显低于市场价|高风险高机会|单车定价复核|不适合直接推荐", text):
        return "selection.low_price_opportunity"

    explicit_price_band_opportunity = bool(
        re.search(r"\d+(?:\.\d+)?\s*(?:[-~—至到]\s*\d+(?:\.\d+)?)?\s*万(?:以内|以下|以上|起)?", text)
        and re.search(r"机会|值得|推荐|适合|可收|能做|筛|优先", text)
    )
    if explicit_price_band_opportunity:
        return "selection.price_band_opportunity"

    asks_for_candidates = bool(re.search(r"哪些|哪几|几个|推荐|找.*方向|筛.*方向|能做.*方向|车系|优先跟进|重点看|优先收", text))
    has_non_price_scope = bool(re.search(r"新能源|燃油|油车|纯电|插混|混动|增程|SUV|MPV|轿车|B级车|家用车|代步车|日系", text, flags=re.I))
    compares_price_bands = bool(re.search(r"\d+(?:\.\d+)?\s*[-~—至到]\s*\d+(?:\.\d+)?\s*万.*(?:还是|和|对比|比较).*\d+(?:\.\d+)?\s*[-~—至到]\s*\d+(?:\.\d+)?\s*万", text))
    # A comparison between two explicit business price bands is still a
    # price-band opportunity question.  Keep this deterministic guard around
    # the LLM detail result so a transient generic-recommendation answer does
    # not send an otherwise complete question to the missing-scope flow.
    if compares_price_bands:
        return "selection.price_band_opportunity"
    if asks_for_candidates and has_non_price_scope and not compares_price_bands:
        return "selection.recommend_scope"

    if has_context and re.search(r"(?:这个车|这台车|它).{0,8}如果.{0,12}(?:排第几|排名|机会分)", text):
        return "selection.followup_contextual_qa"
    if re.search(r"BBA里面|两田一产|新势力|大众新能源|比亚迪宋|宝马5(?!系)|毛豆Y|这个FREE|问界现在|特斯拉怎么样", text, flags=re.I):
        return "selection.entity_resolution"
    if re.search(r"(?:找到|锁定|有了).{0,8}具体车.{0,12}(?:怎么|如何).{0,8}(?:定价|收车价)", text):
        return "selection.module_boundary_qa"

    semantic_family = classify_selection_query_family(text, has_vehicle_entity=_has_entity(slots))
    if semantic_family == "rank_lookup":
        return "selection.rank_lookup"
    if semantic_family == "explain_exclusion":
        return "selection.explain_exclusion"
    if semantic_family == "series_judgement":
        return "selection.series_judgement"
    if semantic_family == "score_explanation":
        return "selection.explain_rank_score"
    if semantic_family == "method_explanation":
        return "selection.signal_rule_explain"
    if semantic_family == "evidence_request":
        return "selection.evidence_request"
    if semantic_family == "compare":
        return "selection.compare"
    if semantic_family == "recommend_scope":
        return "selection.recommend_scope"
    if semantic_family == "city_opportunity":
        return "selection.city_opportunity"

    # Explicit output actions outrank the subject being exported. Two test
    # operations remain analytical tasks because the user asks how to run or
    # inspect them rather than asking for a business artifact.
    if re.search(r"导出这次回测指标", text):
        return "selection.backtest_metric"
    if re.search(r"证明\s*dsi.*报告怎么跑", normalized):
        return "selection.signal_ablation"
    if re.search(
        r"导出|导成\s*excel|生成.*(?:ppt|报告|prompt)|一页PPT|打包|给JSON|json格式|"
        r"前端要用|保存成规则|给领导看的.*报告|给Codex",
        text,
        flags=re.I,
    ):
        return "selection.export_report"
    if re.search(r"这个结果.*demo|业务员看不懂|模型词|理由.*业务员|卡片|空话|太AI|重写|别漏|放到后面|以后遇到|看不懂机会分|暂无风险|领导会问总利润", text, flags=re.I):
        return "selection.feedback_rewrite"
    if re.search(
        r"推荐\s*10\s*个|强行|别管数据|100%赚钱|所有城市所有车系|别筛条件|忽略回测|"
        r"只要高利润|周转慢无所谓|转化为0|成交周期长但利润低|成交2辆也给我重点关注|"
        r"最优推荐|豪华纯电MPV推荐\s*10\s*个",
        text,
        flags=re.I,
    ):
        return "selection.constraint_handling"
    if re.search(
        r"编一个|不用解释|删掉样本|样本不足.*删|不要.*证据|没有数据也|直接说.*第一|"
        r"包装成达标|proxy说成真实|没有.*编|没有.*代替|不要转定价|别写风险|"
        r"领导不看过程|不要管成交周期|没有政策也编|没有DSI.*热门榜代替|毛利预测",
        text,
    ):
        return "selection.safety_business_integrity"

    if re.search(r"BBA里面|两田一产|新势力|大众新能源|比亚迪宋|宝马5(?!系)|毛豆Y|这个FREE|问界现在|特斯拉怎么样", text, flags=re.I):
        return "selection.entity_resolution"
    if re.search(r"列表里没有|(?<!有)没有.*推荐|没进.*推荐|没进榜|不在.*榜|不在.*推荐|没出现|为什么没有|为啥.*不在|没有被推荐", text):
        return "selection.explain_exclusion"
    if re.search(r"日报/政策有没有影响.*推荐|排行榜有没有参与排序", text, flags=re.I):
        return "selection.evidence_request"
    if re.search(r"baseline|基线|全量平均|筛选后的|包含避免组|跟谁比|全量.*子集|筛选范围.*变|推荐组是跟谁比", normalized):
        return "selection.baseline_question"
    if re.search(r"Top\s*20%|同容量结果|总利润保留率是多少|平均利润高但总利润低|选中率太低会不会", text, flags=re.I):
        return "selection.backtest_metric"
    if re.search(r"排行榜.*总利润下降|加了排行榜.*总利润下降", text):
        return "selection.signal_ablation"
    if re.search(r"排行榜.*火.*总利润低|排行榜很火.*不推荐", text):
        return "selection.signal_rule_explain"
    if has_context and re.search(r"按总利润排序.*不按机会分|不按机会分", text):
        return "selection.followup_refine"
    if re.search(r"按.*总利润.*排|总利润贡献排", text):
        return "selection.sort_filter"
    if re.search(r"总利润和利润率冲突|保守过滤器|总利润|业务规模|利润保留率|只挑少量", text):
        return "selection.total_profit_scale"
    if re.search(r"低价机会.*放前面|放前面.*低价机会", text):
        return "selection.sort_filter"
    if re.search(r"选品和行情|选品和定价|热度榜|模块.*区别|为什么选品|选品结果能不能|推荐收是不是|避坑是不是|低价机会是不是|Agent里LLM|为什么还要进单车定价", text, flags=re.I):
        return "selection.module_boundary_qa"
    if has_context and re.search(r"那它|刚才|第\s*\d|这个车如果|它和|为什么把它|只看利润|换成售车转化|结论和之前|上面那个|为什么你说它|差在哪", text):
        return "selection.followup_contextual_qa"
    if re.search(r"去掉\s*dsi|只用排行榜|不要日报|日报影响|信号.*调整|只看行情状态机|排行榜里的降价榜|全信号的新增|dsi加进去后|误推|政策单独|只准行情\+日报", normalized):
        return "selection.followup_signal_adjust"
    if has_context and re.search(r"那只看|把混动也加上|只看SUV|价格带改成|不要特斯拉|样本少于\s*10|不按机会分|只看重庆本地|扩大到全国|也算进去", text, flags=re.I):
        return "selection.followup_refine"
    if re.search(r"政策|补贴|新车|新款|上市|以旧换新", text) and re.search(r"选品|推荐|收车|二手|排序|展示|回测|去掉|准新车|老款|不参与", text):
        return "selection.policy_newcar_effect"
    if re.search(r"如果不用日报|政策新车对选品.*帮助|排行榜.*总利润下降|证明\s*dsi|只要行情\+日报|全用是不是更强|ablation|策略对照|market_only|market_daily|full_signal|增益|排行榜反而总利润下降", normalized):
        return "selection.signal_ablation"
    if re.search(r"DSI高|热门榜|降价榜|城市榜|销量榜|排行榜.*(?:规则|火|变差|效果|加进去|命中|导致)|DSI弱|DSI缺失.*不能上榜|热门榜.*该收|降价榜.*避坑|信号.*规则|销量榜和热门榜|风险还是机会", text, flags=re.I):
        return "selection.signal_rule_explain"
    if re.search(r"日报/政策有没有影响.*推荐|内部行情.*DSI.*榜单.*日报|数据来源|证据.*可信度|证据|展开|分别是什么结论|有没有数据来源|强风险标签|排行榜有没有参与排序", text, flags=re.I):
        return "selection.evidence_request"
    if re.search(r"哪个价格带|价格带.*周转|利润和周转.*价格带|预算价格带|这个价位|价位推荐|价位.*方向", text):
        return "selection.price_band_opportunity"
    if re.search(r"重庆和成都|成都和重庆|北京和上海|上海和北京|哪个城市|城市.*适合|同样车系.*排序|区域|本地|扩大到全国|城市机会|只适合看纯电|15万以内能做|15-25万SUV机会", text):
        return "selection.city_opportunity"
    if re.search(r"横向比较|谁风险更低|谁更适合做|谁更稳|怎么排|哪个更|哪个更值得|哪个更可信|对比|比较|vs| or |和.*哪个|前\s*\d+.*比较", text, flags=re.I):
        return "selection.compare"
    if re.search(r"具体这台车.*多少钱|进入单车定价|只知道车系|不补六要素|先估个大概|最高追到|能多少钱收|能收多少|收车价|估价|报价|出多少钱|带到估价", text):
        return "selection.handoff_pricing"
    if re.search(r"谨慎而不是推荐|列表里没有|没有.*推荐|没进.*推荐|没进榜|不在.*榜|不在.*推荐|没出现|为什么没有|为啥.*不在|没有被推荐", text):
        return "selection.explain_exclusion"
    if re.search(r"样本可信度|小样本惩罚|排序依据|前十车系|前五|排名靠前|在前\s*\d*|机会分|凭什么|成交\s*\d+\s*(?:辆|台).*(?:高|分|重点|样本不足|才)|为什么.*排|为什么.*样本不足|周转.*为啥.*重点|为啥.*重点|排第一", text):
        return "selection.explain_rank_score"
    if re.search(r"低价|捡漏|只能低价|不是推荐收.*低价|不能正常价|低于市场价|高风险高机会|单车定价复核|不适合直接推荐|库存有压力.*利润", text):
        return "selection.low_price_opportunity"
    if re.search(r"按.*排|从.*到.*排|只看样本|样本量大于|过滤|隐藏|排序|筛选|top\s*\d+|前\s*\d+|只看强推荐|只看避坑|放前面|剔除|至少20%|贡献排|小样本隐藏", text, flags=re.I) and not re.search(r"不按|也算进去|只看重庆|扩大到全国|混动也加|不要特斯拉|价格带改成|那只看", text):
        return "selection.sort_filter"
    if re.search(r"回测|达标|四项指标|推荐组|避免组|过没过|经营效果|指标是多少|成交周期方向|Top20%|只选10台|导出这次回测|总利润保留率|平均利润高但总利润低|选中率太低会不会", text, flags=re.I):
        return "selection.backtest_metric"
    if re.search(r"baseline|基线|全量平均|筛选后的|包含避免组|跟谁比|全量.*子集|筛选范围.*变|推荐组是跟谁比", normalized):
        return "selection.baseline_question"
    if re.search(r"选中率太低|业务规模|总利润和利润率冲突|保守过滤器|总利润|规模|利润保留率|平均利润|只挑少量", text):
        return "selection.total_profit_scale"
    if re.search(r"回测|达标|四项指标|推荐组|避免组|过没过|经营效果|指标是多少|成交周期方向|Top20%|只选10台|导出这次回测", text, flags=re.I):
        return "selection.backtest_metric"
    if re.search(
        r"编一个|不用解释|删掉样本|样本不足.*删|不要.*证据|没有数据也|直接说.*第一|强行|别管数据|"
        r"包装成达标|proxy说成真实|没有.*编|没有.*代替|不要转定价|别写风险|售车转化为0也没事|"
        r"100%赚钱|不要管成交周期",
        text,
    ):
        return "selection.safety_business_integrity"
    if re.search(
        r"推荐\s*10\s*个|强行|别管数据|100%赚钱|所有城市所有车系|别筛条件|忽略回测|只要高利润|周转慢无所谓|"
        r"转化为0|没有数据也|包装成达标|成交周期长但利润低|成交2辆也给我重点关注|所有城市所有车系|最优推荐",
        text,
        flags=re.I,
    ):
        return "selection.constraint_handling"
    if re.search(r"导出|excel|报告|给领导|ppt|codex|prompt|json|保存成规则|打包", normalized):
        return "selection.export_report"
    if re.search(r"这个结果.*demo|业务员看不懂|模型词|理由.*业务员|卡片|空话|太AI|重写|别漏|放到后面|以后遇到|看不懂机会分|暂无风险", text, flags=re.I):
        return "selection.feedback_rewrite"
    if re.search(r"选品和行情|选品和定价|热度榜|模块.*区别|为什么选品|选品结果能不能|推荐收是不是|避坑是不是|低价机会是不是|Agent里LLM|为什么还要进单车定价", text, flags=re.I):
        return "selection.module_boundary_qa"
    if has_context and re.search(r"那它|刚才|第\s*\d|这个车如果|它和|为什么把它|只看利润|换成售车转化|结论和之前|上面那个|为什么你说它|差在哪", text):
        return "selection.followup_contextual_qa"
    if re.search(r"去掉\s*dsi|只用排行榜|不要日报|日报影响|信号.*调整|只看行情状态机|排行榜里的降价榜|全信号的新增|dsi加进去后|误推|政策单独|只准行情\+日报", normalized):
        return "selection.followup_signal_adjust"
    if re.search(r"如果不用日报|政策新车对选品.*帮助|排行榜.*总利润下降|证明\s*dsi|只要行情\+日报|全用是不是更强|ablation|策略对照|market_only|market_daily|full_signal|增益", normalized):
        return "selection.signal_ablation"
    if re.search(r"DSI缺失|排行榜匹配不上|数据质量|数据覆盖|覆盖率|映射|车型库|样本太少|字段|price[_ ]?band|匹配不上|英文和中文|中文和英文|同一个|是不是同一个", text, flags=re.I):
        return "selection.data_quality"
    if re.search(r"BBA里面|两田一产|新势力|大众新能源|比亚迪宋|宝马5(?!系)|毛豆Y|这个FREE|问界现在|特斯拉怎么样", text, flags=re.I):
        return "selection.entity_resolution"
    if re.search(r"tesla|zeekr|byd|bba|model\s*[3y]|free|mona|m03|15-25w|20-30w|问届|新能源suv\s*风险榜|岚图free", normalized):
        return "selection.robust_nlu"
    if re.search(r"DSI高|热门榜|降价榜|城市榜|销量榜|排行榜.*(?:规则|火|变差|效果|加进去|命中|导致)|DSI弱|热门榜.*该收|降价榜.*避坑|信号.*规则|销量榜和热门榜|风险还是机会", text, flags=re.I):
        return "selection.signal_rule_explain"
    if re.search(r"日报/政策有没有影响.*推荐|内部行情.*DSI.*榜单.*日报|数据来源|证据.*可信度|证据|展开|分别是什么结论|有没有数据来源|强风险标签", text, flags=re.I):
        return "selection.evidence_request"
    if re.search(r"购车补贴|最新政策|查一下.*政策", text) and not re.search(r"选品|推荐|收车|二手车", text):
        return "policy_search_or_policy_tool"
    if re.search(r"按.*排|从.*到.*排|只看样本|样本量大于|过滤|隐藏|排序|筛选|top\s*\d+|前\s*\d+|只看强推荐|只看避坑|放前面|剔除|至少20%|贡献排|小样本隐藏", text, flags=re.I) and not re.search(r"不按|也算进去|只看重庆|扩大到全国|混动也加|不要特斯拉|价格带改成|那只看", text):
        return "selection.sort_filter"
    if not _has_scope(slots, text) and re.search(r"哪些别碰|什么车值得收|帮我选品|推荐几个车", text):
        return "clarify.missing_scope"
    if re.search(r"重庆和成都|成都和重庆|北京和上海|上海和北京|哪个城市|城市.*适合|同样车系.*排序|区域|本地|扩大到全国|城市机会|只适合看纯电|15万以内能做|15-25万SUV机会", text):
        return "selection.city_opportunity"
    if re.search(r"样本可信度|小样本惩罚|排序依据|前十车系|前五|排名靠前|在前\s*\d*|机会分|凭什么|成交\s*\d+\s*(?:辆|台).*(?:高|分|重点|样本不足)|为什么.*排|为什么.*样本不足|周转.*为啥.*重点|为啥.*重点", text):
        return "selection.explain_rank_score"
    if re.search(r"补贴|新车上市|以旧换新|政策.*影响|新车.*影响|政策表|有效期|新车事件|新车降价|政策只影响|老款还推荐|上市了.*推荐|不参与排序|从选品去掉", text) and re.search(r"选品|推荐|收车|二手|排序|去掉|准新车|老款|不参与", text):
        return "selection.policy_newcar_effect"
    if re.search(r"低价|捡漏|只能低价|不是推荐收.*低价|不能正常价|低于市场价|高风险高机会|单车定价复核|不适合直接推荐|库存有压力.*利润", text):
        return "selection.low_price_opportunity"
    if re.search(r"谨慎而不是推荐|列表里没有|没有.*推荐|没进.*推荐|没进榜|不在.*榜|不在.*推荐|没出现|为什么没有|为啥.*不在", text):
        return "selection.explain_exclusion"
    if re.search(r"别碰|暂缓|风险|库存.*风险|周转.*风险|不要收|不建议收|不建议主动|避坑|容易亏|别追价|转化差|周转.*慢|周转明显慢|补库.*谨慎", text):
        return "selection.risk_scope"
    if re.search(r"横向比较|谁风险更低|谁更适合做|谁更稳|怎么排|哪个更|对比|比较|vs| or |前\s*\d+.*比较", text, flags=re.I):
        return "selection.compare"
    if has_context and re.search(r"把|那只看|只看|扩大到|按.*排|换成|改成|过滤|剔除|样本少于|样本量大于|不要", text, flags=re.I):
        return "selection.followup_refine"
    if re.search(r"排行榜有没有参与|日报/政策有没有影响|内部行情.*DSI.*榜单.*日报|数据来源|证据.*可信度|证据|展开|分别是什么结论|有没有数据来源", text, flags=re.I):
        return "selection.evidence_request"
    if re.search(r"具体这台车.*多少钱|进入单车定价|只知道车系|不补六要素|先估个大概|最高追到|能多少钱收|能收多少|收车价|估价|报价|出多少钱", text):
        return "selection.handoff_pricing"
    if re.search(r"样本可信度|小样本惩罚|排序依据|前十车系|前五|排名靠前|在前\s*\d*|机会分|凭什么|成交\s*\d+\s*(?:辆|台).*(?:高|分|重点|样本不足)|为什么.*排|为什么.*样本不足|周转.*为啥.*重点|为啥.*重点", text):
        return "selection.explain_rank_score"
    if re.search(r"谨慎而不是推荐|列表里没有|没有.*推荐|没进.*推荐|没进榜|不在.*榜|不在.*推荐|没出现|为什么没有|为啥.*不在", text):
        return "selection.explain_exclusion"
    if re.search(r"排行榜很火但总利润低|降价榜是风险还是机会|城市榜|销量榜和热门榜|热门榜.*冲突|dsi弱|dsi缺失|排行榜.*规则|排行榜.*火", normalized):
        return "selection.signal_rule_explain"
    if re.search(r"总利润和利润率冲突|保守过滤器|总利润|业务规模|规模|利润保留率|平均利润|只挑少量", text):
        return "selection.total_profit_scale"
    if re.search(r"重庆和成都|成都和重庆|哪个城市|城市.*适合|同样车系.*排序|区域|本地|扩大到全国|城市机会|只适合看纯电|15万以内能做|15-25万SUV机会", text):
        return "selection.city_opportunity"
    if re.search(r"横向比较|谁风险更低|谁更适合做|谁更稳|怎么排|哪个更|对比|比较|vs| or ", text, flags=re.I):
        return "selection.compare"
    if re.search(r"哪个价格带|价格带.*周转|利润和周转.*价格带|这个价位|预算价格带|价位推荐|价位.*方向", text):
        return "selection.price_band_opportunity"
    if re.search(r"tesla|zeekr|byd|model\s*[3y]|free|mona|m03|宋plus\s*dmi|新能源suv\s*风险榜|岚图free", normalized):
        return "selection.robust_nlu"
    if re.search(r"excel|字段够不够|表字段|schema|数据表", normalized):
        return "data_schema_review"
    if re.search(r"ui|页面|前端|太丑|按钮|交互", normalized):
        return "product_feedback_ui"
    if re.search(r"购车补贴|最新政策|查一下.*政策", text):
        return "policy_search_or_policy_tool"
    if re.search(r"英文|英语|english|翻译", normalized):
        return "selection_qa_translation"

    if re.search(
        r"编一个|不用解释|删掉样本|样本不足.*删|不要.*证据|没有数据也|直接说.*第一|强行|别管数据|"
        r"包装成达标|proxy说成真实|没有.*编|没有.*代替|不要转定价|别写风险|售车转化为0也没事",
        text,
    ):
        return "selection.safety_business_integrity"
    if re.search(
        r"什么车值得收|帮我选品|给我推荐几个车|哪些别碰|最近行情好的给我|新能源现在能不能做|"
        r"^SUV推荐一下$|重庆有什么机会|15万左右推荐|我要稳一点",
        text,
        flags=re.I,
    ):
        return "clarify.missing_scope"
    if re.search(r"选品和行情|选品和定价|热度榜|模块.*区别|为什么选品|选品结果能不能|推荐收是不是|避坑是不是|低价机会是不是|Agent里LLM", text, flags=re.I):
        return "selection.module_boundary_qa"
    if re.search(r"这个结果.*demo|业务员看不懂|模型词|理由.*业务员|卡片|空话|太AI|重写|别漏|放到后面|以后遇到", text, flags=re.I):
        return "selection.feedback_rewrite"
    if re.search(r"导出|excel|报告|给领导|ppt|codex|prompt|打包|json|保存成规则", normalized):
        return "selection.export_report"
    if re.search(r"那它|刚才|第\s*\d|这个车如果|它和|为什么把它|只看利润|换成售车转化|结论和之前|上面那个", text):
        return "selection.followup_contextual_qa"
    if re.search(r"那只看|把混动也加上|只看SUV|价格带改成|不要特斯拉|只看重庆|扩大到全国|把低价机会也算进去", text, flags=re.I):
        return "selection.followup_refine"
    if re.search(r"去掉\s*dsi|只用排行榜|不要日报|不用日报|信号.*调整|只看行情状态机|排行榜里的降价榜|全信号的新增|dsi加进去后|误推", normalized):
        return "selection.followup_signal_adjust"
    if re.search(r"按.*排|从.*到.*排|只看样本|样本量大于|过滤|隐藏|排序|筛选|top\s*\d+|前\s*\d+|只看强推荐|只看避坑|放前面|剔除|至少20%", text, flags=re.I):
        return "selection.sort_filter"
    if re.search(r"不要看样本|利润低.*推荐|推荐\s*10\s*个|强行推荐|不合理|矛盾", text) or (
        re.search(r"成交\s*2\s*辆|成交二辆", text) and not re.search(r"为什么|凭什么|为啥|怎么", text)
    ):
        return "selection.constraint_handling"
    if re.search(r"回测|达标|四项指标|推荐组|避免组|过没过|经营效果|指标是多少|成交周期方向|Top20%|只选10台|导出这次回测", text, flags=re.I):
        return "selection.backtest_metric"
    if re.search(r"baseline|基线", normalized):
        return "selection.baseline_question"
    if re.search(r"总利润|选中率|业务规模|只挑少量|规模|平均利润|利润保留率|保守过滤器|利润率冲突", text):
        return "selection.total_profit_scale"
    if re.search(r"字段|price[_ ]?band|车型库|匹配上|匹配不上|数据质量|样本可信|置信|覆盖率|映射|样本太少|英文.*中文|中文.*英文|同一个", normalized):
        return "selection.data_quality"
    if re.search(r"加上\s*dsi|排行榜.*有没有用|只用领导|策略.*日报|全信号|market_only|market_daily|full_signal|证明.*dsi|dsi.*有用", normalized):
        return "selection.signal_ablation"
    if re.search(r"dsi.*一定|热门榜.*该收|降价榜.*避坑|信号.*规则|城市榜|销量榜|热门榜.*冲突|dsi弱|dsi缺失|排行榜.*变差|排行榜.*火", normalized):
        return "selection.signal_rule_explain"
    if re.search(r"补贴|新车上市|以旧换新|政策.*影响|新车.*影响|政策表|有效期|新车事件|新车降价|政策只影响|老款还推荐", text) and re.search(r"选品|推荐|收车|二手|排序|准新车|老款|不参与", text):
        return "selection.policy_newcar_effect"
    if re.search(r"低价|捡漏|只能低价|不是推荐收.*低价|不能正常价|低于市场价|高风险高机会|单车定价复核|不适合直接推荐|库存有压力.*利润", text):
        return "selection.low_price_opportunity"
    if re.search(r"依据|证据|展开|因为行情|因为利润|数据来源|强风险标签|可信度|分别是什么结论|DSI.*作用|排行榜.*参与|日报/政策", text, flags=re.I):
        return "selection.evidence_request"
    if re.search(r"不在.*榜|没进.*推荐|没进榜|没有被推荐|不在推荐|不在选品|没有.*推荐|数据没抓到|没出现|为什么没有|为啥.*不在", text):
        return "selection.explain_exclusion"
    if re.search(r"机会分|凭什么|成交\s*\d+\s*(?:辆|台).*(?:高|分|重点)|为什么.*排|周转.*为啥.*重点|为啥.*重点", text):
        return "selection.explain_rank_score"
    if re.search(r"收车价|能多少钱收|能收多少|直接给我收|估价|报价", text):
        return "selection.handoff_pricing"
    if re.search(r"对比|比较|哪个更|谁更|谁.*稳|怎么排|横向|差在哪|vs| or |和.*哪个", text, flags=re.I):
        return "selection.compare"
    if re.search(r"别碰|暂缓|风险|库存.*风险|周转.*风险|不要收|不建议收|避坑|容易亏|别追价|转化差|周转.*慢|周转明显慢", text):
        return "selection.risk_scope"
    if re.search(r"重庆和成都|北京和上海|哪个城市|城市.*适合|区域|本地|扩大到全国|补库|城市机会", text):
        return "selection.city_opportunity"
    if re.search(r"tesla|zeekr|byd|bba|model\s*[3y]|free|mona|m03|\d+\s*w|问届|毛豆|宋plus|dmi", normalized):
        return "selection.robust_nlu"
    if re.search(r"哪些|什么车|推荐|值得重点看|适合收|值得收|能做", text) and re.search(
        r"新能源|燃油|SUV|MPV|轿车|豪华|\d+(?:\.\d+)?\s*(?:万|w)|全国|北京|上海|广州|深圳|重庆|成都|杭州|武汉",
        text,
        flags=re.I,
    ):
        return "selection.recommend_scope"
    if re.search(r"价格带|预算|价位|万以内|万以上|\d+\s*[-~—至到]\s*\d+\s*万", text):
        if re.search(r"机会|值得做|太卷|还值得", text):
            return "selection.price_band_opportunity"
    if re.search(r"tesla|zeekr|\d+\s*w|model\s*y|model\s*3", normalized):
        return "selection.robust_nlu"
    if _has_entity(slots) and re.search(r"怎么样|能做|推荐吗|值得收|现在", text):
        return "selection.entity_resolution"
    if internal_intent == "MARKET_REASON_QUERY":
        return "selection.explain_exclusion" if _has_entity(slots) else "selection.followup_contextual_qa"
    if internal_intent == "MARKET_RISK_QUERY":
        return "selection.risk_scope"
    if internal_intent == "MARKET_PRICE_BUCKET_QUERY":
        return "selection.price_band_opportunity"
    if internal_intent == "MARKET_CITY_CHANGE":
        return "selection.city_opportunity"
    if internal_intent == "MARKET_SERIES_COMPARE":
        return "selection.compare"
    if not _has_scope(slots, text) and re.search(r"什么车值得收|帮我选品|推荐几个车", text):
        return "clarify.missing_scope"
    return "selection.recommend_scope"


def _has_entity(slots: dict[str, Any]) -> bool:
    generic = {"新能源", "燃油", "油车", "电车", "纯电", "插混", "混动", "二手车", "车", "SUV", "MPV", "轿车", "豪华", "家用车"}
    series = str(slots.get("series") or "").strip()
    brand = str(slots.get("brand") or "").strip()
    return bool(
        (brand and brand.upper() not in generic)
        or (series and series.upper() not in generic and series not in generic)
        or slots.get("raw_vehicle_text")
    )


def _has_scope(slots: dict[str, Any], text: str) -> bool:
    return bool(
        slots.get("city")
        or slots.get("price_band")
        or slots.get("price_bucket")
        or slots.get("energy_type")
        or slots.get("fuel_type")
        or slots.get("brand")
        or slots.get("series")
        or re.search(r"全国|新能源|燃油|SUV|MPV|轿车|\d+\s*万", text, flags=re.I)
    )


def _task_from_internal(internal_intent: str) -> str:
    return {
        "MARKET_OPPORTUNITY_RECOMMEND": "recommend_models",
        "MARKET_RISK_QUERY": "identify_risky_models",
        "MARKET_PRICE_BUCKET_QUERY": "recommend_price_band",
        "MARKET_CITY_CHANGE": "recommend_city_opportunity",
        "MARKET_SERIES_COMPARE": "compare_series",
        "MARKET_REASON_QUERY": "explain_selection_reason",
        "COMPOUND_SELECTION_PRICING": "selection_to_pricing",
    }.get(str(internal_intent or ""), "recommend_models")


def _required_context(intent: str) -> str:
    if intent in {"selection.followup_contextual_qa", "selection.followup_refine", "selection.followup_signal_adjust"}:
        return "last_selection_result"
    if intent in {"selection.export_report", "selection.sort_filter"}:
        return "selection_result"
    if intent.startswith("out_of_scope"):
        return "none"
    return "query_scope_or_selection_result"


def _action_for_intent(intent: str) -> str:
    if intent.startswith("out_of_scope"):
        return "refuse_or_redirect"
    if intent == "clarify.missing_scope":
        return "ask_city_price_energy_scope"
    if intent == "selection.handoff_pricing":
        return "handoff_to_pricing_after_required_slots"
    if intent == "selection.export_report":
        return "export_selection_report"
    return "run_selection_capability"
