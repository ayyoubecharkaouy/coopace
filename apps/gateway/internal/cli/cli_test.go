package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/diagnostic"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestGatewayHelpAndInvalidArgumentsNeverCollect(t *testing.T) {
	collect := func(context.Context, string) (diagnostic.Report, error) {
		t.Fatal("unexpected collection")
		return diagnostic.Report{}, nil
	}
	for _, args := range [][]string{nil, {"help"}, {"--help"}, {"inspect", "--help"}} {
		var stdout, stderr bytes.Buffer
		if code := run(context.Background(), args, "test", &stdout, &stderr, collect); code != 0 || !strings.Contains(stdout.String(), "lecture seule") {
			t.Fatalf("invalid help: %v code %d", args, code)
		}
	}
	for _, args := range [][]string{{"activate"}, {"inspect", "extra"}, {"inspect", "--apply"}, {"inspect", "--json", "extra"}} {
		var stdout, stderr bytes.Buffer
		if code := run(context.Background(), args, "test", &stdout, &stderr, collect); code != 2 || stdout.Len() != 0 {
			t.Fatalf("invalid args accepted: %v", args)
		}
	}
}

func TestGatewayJSONCommandWritesOneDocumentAndNoPreamble(t *testing.T) {
	var stdout, stderr bytes.Buffer
	collect := func(context.Context, string) (diagnostic.Report, error) {
		return diagnostic.Report{Version: "test", OS: "linux"}, nil
	}
	if code := run(context.Background(), []string{"inspect", "--json"}, "test", &stdout, &stderr, collect); code != 0 || stderr.Len() != 0 {
		t.Fatalf("JSON command failed: %d %s", code, &stderr)
	}
	var decoded map[string]any
	if err := json.Unmarshal(stdout.Bytes(), &decoded); err != nil || decoded["kind"] != "gateway_inventory" {
		t.Fatalf("stdout is not one inventory document: %v", err)
	}
	if code := run(context.Background(), []string{"inspect", "--json"}, "test", failedWriter{}, &stderr, collect); code != 1 {
		t.Fatal("JSON output failure ignored")
	}
}

func TestGatewayPartialReportNeverClaimsReadyOrReplacesMissingWithFalse(t *testing.T) {
	var stdout, stderr bytes.Buffer
	collect := func(context.Context, string) (diagnostic.Report, error) {
		return diagnostic.Report{OS: "linux", Architecture: "amd64", Inventory: core.GatewayInventory{IPv6Forwarding: core.GatewayReading[bool]{Reason: "refus"}}}, nil
	}
	if code := run(context.Background(), []string{"inspect"}, "test", &stdout, &stderr, collect); code != 0 {
		t.Fatalf("partial report failed: %s", &stderr)
	}
	output := stdout.String()
	for _, expected := range []string{"Indisponible", "non établie", "non validées", "Aucune configuration modifiée"} {
		if !strings.Contains(output, expected) {
			t.Fatalf("missing %q", expected)
		}
	}
	if strings.Contains(output, "\n  false\n") {
		t.Fatal("missing flag represented as disabled")
	}
	collect = func(context.Context, string) (diagnostic.Report, error) {
		return diagnostic.Report{Inventory: core.GatewayInventory{IPv4Forwarding: core.GatewayReading[bool]{Available: true, Value: false}, IPv4Defaults: core.GatewayReading[[]core.GatewayDefaultRoute]{Available: true}}}, nil
	}
	stdout.Reset()
	if code := run(context.Background(), []string{"inspect"}, "test", &stdout, &stderr, collect); code != 0 || !strings.Contains(stdout.String(), "\n  false\n") || !strings.Contains(stdout.String(), "Aucune route par défaut renvoyée") {
		t.Fatal("known false/empty results not preserved")
	}
	collect = func(context.Context, string) (diagnostic.Report, error) {
		enabled := core.GatewayReading[bool]{Available: true, Value: true}
		return diagnostic.Report{Inventory: core.GatewayInventory{
			IPv4Forwarding: enabled, IPv6Forwarding: enabled, NetAdmin: enabled,
			Interfaces:   core.GatewayReading[[]core.GatewayInterface]{Available: true, Value: []core.GatewayInterface{{Name: "eth0", Index: 2, MTU: 1500, Up: true}}},
			IPv4Defaults: core.GatewayReading[[]core.GatewayDefaultRoute]{Available: true, Value: []core.GatewayDefaultRoute{{Table: "main", Kind: "unicast", Interfaces: []string{"eth0"}}}},
			Queues:       core.GatewayReading[[]core.GatewayQueue]{Available: true, Value: []core.GatewayQueue{{Interface: "eth0", Kind: "cake", Root: true}}},
		}}, nil
	}
	stdout.Reset()
	if code := run(context.Background(), []string{"inspect"}, "test", &stdout, &stderr, collect); code != 0 || !strings.Contains(stdout.String(), "non établie") || !strings.Contains(stdout.String(), "non validées") {
		t.Fatal("forwarding, capabilities and a visible CAKE queue must not establish readiness")
	}
}

type failedWriter struct{}

func (failedWriter) Write([]byte) (int, error) { return 0, io.ErrClosedPipe }

func TestGatewayErrorsCancellationAndOutputFailure(t *testing.T) {
	for _, entry := range []struct {
		err  error
		code int
	}{{errors.New("unsupported"), 1}, {context.Canceled, 130}} {
		collect := func(context.Context, string) (diagnostic.Report, error) { return diagnostic.Report{}, entry.err }
		var stdout, stderr bytes.Buffer
		if code := run(context.Background(), []string{"inspect"}, "test", &stdout, &stderr, collect); code != entry.code || stdout.Len() != 0 {
			t.Fatalf("wrong failure code: %d", code)
		}
	}
	collect := func(context.Context, string) (diagnostic.Report, error) { return diagnostic.Report{}, nil }
	var stderr bytes.Buffer
	if code := run(context.Background(), []string{"inspect"}, "test", failedWriter{}, &stderr, collect); code != 1 {
		t.Fatal("output failure ignored")
	}
}
