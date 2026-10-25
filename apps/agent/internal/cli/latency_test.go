package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/latency"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestLatencyInvalidArgumentsAndHelpNeverProbe(t *testing.T) {
	for _, args := range [][]string{nil, {"--target", "example.com:443"}, {"--count", "0"}, {"--unknown"}, {"extra"}, {"--help"}} {
		calls := 0
		var stdout, stderr bytes.Buffer
		code := runLatency(context.Background(), args, "dev", &stdout, &stderr, func(context.Context, latency.Options) (latency.Report, error) {
			calls++
			return latency.Report{}, nil
		})
		want := 2
		if len(args) == 1 && args[0] == "--help" {
			want = 0
		}
		if code != want || calls != 0 {
			t.Errorf("invalid/help args %v: code=%d, probes=%d", args, code, calls)
		}
	}
}

func TestLatencyAllFailedExportsJSONAndReturnsFailure(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := runLatency(context.Background(), []string{"--target", "127.0.0.1:8765", "--count", "1", "--json"}, "dev", &stdout, &stderr,
		func(_ context.Context, options latency.Options) (latency.Report, error) {
			sample := core.LatencySample{Failure: core.LatencyConnectionFailed}
			summary, err := core.SummarizeLatency([]core.LatencySample{sample})
			return latency.Report{Options: options, Attempts: []latency.Attempt{{Sample: sample}}, Summary: summary}, err
		})
	var data map[string]any
	if code != 1 || json.Unmarshal(stdout.Bytes(), &data) != nil || data["connect_ms"] != nil || data["failed"] != float64(1) || stderr.Len() != 0 {
		t.Fatalf("failed batch incorrectly exported: code=%d, stdout=%q, stderr=%q", code, stdout.String(), stderr.String())
	}
}

func TestLatencyTextAndOutputFailure(t *testing.T) {
	measure := func(_ context.Context, options latency.Options) (latency.Report, error) {
		summary, err := core.SummarizeLatency([]core.LatencySample{{Duration: time.Millisecond}})
		return latency.Report{Options: options, Summary: summary}, err
	}
	var stdout, stderr bytes.Buffer
	args := []string{"--target", "127.0.0.1:8765"}
	if code := runLatency(context.Background(), args, "dev", &stdout, &stderr, measure); code != 0 || !strings.Contains(stdout.String(), "pas un RTT ICMP") {
		t.Fatalf("missing method explanation: code=%d stdout=%q", code, stdout.String())
	}
	if code := runLatency(context.Background(), args, "dev", failingWriter{}, &stderr, measure); code != 1 {
		t.Fatalf("output failure ignored: code=%d", code)
	}
}

func TestLatencyCancellationCode(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := runLatency(context.Background(), []string{"--target", "127.0.0.1:8765"}, "dev", &stdout, &stderr,
		func(context.Context, latency.Options) (latency.Report, error) {
			return latency.Report{}, context.Canceled
		})
	if code != 130 || stdout.Len() != 0 {
		t.Fatalf("canceled batch treated as complete: code=%d stdout=%q", code, stdout.String())
	}
}
