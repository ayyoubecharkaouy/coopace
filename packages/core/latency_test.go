package core_test

import (
	"reflect"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestLatencyNearestRankPercentiles(t *testing.T) {
	samples := make([]core.LatencySample, 100)
	for i := range samples {
		samples[i].Duration = time.Duration(100-i) * time.Millisecond
	}
	want := append([]core.LatencySample(nil), samples...)
	summary, err := core.SummarizeLatency(samples)
	if err != nil {
		t.Fatal(err)
	}
	distribution := summary.Distribution
	if summary.Attempts != 100 || summary.Successful != 100 || summary.Failed != 0 || distribution == nil ||
		distribution.Minimum != time.Millisecond || distribution.P50 != 50*time.Millisecond ||
		distribution.P95 != 95*time.Millisecond || distribution.P99 != 99*time.Millisecond || distribution.Maximum != 100*time.Millisecond {
		t.Fatalf("incorrect distribution: %+v, %+v", summary, distribution)
	}
	if !reflect.DeepEqual(samples, want) {
		t.Fatal("percentile calculation mutated the samples")
	}
}

func TestLatencyFailuresAreExcludedFromQuantiles(t *testing.T) {
	summary, err := core.SummarizeLatency([]core.LatencySample{
		{Duration: time.Millisecond}, {Failure: core.LatencyTimeout},
		{Duration: 3 * time.Millisecond}, {Failure: core.LatencyConnectionFailed},
	})
	if err != nil {
		t.Fatal(err)
	}
	if summary.Successful != 2 || summary.Failed != 2 || summary.Distribution == nil || summary.Distribution.P50 != time.Millisecond || summary.Distribution.P95 != 3*time.Millisecond {
		t.Fatalf("failed attempts contaminated the distribution: %+v", summary)
	}
}

func TestLatencyDistinguishesMissingAndMeasuredZero(t *testing.T) {
	failed, err := core.SummarizeLatency([]core.LatencySample{{Failure: core.LatencyTimeout}})
	if err != nil || failed.Distribution != nil || failed.Failed != 1 {
		t.Fatalf("all-failed sample has fabricated values: %+v, %v", failed, err)
	}
	zero, err := core.SummarizeLatency([]core.LatencySample{{Duration: 0}})
	if err != nil || zero.Distribution == nil || zero.Distribution.P99 != 0 || zero.Successful != 1 {
		t.Fatalf("measured zero incorrectly unavailable: %+v, %v", zero, err)
	}
}

func TestLatencyRejectsInvalidSamples(t *testing.T) {
	for _, samples := range [][]core.LatencySample{
		nil, {{Duration: -1}}, {{Failure: "unknown"}}, {{Failure: core.LatencyTimeout, Duration: time.Second}},
	} {
		if _, err := core.SummarizeLatency(samples); err == nil {
			t.Errorf("invalid latency samples accepted: %+v", samples)
		}
	}
}
