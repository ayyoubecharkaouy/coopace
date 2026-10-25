package core

import (
	"fmt"
	"math"
	"sort"
	"time"
)

type LatencyFailure string

const (
	LatencyTimeout          LatencyFailure = "timeout"
	LatencyConnectionFailed LatencyFailure = "connection_failed"
)

// LatencySample describes a successful connect duration or a failed attempt.
// A failed attempt has no measured duration and is excluded from percentiles.
type LatencySample struct {
	Duration time.Duration
	Failure  LatencyFailure
}

type LatencyDistribution struct {
	Minimum time.Duration
	P50     time.Duration
	P95     time.Duration
	P99     time.Duration
	Maximum time.Duration
}

type LatencySummary struct {
	Attempts     int
	Successful   int
	Failed       int
	Distribution *LatencyDistribution
}

// SummarizeLatency uses nearest-rank percentiles of successful samples only.
// It neither performs I/O nor interprets connection failures as packet loss.
func SummarizeLatency(samples []LatencySample) (LatencySummary, error) {
	if len(samples) == 0 {
		return LatencySummary{}, fmt.Errorf("at least one latency attempt is required")
	}
	values := make([]time.Duration, 0, len(samples))
	for _, sample := range samples {
		if sample.Duration < 0 {
			return LatencySummary{}, fmt.Errorf("latency duration cannot be negative")
		}
		switch sample.Failure {
		case "":
			values = append(values, sample.Duration)
		case LatencyTimeout, LatencyConnectionFailed:
			if sample.Duration != 0 {
				return LatencySummary{}, fmt.Errorf("failed latency attempts cannot have a measured duration")
			}
		default:
			return LatencySummary{}, fmt.Errorf("unknown latency failure: %q", sample.Failure)
		}
	}
	summary := LatencySummary{Attempts: len(samples), Successful: len(values), Failed: len(samples) - len(values)}
	if len(values) == 0 {
		return summary, nil
	}
	sort.Slice(values, func(i, j int) bool { return values[i] < values[j] })
	percentile := func(percent int) time.Duration {
		return values[int(math.Ceil(float64(len(values))*float64(percent)/100))-1]
	}
	summary.Distribution = &LatencyDistribution{
		Minimum: values[0], Maximum: values[len(values)-1],
		P50: percentile(50), P95: percentile(95), P99: percentile(99),
	}
	return summary, nil
}
