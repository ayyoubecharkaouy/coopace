package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/recovery"
	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/snapshot"
)

func recoveryCLIFixture(t *testing.T) (string, string, snapshot.Report) {
	t.Helper()
	data, err := os.ReadFile("../../../../docs/examples/queue-snapshot-noqueue.json")
	if err != nil {
		t.Fatal(err)
	}
	directory := t.TempDir()
	before, after := filepath.Join(directory, "before.json"), filepath.Join(directory, "after.json")
	if err := os.WriteFile(before, data, 0600); err != nil {
		t.Fatal(err)
	}
	imported, err := snapshot.Read(context.Background(), bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	source := imported.Snapshot
	delta := 3 * time.Second
	source.StartedAt = source.StartedAt.Add(delta)
	source.FinishedAt = source.FinishedAt.Add(delta)
	for index := range source.Readings {
		reading := &source.Readings[index]
		reading.StartedAt = reading.StartedAt.Add(delta)
		reading.FinishedAt = reading.FinishedAt.Add(delta)
		if proof := reading.ClassesTextFallback; proof != nil {
			proof.StartedAt = proof.StartedAt.Add(delta)
			proof.FinishedAt = proof.FinishedAt.Add(delta)
		}
	}
	report := snapshot.Report{Version: "test", OS: "linux", Architecture: "amd64", Snapshot: source}
	var output bytes.Buffer
	if err := snapshot.WriteJSON(&output, report); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(after, output.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}
	return before, after, report
}

func TestRecoveryPublicCommandsPlanAndCheckFilesWithoutNetworkCollection(t *testing.T) {
	before, after, _ := recoveryCLIFixture(t)
	for _, test := range []struct {
		args     []string
		decision string
		code     int
	}{
		{[]string{"restore-plan", "--snapshot", before, "--json"}, "candidate_for_lab_validation", 0},
		{[]string{"restore-check", "--before", before, "--after", after, "--json"}, "selected_state_matches", 0},
		{[]string{"restore-check", "--before", before, "--after", before, "--json"}, "indeterminate", 3},
		{[]string{"restore-check", "--before", after, "--after", before, "--json"}, "indeterminate", 3},
	} {
		var stdout, stderr bytes.Buffer
		code := run(context.Background(), test.args, "test", &stdout, &stderr, neverCollect(t))
		if code != test.code || stderr.Len() != 0 {
			t.Fatalf("command failed: %v code %d %s", test.args, code, &stderr)
		}
		var report recovery.Report
		if err := json.Unmarshal(stdout.Bytes(), &report); err != nil {
			t.Fatal(err)
		}
		if report.Decision != test.decision || report.ExecutionAuthorized || report.NetworkChangesExecuted || report.Restoration != "not_implemented" || report.NamespaceContinuity != "unverified" || len(report.BeforeSHA256) != 64 {
			t.Fatalf("misleading result: %+v", report)
		}
	}
	data, _ := os.ReadFile(after)
	data = bytes.Replace(data, []byte(`"kind": "noqueue"`), []byte(`"kind": "cake"`), 1)
	if err := os.WriteFile(after, data, 0600); err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{{"restore-plan", "--snapshot", after}, {"restore-check", "--before", before, "--after", after}} {
		var stdout, stderr bytes.Buffer
		if code := run(context.Background(), args, "test", &stdout, &stderr, neverCollect(t)); code != 3 || stdout.Len() == 0 {
			t.Fatalf("unsupported state accepted: %d %s", code, &stderr)
		}
	}
}

func TestRecoveryCommandsCanCollectOneExplicitInterface(t *testing.T) {
	before, _, observed := recoveryCLIFixture(t)
	for _, command := range []string{"restore-plan", "restore-check"} {
		calls := 0
		collect := func(_ context.Context, version, name string) (snapshot.Report, error) {
			calls++
			if name != "lab0" || version != "test" {
				t.Fatal("wrong live request")
			}
			return observed, nil
		}
		args := []string{"--interface", "lab0", "--json"}
		if command == "restore-check" {
			args = append(args, "--before", before)
		}
		var stdout, stderr bytes.Buffer
		if code := runRecovery(context.Background(), command, args, "test", &stdout, &stderr, collect); code != 0 || calls != 1 {
			t.Fatalf("live command failed: %d %s", code, &stderr)
		}
	}
}

func TestSnapshotOutputFeedsRecoveryCommandsWithoutOverwritingReference(t *testing.T) {
	before, _, report := recoveryCLIFixture(t)
	path := filepath.Join(t.TempDir(), "checkpoint.json")
	collect := func(context.Context, string, string) (snapshot.Report, error) { return report, nil }
	var stdout, stderr bytes.Buffer
	args := []string{"--interface", "lab0", "--output", path, "--json"}
	if code := runSnapshot(context.Background(), args, "test", &stdout, &stderr, collect); code != 0 {
		t.Fatalf("snapshot save failed: %d %s", code, &stderr)
	}
	data, err := os.ReadFile(path)
	if err != nil || !bytes.Equal(data, stdout.Bytes()) {
		t.Fatalf("saved report differs from JSON stdout: %v", err)
	}
	stdout.Reset()
	if code := run(context.Background(), []string{"restore-plan", "--snapshot", path}, "test", &stdout, &stderr, neverCollect(t)); code != 0 {
		t.Fatalf("saved reference not usable: %d %s", code, &stderr)
	}
	stdout.Reset()
	if code := run(context.Background(), []string{"restore-check", "--before", before, "--after", path}, "test", &stdout, &stderr, neverCollect(t)); code != 0 {
		t.Fatalf("saved later observation not usable: %d %s", code, &stderr)
	}
	stdout.Reset()
	if code := runSnapshot(context.Background(), args, "test", &stdout, &stderr, collect); code != 1 || stdout.Len() != 0 {
		t.Fatal("existing checkpoint overwritten")
	}
	unchanged, _ := os.ReadFile(path)
	if !bytes.Equal(data, unchanged) {
		t.Fatal("checkpoint changed after refused overwrite")
	}
}

func TestRecoveryArgumentsHelpAndCancellationNeverCollect(t *testing.T) {
	collect := func(context.Context, string, string) (snapshot.Report, error) {
		t.Fatal("unexpected live collection")
		return snapshot.Report{}, nil
	}
	for _, test := range []struct {
		command string
		args    []string
	}{
		{"restore-plan", nil}, {"restore-plan", []string{"--snapshot", "x", "--interface", "lab0"}}, {"restore-plan", []string{"--interface", "-bad"}},
		{"restore-plan", []string{"--interface", "lab0", "--apply"}}, {"restore-plan", []string{"--snapshot", "x", "extra"}},
		{"restore-check", []string{"--before", "x"}}, {"restore-check", []string{"--after", "x"}}, {"restore-check", []string{"--before", "x", "--after", "y", "--interface", "lab0"}},
	} {
		var stdout, stderr bytes.Buffer
		if code := runRecovery(context.Background(), test.command, test.args, "test", &stdout, &stderr, collect); code != 2 || stdout.Len() != 0 {
			t.Fatalf("invalid arguments accepted: %v code %d", test, code)
		}
	}
	for _, command := range []string{"restore-plan", "restore-check"} {
		var stdout, stderr bytes.Buffer
		if code := run(context.Background(), []string{command, "--help"}, "test", &stdout, &stderr, neverCollect(t)); code != 0 || !strings.Contains(stdout.String(), command) {
			t.Fatal("missing recovery help")
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	var stdout, stderr bytes.Buffer
	if code := runRecovery(ctx, "restore-plan", []string{"--snapshot", "missing"}, "test", &stdout, &stderr, collect); code != 130 || stdout.Len() != 0 {
		t.Fatal("initial cancellation ignored")
	}
}

func TestRecoveryInputAndOutputErrorsPropagate(t *testing.T) {
	before, _, _ := recoveryCLIFixture(t)
	directory := t.TempDir()
	bad := filepath.Join(directory, "bad.json")
	os.WriteFile(bad, []byte("{}"), 0600)
	large := filepath.Join(directory, "large.json")
	os.WriteFile(large, []byte(strings.Repeat(" ", snapshot.MaxImportBytes+1)), 0600)
	paths := []string{directory, filepath.Join(directory, "missing"), bad, large}
	link := filepath.Join(directory, "link.json")
	if err := os.Symlink(before, link); err == nil {
		paths = append(paths, link)
	}
	for _, path := range paths {
		var stdout, stderr bytes.Buffer
		if code := run(context.Background(), []string{"restore-plan", "--snapshot", path}, "test", &stdout, &stderr, neverCollect(t)); code != 1 || stdout.Len() != 0 || stderr.Len() == 0 {
			t.Fatalf("invalid file accepted: %s", path)
		}
	}
	for _, format := range [][]string{nil, {"--json"}} {
		var stderr bytes.Buffer
		args := append([]string{"restore-plan", "--snapshot", before}, format...)
		if code := run(context.Background(), args, "test", failedWriter{}, &stderr, neverCollect(t)); code != 1 {
			t.Fatal("output error ignored")
		}
	}
}
