from __future__ import annotations

from pathlib import Path
import json


ROOT = Path("/www/wwwroot/QuantBot")
DOCS = ROOT / "docs" / "model_catalog"
REPORTS = ROOT / "data" / "reports"

DOCS.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)


MODELS = [
    # ============================================================
    # 已有 QuantBot 模型
    # ============================================================

    {
        "id": "QB-TREND-001",
        "name": "趋势突破",
        "category": "趋势/突破",
        "source": ["QuantBot现有模型", "经典趋势跟随"],
        "evidence": "A",
        "status": "已验证",
        "implementation": "quantbot.strategies.models.trend_breakout",
        "notes": "已完成 TRAIN / VALIDATION / OOS；目前属于正式研究候选。",
    },
    {
        "id": "QB-TREND-002",
        "name": "趋势回调",
        "category": "趋势",
        "source": ["QuantBot现有模型", "经典趋势跟随"],
        "evidence": "A",
        "status": "已验证",
        "implementation": "quantbot.strategies.models.trend_pullback",
        "notes": "已完成 TRAIN / VALIDATION / OOS；不同资产表现差异较大。",
    },
    {
        "id": "QB-VOL-001",
        "name": "波动率突破",
        "category": "波动率/突破",
        "source": ["QuantBot现有模型", "经典波动率突破"],
        "evidence": "A",
        "status": "已验证",
        "implementation": "quantbot.strategies.models.volatility_breakout",
        "notes": "已完成 TRAIN / VALIDATION / OOS。",
    },
    {
        "id": "QB-MR-001",
        "name": "均值回归",
        "category": "反转/均值回归",
        "source": ["QuantBot现有模型", "经典统计模型"],
        "evidence": "A",
        "status": "已验证-暂不推荐",
        "implementation": "quantbot.strategies.models.mean_reversion",
        "notes": "当前多资产 OOS 表现整体较差，暂不删除，保留作为对照。",
    },

    # ============================================================
    # 经典量化研究优先候选
    # ============================================================

    {
        "id": "RS-TREND-001",
        "name": "时间序列动量",
        "category": "趋势/动量",
        "source": ["经典量化研究"],
        "evidence": "S",
        "status": "候选",
        "implementation": "待实现",
        "notes": "优先级最高。与现有趋势突破形成独立模型族。",
    },
    {
        "id": "RS-TREND-002",
        "name": "多周期趋势跟随",
        "category": "趋势",
        "source": ["经典量化研究"],
        "evidence": "S",
        "status": "候选",
        "implementation": "待实现",
        "notes": "测试 1H 信号结合 4H / 1D 环境确认。",
    },
    {
        "id": "RS-MOM-001",
        "name": "价格动量",
        "category": "动量",
        "source": ["经典量化研究"],
        "evidence": "S",
        "status": "候选",
        "implementation": "待实现",
        "notes": "以过去 N 根收益率作为核心变量。",
    },
    {
        "id": "RS-MOM-002",
        "name": "多周期动量",
        "category": "动量",
        "source": ["经典量化研究"],
        "evidence": "A",
        "status": "候选",
        "implementation": "待实现",
        "notes": "同时观察短、中、长周期动量方向。",
    },
    {
        "id": "RS-REV-001",
        "name": "短周期价格反转",
        "category": "反转",
        "source": ["经典量化研究"],
        "evidence": "A",
        "status": "候选",
        "implementation": "待实现",
        "notes": "与当前均值回归模型分开，避免把所有反转模型混为一谈。",
    },
    {
        "id": "RS-VOL-001",
        "name": "波动率压缩后扩张",
        "category": "波动率",
        "source": ["经典技术/量化模型"],
        "evidence": "A",
        "status": "候选",
        "implementation": "待实现",
        "notes": "研究低波动压缩后的方向性扩张。",
    },
    {
        "id": "RS-VOL-002",
        "name": "ATR 波动状态突破",
        "category": "波动率/突破",
        "source": ["经典技术/量化模型"],
        "evidence": "A",
        "status": "候选",
        "implementation": "待实现",
        "notes": "重点研究 ATR 扩张是否提供有效交易过滤。",
    },

    # ============================================================
    # ABU 模型来源
    # ============================================================

    {
        "id": "ABU-BRK-001",
        "name": "唐奇安通道突破",
        "category": "突破",
        "source": ["ABU候选体系", "经典突破模型"],
        "evidence": "A",
        "status": "候选",
        "implementation": "待实现",
        "notes": "与当前趋势突破区别：独立测试通道突破逻辑。",
    },
    {
        "id": "ABU-BRK-002",
        "name": "趋势线突破",
        "category": "趋势/突破",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "ABU 明确存在趋势线突破模型。",
    },
    {
        "id": "ABU-STR-001",
        "name": "支撑阻力突破",
        "category": "结构/突破",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "必须严格定义支撑阻力形成时间，避免未来数据。",
    },
    {
        "id": "ABU-STR-002",
        "name": "支撑阻力反弹",
        "category": "结构/反转",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "测试结构位附近反转，而不是简单价格触碰。",
    },
    {
        "id": "ABU-MA-001",
        "name": "均线趋势",
        "category": "趋势/均线",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "先做简单版本，不直接复制大量均线组合。",
    },
    {
        "id": "ABU-MA-002",
        "name": "均线交叉",
        "category": "趋势/均线",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "短均线上穿/下穿长均线。",
    },
    {
        "id": "ABU-KLINE-001",
        "name": "Pin Bar 反转",
        "category": "K线形态",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "必须加入趋势环境过滤，不单独假设形态有效。",
    },
    {
        "id": "ABU-KLINE-002",
        "name": "吞没形态",
        "category": "K线形态",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "测试阳包阴/阴包阳。",
    },
    {
        "id": "ABU-KLINE-003",
        "name": "双针探底",
        "category": "K线形态",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "作为底部反转形态候选。",
    },
    {
        "id": "ABU-KLINE-004",
        "name": "早晨之星/黄昏之星",
        "category": "K线形态",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "一组模型，分别测试看涨和看跌。",
    },
    {
        "id": "ABU-KLINE-005",
        "name": "多方炮/空方炮",
        "category": "K线形态",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "测试多根K线组合后的方向性突破。",
    },
    {
        "id": "ABU-PAT-001",
        "name": "上升三角突破",
        "category": "价格形态/突破",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "重点是形态识别必须只使用 T 之前信息。",
    },
    {
        "id": "ABU-PAT-002",
        "name": "下降三角突破",
        "category": "价格形态/突破",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "与上升三角形成对称模型。",
    },
    {
        "id": "ABU-PAT-003",
        "name": "头肩顶/头肩底",
        "category": "价格形态/反转",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "必须研究确认点，不能使用未来确认数据提前交易。",
    },
    {
        "id": "ABU-PAT-004",
        "name": "双顶/双底",
        "category": "价格形态/反转",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "重点测试确认突破后的交易，而不是预测第二个顶/底。",
    },
    {
        "id": "ABU-PAT-005",
        "name": "旗形突破",
        "category": "价格形态/突破",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "适合与趋势环境组合测试。",
    },
    {
        "id": "ABU-PAT-006",
        "name": "楔形突破",
        "category": "价格形态/突破",
        "source": ["ABU"],
        "evidence": "B",
        "status": "候选",
        "implementation": "待实现",
        "notes": "区分上升楔形与下降楔形。",
    },
    {
        "id": "ABU-WAVE-001",
        "name": "波浪回调反转",
        "category": "价格结构",
        "source": ["ABU"],
        "evidence": "C",
        "status": "候选-后置",
        "implementation": "待实现",
        "notes": "定义主观性较强，暂不作为第一批核心模型。",
    },
    {
        "id": "ABU-HARM-001",
        "name": "谐波形态",
        "category": "价格结构",
        "source": ["ABU"],
        "evidence": "C",
        "status": "候选-后置",
        "implementation": "待实现",
        "notes": "先不进入第一批自动化验证，避免模型复杂度过高。",
    },
    {
        "id": "ABU-CHAN-001",
        "name": "缠论结构",
        "category": "价格结构",
        "source": ["ABU"],
        "evidence": "C",
        "status": "候选-后置",
        "implementation": "待实现",
        "notes": "定义复杂且主观性较高，必须先建立严格机器定义。",
    },

    # ============================================================
    # 市场环境模型
    # ============================================================

    {
        "id": "REGIME-001",
        "name": "趋势/震荡状态识别",
        "category": "市场环境",
        "source": ["QuantBot原始大纲", "经典市场状态模型"],
        "evidence": "A",
        "status": "基础设施候选",
        "implementation": "待实现",
        "notes": "不是直接交易模型，而是未来模型选择器。",
    },
    {
        "id": "REGIME-002",
        "name": "高波动/低波动状态识别",
        "category": "市场环境",
        "source": ["QuantBot原始大纲", "经典波动率模型"],
        "evidence": "A",
        "status": "基础设施候选",
        "implementation": "待实现",
        "notes": "用于决定突破、趋势、反转模型是否允许工作。",
    },
    {
        "id": "REGIME-003",
        "name": "BTC 市场环境过滤",
        "category": "市场环境",
        "source": ["QuantBot原始大纲"],
        "evidence": "A",
        "status": "基础设施候选",
        "implementation": "待实现",
        "notes": "利用 BTC 环境作为山寨币交易过滤器。",
    },
]


