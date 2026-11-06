// Package snapshot assembles a local queue observation, not a restorable backup.
package snapshot

import (
	"context"
	"encoding/json"
	"io"
	"runtime"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/buildinfo"
	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

type Report struct {
	Version      string
	OS           string
	Architecture string
	Build        buildinfo.Info
	Snapshot     linux.GatewayQueueSnapshot
}

func ValidateInterface(name string) error {
	return linux.ValidateGatewaySnapshotInterfaceName(name)
}

func Local(ctx context.Context, version, name string) (Report, error) {
	observation, err := linux.SnapshotGatewayQueues(ctx, name)
	if err != nil {
		return Report{}, err
	}
	return Report{Version: version, OS: runtime.GOOS, Architecture: runtime.GOARCH, Build: buildinfo.Local(), Snapshot: observation}, nil
}

// WriteJSON preserves producer options. Unlike inspect, this export can contain
// hardware addresses and filter-specific addresses, identifiers or configuration.
func WriteJSON(output io.Writer, report Report) error {
	optional := func(value string) *string {
		if value == "" {
			return nil
		}
		return &value
	}
	data := struct {
		SchemaVersion int    `json:"schema_version"`
		Kind          string `json:"kind"`
		Version       string `json:"coopace_version"`
		OS            string `json:"os"`
		Architecture  string `json:"architecture"`
		Build         struct {
			GoVersion *string `json:"go_version"`
			VCS       *string `json:"vcs"`
			Revision  *string `json:"vcs_revision"`
			Modified  *bool   `json:"vcs_modified"`
		} `json:"build"`
		Scope           string                     `json:"scope"`
		Mode            string                     `json:"mode"`
		Partial         bool                       `json:"partial"`
		Atomic          bool                       `json:"atomic"`
		Completeness    string                     `json:"completeness"`
		TrafficCoverage string                     `json:"traffic_coverage"`
		Restoration     string                     `json:"restoration"`
		Snapshot        linux.GatewayQueueSnapshot `json:"snapshot"`
	}{SchemaVersion: 1, Kind: "gateway_queue_snapshot", Version: report.Version, OS: report.OS, Architecture: report.Architecture,
		Scope: "process_network_namespace", Mode: "read_only", Partial: report.Snapshot.Partial(), Atomic: false,
		Completeness: "selected_queries_only", TrafficCoverage: "unverified", Restoration: "not_implemented", Snapshot: report.Snapshot}
	data.Build.GoVersion, data.Build.VCS, data.Build.Revision, data.Build.Modified = optional(report.Build.GoVersion), optional(report.Build.VCS), optional(report.Build.Revision), report.Build.Modified
	encoder := json.NewEncoder(output)
	encoder.SetIndent("", "  ")
	return encoder.Encode(data)
}
