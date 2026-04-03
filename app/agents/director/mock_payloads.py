from __future__ import annotations

_LOGLINE_TITLES = ("版本A", "版本B", "版本C")
_MODE_TITLES = ("模式A", "模式B", "模式C")


def _logline_title(index: int) -> str:
    return _LOGLINE_TITLES[index % len(_LOGLINE_TITLES)]


def _mode_title(index: int) -> str:
    return _MODE_TITLES[index % len(_MODE_TITLES)]


def build_project_payload(
    *,
    movie_name: str,
    type_value: str,
    duration: str,
    tone: str,
    reference_ip: str,
) -> dict:
    return {
        "ok": True,
        "project": {
            "project_id": "director_demo_001",
            "movie_name": str(movie_name or ""),
            "type": str(type_value or ""),
            "duration": str(duration or ""),
            "tone": str(tone or ""),
            "reference_ip": str(reference_ip or ""),
            "status": "created",
        },
    }


def build_seed_payload(
    *,
    seed: str,
    protagonist: str,
    antagonist: str,
    core_synopsis: str,
    key_setting: str,
) -> dict:
    seed_hint = seed or "一个被迫做选择的主角，在高压规则下揭开真相"
    protagonist_hint = protagonist or "主角（暂定）"
    antagonist_hint = antagonist or "对立面（暂定）"
    synopsis_hint = core_synopsis or "主角在失序环境中为守护重要关系，必须挑战既有规则并承担代价。"
    setting_hint = key_setting or "关键设定待补充（当前为假响应）"

    return {
        "ok": True,
        "seed_result": {
            "loglines": [
                {
                    "title": "版本A",
                    "logline": f"{protagonist_hint}被卷入一场围绕“{seed_hint}”的冲突，必须在时间耗尽前击败{antagonist_hint}。",
                    "sell_line": "高概念冲突 + 情感代价驱动的角色成长线。",
                    "hook_question": f"当代价越来越高时，{protagonist_hint}还会坚持原本的选择吗？",
                },
                {
                    "title": "版本B",
                    "logline": f"在“{setting_hint}”的规则下，{protagonist_hint}与{antagonist_hint}围绕同一目标展开对抗。",
                    "sell_line": "规则感世界观与人物立场冲突并行推进。",
                    "hook_question": "如果双方都认为自己在拯救世界，真正的反派是谁？",
                },
                {
                    "title": "版本C",
                    "logline": f"{synopsis_hint}而这一切都指向{antagonist_hint}隐藏的真实动机。",
                    "sell_line": "情绪悬念先行，逐步揭示核心秘密。",
                    "hook_question": "真相被揭开后，主角还能回到最初的自己吗？",
                },
            ],
            "themes": [
                {"title": "主题1", "theme_question": "守护重要之物时，人愿意牺牲到什么程度？"},
                {"title": "主题2", "theme_question": "秩序与自由的边界应由谁来决定？"},
                {"title": "主题3", "theme_question": "当信念建立在误解之上，成长意味着什么？"},
                {"title": "主题4", "theme_question": "面对无法两全的选择，什么才算正确？"},
            ],
            "world_rules": [
                {
                    "rule": f"世界运行受一套公开规则约束（围绕：{setting_hint}）。",
                    "cost": "每次突破规则都会消耗关系、时间或身体负担。",
                    "forbidden": "禁止无代价地使用关键能力或获得关键情报。",
                },
                {
                    "rule": "重要信息只能通过行动与后果逐步暴露。",
                    "cost": "角色必须承担错误决策的连锁后果。",
                    "forbidden": "禁止用旁白/解释性台词一次性讲清全部设定。",
                },
            ],
            "characters": [
                {
                    "name": protagonist_hint,
                    "desire": "守住眼前最重要的人或目标",
                    "fear": "因自己的选择导致无法挽回的失去",
                    "misbelief": "只要独自承担一切，就能保护所有人",
                    "cost": "关系疏离与自我消耗持续加重",
                },
                {
                    "name": antagonist_hint,
                    "desire": "用更极端但高效的方法实现秩序/结果",
                    "fear": "再次陷入失控与混乱",
                    "misbelief": "目的正确就可以覆盖过程伤害",
                    "cost": "逐步失去同伴信任与人性弹性",
                },
            ],
            "modes": [
                {
                    "title": "模式A",
                    "manifesto": "角色情感弧线优先，冲突围绕关系推进。",
                    "anti_trope": "避免靠信息差硬拧反转。",
                    "payoff_rhythm": "前中段埋压，中后段连续兑现角色选择代价。",
                },
                {
                    "title": "模式B",
                    "manifesto": "规则推演优先，让世界观驱动剧情选择。",
                    "anti_trope": "避免设定炫技盖过人物动机。",
                    "payoff_rhythm": "每一轮规则突破都伴随更高代价回收。",
                },
                {
                    "title": "模式C",
                    "manifesto": "悬念揭示优先，逐层翻开立场与真相。",
                    "anti_trope": "避免无铺垫的结尾翻盘。",
                    "payoff_rhythm": "小揭示密集推进，终局给一次大情绪回收。",
                },
            ],
            "novel_idea_gate": {
                "score": 3.8,
                "evidence": [
                    f"核心种子已形成冲突方向：{seed_hint}",
                    "人物与规则草案已具备可迭代的差异化空间",
                ],
                "improve_instruction": "下一步优先收紧主角目标与代价机制，并明确对立面为何在此刻行动。",
            },
        },
    }


