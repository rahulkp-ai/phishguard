"""
phishguard.drift
=================
Prediction drift detection for the PhishGuard API.

What is prediction drift?
--------------------------
Prediction drift (also called label drift or output drift) occurs when the
distribution of your model's predictions changes significantly from what you
observed during training or a stable production baseline.

For a phishing detector, prediction drift looks like:
- Baseline: 35% of URLs predicted as phishing (normal internet traffic)
- Drift:    90% of URLs predicted as phishing (attack targeting the API,
            or a new wave of phishing campaigns the model hasn't seen)

Drift is a signal that something changed — either in the incoming data or
in the model's behaviour.  It does NOT mean the model is wrong.  It means
you should investigate.

How this detector works
------------------------
``DriftDetector`` maintains a fixed-size deque (``window_size`` predictions).
After every prediction, it:

1. Appends the new prediction (1=phishing, 0=legitimate) to the window.
2. Computes the rolling phishing rate = sum(window) / len(window).
3. Updates the ``phishguard_phishing_rate_1m`` Prometheus gauge.
4. Checks whether the rolling rate has deviated from ``baseline_rate`` by
   more than ``threshold`` (absolute difference).
5. If drift is detected, emits a structured log warning with the current
   rate, baseline, and deviation — once per ``alert_cooldown_s`` seconds
   to avoid log flooding.
6. Updates the ``phishguard_drift_detected`` Prometheus gauge (0 or 1).

Baseline rate
-------------
The default ``baseline_rate=0.35`` means we expect 35% of submitted URLs
to be phishing.  This is a reasonable estimate for a public phishing
detection API — adjust it based on your observed production traffic after
the first week of real usage.

Thread safety
-------------
``DriftDetector`` is not thread-safe by design — gunicorn with sync workers
uses a separate process per worker, and the detector lives in process memory.
Each worker maintains its own window.  The Prometheus Gauge (which IS
multi-process aware) aggregates across workers in the Prometheus scrape.

For multi-threaded servers (gevent/uvicorn), wrap in a threading.Lock.
"""

from __future__ import annotations

import time
from collections import deque

import structlog

from phishguard.metrics import DRIFT_BASELINE, DRIFT_DETECTED, PHISHING_RATE

logger = structlog.get_logger(__name__)


class DriftDetector:
    """
    Rolling-window prediction drift detector.

    Parameters
    ----------
    baseline_rate:
        Expected fraction of predictions that should be phishing (0.0–1.0).
        Default: 0.35 (35%).
    threshold:
        Absolute deviation from baseline that triggers a drift alert.
        Default: 0.30 (30 percentage points — e.g. baseline 35%, alert if > 65%).
    window_size:
        Number of recent predictions to track.
        Default: 60 (roughly 1 minute of traffic at 1 req/s).
    alert_cooldown_s:
        Minimum seconds between repeated drift log alerts.
        Default: 60 (alert at most once per minute).
    """

    def __init__(
        self,
        *,
        baseline_rate: float = 0.35,
        threshold: float = 0.30,
        window_size: int = 60,
        alert_cooldown_s: float = 60.0,
    ) -> None:
        if not 0.0 <= baseline_rate <= 1.0:
            raise ValueError(f"baseline_rate must be in [0, 1], got {baseline_rate}")
        if not 0.0 < threshold <= 1.0:
            raise ValueError(f"threshold must be in (0, 1], got {threshold}")
        if window_size < 1:
            raise ValueError(f"window_size must be >= 1, got {window_size}")

        self.baseline_rate = baseline_rate
        self.threshold = threshold
        self.window_size = window_size
        self.alert_cooldown_s = alert_cooldown_s

        self._window: deque[int] = deque(maxlen=window_size)
        self._drift_active: bool = False
        self._last_alert_ts: float = 0.0

        # Initialise Prometheus gauges with config values
        DRIFT_BASELINE.set(baseline_rate)
        DRIFT_DETECTED.set(0)
        PHISHING_RATE.set(baseline_rate)  # start at baseline until window fills

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, is_phishing: bool) -> None:
        """
        Record a new prediction and check for drift.

        Parameters
        ----------
        is_phishing:
            True if the model predicted the URL as phishing.
        """
        self._window.append(int(is_phishing))
        self._check_drift()

    @property
    def current_rate(self) -> float:
        """Rolling phishing rate over the current window (0.0–1.0)."""
        if not self._window:
            return self.baseline_rate
        return sum(self._window) / len(self._window)

    @property
    def window_full(self) -> bool:
        """True once the window has accumulated ``window_size`` predictions."""
        return len(self._window) == self.window_size

    def reset(self) -> None:
        """Clear the window and reset drift state. Useful in tests."""
        self._window.clear()
        self._drift_active = False
        self._last_alert_ts = 0.0
        DRIFT_DETECTED.set(0)
        PHISHING_RATE.set(self.baseline_rate)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_drift(self) -> None:
        rate = self.current_rate
        deviation = abs(rate - self.baseline_rate)

        # Update Prometheus gauge on every prediction
        PHISHING_RATE.set(rate)

        # Only trigger drift alerts once the window is full —
        # a half-full window produces unreliable rates.
        if not self.window_full:
            return

        drift_now = deviation > self.threshold

        if drift_now:
            DRIFT_DETECTED.set(1)
            self._emit_alert(rate, deviation)
        else:
            if self._drift_active:
                # Drift just cleared — log recovery
                logger.info(
                    "drift resolved",
                    phishing_rate=round(rate, 4),
                    baseline_rate=self.baseline_rate,
                    deviation=round(deviation, 4),
                    threshold=self.threshold,
                )
            DRIFT_DETECTED.set(0)

        self._drift_active = drift_now

    def _emit_alert(self, rate: float, deviation: float) -> None:
        """Emit a structured warning log, rate-limited by alert_cooldown_s."""
        now = time.monotonic()
        if now - self._last_alert_ts < self.alert_cooldown_s:
            return  # suppress repeated alerts within the cooldown window

        self._last_alert_ts = now

        direction = "HIGH" if rate > self.baseline_rate else "LOW"

        logger.warning(
            "prediction drift detected",
            phishing_rate=round(rate, 4),
            baseline_rate=self.baseline_rate,
            deviation=round(deviation, 4),
            threshold=self.threshold,
            direction=direction,
            window_size=self.window_size,
            window_fill=len(self._window),
            action=(
                "Investigate: unusual traffic pattern or new phishing campaign. "
                "If sustained, consider retraining the model."
            ),
        )


# ---------------------------------------------------------------------------
# Module-level singleton used by the Flask app
# ---------------------------------------------------------------------------
# Instantiated once at module import time so all gunicorn workers that
# preload the app share the same initial state before forking.
#
# Adjust baseline_rate after observing real traffic:
#   from phishguard.drift import detector
#   detector.baseline_rate = 0.42   # observed real-world rate
# ---------------------------------------------------------------------------

detector = DriftDetector(
    baseline_rate=0.35,
    threshold=0.30,
    window_size=60,
    alert_cooldown_s=60.0,
)
