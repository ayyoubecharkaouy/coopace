package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/diagnostic"
	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/planning"
)

const planScenario = `{"schema_version":1,"kind":"static_cake_scenario","scope":"owned_ipv4_lab","queue":"unconfigured","checks":{"reference_validated":true,"local_consent":true,"path_validated":true,"ownership_validated":true,"supervision_ready":true,"permissions_checked":true}}`

func neverCollect(t *testing.T) func(context.Context, string) (diagnostic.Report, error) {
	return func(context.Context, string) (diagnostic.Report, error) {
		t.Fatal("simulation collected a network inventory")
		return diagnostic.Report{}, nil
	}
}

func TestPlanCommandDecisionsAreSuccessfulOfflineSimulations(t *testing.T) {
	for _, tt := range []struct{ queue, scope, decision string }{
		{"unconfigured", "owned_ipv4_lab", "propose_reference"}, {"reference_conformant", "owned_ipv4_lab", "keep_reference"},
		{"other_configuration", "owned_ipv4_lab", "abstain"}, {"unconfigured", "existing_gateway", "abstain"},
	} {
		t.Run(tt.decision+tt.scope, func(t *testing.T) {
			dir := t.TempDir()
			path := filepath.Join(dir, "scénario local.json")
			data := strings.Replace(strings.Replace(planScenario, "unconfigured", tt.queue, 1), "owned_ipv4_lab", tt.scope, 1)
			if err := os.WriteFile(path, []byte(data), 0o600); err != nil {
				t.Fatal(err)
			}
			var stdout, stderr bytes.Buffer
			if code := run(context.Background(), []string{"plan", "--scenario", path, "--json"}, "test", &stdout, &stderr, neverCollect(t)); code != 0 || stderr.Len() != 0 {
				t.Fatalf("simulation failed: code=%d %s", code, &stderr)
			}
			var value struct {
				Decision   string `json:"decision"`
				Authorized bool   `json:"execution_authorized"`
			}
			if err := json.Unmarshal(stdout.Bytes(), &value); err != nil || value.Decision != tt.decision || value.Authorized {
				t.Fatalf("invalid JSON output: %s, %v", stdout.Bytes(), err)
			}
			stdout.Reset()
			if code := run(context.Background(), []string{"plan", "--scenario", path}, "test", &stdout, &stderr, neverCollect(t)); code != 0 || !strings.Contains(stdout.String(), "Mode simulation") || !strings.Contains(stdout.String(), "SHA-256") {
				t.Fatalf("invalid text output: %s", &stdout)
			}
			after, err := os.ReadFile(path)
			files, _ := os.ReadDir(dir)
			if err != nil || string(after) != data || len(files) != 1 {
				t.Fatal("simulation modified its scenario or created files")
			}
		})
	}
}

func TestPlanArgumentsHelpAndInvalidFilesNeverCollectOrPrintAPlan(t *testing.T) {
	for _, args := range [][]string{{"plan"}, {"plan", "--scenario"}, {"plan", "--scenario", "missing", "extra"}, {"plan", "--apply"}} {
		var stdout, stderr bytes.Buffer
		if code := run(context.Background(), args, "test", &stdout, &stderr, neverCollect(t)); code != 2 || stdout.Len() != 0 {
			t.Fatalf("invalid arguments accepted: %v", args)
		}
	}
	var stdout, stderr bytes.Buffer
	if code := run(context.Background(), []string{"plan", "--help"}, "test", &stdout, &stderr, neverCollect(t)); code != 0 || !strings.Contains(stdout.String(), "--scenario") {
		t.Fatal("plan help failed")
	}
	dir := t.TempDir()
	bad := filepath.Join(dir, "invalid.json")
	os.WriteFile(bad, []byte("{}"), 0o600)
	large := filepath.Join(dir, "large.json")
	os.WriteFile(large, []byte(strings.Repeat(" ", planning.MaxScenarioBytes+1)), 0o600)
	paths := []string{filepath.Join(dir, "missing"), dir, bad, large}
	link := filepath.Join(dir, "link.json")
	if err := os.Symlink(bad, link); err == nil {
		paths = append(paths, link)
	}
	for _, path := range paths {
		stdout.Reset()
		stderr.Reset()
		if code := run(context.Background(), []string{"plan", "--scenario", path, "--json"}, "test", &stdout, &stderr, neverCollect(t)); code != 1 || stdout.Len() != 0 || stderr.Len() == 0 {
			t.Fatalf("invalid file printed a plan: %s", path)
		}
	}
}

func TestPlanCancellationAndOutputErrorsPropagate(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	var stdout, stderr bytes.Buffer
	if code := run(ctx, []string{"plan", "--scenario", "missing"}, "test", &stdout, &stderr, neverCollect(t)); code != 130 || stdout.Len() != 0 {
		t.Fatal("cancelled plan read a file or succeeded")
	}
	path := filepath.Join(t.TempDir(), "scenario.json")
	os.WriteFile(path, []byte(planScenario), 0o600)
	for _, format := range [][]string{nil, {"--json"}} {
		args := append([]string{"plan", "--scenario", path}, format...)
		if code := run(context.Background(), args, "test", failedWriter{}, &stderr, neverCollect(t)); code != 1 {
			t.Fatal("output failure ignored")
		}
	}
}
