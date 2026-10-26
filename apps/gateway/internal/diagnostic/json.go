package diagnostic

import (
	"encoding/json"
	"io"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

// This schema describes a local inventory. It is neither the group protocol nor
// the latency export, and cannot be replayed to restore system configuration.
type jsonReading[T any] struct {
	Available bool    `json:"available"`
	Value     *T      `json:"value"`
	Reason    *string `json:"reason,omitempty"`
}

type jsonInterface struct {
	Name     string `json:"name"`
	Index    int    `json:"index"`
	MTU      int    `json:"mtu"`
	Up       bool   `json:"administratively_up"`
	Loopback bool   `json:"loopback"`
}

type jsonRoute struct {
	Table             string   `json:"table"`
	Kind              string   `json:"kind"`
	Interfaces        []string `json:"interfaces"`
	UnresolvedNexthop bool     `json:"unresolved_nexthop"`
}

type jsonQueue struct {
	Interface string `json:"interface"`
	Kind      string `json:"kind"`
	Handle    string `json:"handle"`
	Parent    string `json:"parent"`
	Root      bool   `json:"root"`
}

type jsonTool struct {
	Name      string  `json:"name"`
	Available bool    `json:"available"`
	Path      *string `json:"path"`
}

type jsonBuild struct {
	GoVersion *string `json:"go_version"`
	VCS       *string `json:"vcs"`
	Revision  *string `json:"vcs_revision"`
	Modified  *bool   `json:"vcs_modified"`
}

type jsonInventory struct {
	Interfaces     jsonReading[[]jsonInterface] `json:"interfaces"`
	IPv4Forwarding jsonReading[bool]            `json:"ipv4_forwarding"`
	IPv6Forwarding jsonReading[bool]            `json:"ipv6_global_forwarding"`
	NetAdmin       jsonReading[bool]            `json:"effective_cap_net_admin"`
	IPv4Defaults   jsonReading[[]jsonRoute]     `json:"ipv4_default_routes"`
	IPv6Defaults   jsonReading[[]jsonRoute]     `json:"ipv6_default_routes"`
	Queues         jsonReading[[]jsonQueue]     `json:"queues"`
	Tools          []jsonTool                   `json:"tools"`
}

type jsonReport struct {
	SchemaVersion   int           `json:"schema_version"`
	Kind            string        `json:"kind"`
	Version         string        `json:"coopace_version"`
	OS              string        `json:"os"`
	Architecture    string        `json:"architecture"`
	CollectedAt     time.Time     `json:"collected_at"`
	Build           jsonBuild     `json:"build"`
	Scope           string        `json:"scope"`
	Mode            string        `json:"mode"`
	Partial         bool          `json:"partial"`
	TrafficCoverage string        `json:"traffic_coverage"`
	Restoration     string        `json:"restoration"`
	Inventory       jsonInventory `json:"inventory"`
}

func exportReading[A, B any](source core.GatewayReading[A], value B) jsonReading[B] {
	if !source.Available {
		reason := source.Reason
		if reason == "" {
			reason = "not_collected"
		}
		return jsonReading[B]{Reason: &reason}
	}
	return jsonReading[B]{Available: true, Value: &value}
}

func optionalString(value string) *string {
	if value == "" {
		return nil
	}
	return &value
}

// WriteJSON writes only the selected report fields to the supplied writer.
// Unavailable readings have null values; known empty collections stay arrays.
func WriteJSON(output io.Writer, report Report) error {
	source := report.Inventory
	interfaces := make([]jsonInterface, 0, len(source.Interfaces.Value))
	for _, item := range source.Interfaces.Value {
		interfaces = append(interfaces, jsonInterface{Name: item.Name, Index: item.Index, MTU: item.MTU, Up: item.Up, Loopback: item.Loopback})
	}
	queues := make([]jsonQueue, 0, len(source.Queues.Value))
	for _, item := range source.Queues.Value {
		queues = append(queues, jsonQueue{Interface: item.Interface, Kind: item.Kind, Handle: item.Handle, Parent: item.Parent, Root: item.Root})
	}
	tools := make([]jsonTool, 0, len(source.Tools))
	for _, item := range source.Tools {
		tool := jsonTool{Name: item.Name, Available: item.Available}
		if item.Available {
			tool.Path = optionalString(item.Path)
		}
		tools = append(tools, tool)
	}
	data := jsonReport{
		SchemaVersion: 1, Kind: "gateway_inventory", Version: report.Version, OS: report.OS, Architecture: report.Architecture, CollectedAt: report.CollectedAt.UTC(),
		Build: jsonBuild{GoVersion: optionalString(report.Build.GoVersion), VCS: optionalString(report.Build.VCS), Revision: optionalString(report.Build.Revision), Modified: report.Build.Modified},
		Scope: "process_network_namespace", Mode: "read_only", TrafficCoverage: "unverified", Restoration: "not_implemented",
		Partial: !source.Interfaces.Available || !source.IPv4Forwarding.Available || !source.IPv6Forwarding.Available || !source.NetAdmin.Available || !source.IPv4Defaults.Available || !source.IPv6Defaults.Available || !source.Queues.Available,
		Inventory: jsonInventory{
			Interfaces: exportReading(source.Interfaces, interfaces), IPv4Forwarding: exportReading(source.IPv4Forwarding, source.IPv4Forwarding.Value),
			IPv6Forwarding: exportReading(source.IPv6Forwarding, source.IPv6Forwarding.Value), NetAdmin: exportReading(source.NetAdmin, source.NetAdmin.Value),
			IPv4Defaults: exportReading(source.IPv4Defaults, exportRoutes(source.IPv4Defaults.Value)), IPv6Defaults: exportReading(source.IPv6Defaults, exportRoutes(source.IPv6Defaults.Value)),
			Queues: exportReading(source.Queues, queues), Tools: tools,
		},
	}
	encoder := json.NewEncoder(output)
	encoder.SetIndent("", "  ")
	return encoder.Encode(data)
}

func exportRoutes(source []core.GatewayDefaultRoute) []jsonRoute {
	result := make([]jsonRoute, 0, len(source))
	for _, item := range source {
		result = append(result, jsonRoute{Table: item.Table, Kind: item.Kind, Interfaces: append([]string{}, item.Interfaces...), UnresolvedNexthop: item.UnresolvedNexthop})
	}
	return result
}
