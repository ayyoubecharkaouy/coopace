// Package recovery assembles read-only queue recovery assessments. It never
// executes a plan, and comparison is limited to the selected snapshot fields.
package recovery

import (
	"context"
	"encoding/json"
	"io"
	"runtime"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/buildinfo"
	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/snapshot"
	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

type Report struct {
	SchemaVersion          int       `json:"schema_version"`
	Kind                   string    `json:"kind"`
	Version                string    `json:"coopace_version"`
	CollectedAt            time.Time `json:"evaluated_at"`
	GoVersion              string    `json:"go_version"`
	OS                     string    `json:"evaluator_os"`
	Architecture           string    `json:"evaluator_architecture"`
	Mode                   string    `json:"mode"`
	Decision               string    `json:"decision"`
	Profile                string    `json:"profile,omitempty"`
	Interface              string    `json:"interface"`
	BeforeSHA256           string    `json:"before_sha256"`
	AfterSHA256            *string   `json:"after_sha256"`
	Reasons                []string  `json:"reasons"`
	Steps                  []string  `json:"planned_steps"`
	Requirements           []string  `json:"unverified_requirements"`
	ExecutionAuthorized    bool      `json:"execution_authorized"`
	NetworkChangesExecuted bool      `json:"network_changes_executed"`
	Restoration            string    `json:"restoration"`
	TrafficCoverage        string    `json:"traffic_coverage"`
	NamespaceContinuity    string    `json:"namespace_continuity"`
}

func base(version string, before snapshot.Imported) Report {
	return Report{SchemaVersion: 1, Version: version, CollectedAt: time.Now().UTC(), GoVersion: buildinfo.Local().GoVersion,
		OS: runtime.GOOS, Architecture: runtime.GOARCH, Mode: "read_only_assessment", Interface: before.Snapshot.Interface.Name,
		BeforeSHA256: before.SHA256, Steps: []string{}, Requirements: []string{}, Restoration: "not_implemented", TrafficCoverage: "unverified", NamespaceContinuity: "unverified"}
}

func Plan(ctx context.Context, before snapshot.Imported, version string) (Report, error) {
	if err := ctx.Err(); err != nil {
		return Report{}, err
	}
	assessment, err := linux.AssessQueueRecovery(before.Snapshot)
	if err != nil {
		return Report{}, err
	}
	report := base(version, before)
	report.Kind, report.Decision, report.Profile, report.Reasons = "queue_recovery_plan", "refused", assessment.Profile, assessment.Reasons
	if assessment.Candidate {
		report.Decision = "candidate_for_lab_validation"
		report.Steps = []string{"capture_and_compare_initial_state", "record_owned_root_installation", "recheck_namespace_link_and_owned_root", "remove_only_owned_root", "capture_and_compare_selected_initial_state"}
		report.Requirements = []string{"fresh_owned_lab_resources", "verified_namespace_continuity", "pinned_tools_and_durable_ownership_journal", "independent_recovery_supervisor", "native_normal_and_crash_restore_tests", "real_gateway_traffic_coverage_and_consent"}
	}
	if err := ctx.Err(); err != nil {
		return Report{}, err
	}
	return report, nil
}

func Check(ctx context.Context, before, after snapshot.Imported, version string) (Report, error) {
	if err := ctx.Err(); err != nil {
		return Report{}, err
	}
	comparison, err := linux.CompareQueueRecovery(before.Snapshot, after.Snapshot)
	if err != nil {
		return Report{}, err
	}
	report := base(version, before)
	report.Kind, report.Decision, report.Reasons = "queue_recovery_check", comparison.Decision, comparison.Reasons
	report.AfterSHA256 = &after.SHA256
	if before.SHA256 == after.SHA256 {
		report.Decision, report.Reasons = "indeterminate", []string{"distinct_snapshot_files_required"}
	}
	if err := ctx.Err(); err != nil {
		return Report{}, err
	}
	return report, nil
}

func WriteJSON(output io.Writer, report Report) error {
	encoder := json.NewEncoder(output)
	encoder.SetIndent("", "  ")
	return encoder.Encode(report)
}
