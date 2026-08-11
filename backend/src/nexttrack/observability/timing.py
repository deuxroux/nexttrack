# Timing Class to check how long things ar etaking for benchmarking
from collections import deque
from statistics import quantiles


class StageTimings:
    # rolling buffer of per-stage elapsed times (ms).

    def __init__(self, maxlen: int = 100) -> None:
        self._buffers: dict[str, deque[float]] = {}
        self._maxlen = maxlen

    def record(self, stage: str, elapsed_ms: float) -> None:
        if stage not in self._buffers:
            self._buffers[stage] = deque(maxlen=self._maxlen)
        self._buffers[stage].append(elapsed_ms)

    def summary(self) -> dict[str, dict[str, float]]:
        # Return percentile and max per stage from the current ring buffers.
        # gives empty dict if nothing has been recorded yet.
        result: dict[str, dict[str, float]] = {}
        for stage, buf in self._buffers.items():
            data = list(buf)
            n = len(data)
            if n == 0:
                continue
            if n < 2:
                v = data[0]
                result[stage] = {"p50": v, "p95": v, "max": v, "n": float(n)}
            else:
                # get "percentiles" via quantiles method
                qs = quantiles(data, n=100, method="inclusive")
                result[stage] = {
                    "p50": qs[49], #99 indices returned so appears off by 1
                    "p95": qs[94],
                    "max": float(max(data)),
                    "n": float(n),
                }
        return result
