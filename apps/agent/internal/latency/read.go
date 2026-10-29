package latency

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"strings"
	"time"

	"github.com/ayyoubecharkaouy/coopace/internal/strictjson"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const maxBaselineBytes = 256 * 1024

type baseline struct {
	report                               Report
	version, goVersion, os, architecture string
}

// readBaseline accepts complete local v1 exports, including all-failed series.
// It recomputes summaries from attempts instead of trusting imported statistics.
func readBaseline(input io.Reader) (baseline, error) {
	data, err := io.ReadAll(io.LimitReader(input, maxBaselineBytes+1))
	if err != nil {
		return baseline{}, err
	}
	if err := strictjson.Check(data, maxBaselineBytes); err != nil {
		return baseline{}, err
	}
	if err := requiredFields(data, "schema_version", "method", "coopace_version", "go_version", "os", "architecture", "target", "declared_condition", "requested_attempts", "timeout_ms", "pause_between_attempts_ms", "started_at", "finished_at", "attempts", "successful", "failed"); err != nil {
		return baseline{}, err
	}
	var raw struct {
		Attempts     []json.RawMessage `json:"attempts"`
		Distribution json.RawMessage   `json:"connect_ms"`
	}
	if err := json.Unmarshal(data, &raw); err != nil {
		return baseline{}, err
	}
	if len(raw.Distribution) == 0 {
		return baseline{}, fmt.Errorf("champ connect_ms absent")
	}
	if len(raw.Attempts) > 100 {
		return baseline{}, fmt.Errorf("trop d’essais dans le rapport")
	}
	for _, attempt := range raw.Attempts {
		if err := requiredFields(attempt, "started_at"); err != nil {
			return baseline{}, err
		}
		var fields map[string]json.RawMessage
		if err := json.Unmarshal(attempt, &fields); err != nil {
			return baseline{}, err
		}
		if len(fields["connect_ms"]) == 0 || isJSONNull(fields["failure"]) {
			return baseline{}, fmt.Errorf("essai incomplet")
		}
	}
	if !isJSONNull(raw.Distribution) {
		if err := requiredFields(raw.Distribution, "min", "p50", "p95", "p99", "max"); err != nil {
			return baseline{}, err
		}
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var imported jsonReport
	if err := decoder.Decode(&imported); err != nil {
		return baseline{}, err
	}
	if imported.SchemaVersion != 1 || imported.Method != "tcp_connect" || strings.TrimSpace(imported.Version) == "" || strings.TrimSpace(imported.GoVersion) == "" || strings.TrimSpace(imported.OS) == "" || strings.TrimSpace(imported.Architecture) == "" {
		return baseline{}, fmt.Errorf("format, méthode ou provenance de rapport invalide")
	}
	timeout, err := durationFromMS(imported.TimeoutMS)
	if err != nil {
		return baseline{}, err
	}
	interval, err := durationFromMS(imported.IntervalMS)
	if err != nil {
		return baseline{}, err
	}
	options := Options{Target: imported.Target, Count: imported.Requested, Timeout: timeout, Interval: interval, Condition: imported.Condition}
	if err := options.Validate(); err != nil {
		return baseline{}, err
	}
	if len(imported.Attempts) != options.Count || imported.StartedAt.IsZero() || imported.FinishedAt.IsZero() || imported.FinishedAt.Before(imported.StartedAt) {
		return baseline{}, fmt.Errorf("série incomplète ou horodatages incohérents")
	}
	report := Report{Options: options, StartedAt: imported.StartedAt, FinishedAt: imported.FinishedAt}
	samples := make([]core.LatencySample, 0, len(imported.Attempts))
	previous := imported.StartedAt
	for _, attempt := range imported.Attempts {
		if attempt.StartedAt.IsZero() || attempt.StartedAt.Before(previous) || attempt.StartedAt.After(imported.FinishedAt) {
			return baseline{}, fmt.Errorf("horodatage d'essai incohérent")
		}
		previous = attempt.StartedAt
		sample := core.LatencySample{Failure: attempt.Failure}
		if attempt.Failure == "" {
			if attempt.ConnectMS == nil {
				return baseline{}, fmt.Errorf("durée de connexion réussie absente")
			}
			sample.Duration, err = durationFromMS(*attempt.ConnectMS)
			if err != nil {
				return baseline{}, err
			}
		} else if attempt.ConnectMS != nil {
			return baseline{}, fmt.Errorf("durée associée à un échec")
		}
		samples = append(samples, sample)
		report.Attempts = append(report.Attempts, Attempt{StartedAt: attempt.StartedAt, Sample: sample})
	}
	report.Summary, err = core.SummarizeLatency(samples)
	if err != nil {
		return baseline{}, err
	}
	if report.Summary.Successful != imported.Successful || report.Summary.Failed != imported.Failed {
		return baseline{}, fmt.Errorf("comptages incompatibles avec les essais")
	}
	if err := checkDistribution(imported.ConnectMS, report.Summary.Distribution); err != nil {
		return baseline{}, err
	}
	return baseline{report: report, version: imported.Version, goVersion: imported.GoVersion, os: imported.OS, architecture: imported.Architecture}, nil
}

func requiredFields(data []byte, names ...string) error {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return err
	}
	for _, name := range names {
		if len(fields[name]) == 0 || isJSONNull(fields[name]) {
			return fmt.Errorf("champ requis absent ou nul : %s", name)
		}
	}
	return nil
}

func durationFromMS(value float64) (time.Duration, error) {
	if math.IsNaN(value) || math.IsInf(value, 0) || value < 0 || value >= float64(math.MaxInt64)/float64(time.Millisecond) {
		return 0, fmt.Errorf("durée en millisecondes invalide")
	}
	return time.Duration(math.Round(value * float64(time.Millisecond))), nil
}

func checkDistribution(imported *jsonDistribution, computed *core.LatencyDistribution) error {
	if (imported == nil) != (computed == nil) {
		return fmt.Errorf("distribution absente ou inventée")
	}
	if imported == nil {
		return nil
	}
	values := []float64{imported.Minimum, imported.P50, imported.P95, imported.P99, imported.Maximum}
	expected := []time.Duration{computed.Minimum, computed.P50, computed.P95, computed.P99, computed.Maximum}
	for index, value := range values {
		duration, err := durationFromMS(value)
		if err != nil || duration != expected[index] {
			return fmt.Errorf("distribution incompatible avec les essais")
		}
	}
	return nil
}

func isJSONNull(data []byte) bool { return bytes.Equal(bytes.TrimSpace(data), []byte("null")) }