def build_blueprint_payload(
    *,
    selected_logline_index: int,
    selected_mode_index: int,
    audience: str,
    narrative_focus: str,
    ending_tendency: str,
) -> dict:
    logline_title = _logline_title(selected_logline_index)
    mode_title = _mode_title(selected_mode_index)
    audience_hint = audience or "泛年轻向观众"
    focus_hint = narrative_focus or "人物关系与选择代价"
    ending_hint = ending_tendency or "带余味的阶段性完成"

    return {
        "ok": True,
        "blueprint_result": {
            "three_act_structure": [
                {
                    "act": "Act 1",
                    "range": "0–25%",
                    "summary": f"基于{logline_title}+{mode_title}建立世界规则、人物目标与初始冲突，并抛出必须行动的诱因（受众倾向：{audience_hint}）。",
                },
                {
                    "act": "Act 2",
                    "range": "25–75%",
                    "summary": f"围绕“{focus_hint}”逐步升级因果链，角色每次推进都付出更高成本，同时信息披露推动立场变化。",
                },
                {
                    "act": "Act 3",
                    "range": "75–100%",
                    "summary": f"在终局决战中回收前文伏笔与代价机制，导向“{ending_hint}”的结局表达。",
                },
            ],
            "key_nodes": [
                {"name": "诱因", "content": f"主角被迫进入主线冲突，且与{logline_title}的核心命题直接绑定。"},
                {"name": "第一转折", "content": f"主角主动选择行动路径，正式进入{mode_title}的推进模式。"},
                {"name": "中点", "content": "局势短暂反转或获得阶段性胜利，但代价与真相同时放大。"},
                {"name": "谷底", "content": "主角在关系/信念/资源层面遭遇重挫，原策略被证明不足。"},
                {"name": "第二转折", "content": "主角重建行动逻辑，做出新的关键选择并明确终局目标。"},
                {"name": "终局决战", "content": "围绕最终选择进行冲突兑现，回收主题表达与角色代价。"},
            ],
            "reveal_plan": [
                {"minute": "10", "audience_knows": "世界规则表层信息与主角当前目标", "character_knows": "只知道局部真相，误判对立面动机"},
                {"minute": "45", "audience_knows": f"{mode_title}推进下的关键代价机制与隐藏线索", "character_knows": "意识到问题规模超出预期，但尚未掌握核心真相"},
                {"minute": "80", "audience_knows": "核心真相与终局选择代价基本明牌", "character_knows": "与观众认知接近，进入最终抉择"},
            ],
            "set_pieces": [
                {"title": "场面1", "sell_line": "规则首次显形的高张力开场", "scene_goal": "建立世界规则与角色处境", "cost_point": "主角失去先手/信誉"},
                {"title": "场面2", "sell_line": "第一次主动尝试带来意外后果", "scene_goal": "展示行动与代价绑定", "cost_point": "资源消耗或关系裂痕"},
                {"title": "场面3", "sell_line": "中段强冲突场面推动立场对撞", "scene_goal": "让主角与对立面理念正面碰撞", "cost_point": "暴露弱点/误伤同伴"},
                {"title": "场面4", "sell_line": "真相揭示前后的失控段落", "scene_goal": "制造谷底并重置目标", "cost_point": "主角核心信念崩塌边缘"},
                {"title": "场面5", "sell_line": "终局前集结与策略重构", "scene_goal": "完成角色选择与方案成形", "cost_point": "必须放弃一项重要利益"},
                {"title": "场面6", "sell_line": "终局决战与主题兑现", "scene_goal": "完成主冲突并回收主题", "cost_point": "以真实代价换取结果成立"},
            ],
            "hard_gate_precheck": [
                {"type": "完整性", "status": "通过", "note": f"三幕结构与关键节点已形成基础闭环（来源：{logline_title}/{mode_title}）。"},
                {"type": "因果链", "status": "提示", "note": "建议在 Act2 强化每个节点之间的触发因果，而非并列事件推进。"},
                {"type": "动机闭环", "status": "通过", "note": "主角推进与代价方向一致，具备后续细化空间。"},
                {"type": "世界规则一致", "status": "提示", "note": "建议进一步明确规则例外条件与违规后果边界。"},
                {"type": "三观风险", "status": "提示", "note": "后续需检查角色行为奖励导向是否与主题表达冲突。"},
            ],
        },
    }


