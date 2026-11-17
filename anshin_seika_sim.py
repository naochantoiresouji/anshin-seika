"""
あんしん正価モデル 経済検証シミュレーション（v1.0）
単発の抽選販売イベントにおける一般消費者と大量応募を行う転売業者の期待収益（ROI）比較モデル
"""

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

# ==========================================
# 出力切り替えスイッチ（デフォルト: False）
# True にすると、標準出力と同じ内容を同フォルダ内の result.md に出力する
# ==========================================
EXPORT_RESULT_MD: bool = False
RESULT_MD_FILENAME: str = "result.md"


@dataclass
class SimulationConfig:
    """シミュレーション入力パラメータ"""
    face_value: int = 10000            # チケット1枚あたりの定価（円）
    resale_price: int = 30000          # 二次流通市場での想定転売価格（円）
    resale_fee_rate: float = 0.10      # 転売プラットフォーム手数料率（0.0 <= rate < 1.0）
    token_fee: int = 200               # 1口応募あたりのZKPトークン発行手数料（円・返金不可）
    win_rate: float = 0.20             # 1口あたりの当選確率（0.0 < rate <= 1.0）
    self_quota: int = 2                # 自前・家族等で無料調達できる上限口数
    id_procurement_cost: int = 3000    # 自前枠を超えた1口あたりの名義借り・認証代行コスト（円）
    application_counts: List[int] = field(default_factory=lambda: [1, 2, 10, 50, 100])
    export_md: bool = EXPORT_RESULT_MD # result.md へのファイル出力フラグ

    def validate(self) -> None:
        """エッジケースおよび入力制約のバリデーション"""
        if self.face_value < 0:
            raise ValueError("チケット定価（face_value）は0以上で指定してください。")
        if self.resale_price < 0:
            raise ValueError("想定転売価格（resale_price）は0以上で指定してください。")
        if not (0.0 <= self.resale_fee_rate < 1.0):
            raise ValueError("手数料率（resale_fee_rate）は 0.0 以上 1.0 未満の値で指定してください。")
        if self.token_fee < 0:
            raise ValueError("トークン発行手数料（token_fee）は0以上で指定してください。")
        if not (0.0 < self.win_rate <= 1.0):
            raise ValueError("当選確率（win_rate）は 0 より大きく 1.0 以下の値で指定してください。")
        if self.self_quota < 0:
            raise ValueError("自前枠上限（self_quota）は0以上で指定してください。")
        if self.id_procurement_cost < 0:
            raise ValueError("名義調達コスト（id_procurement_cost）は0以上で指定してください。")
        if not self.application_counts or any(n <= 0 for n in self.application_counts):
            raise ValueError("応募口数（application_counts）は1以上の整数リストで指定してください。")


def calculate_scenario(n: int, config: SimulationConfig) -> Dict[str, Any]:
    """指定された応募口数 N に対する期待値計算を実行する"""
    # 3.1. 応募段階の確定コスト（サンクコスト）
    c_token = n * config.token_fee
    c_id = max(0, n - config.self_quota) * config.id_procurement_cost
    c_entry = c_token + c_id

    # 3.2. 当選時の期待値計算（期待当選枚数は切り捨てず浮動小数点で保持）
    e_wins = n * config.win_rate
    c_ticket = e_wins * config.face_value
    c_total = c_entry + c_ticket

    # 3.3. 収益とROI（転売業者視点）
    r_unit = config.resale_price * (1.0 - config.resale_fee_rate)
    r_total = e_wins * r_unit
    profit = r_total - c_total

    # 総投資コスト0円（無料チケットかつ手数料0円）のゼロ除算回避
    if c_total == 0:
        roi_str = "N/A (0.0%)"
    else:
        roi = (profit / c_total) * 100.0
        roi_str = f"{roi:+.1f} %"

    # 損益分岐点となる最低転売価格
    p_breakeven = (config.face_value + (c_entry / e_wins)) / (1.0 - config.resale_fee_rate)

    return {
        "n": n,
        "e_wins": e_wins,
        "c_token": c_token,
        "c_id": c_id,
        "c_entry": c_entry,
        "c_total": c_total,
        "profit": profit,
        "roi_str": roi_str,
        "p_breakeven": p_breakeven,
    }


