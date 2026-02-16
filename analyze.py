#!/usr/bin/env python3
"""
Polymarket CSV analysis for 5/15 minute cycles with strategy-level estimation.
"""

import argparse
import glob
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


YES_THRESHOLD = 0.99
NO_THRESHOLD = 0.01
INVALID_RATE_LIMIT = 0.05


def safe_percentile(values: List[float], q: float) -> Optional[float]:
    if len(values) < 5:
        return None
    return float(np.percentile(values, q))


def price_clamp(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return float(min(max(value, 0.0), 1.0))


def format_price(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4f}"


def classify_cycle(start_time: datetime) -> str:
    if start_time.weekday() >= 5:
        return "weekend"
    hour = start_time.hour
    if hour >= 20 or hour < 8:
        return "weekday_high"
    return "weekday_low"


def find_csv_files(date: Optional[str] = None) -> List[str]:
    patterns = [
        "BTC5MIN_*.csv",
        "BTC_*.csv",
        "BTC1MIN_*.csv",
        "BTC10MIN_*.csv",
        "BTC30MIN_*.csv",
    ]
    all_files: List[str] = []
    for pattern in patterns:
        all_files.extend(glob.glob(pattern))
    all_files = sorted(set(all_files))
    if date:
        all_files = [f for f in all_files if date in f]
    return all_files


class CycleAnalyzer:
    def __init__(self, file_path: str, interval_minutes: int):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.interval_minutes = interval_minutes
        self.df: Optional[pd.DataFrame] = None
        self.cycles: List[Dict] = []
        self.invalid_cycles: List[Dict] = []

    def load_data(self) -> bool:
        try:
            df = pd.read_csv(self.file_path, dtype=str)
            if "time" not in df.columns or "price" not in df.columns:
                print("错误: CSV 必须包含 'time' 和 'price' 列")
                return False

            df["time"] = pd.to_datetime(df["time"], errors="coerce")
            df["price_raw"] = df["price"]
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)

            if len(df) == 0:
                print("错误: 没有有效的时间数据")
                return False

            self.df = df
            return True
        except Exception as exc:
            print(f"加载文件失败: {exc}")
            return False

    def build_cycles(self) -> None:
        if self.df is None or len(self.df) == 0:
            return

        df = self.df.set_index("time")
        freq = f"{self.interval_minutes}min"
        grouped = df.groupby(pd.Grouper(freq=freq, origin="start_day"))

        for start_time, group in grouped:
            if group.empty:
                continue

            expected_points = self.interval_minutes * 60
            unique_seconds = group.index.floor("s").nunique()
            invalid_rows = int(group["price"].isna().sum())
            missing_seconds = max(0, expected_points - unique_seconds)
            invalid_rate = (invalid_rows + missing_seconds) / expected_points

            cycle_info = {
                "start_time": start_time,
                "end_time": start_time + pd.Timedelta(minutes=self.interval_minutes),
                "expected_points": expected_points,
                "unique_seconds": unique_seconds,
                "invalid_rows": invalid_rows,
                "missing_seconds": missing_seconds,
                "invalid_rate": invalid_rate,
            }

            if invalid_rate > INVALID_RATE_LIMIT:
                self.invalid_cycles.append(cycle_info)
                continue

            valid_prices = group.dropna(subset=["price"]).sort_index()
            if len(valid_prices) < 2:
                self.invalid_cycles.append(cycle_info)
                continue

            prices = valid_prices["price"].to_numpy(dtype=float)
            times = valid_prices.index.to_pydatetime()
            start_price = float(prices[0])
            end_price = float(prices[-1])
            max_price = float(np.max(prices))
            min_price = float(np.min(prices))

            if end_price >= YES_THRESHOLD:
                outcome = "YES"
            elif end_price <= NO_THRESHOLD:
                outcome = "NO"
            else:
                outcome = "UNDETERMINED"

            self.cycles.append(
                {
                    **cycle_info,
                    "start_price": start_price,
                    "end_price": end_price,
                    "max_price": max_price,
                    "min_price": min_price,
                    "outcome": outcome,
                    "prices": prices,
                    "times": times,
                }
            )

    def _slippage_stats(self, cycles: List[Dict]) -> Dict[str, Optional[float]]:
        deltas: List[float] = []
        for cycle in cycles:
            prices = cycle["prices"]
            if len(prices) < 2:
                continue
            deltas.extend(np.abs(np.diff(prices)).tolist())
        if len(deltas) < 5:
            return {"median": None, "p90": None}
        return {
            "median": float(np.percentile(deltas, 50)),
            "p90": float(np.percentile(deltas, 90)),
        }

    def _extract_level_features(self, cycles: List[Dict]) -> Dict[str, List[float]]:
        features: Dict[str, List[float]] = {
            "min_before_max": [],
            "max_after_min": [],
            "min_after_rebound": [],
            "max_after_pullback": [],
            "min_after_first_dip": [],
            "max_after_deeper": [],
            "min_after_F": [],
            "max_after_G": [],
            "max_before_first_dip": [],
            "min_after_early_high": [],
        }

        for cycle in cycles:
            prices = cycle["prices"]
            if len(prices) < 5:
                continue

            idx_max = int(np.argmax(prices))
            idx_min = int(np.argmin(prices))

            min_before_max = float(np.min(prices[: idx_max + 1]))
            idx_min_before_max = int(np.argmin(prices[: idx_max + 1]))
            max_after_min = float(np.max(prices[idx_min_before_max:]))
            idx_max_after_min = (
                int(np.argmax(prices[idx_min_before_max:])) + idx_min_before_max
            )

            if idx_max_after_min < len(prices) - 1:
                min_after_rebound = float(np.min(prices[idx_max_after_min:]))
                idx_min_after_rebound = (
                    int(np.argmin(prices[idx_max_after_min:])) + idx_max_after_min
                )
            else:
                min_after_rebound = float(prices[-1])
                idx_min_after_rebound = len(prices) - 1

            if idx_min_after_rebound < len(prices) - 1:
                max_after_pullback = float(np.max(prices[idx_min_after_rebound:]))
            else:
                max_after_pullback = float(prices[-1])

            min_after_first_dip = float(np.min(prices[idx_min_before_max:]))
            idx_min_after_first_dip = (
                int(np.argmin(prices[idx_min_before_max:])) + idx_min_before_max
            )

            if idx_min_after_first_dip < len(prices) - 1:
                max_after_deeper = float(np.max(prices[idx_min_after_first_dip:]))
                idx_max_after_deeper = (
                    int(np.argmax(prices[idx_min_after_first_dip:]))
                    + idx_min_after_first_dip
                )
            else:
                max_after_deeper = float(prices[-1])
                idx_max_after_deeper = len(prices) - 1

            if idx_max_after_deeper < len(prices) - 1:
                min_after_F = float(np.min(prices[idx_max_after_deeper:]))
                idx_min_after_F = (
                    int(np.argmin(prices[idx_max_after_deeper:]))
                    + idx_max_after_deeper
                )
            else:
                min_after_F = float(prices[-1])
                idx_min_after_F = len(prices) - 1

            if idx_min_after_F < len(prices) - 1:
                max_after_G = float(np.max(prices[idx_min_after_F:]))
            else:
                max_after_G = float(prices[-1])

            start_price = float(prices[0])
            first_dip_idx = len(prices)
            for i, value in enumerate(prices):
                if value < start_price - 0.01:
                    first_dip_idx = i
                    break
            max_before_first_dip = float(np.max(prices[: max(first_dip_idx, 1)]))

            idx_max_before_dip = int(
                np.argmax(prices[: max(first_dip_idx, 1)])
            )
            if idx_max_before_dip < len(prices) - 1:
                min_after_early_high = float(np.min(prices[idx_max_before_dip:]))
            else:
                min_after_early_high = float(prices[-1])

            features["min_before_max"].append(min_before_max)
            features["max_after_min"].append(max_after_min)
            features["min_after_rebound"].append(min_after_rebound)
            features["max_after_pullback"].append(max_after_pullback)
            features["min_after_first_dip"].append(min_after_first_dip)
            features["max_after_deeper"].append(max_after_deeper)
            features["min_after_F"].append(min_after_F)
            features["max_after_G"].append(max_after_G)
            features["max_before_first_dip"].append(max_before_first_dip)
            features["min_after_early_high"].append(min_after_early_high)

        return features

    def _estimate_levels(self, cycles: List[Dict]) -> Dict[str, Optional[float]]:
        yes_cycles = [c for c in cycles if c["outcome"] == "YES"]
        if len(yes_cycles) < 5:
            return {key: None for key in list("ABCDEFGHIJK")}

        features = self._extract_level_features(yes_cycles)

        levels = {
            "A": safe_percentile(features["min_before_max"], 30),
            "B": safe_percentile(features["max_after_min"], 70),
            "C": safe_percentile(features["min_after_rebound"], 40),
            "D": safe_percentile(features["max_after_pullback"], 90),
            "E": safe_percentile(features["min_after_first_dip"], 15),
            "F": safe_percentile(features["max_after_deeper"], 65),
            "G": safe_percentile(features["min_after_F"], 35),
            "H": safe_percentile(features["max_after_G"], 90),
            "I": safe_percentile(features["min_after_first_dip"], 10),
            "J": safe_percentile(features["max_before_first_dip"], 65),
            "K": safe_percentile(features["min_after_early_high"], 20),
        }

        return {key: price_clamp(value) for key, value in levels.items()}

    def _simulate_case1(self, cycle: Dict, levels: Dict[str, float]) -> Tuple[Optional[float], Optional[int]]:
        prices = cycle["prices"]
        times = cycle["times"]
        if len(prices) < 2:
            return None, None

        A, B, C, D = levels["A"], levels["B"], levels["C"], levels["D"]
        if None in (A, B, C, D):
            return None, None

        entry_idx = None
        for i, price in enumerate(prices):
            if price <= A:
                entry_idx = i
                break
        if entry_idx is None:
            return None, None

        entry_price = prices[entry_idx]
        pnl = 0.0

        hit_B = None
        for i in range(entry_idx + 1, len(prices)):
            if prices[i] >= B:
                hit_B = i
                break

        if hit_B is None:
            pnl = (prices[-1] - entry_price)
            return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

        pnl += (B - entry_price) * 0.5
        remaining_entry = entry_price

        hit_C = None
        hit_one = None
        for i in range(hit_B + 1, len(prices)):
            if prices[i] >= 1.0:
                hit_one = i
                break
            if prices[i] <= C:
                hit_C = i
                break

        if hit_one is not None:
            pnl += (1.0 - remaining_entry) * 0.5
            return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

        if hit_C is None:
            pnl += (prices[-1] - remaining_entry) * 0.5
            return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

        pnl += (C - remaining_entry) * 0.5
        short_entry = C

        hit_D = None
        for i in range(hit_C + 1, len(prices)):
            if prices[i] >= D:
                hit_D = i
                break
        if hit_D is None:
            pnl += (short_entry - prices[-1])
        else:
            pnl += (short_entry - D)

        return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

    def _simulate_case2(self, cycle: Dict, levels: Dict[str, float]) -> Tuple[Optional[float], Optional[int]]:
        prices = cycle["prices"]
        times = cycle["times"]
        if len(prices) < 2:
            return None, None

        A, E, F, G, H, I = (
            levels["A"],
            levels["E"],
            levels["F"],
            levels["G"],
            levels["H"],
            levels["I"],
        )
        if None in (A, E, F, G, H, I):
            return None, None

        entry_idx = None
        for i, price in enumerate(prices):
            if price <= A:
                entry_idx = i
                break
        if entry_idx is None:
            return None, None

        entry_price = prices[entry_idx]
        size = 1.0
        avg_price = entry_price
        pnl = 0.0

        add_idx = None
        for i in range(entry_idx + 1, len(prices)):
            if prices[i] <= E:
                add_idx = i
                break
            if prices[i] >= F:
                add_idx = None
                break

        if add_idx is not None:
            avg_price = (avg_price * size + prices[add_idx]) / (size + 1.0)
            size += 1.0

        hit_F = None
        for i in range((add_idx or entry_idx) + 1, len(prices)):
            if prices[i] >= F:
                hit_F = i
                break
            if prices[i] <= I:
                pnl += (I - avg_price) * size
                return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

        if hit_F is None:
            pnl += (prices[-1] - avg_price) * size
            return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

        pnl += (F - avg_price) * 0.5 * size
        remaining_size = 0.5 * size

        hit_G = None
        hit_one = None
        for i in range(hit_F + 1, len(prices)):
            if prices[i] >= 1.0:
                hit_one = i
                break
            if prices[i] <= G:
                hit_G = i
                break

        if hit_one is not None:
            pnl += (1.0 - avg_price) * remaining_size
            return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

        if hit_G is None:
            pnl += (prices[-1] - avg_price) * remaining_size
            return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

        pnl += (G - avg_price) * remaining_size
        short_entry = G

        hit_H = None
        for i in range(hit_G + 1, len(prices)):
            if prices[i] >= H:
                hit_H = i
                break
        if hit_H is None:
            pnl += (short_entry - prices[-1])
        else:
            pnl += (short_entry - H)

        return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

    def _simulate_case3(self, cycle: Dict, levels: Dict[str, float]) -> Tuple[Optional[float], Optional[int]]:
        prices = cycle["prices"]
        times = cycle["times"]
        if len(prices) < 2:
            return None, None

        J, K = levels["J"], levels["K"]
        if None in (J, K):
            return None, None

        entry_idx = None
        for i, price in enumerate(prices):
            if price >= J:
                entry_idx = i
                break
        if entry_idx is None:
            return None, None

        entry_price = prices[entry_idx]

        for i in range(entry_idx + 1, len(prices)):
            if prices[i] <= K:
                pnl = (K - entry_price)
                return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

        pnl = (prices[-1] - entry_price)
        return pnl, int((times[entry_idx] - cycle["start_time"]).total_seconds())

    def _estimate_latest_entry(self, entries: List[Tuple[float, int]]) -> Optional[int]:
        if len(entries) < 5:
            return None
        win_entries = [t for pnl, t in entries if pnl > 0]
        if len(win_entries) < 5:
            return None
        return int(np.percentile(win_entries, 80))

    def _simulate_strategies(self, cycles: List[Dict], levels: Dict[str, float]) -> Dict[str, Dict]:
        results = {}

        def aggregate(sim_fn):
            pnls = []
            entries = []
            for cycle in cycles:
                pnl, entry_time = sim_fn(cycle, levels)
                if pnl is None or entry_time is None:
                    continue
                pnls.append(pnl)
                entries.append((pnl, entry_time))
            if len(pnls) == 0:
                return {"trades": 0, "win_rate": None, "avg_pnl": None, "latest_entry": None}
            win_rate = sum(1 for v in pnls if v > 0) / len(pnls)
            avg_pnl = float(np.mean(pnls))
            latest_entry = self._estimate_latest_entry(entries)
            return {
                "trades": len(pnls),
                "win_rate": win_rate,
                "avg_pnl": avg_pnl,
                "latest_entry": latest_entry,
            }

        results["case1"] = aggregate(self._simulate_case1)
        results["case2"] = aggregate(self._simulate_case2)
        results["case3"] = aggregate(self._simulate_case3)
        return results

    def analyze_group(self, cycles: List[Dict]) -> Dict[str, Dict]:
        levels = self._estimate_levels(cycles)
        slippage = self._slippage_stats(cycles)
        stats = self._simulate_strategies(cycles, levels)

        return {
            "levels": levels,
            "slippage": slippage,
            "stats": stats,
        }

    def print_analysis(self) -> None:
        if self.df is None or len(self.df) == 0:
            print("\n========================================")
            print(f"文件: {self.file_name}")
            print("错误: 没有可分析的数据")
            print("========================================\n")
            return

        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", self.file_name)
        date_str = date_match.group(1) if date_match else "未知"

        print("\n" + "=" * 80)
        print(f"文件分析: {self.file_name}")
        print(f"日期: {date_str}")
        print(f"周期: {self.interval_minutes} 分钟")
        print("=" * 80)

        total_points = len(self.df)
        valid_points = int(self.df["price"].notna().sum())
        print("\n基础统计:")
        print(f"  数据点总数: {total_points}")
        print(f"  有效价格点数: {valid_points}")
        print(
            f"  时间范围: {self.df['time'].min()} 到 {self.df['time'].max()}"
        )
        print(f"  识别到的周期数: {len(self.cycles) + len(self.invalid_cycles)}")
        print(f"  有效周期: {len(self.cycles)}")
        print(f"  无效周期(无效数据>5%): {len(self.invalid_cycles)}")

        if len(self.cycles) == 0:
            print("\n没有有效周期可以分析。")
            return

        groups = {
            "all": self.cycles,
            "weekend": [c for c in self.cycles if classify_cycle(c["start_time"]) == "weekend"],
            "weekday_high": [
                c for c in self.cycles if classify_cycle(c["start_time"]) == "weekday_high"
            ],
            "weekday_low": [
                c for c in self.cycles if classify_cycle(c["start_time"]) == "weekday_low"
            ],
        }

        print("\n策略价格估计(基于历史分位数, 仅供参考):")
        for group_name, group_cycles in groups.items():
            if len(group_cycles) < 5:
                print(f"\n[{group_name}] 样本不足, 无法稳定估计参数")
                continue

            analysis = self.analyze_group(group_cycles)
            levels = analysis["levels"]
            slippage = analysis["slippage"]
            stats = analysis["stats"]

            if group_name == "all":
                title = "全量周期"
            elif group_name == "weekend":
                title = "周末"
            elif group_name == "weekday_high":
                title = "工作日高波动(20:00-08:00)"
            else:
                title = "工作日低波动(08:00-20:00)"

            print(f"\n[{title}]")
            print(
                "  建议价格: "
                + ", ".join(
                    [f"{key}={format_price(levels[key])}" for key in list("ABCDEFGHIJK")]
                )
            )

            if slippage["median"] is None:
                print("  滑点估计: 样本不足")
            else:
                print(
                    f"  滑点估计: 中位数={slippage['median']:.4f}, P90={slippage['p90']:.4f}"
                )

            print("  方案一-情况1(先跌后涨):")
            case1 = stats["case1"]
            if case1["trades"] == 0:
                print("    样本不足")
            else:
                win_rate = case1["win_rate"] * 100 if case1["win_rate"] is not None else 0
                avg_pnl = case1["avg_pnl"] if case1["avg_pnl"] is not None else 0
                latest_entry = case1["latest_entry"]
                latest_entry_str = (
                    f"{latest_entry} 秒" if latest_entry is not None else "N/A"
                )
                print(
                    f"    交易次数={case1['trades']}, 胜率={win_rate:.2f}%, 平均收益={avg_pnl:.4f}, 建议最晚入场={latest_entry_str}"
                )

            print("  方案一-情况2(先跌再跌后涨):")
            case2 = stats["case2"]
            if case2["trades"] == 0:
                print("    样本不足")
            else:
                win_rate = case2["win_rate"] * 100 if case2["win_rate"] is not None else 0
                avg_pnl = case2["avg_pnl"] if case2["avg_pnl"] is not None else 0
                latest_entry = case2["latest_entry"]
                latest_entry_str = (
                    f"{latest_entry} 秒" if latest_entry is not None else "N/A"
                )
                print(
                    f"    交易次数={case2['trades']}, 胜率={win_rate:.2f}%, 平均收益={avg_pnl:.4f}, 建议最晚入场={latest_entry_str}"
                )

            print("  方案二(追涨市价进):")
            case3 = stats["case3"]
            if case3["trades"] == 0:
                print("    样本不足")
            else:
                win_rate = case3["win_rate"] * 100 if case3["win_rate"] is not None else 0
                avg_pnl = case3["avg_pnl"] if case3["avg_pnl"] is not None else 0
                latest_entry = case3["latest_entry"]
                latest_entry_str = (
                    f"{latest_entry} 秒" if latest_entry is not None else "N/A"
                )
                print(
                    f"    交易次数={case3['trades']}, 胜率={win_rate:.2f}%, 平均收益={avg_pnl:.4f}, 建议最晚入场={latest_entry_str}"
                )

        print("\n说明:")
        print("  1) 价格参数是基于历史分位数估计的启发式结果, 请结合实盘验证。")
        print("  2) 做空可使用 1-价格 的镜像参数。")
        print("  3) 胜率与收益仅在历史数据上回测, 未来不保证。")
        print("=" * 80 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Polymarket 量化数据分析")
    parser.add_argument("--date", type=str, help="按日期过滤 (YYYY-MM-DD)")
    parser.add_argument("--file", type=str, help="分析指定文件")
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        choices=[5, 15],
        help="周期长度(分钟): 5 或 15",
    )

    args = parser.parse_args()

    if args.file:
        if not os.path.exists(args.file):
            print(f"错误: 文件不存在: {args.file}")
            return 1
        files_to_analyze = [args.file]
    else:
        files_to_analyze = find_csv_files(args.date)

    if not files_to_analyze:
        if args.date:
            print(f"未找到匹配日期的 CSV: {args.date}")
        else:
            print("未找到匹配的 CSV 文件")
        print("期望文件格式示例:")
        print("  - BTC5MIN_YYYY-MM-DD.csv")
        print("  - BTC_YYYY-MM-DD.csv")
        return 1

    print(f"\n找到 {len(files_to_analyze)} 个文件:")
    for path in files_to_analyze:
        print(f"  - {path}")

    for file_path in files_to_analyze:
        analyzer = CycleAnalyzer(file_path, args.interval)
        if analyzer.load_data():
            analyzer.build_cycles()
            analyzer.print_analysis()
        else:
            print(f"\n跳过文件: {file_path}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