def build_beats_payload(
    *,
    selected_logline_index: int,
    selected_mode_index: int,
    segment_granularity: str,
    action_ratio: str,
    character_ratio: str,
) -> dict:
    logline_title = _logline_title(selected_logline_index)
    mode_title = _mode_title(selected_mode_index)
    segment_hint = segment_granularity or "8段"
    action_hint = action_ratio or "50%"
    character_hint = character_ratio or "50%"

    return {
        "ok": True,
        "beats_result": {
            "beat_sheet": [
                {
                    "segment": "段落1",
                    "goal": f"基于{logline_title}/{mode_title}建立主角短期目标并进入主冲突（粒度参考：{segment_hint}）",
                    "conflict": "对立力量先发制人，迫使主角在信息不足下行动",
                    "turn": "主角发现当前目标只是更大局面的表层诱饵",
                    "emotion_curve": f"紧张上升（动作约{action_hint} / 角色约{character_hint}）",
                },
                {
                    "segment": "段落2",
                    "goal": "主角尝试修复关系并验证关键线索",
                    "conflict": "关系信任下降与外部压力同步升级",
                    "turn": "第三方势力的介入改变原有对抗格局",
                    "emotion_curve": "不安累积后短暂拉升，转入更强悬念",
                },
            ],
            "arc_map": [
                {
                    "segment": "段落1",
                    "belief_change": "主角开始意识到单靠旧方法无法解决问题",
                    "relationship_change": "与同伴形成暂时协作但缺乏深度信任",
                    "cost_upgrade": "首次付出可见代价（资源/信誉/时间）",
                },
                {
                    "segment": "段落2",
                    "belief_change": "主角开始怀疑自己对局势的核心判断",
                    "relationship_change": "与关键关系对象出现试探与裂痕",
                    "cost_upgrade": "代价由外部损失升级为关系与身份风险",
                },
            ],
            "foreshadow_plan": [
                {
                    "setup": "早期埋下第三方监视主角的迹象",
                    "payoff": "中段确认第三方一直在操控冲突节奏",
                    "segment": "段落2",
                    "intentional_open": False,
                },
                {
                    "setup": "对立面行为中的不一致细节",
                    "payoff": "后续揭示其真实动机并非表面目标",
                    "segment": "段落4",
                    "intentional_open": True,
                },
            ],
            "rhythm_risks": [
                {"type": "中段松", "note": "建议在段落2结尾加入更明确的不可逆代价，避免信息推进弱于情节推进。"},
                {"type": "信息过载", "note": "段落1若同时解释规则与人物关系，需控制解释密度，优先行动化呈现。"},
            ],
            "soft_alignment": {
                "status": "部分一致",
                "option_a": "更贴近当前创作空间偏好的方案：压缩解释段，强化角色选择带来的情绪波动。",
                "option_b": "保留当前节奏取向的方案：维持信息层层揭示，但用更明确的段落目标增强推进感。",
            },
        },
    }


