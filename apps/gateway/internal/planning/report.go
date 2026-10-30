package planning

import (
	"context"
	"encoding/json"
	"io"
	"runtime"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/buildinfo"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

type Report struct {
	Version      string
	OS           string
	Architecture string
	EvaluatedAt  time.Time
	Build        buildinfo.Info
	Scenario     Scenario
	Plan         core.CakePlan
}

func Evaluate(ctx context.Context, input io.Reader, version string) (Report, error) {
	scenario, err := ReadScenario(ctx, input)
	if err != nil {
		return Report{}, err
	}
	plan, err := core.PlanStaticCake(scenario.Input)
	if err != nil {
		return Report{}, err
	}
	if err := ctx.Err(); err != nil {
		return Report{}, err
	}
	return Report{Version: version, OS: runtime.GOOS, Architecture: runtime.GOARCH, EvaluatedAt: time.Now().UTC(),
		Build: buildinfo.Local(), Scenario: scenario, Plan: plan}, nil
}

func optional(value string) *string {
	if value == "" {
		return nil
	}
	return &value
}

func WriteJSON(output io.Writer, report Report) error {
	value := struct {
		SchemaVersion       int                       `json:"schema_version"`
		Kind                string                    `json:"kind"`
		Version             string                    `json:"coopace_version"`
		OS                  string                    `json:"os"`
		Architecture        string                    `json:"architecture"`
		EvaluatedAt         time.Time                 `json:"evaluated_at"`
		Mode                string                    `json:"mode"`
		Basis               string                    `json:"basis"`
		ExecutionAuthorized bool                      `json:"execution_authorized"`
		ScenarioSHA256      string                    `json:"scenario_sha256"`
		ScenarioBytes       int                       `json:"scenario_bytes"`
		Scenario            scenarioDocument          `json:"scenario"`
		Decision            core.CakePlanningDecision `json:"decision"`
		Reference           *string                   `json:"reference"`
		Reasons             []core.CakePlanningReason `json:"reasons"`
		Build               struct {
			GoVersion *string `json:"go_version"`
			VCS       *string `json:"vcs"`
			Revision  *string `json:"vcs_revision"`
			Modified  *bool   `json:"vcs_modified"`
		} `json:"build"`
	}{SchemaVersion: 1, Kind: "static_cake_plan", Version: report.Version, OS: report.OS, Architecture: report.Architecture,
		EvaluatedAt: report.EvaluatedAt.UTC(), Mode: "simulation", Basis: "declared_scenario", ExecutionAuthorized: false,
		ScenarioSHA256: report.Scenario.SHA256, ScenarioBytes: report.Scenario.Bytes, Scenario: exportScenario(report.Scenario.Input),
		Decision: report.Plan.Decision, Reference: optional(string(report.Plan.Reference)), Reasons: report.Plan.Reasons}
	value.Build.GoVersion, value.Build.VCS = optional(report.Build.GoVersion), optional(report.Build.VCS)
	value.Build.Revision, value.Build.Modified = optional(report.Build.Revision), report.Build.Modified
	encoder := json.NewEncoder(output)
	encoder.SetIndent("", "  ")
	return encoder.Encode(value)
}
