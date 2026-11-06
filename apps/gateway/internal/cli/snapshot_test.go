package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/diagnostic"
	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/snapshot"
	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

func TestSnapshotArgumentsAndHelpDoNotCollect(t *testing.T) {
	collect := func(context.Context, string, string) (snapshot.Report, error) {
		t.Fatal("unexpected collection")
		return snapshot.Report{}, nil
	}
	for _, args := range [][]string{nil, {"--json"}, {"--interface", "-eth0"}, {"--interface", "eth0", "extra"}, {"--interface", "eth0", "--apply"}} {
		var stdout, stderr bytes.Buffer
		if code := runSnapshot(context.Background(), args, "test", &stdout, &stderr, collect); code != 2 || stdout.Len() != 0 {
			t.Fatalf("invalid args %v: %d", args, code)
		}
	}
	var stdout, stderr bytes.Buffer
	if code := run(context.Background(), []string{"snapshot", "--help"}, "test", &stdout, &stderr, func(context.Context, string) (diagnostic.Report, error) {
		t.Fatal("inspect ran")
		return diagnostic.Report{}, nil
	}); code != 0 || !strings.Contains(stdout.String(), "--interface") {
		t.Fatal("missing snapshot help")
	}
}

func TestSnapshotJSONExportsDetailedOptionsAndExplicitLimits(t *testing.T) {
	collect := func(_ context.Context, version, name string) (snapshot.Report, error) {
		if version != "test" || name != "eth0" {
			t.Fatal("wrong collection request")
		}
		return snapshot.Report{Version: version, OS: "linux", Snapshot: linux.GatewayQueueSnapshot{
			Interface: linux.GatewaySnapshotInterface{Name: name, Index: 2},
			Readings: []linux.GatewaySnapshotReading{
				{Section: "qdiscs", Available: true, Value: json.RawMessage(`[{"kind":"cake","options":{"counter":18446744073709551615}}]`)},
				{Section: "filters_root", Reason: "unavailable"},
				{Section: "classes", Available: true, Value: json.RawMessage(`[]`)},
			},
		}}, nil
	}
	var stdout, stderr bytes.Buffer
	if code := runSnapshot(context.Background(), []string{"--interface", "eth0", "--json"}, "test", &stdout, &stderr, collect); code != 0 || stderr.Len() != 0 {
		t.Fatalf("snapshot failed: %d %s", code, &stderr)
	}
	var decoded struct {
		Kind         string                     `json:"kind"`
		Partial      bool                       `json:"partial"`
		Atomic       bool                       `json:"atomic"`
		Restoration  string                     `json:"restoration"`
		Completeness string                     `json:"completeness"`
		Snapshot     linux.GatewayQueueSnapshot `json:"snapshot"`
	}
	if err := json.Unmarshal(stdout.Bytes(), &decoded); err != nil {
		t.Fatal(err)
	}
	if decoded.Kind != "gateway_queue_snapshot" || !decoded.Partial || decoded.Atomic || decoded.Restoration != "not_implemented" || decoded.Completeness != "selected_queries_only" {
		t.Fatalf("misleading export: %+v", decoded)
	}
	if string(decoded.Snapshot.Readings[1].Value) != "null" || string(decoded.Snapshot.Readings[2].Value) != "[]" || !strings.Contains(stdout.String(), "18446744073709551615") {
		t.Fatal("lost missing/empty distinction or precision")
	}
	if code := runSnapshot(context.Background(), []string{"--interface", "eth0", "--json"}, "test", failedWriter{}, &stderr, collect); code != 1 {
		t.Fatal("output failure ignored")
	}
	stdout.Reset()
	if code := runSnapshot(context.Background(), []string{"--interface", "eth0"}, "test", &stdout, &stderr, collect); code != 0 || !strings.Contains(stdout.String(), "Restauration non implémentée") {
		t.Fatal("text output missing limits")
	}
}

func TestSnapshotCollectionErrorsNeverEmitReport(t *testing.T) {
	for _, test := range []struct {
		err  error
		code int
	}{{context.Canceled, 130}, {context.DeadlineExceeded, 1}, {errors.New("changed interface"), 1}} {
		var stdout, stderr bytes.Buffer
		code := runSnapshot(context.Background(), []string{"--interface", "eth0"}, "test", &stdout, &stderr, func(context.Context, string, string) (snapshot.Report, error) { return snapshot.Report{}, test.err })
		if code != test.code || stdout.Len() != 0 || stderr.Len() == 0 {
			t.Fatalf("error ignored: %v code %d", test.err, code)
		}
	}
}