def build_scenes_payload(
    *,
    selected_logline_index: int,
    selected_mode_index: int,
    target_scene_count: str,
    scene_constraints: str,
    language_style: str,
) -> dict:
    logline_title = _logline_title(selected_logline_index)
    mode_title = _mode_title(selected_mode_index)
    scene_count_hint = target_scene_count or "13"
    constraint_hint = scene_constraints or "无额外限制（假响应）"
    language_hint = language_style or "偏影视化描述"

    return {
        "ok": True,
        "scenes_result": {
            "scene_list": [
                {
                    "scene_title": "INT. 旧仓库 - 夜",
                    "goal": f"主角试图拿回关键证据（基于{logline_title}/{mode_title}推进）",
                    "conflict": "对立面提前设伏并切断退路",
                    "turn": "主角发现真正被盯上的不是证据而是同伴",
                },
                {
                    "scene_title": "EXT. 天桥 - 凌晨",
                    "goal": "主角试探同伴是否仍可信",
                    "conflict": "同伴回避关键问题，关系变得紧张",
                    "turn": "一条匿名短信让双方都意识到第三方在操控局面",
                },
            ],
            "scene_functions": [
                {
                    "scene_title": "INT. 旧仓库 - 夜",
                    "tags": ["动作", "悬疑", "反转"],
                },
                {
                    "scene_title": "EXT. 天桥 - 凌晨",
                    "tags": ["关系", "信息"],
                },
            ],
            "scene_event_coupling": [
                {
                    "scene_title": "INT. 旧仓库 - 夜",
                    "why_here": f"仓库的封闭结构与复杂掩体使伏击和反制成立，适配{mode_title}的高压推进；场次目标参考总量 {scene_count_hint}。",
                },
                {
                    "scene_title": "EXT. 天桥 - 凌晨",
                    "why_here": f"空旷高处与深夜人流稀少强化角色不安全感，使试探与怀疑更具张力（限制条件：{constraint_hint}）。",
                },
            ],
            "scene_stats": {
                "interior_count": 8,
                "exterior_count": 5,
                "day_count": 4,
                "night_count": 9,
                "core_location_ratio": "62%",
            },
            "hard_gate_precheck": [
                {"type": "场景有效性", "status": "通过", "note": f"大多数场景具备明确目标/冲突/转折，描述风格为{language_hint}。"},
                {"type": "状态变量变化", "status": "提示", "note": "个别场景的关系变化尚不够明显。"},
                {"type": "关键代价递增", "status": "提示", "note": "中段代价升级可以再前置。"},
                {"type": "规则一致", "status": "通过", "note": "未见明显设定冲突。"},
            ],
        },
    }


