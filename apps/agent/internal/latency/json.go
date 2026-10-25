package latency

import (
	"encoding/json"
	"io"
	"runtime"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

// This versioned local export is distinct from future group protocol messages.
type jsonAttempt struct {
	StartedAt time.Time           `json:"started_at"`
	ConnectMS *float64            `json:"connect_ms"`
	Failure   core.LatencyFailure `json:"failure,omitempty"`
}

type jsonDistribution struct {
	Minimum float64 `json:"min"`
	P50     float64 `json:"p50"`
	P95     float64 `json:"p95"`
	P99     float64 `json:"p99"`
	Maximum float64 `json:"max"`
}

type jsonReport struct {
	SchemaVersion int               `json:"schema_version"`
	Method        string            `json:"method"`
	Version       string            `json:"coopace_version"`
	GoVersion     string            `json:"go_version"`
	OS            string            `json:"os"`
	Architecture  string            `json:"architecture"`
	Target        string            `json:"target"`
	Condition     string            `json:"declared_condition"`
	Requested     int               `json:"requested_attempts"`
	TimeoutMS     float64           `json:"timeout_ms"`
	IntervalMS    float64           `json:"pause_between_attempts_ms"`
	StartedAt     time.Time         `json:"started_at"`
	FinishedAt    time.Time         `json:"finished_at"`
	Attempts      []jsonAttempt     `json:"attempts"`
	Successful    int               `json:"successful"`
	Failed        int               `json:"failed"`
	ConnectMS     *jsonDistribution `json:"connect_ms"`
}

func WriteJSON(output io.Writer, report Report, version string) error {
	data := jsonReport{
		SchemaVersion: 1, Method: "tcp_connect", Version: version, GoVersion: runtime.Version(),
		OS: runtime.GOOS, Architecture: runtime.GOARCH,
		Target: report.Options.Target, Condition: report.Options.Condition,
		Requested: report.Options.Count, TimeoutMS: milliseconds(report.Options.Timeout), IntervalMS: milliseconds(report.Options.Interval),
		StartedAt: report.StartedAt.UTC(), FinishedAt: report.FinishedAt.UTC(),
		Attempts:   make([]jsonAttempt, 0, len(report.Attempts)),
		Successful: report.Summary.Successful, Failed: report.Summary.Failed,
	}
	for _, attempt := range report.Attempts {
		item := jsonAttempt{StartedAt: attempt.StartedAt.UTC(), Failure: attempt.Sample.Failure}
		if attempt.Sample.Failure == "" {
			value := milliseconds(attempt.Sample.Duration)
			item.ConnectMS = &value
		}
		data.Attempts = append(data.Attempts, item)
	}
	if distribution := report.Summary.Distribution; distribution != nil {
		data.ConnectMS = &jsonDistribution{
			Minimum: milliseconds(distribution.Minimum), Maximum: milliseconds(distribution.Maximum),
			P50: milliseconds(distribution.P50), P95: milliseconds(distribution.P95), P99: milliseconds(distribution.P99),
		}
	}
	encoder := json.NewEncoder(output)
	encoder.SetIndent("", "  ")
	return encoder.Encode(data)
}

func milliseconds(duration time.Duration) float64 {
	return float64(duration) / float64(time.Millisecond)
}
