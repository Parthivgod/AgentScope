import pytest
import os
import sys

# Ensure SDK is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agentscope.benchmarks.overhead_benchmark import OverheadBenchmark, dummy_workload

def test_overhead_benchmark_scaffold_runs():
    benchmark = OverheadBenchmark(warmup_runs=2, benchmark_runs=5)
    
    baseline = lambda: dummy_workload(50)
    instrumented = lambda: dummy_workload(50)

    result = benchmark.run_comparison(baseline, instrumented, workload_name="test_workload")
    
    assert result["workload"] == "test_workload"
    assert result["runs"] == 5
    assert result["baseline_avg_ns"] > 0
    assert result["instrumented_avg_ns"] > 0
    assert result["status"] == "scaffolding_only_week_5"

@pytest.mark.asyncio
async def test_overhead_benchmark_async_measure():
    benchmark = OverheadBenchmark(warmup_runs=1, benchmark_runs=3)

    async def async_dummy():
        return 42

    durations = await benchmark.measure_async(async_dummy)
    assert len(durations) == 3
    for d in durations:
        assert d >= 0