def format_simulation_report(config: SimulationConfig) -> str:
    """シミュレーションを実行し、Markdown形式のレポート文字列を生成する"""
    config.validate()

    # 現行システム（追加コスト0円）での1枚あたり転売粗利
    legacy_unit_profit = config.resale_price * (1.0 - config.resale_fee_rate) - config.face_value

    lines: List[str] = [
        "### 1. 前提条件サマリー",
        f"- **チケット定価**: {config.face_value:,} 円",
        f"- **想定転売価格**: {config.resale_price:,} 円（プラットフォーム手数料率: {config.resale_fee_rate * 100:.1f}%）",
        f"- **当選確率**: {config.win_rate * 100:.1f}%（実質倍率: {1.0 / config.win_rate:.1f} 倍）",
        f"- **ZKPトークン発行料（返金不可）**: {config.token_fee:,} 円 / 口",
        f"- **自前枠（名義調達コスト0円）**: {config.self_quota} 口まで",
        f"- **名義調達コスト（自前枠超過分）**: {config.id_procurement_cost:,} 円 / 口",
        f"- **【参考】現行制度（対策なし）での1枚あたり転売粗利**: {legacy_unit_profit:,.0f} 円",
        "",
        "### 2. 応募口数（プレイヤー規模）別の期待値シミュレーション結果",
        "",
    ]

    headers = [
        "応募口数 (N)",
        "期待当選数",
        "応募時確定コスト (トークン + 名義調達)",
        "総投資コスト期待値",
        "期待純利益",
        "期待ROI",
        "損益分岐転売価格",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join([":---"] + ["---:"] * (len(headers) - 1)) + " |")

    for n in config.application_counts:
        res = calculate_scenario(n, config)
        profit_val = res["profit"]
        profit_str = f"**{profit_val:+,.0f} 円 (赤字)**" if profit_val < 0 else f"{profit_val:+,.0f} 円"
        entry_detail = f"{res['c_entry']:,} 円 ({res['c_token']:,} + {res['c_id']:,})"

        row = [
            f"{res['n']:,} 口",
            f"{res['e_wins']:.1f} 枚",
            entry_detail,
            f"{res['c_total']:,.0f} 円",
            profit_str,
            res["roi_str"],
            f"{res['p_breakeven']:,.0f} 円",
        ]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def run_simulation(config: SimulationConfig) -> None:
    """シミュレーションを実行し、標準出力（および設定に応じて result.md）に出力する"""
    report_text = format_simulation_report(config)
    print(report_text)

    if config.export_md:
        output_path = Path(__file__).resolve().parent / RESULT_MD_FILENAME
        output_path.write_text(report_text + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """CLI引数パーサーを構築する"""
    defaults = SimulationConfig()
    parser = argparse.ArgumentParser(
        description="あんしん正価モデル 経済検証シミュレーション（v1.0）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--face-value",
        type=int,
        default=defaults.face_value,
        help="チケット1枚あたりの定価（円）",
    )
    parser.add_argument(
        "--resale-price",
        type=int,
        default=defaults.resale_price,
        help="二次流通市場での想定転売価格（円）",
    )
    parser.add_argument(
        "--resale-fee-rate",
        type=float,
        default=defaults.resale_fee_rate,
        help="転売プラットフォーム手数料率（0.0 以上 1.0 未満）",
    )
    parser.add_argument(
        "--token-fee",
        type=int,
        default=defaults.token_fee,
        help="1口応募あたりのZKPトークン発行手数料（円・返金不可）",
    )
    parser.add_argument(
        "--win-rate",
        type=float,
        default=defaults.win_rate,
        help="1口あたりの当選確率（0.0 より大きく 1.0 以下）",
    )
    parser.add_argument(
        "--self-quota",
        type=int,
        default=defaults.self_quota,
        help="自前・家族等で無料調達できる上限口数",
    )
    parser.add_argument(
        "--id-procurement-cost",
        "--id-cost",
        dest="id_procurement_cost",
        type=int,
        default=defaults.id_procurement_cost,
        help="自前枠を超えた1口あたりの名義借り・認証代行コスト（円）",
    )
    parser.add_argument(
        "--application-counts",
        "--counts",
        dest="application_counts",
        type=int,
        nargs="+",
        default=defaults.application_counts,
        help="シミュレーションを実行する応募口数のリスト（スペース区切り）",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = SimulationConfig(
        face_value=args.face_value,
        resale_price=args.resale_price,
        resale_fee_rate=args.resale_fee_rate,
        token_fee=args.token_fee,
        win_rate=args.win_rate,
        self_quota=args.self_quota,
        id_procurement_cost=args.id_procurement_cost,
        application_counts=args.application_counts,
    )
    try:
        run_simulation(config)
    except ValueError as e:
        parser.error(str(e))


if __name__ == "__main__":
    main()