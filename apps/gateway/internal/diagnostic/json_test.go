package diagnostic

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/buildinfo"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestInventoryJSONKeepsMissingFalseAndKnownEmptyDistinct(t *testing.T) {
	report := Report{Version: "test", OS: "linux", Architecture: "amd64", CollectedAt: time.Date(2026, 10, 26, 12, 0, 0, 0, time.FixedZone("test", 3600)),
		Inventory: core.GatewayInventory{
			Interfaces:     core.GatewayReading[[]core.GatewayInterface]{Available: true},
			IPv4Forwarding: core.GatewayReading[bool]{Available: true, Value: false},
			IPv6Forwarding: core.GatewayReading[bool]{Value: true, Reason: "unreadable"},
			Queues:         core.GatewayReading[[]core.GatewayQueue]{Value: []core.GatewayQueue{{Kind: "must-not-leak"}}},
		},
	}
	var output bytes.Buffer
	if err := WriteJSON(&output, report); err != nil {
		t.Fatal(err)
	}
	type rawReading struct {
		Available bool            `json:"available"`
		Value     json.RawMessage `json:"value"`
		Reason    string          `json:"reason"`
	}
	var decoded struct {
		Schema      int                        `json:"schema_version"`
		Kind        string                     `json:"kind"`
		Partial     bool                       `json:"partial"`
		CollectedAt time.Time                  `json:"collected_at"`
		Build       map[string]json.RawMessage `json:"build"`
		Inventory   map[string]json.RawMessage `json:"inventory"`
	}
	if err := json.Unmarshal(output.Bytes(), &decoded); err != nil {
		t.Fatal(err)
	}
	reading := func(name string) rawReading {
		var value rawReading
		if err := json.Unmarshal(decoded.Inventory[name], &value); err != nil {
			t.Fatal(err)
		}
		return value
	}
	interfaces, ipv4, ipv6 := reading("interfaces"), reading("ipv4_forwarding"), reading("ipv6_global_forwarding")
	if decoded.Schema != 1 || decoded.Kind != "gateway_inventory" || !decoded.Partial || decoded.CollectedAt.Hour() != 11 || decoded.CollectedAt.Location() != time.UTC {
		t.Fatalf("wrong metadata: %+v", decoded)
	}
	if string(interfaces.Value) != "[]" || !interfaces.Available {
		t.Fatal("known empty interfaces became unavailable/null")
	}
	if string(ipv4.Value) != "false" || !ipv4.Available {
		t.Fatal("known false flag lost")
	}
	if string(ipv6.Value) != "null" || ipv6.Available || ipv6.Reason != "unreadable" {
		t.Fatal("missing flag became enabled/disabled")
	}
	if string(decoded.Build["vcs_modified"]) != "null" || string(decoded.Build["vcs_revision"]) != "null" || strings.Contains(output.String(), "must-not-leak") {
		t.Fatal("missing provenance or unavailable data was fabricated/exported")
	}
}

func TestCompleteInventoryDoesNotClaimCoverageOrRestoration(t *testing.T) {
	known := core.GatewayReading[bool]{Available: true, Value: true}
	modified := true
	report := Report{Build: buildinfo.Info{GoVersion: "go-test", VCS: "git", Revision: "revision", Modified: &modified}, Inventory: core.GatewayInventory{
		Interfaces:     core.GatewayReading[[]core.GatewayInterface]{Available: true, Value: []core.GatewayInterface{{Name: "eth0", Index: 2, MTU: 1500, Up: true}}},
		IPv4Forwarding: known, IPv6Forwarding: known, NetAdmin: known,
		IPv4Defaults: core.GatewayReading[[]core.GatewayDefaultRoute]{Available: true, Value: []core.GatewayDefaultRoute{{Table: "main", Kind: "unicast", Interfaces: []string{"eth0"}}}},
		IPv6Defaults: core.GatewayReading[[]core.GatewayDefaultRoute]{Available: true},
		Queues:       core.GatewayReading[[]core.GatewayQueue]{Available: true, Value: []core.GatewayQueue{{Interface: "eth0", Kind: "cake", Root: true}}},
		Tools:        []core.GatewayTool{{Name: "ip", Available: true, Path: "/tools/ip"}, {Name: "nft", Path: "must-not-leak"}},
	}}
	var output bytes.Buffer
	if err := WriteJSON(&output, report); err != nil {
		t.Fatal(err)
	}
	var decoded jsonReport
	if err := json.Unmarshal(output.Bytes(), &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded.Partial || decoded.TrafficCoverage != "unverified" || decoded.Restoration != "not_implemented" || decoded.Mode != "read_only" || decoded.Scope != "process_network_namespace" {
		t.Fatal("inventory completeness became an intervention/coverage decision")
	}
	if decoded.Build.Revision == nil || *decoded.Build.Revision != "revision" || decoded.Build.Modified == nil || !*decoded.Build.Modified || decoded.Inventory.Queues.Value == nil || (*decoded.Inventory.Queues.Value)[0].Kind != "cake" || decoded.Inventory.Tools[1].Path != nil || strings.Contains(output.String(), "must-not-leak") {
		t.Fatal("report fields lost or an unavailable tool path was exported")
	}
}

type failedJSONWriter struct{}

func (failedJSONWriter) Write([]byte) (int, error) { return 0, io.ErrClosedPipe }

func TestInventoryJSONPropagatesWriteFailure(t *testing.T) {
	if err := WriteJSON(failedJSONWriter{}, Report{}); !errors.Is(err, io.ErrClosedPipe) {
		t.Fatalf("write failure ignored: %v", err)
	}
}
