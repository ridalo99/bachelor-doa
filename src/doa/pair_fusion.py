# File: src/doa/pair_fusion.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


Pair = Tuple[int, int]


@dataclass
class PairCandidate:
    pair: Pair
    rank: int
    angle_deg: float
    score: float


@dataclass
class PairFusionResult:
    theta_deg: float
    support_pairs: int
    total_candidates: int
    cluster_weight: float
    members: List[PairCandidate]
    ambiguous: bool = False
    reason: str = ""


def _norm_angle_deg(angle: float) -> float:
    return angle % 360.0


def _circ_dist_deg(a: float, b: float) -> float:
    d = abs(_norm_angle_deg(a) - _norm_angle_deg(b))
    return min(d, 360.0 - d)


def _circ_mean_deg(angles: Sequence[float], weights: Sequence[float]) -> float:
    import math

    if not angles:
        return 0.0

    sx = 0.0
    sy = 0.0
    for a, w in zip(angles, weights):
        r = math.radians(_norm_angle_deg(a))
        sx += math.cos(r) * float(w)
        sy += math.sin(r) * float(w)

    if abs(sx) < 1e-12 and abs(sy) < 1e-12:
        return _norm_angle_deg(float(angles[0]))

    return _norm_angle_deg(math.degrees(math.atan2(sy, sx)))


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def _extract_pair(result: Any) -> Optional[Pair]:
    pair = _get_attr(result, "pair")
    if isinstance(pair, (tuple, list)) and len(pair) == 2:
        return int(pair[0]), int(pair[1])
    return None


def _extract_topk(result: Any) -> List[Tuple[float, float]]:
    topk = _get_attr(result, "topk")
    if isinstance(topk, list) and topk:
        out: List[Tuple[float, float]] = []
        for item in topk:
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                out.append((float(item[0]), float(item[1])))
        if out:
            return out

    theta = _get_attr(result, "theta_deg", _get_attr(result, "theta"))
    score = _get_attr(result, "score", 0.0)
    if theta is None:
        return []
    return [(float(theta), float(score))]


def _pair_group(pair: Pair) -> str:
    pair_set = tuple(sorted(pair))
    if pair_set in {(0, 1), (2, 3)}:
        return "horizontal"
    if pair_set in {(0, 3), (1, 2)}:
        return "vertical"
    return "diagonal"


def _to_candidates(
    pair_results: Sequence[Any],
    topn_per_pair: int = 1,
    min_score: float = 0.0,
    rank_weight_decay: float = 0.35,
) -> List[PairCandidate]:
    candidates: List[PairCandidate] = []

    for result in pair_results:
        pair = _extract_pair(result)
        if pair is None:
            continue

        ranked = _extract_topk(result)[: max(1, int(topn_per_pair))]
        for rank, (angle, score) in enumerate(ranked, start=1):
            score = float(score)
            if score < float(min_score):
                continue

            weighted_score = score * (float(rank_weight_decay) ** (rank - 1))
            candidates.append(
                PairCandidate(
                    pair=pair,
                    rank=rank,
                    angle_deg=_norm_angle_deg(float(angle)),
                    score=weighted_score,
                )
            )

    return candidates


