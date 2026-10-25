package latency

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func validOptions() Options {
	return Options{Target: "127.0.0.1:8765", Count: 3, Timeout: time.Second, Condition: "idle"}
}

func TestOptionsValidateTargetsAndLimits(t *testing.T) {
	for _, target := range []string{"127.0.0.1:8765", "192.168.1.1:443", "[::1]:8765", "[fe80::1%eth0]:443"} {
		options := validOptions()
		options.Target = target
		if err := options.Validate(); err != nil {
			t.Errorf("valid target %q rejected: %v", target, err)
		}
	}
	for _, change := range []func(*Options){
		func(o *Options) { o.Target = "" }, func(o *Options) { o.Target = "example.com:443" },
		func(o *Options) { o.Target = "127.0.0.1:0" }, func(o *Options) { o.Target = "[::]:443" },
		func(o *Options) { o.Target = "224.0.0.1:443" }, func(o *Options) { o.Target = "255.255.255.255:443" },
		func(o *Options) { o.Count = 0 }, func(o *Options) { o.Count = 101 },
		func(o *Options) { o.Timeout = 0 }, func(o *Options) { o.Timeout = 11 * time.Second },
		func(o *Options) { o.Interval = -1 }, func(o *Options) { o.Interval = 6 * time.Second },
		func(o *Options) { o.Condition = "detected_congestion" },
	} {
		options := validOptions()
		change(&options)
		calls := 0
		_, err := measure(context.Background(), options, func(context.Context, string, time.Duration) core.LatencySample {
			calls++
			return core.LatencySample{}
		})
		if err == nil || calls != 0 {
			t.Errorf("invalid options reached the probe: %+v, calls=%d", options, calls)
		}
	}
}

func TestMeasurePreservesIndividualAttempts(t *testing.T) {
	options := validOptions()
	samples := []core.LatencySample{{Duration: time.Millisecond}, {Failure: core.LatencyTimeout}, {Duration: 3 * time.Millisecond}}
	calls := 0
	report, err := measure(context.Background(), options, func(_ context.Context, target string, timeout time.Duration) core.LatencySample {
		if target != options.Target || timeout != options.Timeout {
			t.Fatal("probe options changed")
		}
		sample := samples[calls]
		calls++
		return sample
	})
	if err != nil || calls != 3 || len(report.Attempts) != 3 || report.Summary.Successful != 2 || report.Summary.Failed != 1 || report.FinishedAt.Before(report.StartedAt) {
		t.Fatalf("incorrect measurement batch: %+v, err=%v, calls=%d", report, err, calls)
	}
	for i, attempt := range report.Attempts {
		if attempt.Sample != samples[i] || attempt.StartedAt.Before(report.StartedAt) || attempt.StartedAt.After(report.FinishedAt) {
			t.Errorf("attempt provenance lost: %+v", attempt)
		}
	}
}

func TestMeasureCancellationStopsFurtherAttempts(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	options := validOptions()
	options.Interval = 5 * time.Second
	calls := 0
	_, err := measure(ctx, options, func(context.Context, string, time.Duration) core.LatencySample {
		calls++
		cancel()
		return core.LatencySample{Duration: time.Millisecond}
	})
	if !errors.Is(err, context.Canceled) || calls != 1 {
		t.Fatalf("cancellation did not stop the batch: calls=%d, err=%v", calls, err)
	}
}
