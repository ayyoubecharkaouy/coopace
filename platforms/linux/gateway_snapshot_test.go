package linux

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"reflect"
	"strings"
	"testing"
)

func snapshotTestSources() gatewaySnapshotSources {
	return gatewaySnapshotSources{
		interfaceByName: func(string) (*net.Interface, error) {
			return &net.Interface{Name: "eth0", Index: 2, MTU: 1500, Flags: net.FlagUp}, nil
		},
		lookPath: func(name string) (string, error) { return "/tools/" + name, nil },
		run: func(_ context.Context, _ string, args ...string) ([]byte, error) {
			if args[0] == "-j" && args[1] == "-d" {
				return []byte(`[{"ifindex":2,"ifname":"eth0","mtu":1500}]`), nil
			}
			return []byte(`[]`), nil
		},
	}
}

func TestQueueSnapshotQueriesOnlyExplicitInterfaceAndPreservesOptions(t *testing.T) {
	sources := snapshotTestSources()
	run := sources.run
	var calls [][]string
	sources.run = func(ctx context.Context, path string, args ...string) ([]byte, error) {
		calls = append(calls, append([]string{path}, args...))
		if args[3] == "qdisc" {
			return []byte(`[{"kind":"cake","options":{"ack-filter":"disabled","counter":18446744073709551615}}]`), nil
		}
		return run(ctx, path, args...)
	}
	report, err := collectGatewayQueueSnapshot(context.Background(), "eth0", sources)
	if err != nil || report.Partial() {
		t.Fatalf("snapshot failed: %v %+v", err, report)
	}
	want := [][]string{
		{"/tools/ip", "-j", "-d", "link", "show", "dev", "eth0"},
		{"/tools/tc", "-j", "-s", "-d", "qdisc", "show", "dev", "eth0"},
		{"/tools/tc", "-j", "-s", "-d", "class", "show", "dev", "eth0"},
		{"/tools/tc", "-j", "-s", "-d", "filter", "show", "dev", "eth0", "root"},
		{"/tools/tc", "-j", "-s", "-d", "filter", "show", "dev", "eth0", "ingress"},
		{"/tools/tc", "-j", "-s", "-d", "filter", "show", "dev", "eth0", "egress"},
	}
	if !reflect.DeepEqual(calls, want) {
		t.Fatalf("unexpected tool calls: %v", calls)
	}
	encoded, err := json.Marshal(report)
	if err != nil || !strings.Contains(string(encoded), `18446744073709551615`) || !strings.Contains(string(encoded), `"ack-filter":"disabled"`) {
		t.Fatalf("options changed: %s %v", encoded, err)
	}
	if report.StartedAt.After(report.FinishedAt) || report.StartedAt.IsZero() {
		t.Fatal("invalid collection times")
	}
}

func TestQueueSnapshotMissingToolAndQueryFailureRemainUnavailable(t *testing.T) {
	for _, missing := range []bool{true, false} {
		sources := snapshotTestSources()
		if missing {
			sources.lookPath = func(name string) (string, error) {
				if name == "tc" {
					return "", errors.New("tc missing")
				}
				return "/tools/ip", nil
			}
		} else {
			run := sources.run
			sources.run = func(ctx context.Context, path string, args ...string) ([]byte, error) {
				if args[len(args)-1] == "ingress" {
					return nil, errors.New("parent absent")
				}
				return run(ctx, path, args...)
			}
		}
		report, err := collectGatewayQueueSnapshot(context.Background(), "eth0", sources)
		if err != nil || !report.Partial() || !report.Readings[0].Available {
			t.Fatalf("invalid partial snapshot: %+v %v", report, err)
		}
		reading := report.Readings[4]
		if reading.Available || reading.Value != nil || reading.Reason == "" {
			t.Fatal("unavailable confused with empty")
		}
		if !missing && string(report.Readings[2].Value) != "[]" {
			t.Fatal("successful empty class list lost")
		}
	}
}

func TestQueueSnapshotRefusesInvalidNamesBeforeIO(t *testing.T) {
	for _, name := range []string{"", "-eth0", ".", "..", "eth 0", "eth0\n", "éth0", "eth0/foo", "abcdefghijklmnop", "$(id)"} {
		sources := snapshotTestSources()
		sources.interfaceByName = func(string) (*net.Interface, error) { t.Fatal("unexpected interface lookup"); return nil, nil }
		if _, err := collectGatewayQueueSnapshot(context.Background(), name, sources); err == nil {
			t.Fatalf("accepted %q", name)
		}
	}
	for _, name := range []string{"eth0", "wlp3s0", "br-lan", "enp0s1.10", "eth0:1"} {
		if err := ValidateGatewaySnapshotInterfaceName(name); err != nil {
			t.Fatalf("valid name refused %q: %v", name, err)
		}
	}
}

