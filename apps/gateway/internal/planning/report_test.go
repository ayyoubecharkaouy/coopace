package planning

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"strings"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/buildinfo"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestSimulationReportDistinguishesDeclaredAssumptionsFromAuthority(t *testing.T) {
	for _, consent := range []bool{false, true} {
		data := sampleScenario
		if consent {
			data = strings.Replace(data, `"local_consent":false`, `"local_consent":true`, 1)
		}
		before := time.Now().UTC()
		report, err := Evaluate(context.Background(), strings.NewReader(data), "test-version")
		if err != nil || report.EvaluatedAt.Before(before) || report.EvaluatedAt.After(time.Now().UTC()) || report.OS == "" || report.Architecture == "" {
			t.Fatalf("report metadata invalid: %+v, %v", report, err)
		}
		var output bytes.Buffer
		if err := WriteJSON(&output, report); err != nil {
			t.Fatal(err)
		}
		var decoded struct {
			Schema     int                       `json:"schema_version"`
			Kind       string                    `json:"kind"`
			Version    string                    `json:"coopace_version"`
			Mode       string                    `json:"mode"`
			Basis      string                    `json:"basis"`
			Authorized *bool                     `json:"execution_authorized"`
			Reference  *string                   `json:"reference"`
			Scenario   scenarioDocument          `json:"scenario"`
			Digest     string                    `json:"scenario_sha256"`
			Size       int                       `json:"scenario_bytes"`
			Decision   core.CakePlanningDecision `json:"decision"`
		}
		if err := json.Unmarshal(output.Bytes(), &decoded); err != nil {
			t.Fatal(err)
		}
		if decoded.Schema != 1 || decoded.Kind != "static_cake_plan" || decoded.Version != "test-version" || decoded.Mode != "simulation" || decoded.Basis != "declared_scenario" || decoded.Authorized == nil || *decoded.Authorized {
			t.Fatalf("simulation became an authorization: %s", output.Bytes())
		}
		if decoded.Scenario.Checks.LocalConsent != consent || decoded.Digest != report.Scenario.SHA256 || decoded.Size != len(data) {
			t.Fatal("declared scenario provenance changed")
		}
		if consent {
			if decoded.Decision != core.CakePlanProposeReference || decoded.Reference == nil || *decoded.Reference != string(core.CakeReferenceIPv4LabV1) {
				t.Fatal("proposal missing")
			}
		} else if decoded.Decision != core.CakePlanAbstain || decoded.Reference != nil {
			t.Fatal("abstention invented a reference")
		}
	}
}

type failedWriter struct{}

func (failedWriter) Write([]byte) (int, error) { return 0, io.ErrClosedPipe }

func TestPlanJSONPreservesUnavailableAndKnownBuildProvenance(t *testing.T) {
	report, err := Evaluate(context.Background(), strings.NewReader(sampleScenario), "test")
	if err != nil {
		t.Fatal(err)
	}
	for _, modified := range []*bool{nil, new(bool), func() *bool { value := true; return &value }()} {
		report.Build = buildinfo.Info{Modified: modified}
		var output bytes.Buffer
		if err := WriteJSON(&output, report); err != nil {
			t.Fatal(err)
		}
		var data struct {
			Build map[string]json.RawMessage `json:"build"`
		}
		if err := json.Unmarshal(output.Bytes(), &data); err != nil {
			t.Fatal(err)
		}
		for _, field := range []string{"go_version", "vcs", "vcs_revision"} {
			if string(data.Build[field]) != "null" {
				t.Fatalf("missing %s was fabricated", field)
			}
		}
		want := "null"
		if modified != nil {
			want = "false"
			if *modified {
				want = "true"
			}
		}
		if string(data.Build["vcs_modified"]) != want {
			t.Fatal("build state lost")
		}
	}
	if err := WriteJSON(failedWriter{}, report); err == nil {
		t.Fatal("writer error ignored")
	}
}