def build_markdown() -> str:
    lines = []

    lines.append("# QuantBot 模型候选库")
    lines.append("")
    lines.append("版本：Phase 2.3.5 / V1.0")
    lines.append("")
    lines.append(
        "本目录用于记录 QuantBot 的模型来源、研究依据、实现状态和验证状态。"
    )
    lines.append("")
    lines.append("## 模型准入原则")
    lines.append("")
    lines.append("1. 候选模型不代表有效模型。")
    lines.append("2. 有论文或成熟系统实现，不代表在 QuantBot 的 BTC/ETH 等 1H 永续数据上有效。")
    lines.append("3. 所有模型必须经过统一 TRAIN → VALIDATION → 冻结 → OOS 流程。")
    lines.append("4. 禁止使用 OOS 结果反向选择模型。")
    lines.append("5. 禁止只按照收益率最高选择模型。")
    lines.append("6. 必须考虑最大回撤、盈利因子、交易次数、稳定性和成本敏感性。")
    lines.append("7. 形态模型必须严格证明不存在未来数据。")
    lines.append("")
    lines.append("## 证据等级")
    lines.append("")
    lines.append("| 等级 | 含义 |")
    lines.append("|---|---|")
    lines.append("| S | 有成熟量化研究依据，且适合作为核心研究方向 |")
    lines.append("| A | 有较强研究/工程依据，值得优先测试 |")
    lines.append("| B | ABU 等成熟系统已有实际实现，值得独立验证 |")
    lines.append("| C | 复杂/主观/实验性较强，暂后置 |")
    lines.append("")
    lines.append("## 模型清单")
    lines.append("")
    lines.append("| ID | 模型 | 类别 | 来源 | 证据 | 状态 | 实现 |")
    lines.append("|---|---|---|---|---|---|---|")

    for m in MODELS:
        source = "；".join(m["source"])
        lines.append(
            f"| {m['id']} | {m['name']} | {m['category']} | "
            f"{source} | {m['evidence']} | {m['status']} | "
            f"{m['implementation']} |"
        )

    lines.append("")
    lines.append("## 当前优先级")
    lines.append("")
    lines.append("第一批优先实现：")
    lines.append("")
    lines.append("- 时间序列动量")
    lines.append("- 多周期趋势跟随")
    lines.append("- 价格动量")
    lines.append("- 多周期动量")
    lines.append("- 唐奇安通道突破")
    lines.append("- 趋势线突破")
    lines.append("- 支撑阻力突破")
    lines.append("- 波动率压缩后扩张")
    lines.append("- ATR 波动状态突破")
    lines.append("")
    lines.append("第二批：")
    lines.append("")
    lines.append("- 均线趋势")
    lines.append("- 均线交叉")
    lines.append("- Pin Bar")
    lines.append("- 吞没形态")
    lines.append("- 双针探底")
    lines.append("- 三角形突破")
    lines.append("- 双顶/双底")
    lines.append("- 旗形突破")
    lines.append("- 楔形突破")
    lines.append("")
    lines.append("第三批：")
    lines.append("")
    lines.append("- 波浪")
    lines.append("- 谐波")
    lines.append("- 缠论")
    lines.append("")
    lines.append("## 重要说明")
    lines.append("")
    lines.append(
        "ABU 主要作为候选模型来源和工程思想参考；最终是否有效，以 QuantBot 自己的严格样本外验证为准。"
    )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    md = build_markdown()

    md_path = DOCS / "MODEL_CATALOG_PHASE2_3_5_V1.0.md"
    json_path = REPORTS / "phase2_3_5_model_catalog.json"

    md_path.write_text(md, encoding="utf-8")

    payload = {
        "phase": "2.3.5",
        "version": "1.0",
        "total_models": len(MODELS),
        "models": MODELS,
    }

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 72)
    print("QuantBot Phase 2.3.5 模型候选库")
    print("=" * 72)
    print(f"模型数量: {len(MODELS)}")
    print(f"目录文件: {md_path}")
    print(f"JSON文件: {json_path}")
    print("状态:      OK")


if __name__ == "__main__":
    main()
