"""Positive scalar calibration; held-out residuals define a score-space radius."""

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class Calibration:
    a: float = 1.0
    b: float = 0.0
    radius: float | None = None
    reason: str = "identity"


def fit_score_calibration(s_fit, t_fit):
    s, t = np.asarray(s_fit, dtype=np.float64), np.asarray(t_fit, dtype=np.float64)
    if s.shape != t.shape or s.ndim != 1:
        raise ValueError("Invalid calibration pair shapes")
    if len(s) == 0 or not np.isfinite(s).all() or not np.isfinite(t).all():
        return Calibration(reason="nonfinite_or_empty")
    variance = np.mean((s - s.mean()) ** 2)
    if variance < 1e-12:
        return Calibration(reason="degenerate_variance")
    slope = float(np.mean((s - s.mean()) * (t - t.mean())) / variance)
    a = max(1e-6, slope)
    b = float(t.mean() - a * s.mean())
    if not np.isfinite(a + b):
        return Calibration(reason="nonfinite_fit")
    return Calibration(a, b, reason="slope_boundary" if a == 1e-6 else "ols")


def compute_radius(s_check, t_check, a, b, quantile=0.95):
    errors = np.sort(np.abs(np.asarray(t_check) - (a * np.asarray(s_check) + b)))
    if not len(errors) or not np.isfinite(errors).all() or not 0 < quantile <= 1:
        raise ValueError("Invalid cal-check residual population")
    return float(errors[math.ceil(quantile * len(errors)) - 1])


def calibrate_scores(raw, fidelity, cal):
    return np.where(fidelity, raw, cal.a * raw + cal.b)


def fit_with_roles(s_fit, t_fit, fit_qids, s_check, t_check, check_qids, cfg):
    if set(fit_qids) & set(check_qids):
        raise ValueError("Calibration query roles overlap")
    fit_valid = len(s_fit) >= cfg["min_pairs"] and len(set(fit_qids)) >= cfg["min_queries"]
    check_valid = len(s_check) >= cfg["min_pairs"] and len(set(check_qids)) >= cfg["min_queries"]
    cal = fit_score_calibration(s_fit, t_fit) if fit_valid else Calibration(reason="insufficient_calibration")
    radius = compute_radius(s_check, t_check, cal.a, cal.b, cfg["quantile"]) if check_valid else None
    return Calibration(cal.a, cal.b, radius, cal.reason)