def build_draft_payload(
    *,
    selected_logline_index: int,
    selected_mode_index: int,
    writing_tendency: str,
    dialogue_density: str,
    rating_intensity: str,
) -> dict:
    logline_title = _logline_title(selected_logline_index)
    mode_title = _mode_title(selected_mode_index)
    writing_hint = writing_tendency or "偏电影感"
    dialogue_hint = dialogue_density or "中等对白密度"
    rating_hint = rating_intensity or "中等强度"

    script_text = (
        "FADE IN:\n\n"
        "INT. 旧仓库 - 夜\n"
        "主角小心潜入仓库深处，空气里都是潮湿铁锈味。手电光扫过堆叠木箱，灰尘像细雪一样浮起。\n\n"
        "主角\n"
        "他果然来过这里。\n\n"
        "对立面（画外）\n"
        "你总是慢一步。\n\n"
        "主角猛地转身，脚步声从高处与侧后方同时逼近。\n\n"
        "CUT TO:\n\n"
        "EXT. 天桥 - 凌晨\n"
        "夜风穿过钢梁缝隙，同伴站在路灯阴影边缘，视线始终没有正面看向主角。\n\n"
        "主角\n"
        "如果你提前知道，为什么不告诉我？\n\n"
        "同伴\n"
        "我说了，你就不会来。\n\n"
        "手机震动。匿名短信亮起，只有一行字：你们终于站到该站的位置上了。\n\n"
        "主角和同伴同时沉默，彼此第一次意识到他们都只是棋盘上的一枚子。\n\n"
        "...\n"
    )

    return {
        "ok": True,
        "draft_result": {
            "script_title": f"Demo Script Draft v1（{logline_title} / {mode_title}）",
            "script_text": script_text,
            "action_appendix": [
                {
                    "title": "仓库伏击",
                    "spatial_relation": "上下层夹击，主角被迫转入狭窄通道",
                    "rhythm_layer": "先潜行后爆发再短暂停顿",
                    "climax_point": "主角误以为拿到证据，实际暴露同伴位置",
                    "cost_point": "信任关系被永久撕裂",
                },
                {
                    "title": "天桥对峙",
                    "spatial_relation": "高差与开放空间让角色无法隐藏情绪",
                    "rhythm_layer": "缓慢试探到突然摊牌",
                    "climax_point": "匿名短信让第三方威胁显形",
                    "cost_point": "双方不再可能回到过去",
                },
            ],
            "dialogue_stats": [
                {"character": "主角", "line_ratio": "38%"},
                {"character": "对立面", "line_ratio": "27%"},
                {"character": "同伴", "line_ratio": "18%"},
                {"character": "其他", "line_ratio": "17%"},
            ],
            "soft_alignment_summary": {
                "best_matching_sections": [
                    f"仓库潜入段落较符合你偏好的悬疑压迫感（写作取向：{writing_hint}）",
                    "天桥对峙段落较符合你偏好的关系张力",
                ],
                "deviation_notes": [
                    f"对白直给程度略高于当前设定的对白密度倾向（{dialogue_hint}）",
                    f"中段动作占比略高于当前强度预期（{rating_hint}）",
                ],
                "optional_fixes": [
                    "减少设定解释型对白，改为动作或环境信息传达",
                    "将一个动作段落压缩为关系冲突场景",
                ],
            },
        },
    }