func TestQueueSnapshotRefusesMissingLoopbackOrChangedInterface(t *testing.T) {
	for _, mode := range []string{"missing", "nil", "loopback", "changed", "removed"} {
		t.Run(mode, func(t *testing.T) {
			sources := snapshotTestSources()
			lookup := sources.interfaceByName
			lookups, calls := 0, 0
			sources.interfaceByName = func(name string) (*net.Interface, error) {
				lookups++
				if mode == "missing" || (mode == "removed" && lookups == 2) {
					return nil, errors.New("gone")
				}
				if mode == "nil" {
					return nil, nil
				}
				item, _ := lookup(name)
				if mode == "loopback" {
					item.Flags |= net.FlagLoopback
				}
				if mode == "changed" && lookups == 2 {
					item.Index++
				}
				return item, nil
			}
			run := sources.run
			sources.run = func(ctx context.Context, path string, args ...string) ([]byte, error) {
				calls++
				return run(ctx, path, args...)
			}
			report, err := collectGatewayQueueSnapshot(context.Background(), "eth0", sources)
			if err == nil || len(report.Readings) != 0 {
				t.Fatal("invalid identity yielded a report")
			}
			if mode != "changed" && mode != "removed" && calls != 0 {
				t.Fatal("tools ran for refused interface")
			}
		})
	}
}

func TestQueueSnapshotCancellationStopsFurtherQueries(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	sources := snapshotTestSources()
	calls := 0
	sources.run = func(context.Context, string, ...string) ([]byte, error) {
		calls++
		cancel()
		return nil, context.Canceled
	}
	report, err := collectGatewayQueueSnapshot(ctx, "eth0", sources)
	if !errors.Is(err, context.Canceled) || calls != 1 || len(report.Readings) != 0 {
		t.Fatalf("cancellation ignored: %v %d", err, calls)
	}
	sources.interfaceByName = func(string) (*net.Interface, error) { t.Fatal("lookup after cancellation"); return nil, nil }
	if _, err := collectGatewayQueueSnapshot(ctx, "eth0", sources); !errors.Is(err, context.Canceled) {
		t.Fatalf("initial cancellation ignored: %v", err)
	}
}

func TestQueueSnapshotRejectsMalformedAmbiguousOrWrongTargetJSON(t *testing.T) {
	target := GatewaySnapshotInterface{Name: "eth0", Index: 2, MTU: 1500}
	for _, data := range []string{
		`null`, `{}`, `[null]`, `[1]`, `[] []`, `[{"x":1,"x":2}]`, `[{"options":{"x":1e999}}]`, `[{"dev":"eth1"}]`,
		`[{"dev":null}]`, `[{"dev":2}]`, `[{"options":` + strings.Repeat("[", 20) + `0` + strings.Repeat("]", 20) + `}]`,
		`[{"x":"` + strings.Repeat("x", gatewayOutputLimit) + `"}]`,
	} {
		if err := validateGatewaySnapshotArray([]byte(data), "qdiscs", target); err == nil {
			t.Fatalf("accepted invalid JSON %.100q", data)
		}
	}
	for _, data := range []string{`[]`, `[{}]`, `[{"ifindex":3,"ifname":"eth0","mtu":1500}]`, `[{"ifindex":2,"ifname":"other","mtu":1500}]`, `[{"ifindex":2,"ifname":"eth0","mtu":9000}]`, `[{"IFINDEX":2,"ifname":"eth0","mtu":1500}]`, `[{"ifindex":3,"IFINDEX":2,"ifname":"eth0","mtu":1500}]`} {
		if err := validateGatewaySnapshotArray([]byte(data), "link", target); err == nil {
			t.Fatalf("accepted inconsistent link %q", data)
		}
	}
	sources := snapshotTestSources()
	sources.run = func(context.Context, string, ...string) ([]byte, error) { return []byte(`[null]`), nil }
	report, err := collectGatewayQueueSnapshot(context.Background(), "eth0", sources)
	if err != nil || !report.Partial() {
		t.Fatalf("invalid output not represented as partial: %v", err)
	}
	for _, reading := range report.Readings {
		if reading.Available || reading.Value != nil || reading.Reason == "" {
			t.Fatal("invalid JSON was retained")
		}
	}
}
