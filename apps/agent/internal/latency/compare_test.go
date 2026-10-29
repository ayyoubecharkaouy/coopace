package latency

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func baselineJSON(t *testing.T, condition string, samples ...core.LatencySample) []byte {
	t.Helper()
	started := time.Date(2026, 10, 29, 12, 0, 0, 0, time.UTC)
	options := Options{Target: "127.0.0.1:8765", Count: len(samples), Timeout: time.Second, Interval: time.Millisecond, Condition: condition}
	summary, err := core.SummarizeLatency(samples)
	if err != nil {
		t.Fatal(err)
	}
	report := Report{Options: options, StartedAt: started, FinishedAt: started.Add(time.Minute), Summary: summary}
	for index, sample := range samples {
		report.Attempts = append(report.Attempts, Attempt{StartedAt: started.Add(time.Duration(index) * time.Second), Sample: sample})
	}
	var output bytes.Buffer
	if err := WriteJSON(&output, report, "test"); err != nil {
		t.Fatal(err)
	}
	return output.Bytes()
}

func TestCompareRecomputesStatisticsAndPreservesFailures(t *testing.T) {
	idle := baselineJSON(t, "idle", core.LatencySample{Duration: 1000001}, core.LatencySample{Failure: core.LatencyTimeout}, core.LatencySample{Duration: 3 * time.Millisecond})
	loaded := baselineJSON(t, "loaded", core.LatencySample{Duration: 2 * time.Millisecond}, core.LatencySample{Duration: 4 * time.Millisecond}, core.LatencySample{Failure: core.LatencyConnectionFailed})
	comparison, err := Compare(bytes.NewReader(idle), bytes.NewReader(loaded))
	if err != nil {
		t.Fatal(err)
	}
	if comparison.Count != 3 || comparison.Idle.Failed != 1 || comparison.Loaded.Failed != 1 || comparison.Idle.Distribution.Minimum != 1000001 || comparison.Loaded.Distribution.P50 != 2*time.Millisecond {
		t.Fatalf("counts, units or precision lost: %+v", comparison)
	}
	allFailed := baselineJSON(t, "loaded", core.LatencySample{Failure: core.LatencyTimeout}, core.LatencySample{Failure: core.LatencyTimeout}, core.LatencySample{Failure: core.LatencyTimeout})
	comparison, err = Compare(bytes.NewReader(idle), bytes.NewReader(allFailed))
	if err != nil || comparison.Loaded.Distribution != nil || comparison.Loaded.Failed != 3 {
		t.Fatalf("all-failed report rejected or fabricated: %+v %v", comparison, err)
	}
}

func TestBaselineReaderRejectsMalformedOrInconsistentExports(t *testing.T) {
	valid := baselineJSON(t, "idle", core.LatencySample{Duration: time.Millisecond})
	for _, input := range [][]byte{
		nil, []byte("null"), bytes.Repeat([]byte(" "), maxBaselineBytes+1), append(append([]byte(nil), valid...), valid...),
		bytes.Replace(valid, []byte(`"schema_version": 1`), []byte(`"schema_version": 1, "schema_version": 1`), 1),
		bytes.Replace(valid, []byte(`"schema_version"`), []byte(`"Schema_version"`), 1),
		bytes.Replace(valid, []byte(`"successful"`), []byte(`"ſuccessful"`), 1),
	} {
		if _, err := readBaseline(bytes.NewReader(input)); err == nil {
			t.Fatalf("invalid JSON accepted: length %d", len(input))
		}
	}
	for _, change := range []func(map[string]any){
		func(m map[string]any) { delete(m, "failed") },
		func(m map[string]any) { m["failed"] = nil },
		func(m map[string]any) { m["schema_version"] = 2 },
		func(m map[string]any) { m["method"] = "icmp" },
		func(m map[string]any) { m["requested_attempts"] = 2 },
		func(m map[string]any) { m["successful"] = 0 },
		func(m map[string]any) { m["unknown"] = true },
		func(m map[string]any) { m["finished_at"] = "2025-01-01T00:00:00Z" },
		func(m map[string]any) { m["connect_ms"].(map[string]any)["p95"] = 9 },
		func(m map[string]any) { delete(m["connect_ms"].(map[string]any), "min") },
		func(m map[string]any) { m["connect_ms"] = nil },
		func(m map[string]any) { delete(m, "connect_ms") },
		func(m map[string]any) { m["attempts"].([]any)[0].(map[string]any)["failure"] = "timeout" },
		func(m map[string]any) { m["attempts"].([]any)[0].(map[string]any)["connect_ms"] = nil },
		func(m map[string]any) { m["attempts"].([]any)[0].(map[string]any)["connect_ms"] = -1 },
		func(m map[string]any) { m["attempts"].([]any)[0].(map[string]any)["connect_ms"] = 1e30 },
		func(m map[string]any) {
			m["attempts"].([]any)[0].(map[string]any)["started_at"] = "2025-01-01T00:00:00Z"
		},
	} {
		var document map[string]any
		if err := json.Unmarshal(valid, &document); err != nil {
			t.Fatal(err)
		}
		change(document)
		data, err := json.Marshal(document)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := readBaseline(bytes.NewReader(data)); err == nil {
			t.Fatalf("inconsistent report accepted: %s", data)
		}
	}
}

func TestCompareRejectsDifferentMethodsAndDeclaredContexts(t *testing.T) {
	idle := baselineJSON(t, "idle", core.LatencySample{Duration: 0})
	validLoaded := baselineJSON(t, "loaded", core.LatencySample{Duration: 0})
	for key, value := range map[string]any{"target": "127.0.0.1:9999", "declared_condition": "unspecified", "timeout_ms": 2000, "pause_between_attempts_ms": 0, "coopace_version": "another-build", "go_version": "another-compiler", "os": "another-os", "architecture": "another-arch"} {
		var document map[string]any
		if err := json.Unmarshal(validLoaded, &document); err != nil {
			t.Fatal(err)
		}
		document[key] = value
		data, _ := json.Marshal(document)
		if _, err := Compare(bytes.NewReader(idle), bytes.NewReader(data)); err == nil {
			t.Errorf("mismatched %s accepted", key)
		}
	}
	if comparison, err := Compare(bytes.NewReader(idle), bytes.NewReader(validLoaded)); err != nil || comparison.Idle.Distribution.Minimum != 0 {
		t.Fatalf("valid measured zero rejected: %v", err)
	}
	if _, err := Compare(strings.NewReader("{}"), bytes.NewReader(validLoaded)); err == nil {
		t.Fatal("missing idle metadata accepted")
	}
}