def build_review_payload(
    *,
    selected_logline_index: int,
    selected_mode_index: int,
    review_dimensions: list[str],
    rewrite_preference: str,
) -> dict:
    logline_title = _logline_title(selected_logline_index)
    mode_title = _mode_title(selected_mode_index)
    dimensions_hint = "、".join(review_dimensions) if review_dimensions else "未指定维度"
    rewrite_hint = rewrite_preference or "未指定（假响应）"

    return {
        "ok": True,
        "review_result": {
            "issues": [
                {
                    "id": "issue_1",
                    "severity": "致命",
                    "title": "中段目标发生漂移",
                    "evidence": f"基于{logline_title}/{mode_title}的一稿中，第 2 幕主角行动从“证明真相”偏移到“逃离追捕”，主线动机承接不足。",
                },
                {
                    "id": "issue_2",
                    "severity": "重要",
                    "title": "对立面的施压方式重复",
                    "evidence": f"在当前评审维度（{dimensions_hint}）下，两次关键冲突都依赖同类威胁，缺少层次升级。",
                },
                {
                    "id": "issue_3",
                    "severity": "可优化",
                    "title": "部分对白过于解释性",
                    "evidence": f"仓库段落中存在直接说明背景信息的台词（修改偏好：{rewrite_hint}）。",
                },
            ],
            "fix_options": [
                {
                    "issue_id": "issue_1",
                    "options": [
                        "在中段增加一个迫使主角回到原始目标的事件节点",
                        "把逃离追捕改写为获取真相过程中的副作用",
                        "让同伴的行动反向提醒主角真正代价",
                    ],
                },
                {
                    "issue_id": "issue_2",
                    "options": [
                        "第二次施压改为情感勒索而非物理威胁",
                        "让对立面的权力来源发生变化",
                        "引入第三方压力打破重复节奏",
                    ],
                },
            ],
            "task_sheet": [
                {
                    "task_id": "task_1",
                    "issue_id": "issue_1",
                    "label": "修复中段主线漂移",
                    "default_action": "accept",
                },
                {
                    "task_id": "task_2",
                    "issue_id": "issue_2",
                    "label": "增强对立面施压层次",
                    "default_action": "accept",
                },
                {
                    "task_id": "task_3",
                    "issue_id": "issue_3",
                    "label": "压缩解释性对白",
                    "default_action": "ignore",
                },
            ],
            "change_impact": [
                {
                    "scope": "第二幕中段",
                    "affected_scenes": ["S12", "S13", "S14"],
                    "note": "会影响主角目标线与同伴关系线",
                },
                {
                    "scope": "仓库对峙段落",
                    "affected_scenes": ["S08"],
                    "note": "主要影响对白密度与信息呈现方式",
                },
            ],
            "hard_soft_report": {
                "hard": [
                    {
                        "type": "因果链",
                        "status": "提示",
                        "evidence": "部分转折依赖外部推力，主角主动性不足。",
                    },
                    {
                        "type": "动机闭环",
                        "status": "通过",
                        "evidence": "主角的核心恐惧与目标仍可追踪。",
                    },
                ],
                "soft": [
                    {
                        "type": "审美对齐",
                        "status": "部分一致",
                        "evidence": "氛围已接近冷峻，但对白仍偏直给。",
                    },
                    {
                        "type": "节奏观感",
                        "status": "提示",
                        "evidence": "中段有轻微拖沓感。",
                    },
                ],
            },
        },
    }


