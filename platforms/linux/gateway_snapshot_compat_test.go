package linux

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestQueueSnapshotLegacyEmptyClassesRequireSuccessfulTextConfirmation(t *testing.T) {
	for _, output := range []string{"", " \t\r\n"} {
		sources := snapshotTestSources()
		run := sources.run
		var fallbackCalls [][]string
		sources.run = func(ctx context.Context, path string, args ...string) ([]byte, error) {
			if args[0] == "-s" {
				fallbackCalls = append(fallbackCalls, append([]string{path}, args...))
				return []byte(output), nil
			}
			if args[3] == "class" {
				return []byte(output), nil
			}
			return run(ctx, path, args...)
		}
		report, err := collectGatewayQueueSnapshot(context.Background(), "eth0", sources)
		if err != nil || report.Partial() {
			t.Fatalf("legacy empty classes not handled: %+v %v", report, err)
		}
		want := [][]string{{"/tools/tc", "-s", "-d", "class", "show", "dev", "eth0"}}
		if !reflect.DeepEqual(fallbackCalls, want) {
			t.Fatalf("unexpected fallback commands: %v", fallbackCalls)
		}
		reading := report.Readings[2]
		if !reading.Available || string(reading.Value) != "[]" || reading.Normalization != "empty_classes_confirmed_by_text" || reading.SourceOutput == nil || *reading.SourceOutput != output {
			t.Fatalf("missing normalization evidence: %+v", reading)
		}
		fallback := reading.ClassesTextFallback
		if fallback == nil || !fallback.Succeeded || fallback.StdoutBase64 == nil || string(fallback.StdoutBase64) != output || fallback.Reason != "" || fallback.StartedAt.IsZero() || fallback.FinishedAt.Before(fallback.StartedAt) {
			t.Fatalf("missing confirmation: %+v", fallback)
		}
		encoded, err := json.Marshal(reading)
		if err != nil {
			t.Fatal(err)
		}
		if output == "" && !strings.Contains(string(encoded), `"stdout_base64":""`) {
			t.Fatalf("known empty output became null: %s", encoded)
		}
	}
}

func TestQueueSnapshotEmptyClassesStayUnknownWhenTextConfirmationFails(t *testing.T) {
	for _, test := range []struct {
		name      string
		text      []byte
		err       error
		succeeded bool
	}{
		{"classes_present", []byte("class htb 1:1 root rate 1Mbit\n"), nil, true},
		{"failed_command", nil, errors.New("permission denied"), false},
		{"invalid_encoding", []byte{0xff}, nil, true},
		{"non_ascii_whitespace", []byte("\u00a0"), nil, true},
		{"oversized", []byte(strings.Repeat(" ", gatewayOutputLimit+1)), nil, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			sources := snapshotTestSources()
			run := sources.run
			sources.run = func(ctx context.Context, path string, args ...string) ([]byte, error) {
				if args[0] == "-s" {
					return test.text, test.err
				}
				if args[3] == "class" {
					return nil, nil
				}
				return run(ctx, path, args...)
			}
			report, err := collectGatewayQueueSnapshot(context.Background(), "eth0", sources)
			if err != nil || !report.Partial() {
				t.Fatalf("failed fallback became complete: %v", err)
			}
			reading := report.Readings[2]
			if reading.Available || reading.Value != nil || reading.Normalization != "" || reading.Reason == "" || reading.ClassesTextFallback == nil || reading.ClassesTextFallback.Succeeded != test.succeeded {
				t.Fatalf("false empty class list: %+v", reading)
			}
			if test.name == "oversized" && reading.ClassesTextFallback.StdoutBase64 != nil {
				t.Fatal("oversized evidence retained")
			}
		})
	}
}

func TestQueueSnapshotFallbackIsLimitedToSuccessfulEmptyClassOutput(t *testing.T) {
	for _, test := range []struct {
		section   string
		data      []byte
		err       error
		available bool
	}{
		{"link", nil, nil, false}, {"qdiscs", nil, nil, false}, {"filters_root", nil, nil, false},
		{"classes", []byte("[]"), nil, true}, {"classes", []byte(`[{"class":"htb","handle":"1:1"}]`), nil, true},
		{"classes", []byte("class htb 1:1 root\n"), nil, false}, {"classes", []byte("["), nil, false},
		{"classes", []byte{0xff}, nil, false}, {"classes", []byte(strings.Repeat(" ", gatewayOutputLimit+1)), nil, false},
		{"classes", nil, errors.New("tc failed"), false},
	} {
		sources := snapshotTestSources()
		run := sources.run
		sources.run = func(ctx context.Context, path string, args ...string) ([]byte, error) {
			if args[0] == "-s" {
				t.Fatal("unexpected fallback")
				return nil, nil
			}
			section := ""
			switch args[3] {
			case "show":
				section = "link"
			case "qdisc":
				section = "qdiscs"
			case "class":
				section = "classes"
			case "filter":
				section = "filters_" + args[len(args)-1]
			}
			if section == test.section {
				return test.data, test.err
			}
			return run(ctx, path, args...)
		}
		report, err := collectGatewayQueueSnapshot(context.Background(), "eth0", sources)
		if err != nil {
			t.Fatal(err)
		}
		for _, reading := range report.Readings {
			if reading.ClassesTextFallback != nil || reading.Normalization != "" || reading.SourceOutput != nil {
				t.Fatal("unexpected normalization")
			}
			if reading.Section == test.section && reading.Available != test.available {
				t.Fatalf("incorrect availability for %s", test.section)
			}
		}
	}
}

func TestQueueSnapshotCancellationBeforeEmptyClassFallbackStartsNoNewCommand(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	sources := snapshotTestSources()
	run := sources.run
	calls := 0
	sources.run = func(ctx context.Context, path string, args ...string) ([]byte, error) {
		calls++
		if args[3] == "class" {
			cancel()
			return nil, nil
		}
		return run(ctx, path, args...)
	}
	report, err := collectGatewayQueueSnapshot(ctx, "eth0", sources)
	if !errors.Is(err, context.Canceled) || calls != 3 || len(report.Readings) != 0 {
		t.Fatalf("continued after cancellation: calls=%d err=%v", calls, err)
	}
}
