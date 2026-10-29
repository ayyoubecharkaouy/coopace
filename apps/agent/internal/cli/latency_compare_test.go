package cli

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/latency"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func comparisonFile(t *testing.T, condition string, sample core.LatencySample) string {
	t.Helper()
	started := time.Date(2026, 10, 29, 12, 0, 0, 0, time.UTC)
	summary, err := core.SummarizeLatency([]core.LatencySample{sample})
	if err != nil {
		t.Fatal(err)
	}
	report := latency.Report{Options: latency.Options{Target: "127.0.0.1:8765", Count: 1, Timeout: time.Second, Condition: condition}, StartedAt: started, FinishedAt: started.Add(time.Second), Attempts: []latency.Attempt{{StartedAt: started, Sample: sample}}, Summary: summary}
	var output bytes.Buffer
	if err := latency.WriteJSON(&output, report, "test"); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), condition+".json")
	if err := os.WriteFile(path, output.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestLatencyComparisonNeverProbesAndKeepsMissingValues(t *testing.T) {
	idle := comparisonFile(t, "idle", core.LatencySample{Duration: time.Millisecond})
	loaded := comparisonFile(t, "loaded", core.LatencySample{Failure: core.LatencyTimeout})
	args := []string{"compare", "--idle", idle, "--loaded", loaded}
	noProbe := func(context.Context, latency.Options) (latency.Report, error) {
		t.Fatal("comparison attempted a network probe")
		return latency.Report{}, nil
	}
	var stdout, stderr bytes.Buffer
	if code := runLatency(context.Background(), args, "test", &stdout, &stderr, noProbe); code != 0 {
		t.Fatalf("comparison failed: %d %s", code, &stderr)
	}
	for _, expected := range []string{"indisponible", "Échecs : repos=0, charge=1", "Aucun gain causal", "Aucun essai réseau lancé"} {
		if !strings.Contains(stdout.String(), expected) {
			t.Fatalf("missing %q", expected)
		}
	}
	loaded = comparisonFile(t, "loaded", core.LatencySample{Duration: 3 * time.Millisecond})
	args[len(args)-1] = loaded
	stdout.Reset()
	if code := runLatency(context.Background(), args, "test", &stdout, &stderr, noProbe); code != 0 || !strings.Contains(stdout.String(), "+2.000000") {
		t.Fatalf("missing millisecond difference: %d %s", code, &stdout)
	}
	if code := runLatency(context.Background(), args, "test", failingWriter{}, &stderr, noProbe); code != 1 {
		t.Fatal("comparison output failure ignored")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	stdout.Reset()
	if code := runLatency(ctx, args, "test", &stdout, &stderr, noProbe); code != 130 || stdout.Len() != 0 {
		t.Fatal("cancelled comparison treated as complete")
	}
}

func TestLatencyComparisonRejectsBadArgumentsAndFiles(t *testing.T) {
	for _, entry := range []struct {
		args []string
		code int
	}{
		{[]string{"--help"}, 0}, {nil, 2}, {[]string{"--idle", "missing"}, 2}, {[]string{"--idle", "missing", "--loaded", "also-missing"}, 1}, {[]string{"--idle", "a", "--loaded", "b", "extra"}, 2},
	} {
		var stdout, stderr bytes.Buffer
		if code := runLatencyCompare(context.Background(), entry.args, &stdout, &stderr); code != entry.code {
			t.Errorf("args %v: got %d want %d", entry.args, code, entry.code)
		}
	}
	if _, err := openBaseline(t.TempDir()); err == nil {
		t.Fatal("directory accepted as a baseline file")
	}
}