def build_rewrite_payload(
    *,
    selected_logline_index: int,
    selected_mode_index: int,
    accepted_tasks: list[dict[str, str]],
    rewrite_scope: str,
    strengthen_metrics: str,
) -> dict:
    logline_title = _logline_title(selected_logline_index)
    mode_title = _mode_title(selected_mode_index)
    accepted_count = len([t for t in accepted_tasks if t.get("task_id")])
    accepted_hint = "、".join(f'{t["task_id"]}:{t["action"]}' for t in accepted_tasks if t.get("task_id")) or "无"
    scope_hint = rewrite_scope or "未指定范围（假响应）"
    metric_hint = strengthen_metrics or "未指定指标（假响应）"

    script_text = (
        "FADE IN:\n\n"
        "INT. 旧仓库 - 夜\n"
        "主角这次没有直接闯入，而是先确认同伴是否已暴露位置。手电被压低，只扫过出口和高处掩体。\n\n"
        "主角\n"
        "如果你真的来过这里，就不会把出口留给我。\n\n"
        "对立面（画外）\n"
        "你终于开始问对问题了。\n\n"
        "主角没有立刻追击，而是先折返去确认讯号来源，迫使行动重新围绕“真相”推进。\n\n"
        "CUT TO:\n\n"
        "EXT. 天桥 - 凌晨\n"
        "同伴没有解释，只把手机递给主角。匿名短信的时间戳早于仓库行动，说明他们一直被提前布局。\n\n"
        "主角\n"
        "那就别再证明你站哪边了。证明谁在写我们的结局。\n\n"
        "...\n"
    )

    return {
        "ok": True,
        "rewrite_result": {
            "draft_version": "Draft v2",
            "script_title": f"Demo Script Draft v2（{logline_title} / {mode_title}）",
            "script_text": script_text,
            "change_log": [
                {
                    "scope": "第二幕中段",
                    "changed_scenes": ["S12", "S13", "S14"],
                    "reason": f"修复主线漂移，让主角重新围绕真相推进（采纳任务数：{accepted_count}）。",
                },
                {
                    "scope": "仓库对峙段落",
                    "changed_scenes": ["S08"],
                    "reason": f"减少解释性对白，改用动作和空间关系传达信息（重写范围：{scope_hint}）。",
                },
            ],
            "regression_check": [
                {
                    "type": "主线目标一致性",
                    "status": "通过",
                    "note": "主角的动机链路仍然完整。",
                },
                {
                    "type": "对立面施压层次",
                    "status": "提示",
                    "note": f"仍有一个施压动作与前文略重复（强化指标参考：{metric_hint}）。",
                },
            ],
            "creative_alignment_check": {
                "status": "部分一致",
                "matched": [
                    "中段整体更贴近冷峻悬疑取向",
                    "对白更克制，接近电影感目标",
                ],
                "deviations": [
                    "动作段落仍略高于‘人物关系优先’偏好",
                ],
                "fix_paths": [
                    f"路径A：继续压缩一段追逐戏，换成关系冲突场（任务单：{accepted_hint}）",
                    "路径B：保留动作段落，但降低解释性台词密度",
                ],
            },
        },
    }


def build_deliverables_payload(
    *,
    selected_version: str,
    asset_filter: str,
    export_format: str,
    export_items: list[str],
) -> dict:
    version_hint = selected_version or "Draft v2"
    filter_hint = asset_filter or "全部"
    format_hint = export_format or "PDF"
    items_hint = export_items or ["剧本", "分场表", "评审报告"]
    items_text = "、".join(items_hint)

    return {
        "ok": True,
        "deliverables_result": {
            "asset_overview": [
                {"type": "剧本", "count": 3},
                {"type": "结构", "count": 2},
                {"type": "场次", "count": 1},
                {"type": "评审", "count": 2},
                {"type": "归档", "count": 1},
            ],
            "version_assets": [
                {
                    "version": "Draft v1",
                    "assets": ["剧本 Draft v1", "结构蓝图 v1", "分场表 v1"],
                },
                {
                    "version": "Draft v2",
                    "assets": ["剧本 Draft v2", "评审报告 v1", "改稿日志 v2", "归档快照"],
                },
            ],
            "export_bundle_preview": {
                "selected_version": version_hint,
                "export_format": format_hint,
                "items": items_hint,
                "summary": f"将导出 {version_hint} 相关 {items_text} 的 {format_hint} 打包（资产筛选：{filter_hint}）。",
            },
            "download_items": [
                {
                    "label": "Draft_v2_script.pdf",
                    "kind": "script",
                    "status": "ready",
                },
                {
                    "label": "Draft_v2_scene_list.csv",
                    "kind": "scene_list",
                    "status": "ready",
                },
                {
                    "label": "Draft_v2_review_report.pdf",
                    "kind": "review",
                    "status": "ready",
                },
            ],
            "archive_snapshot": {
                "mode_constitution": "模式B：以关系反噬驱动悬疑推进，反套路承诺是让反转来自代价而非身份揭露。",
                "creative_panel_summary": [
                    "主题问题：信任在记忆不可靠时如何成立？",
                    "避雷：避免强行解释、避免失忆式偷懒反转",
                    "必须保留：冷峻克制感与结尾余味",
                    "整体更：更电影感、更少直白台词",
                ],
                "current_version": version_hint,
            },
        },
    }