def _cluster_candidates(
    candidates: Sequence[PairCandidate],
    tol_deg: float,
    min_support_pairs: int,
    min_best_second_gap: float,
) -> List[PairFusionResult]:
    if not candidates:
        return []

    clusters: List[List[PairCandidate]] = []

    for cand in sorted(candidates, key=lambda c: c.score, reverse=True):
        placed = False

        for cluster in clusters:
            center = _circ_mean_deg(
                [item.angle_deg for item in cluster],
                [item.score for item in cluster],
            )
            if _circ_dist_deg(cand.angle_deg, center) <= float(tol_deg):
                cluster.append(cand)
                placed = True
                break

        if not placed:
            clusters.append([cand])

    fused: List[PairFusionResult] = []
    total_candidates = len(candidates)

    for cluster in clusters:
        best_per_pair: Dict[Pair, PairCandidate] = {}

        for cand in sorted(cluster, key=lambda c: (c.score, -c.rank), reverse=True):
            prev = best_per_pair.get(cand.pair)
            if prev is None:
                best_per_pair[cand.pair] = cand
                continue

            if cand.rank < prev.rank:
                best_per_pair[cand.pair] = cand
            elif cand.rank == prev.rank and cand.score > prev.score:
                best_per_pair[cand.pair] = cand

        uniq_members = sorted(best_per_pair.values(), key=lambda x: x.score, reverse=True)
        weights = [m.score for m in uniq_members]
        angles = [m.angle_deg for m in uniq_members]
        cluster_weight = float(sum(weights))
        theta_deg = _circ_mean_deg(angles, weights)

        fused.append(
            PairFusionResult(
                theta_deg=_norm_angle_deg(theta_deg),
                support_pairs=len(uniq_members),
                total_candidates=total_candidates,
                cluster_weight=cluster_weight,
                members=uniq_members,
                ambiguous=False,
                reason="",
            )
        )

    fused.sort(
        key=lambda item: (
            item.support_pairs,
            item.cluster_weight,
        ),
        reverse=True,
    )

    if not fused:
        return fused

    best = fused[0]
    if best.support_pairs < int(min_support_pairs):
        best.ambiguous = True
        best.reason = f"support_pairs<{min_support_pairs}"

    if len(fused) > 1:
        second = fused[1]
        gap = best.cluster_weight - second.cluster_weight
        if gap < float(min_best_second_gap):
            best.ambiguous = True
            if best.reason:
                best.reason += "; "
            best.reason += f"small_gap={gap:.6f}"

    return fused


def majority_pair_theta(
    pair_results: Sequence[Any],
    *,
    topn_per_pair: int = 1,
    tol_deg: float = 12.0,
    min_score: float = 0.0,
    min_support_pairs: int = 2,
    min_best_second_gap: float = 0.05,
    rank_weight_decay: float = 0.35,
) -> PairFusionResult:
    candidates = _to_candidates(
        pair_results=pair_results,
        topn_per_pair=topn_per_pair,
        min_score=min_score,
        rank_weight_decay=rank_weight_decay,
    )
    fused = _cluster_candidates(
        candidates,
        tol_deg=tol_deg,
        min_support_pairs=min_support_pairs,
        min_best_second_gap=min_best_second_gap,
    )
    if not fused:
        return PairFusionResult(
            theta_deg=0.0,
            support_pairs=0,
            total_candidates=0,
            cluster_weight=0.0,
            members=[],
            ambiguous=True,
            reason="no_candidates",
        )
    return fused[0]


def grouped_pair_fusions(
    pair_results: Sequence[Any],
    *,
    topn_per_pair: int = 1,
    tol_deg: float = 12.0,
    min_score: float = 0.0,
    min_support_pairs: int = 1,
    min_best_second_gap: float = 0.05,
    rank_weight_decay: float = 0.35,
) -> Dict[str, PairFusionResult]:
    grouped_raw: Dict[str, List[Any]] = {
        "horizontal": [],
        "vertical": [],
        "diagonal": [],
    }

    for result in pair_results:
        pair = _extract_pair(result)
        if pair is None:
            continue
        grouped_raw[_pair_group(pair)].append(result)

    out: Dict[str, PairFusionResult] = {}
    for group_name, group_results in grouped_raw.items():
        fused = majority_pair_theta(
            group_results,
            topn_per_pair=topn_per_pair,
            tol_deg=tol_deg,
            min_score=min_score,
            min_support_pairs=min_support_pairs,
            min_best_second_gap=min_best_second_gap,
            rank_weight_decay=rank_weight_decay,
        )
        if fused.total_candidates > 0:
            out[group_name] = fused

    return out