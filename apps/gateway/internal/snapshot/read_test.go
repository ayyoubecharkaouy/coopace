package snapshot

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"
	"testing"
)

func snapshotFixture(t *testing.T) []byte {
	t.Helper()
	data, err := os.ReadFile("../../../../docs/examples/queue-snapshot-noqueue.json")
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestReadSnapshotPreservesExactDigestPrecisionAndLegacyProof(t *testing.T) {
	data := bytes.Replace(snapshotFixture(t), []byte(`"bytes": 0`), []byte(`"bytes": 18446744073709551615`), 1)
	imported, err := Read(context.Background(), bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	if imported.SHA256 != fmt.Sprintf("%x", sha256.Sum256(data)) || imported.Snapshot.Partial() {
		t.Fatal("digest or availability lost")
	}
	if !bytes.Contains(imported.Snapshot.Readings[1].Value, []byte("18446744073709551615")) {
		t.Fatal("integer precision lost")
	}
	classes := imported.Snapshot.Readings[2]
	if classes.Normalization != "empty_classes_confirmed_by_text" || classes.ClassesTextFallback == nil || classes.ClassesTextFallback.StdoutBase64 == nil {
		t.Fatal("legacy proof lost")
	}
	var output bytes.Buffer
	err = WriteJSON(&output, Report{Version: "test", OS: "linux", Architecture: "amd64", Snapshot: imported.Snapshot})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := Read(context.Background(), &output); err != nil {
		t.Fatalf("export cannot be imported: %v", err)
	}
}

func TestReadSnapshotRejectsMissingAmbiguousAndContradictoryEvidence(t *testing.T) {
	for name, mutate := range map[string]func(map[string]any){
		"missing_partial":  func(d map[string]any) { delete(d, "partial") },
		"null_partial":     func(d map[string]any) { d["partial"] = nil },
		"false_partial":    func(d map[string]any) { d["partial"] = true },
		"unknown_field":    func(d map[string]any) { d["authorize_apply"] = true },
		"case_alias":       func(d map[string]any) { d["PARTIAL"] = false },
		"wrong_kind":       func(d map[string]any) { d["kind"] = "gateway_inventory" },
		"wrong_schema":     func(d map[string]any) { d["schema_version"] = 2 },
		"wrong_scope":      func(d map[string]any) { d["scope"] = "global" },
		"atomic_claim":     func(d map[string]any) { d["atomic"] = true },
		"build_type":       func(d map[string]any) { d["build"].(map[string]any)["vcs_modified"] = "false" },
		"missing_identity": func(d map[string]any) { delete(d["snapshot"].(map[string]any)["interface"].(map[string]any), "flags") },
		"wrong_target":     func(d map[string]any) { readingObject(d, 0)["value"].([]any)[0].(map[string]any)["ifname"] = "eth1" },
		"wrong_command": func(d map[string]any) {
			readingObject(d, 1)["arguments"] = []string{"qdisc", "del", "dev", "lab0", "root"}
		},
		"missing_available": func(d map[string]any) { delete(readingObject(d, 1), "available") },
		"null_available":    func(d map[string]any) { readingObject(d, 1)["available"] = nil },
		"null_value":        func(d map[string]any) { readingObject(d, 1)["value"] = nil },
		"unavailable_with_value": func(d map[string]any) {
			readingObject(d, 1)["available"] = false
			readingObject(d, 1)["reason"] = "missing"
			d["partial"] = true
		},
		"overlap": func(d map[string]any) { readingObject(d, 1)["started_at"] = readingObject(d, 0)["started_at"] },
		"missing_section": func(d map[string]any) {
			body := d["snapshot"].(map[string]any)
			body["readings"] = body["readings"].([]any)[:5]
		},
		"forged_legacy_success": func(d map[string]any) {
			readingObject(d, 2)["classes_text_fallback"].(map[string]any)["succeeded"] = false
		},
		"legacy_nonempty": func(d map[string]any) {
			readingObject(d, 2)["classes_text_fallback"].(map[string]any)["stdout_base64"] = "Y2xhc3M="
		},
		"legacy_proof_missing": func(d map[string]any) { delete(readingObject(d, 2), "classes_text_fallback") },
		"legacy_unknown_key": func(d map[string]any) {
			readingObject(d, 2)["classes_text_fallback"].(map[string]any)["SUCCEEDED"] = true
		},
	} {
		t.Run(name, func(t *testing.T) {
			var document map[string]any
			if err := json.Unmarshal(snapshotFixture(t), &document); err != nil {
				t.Fatal(err)
			}
			mutate(document)
			data, err := json.Marshal(document)
			if err != nil {
				t.Fatal(err)
			}
			if _, err := Read(context.Background(), bytes.NewReader(data)); err == nil {
				t.Fatal("invalid evidence accepted")
			}
		})
	}
}

func readingObject(document map[string]any, index int) map[string]any {
	return document["snapshot"].(map[string]any)["readings"].([]any)[index].(map[string]any)
}

func TestReadSnapshotPreservesExplicitPartialObservation(t *testing.T) {
	var document map[string]any
	json.Unmarshal(snapshotFixture(t), &document)
	reading := readingObject(document, 3)
	reading["available"], reading["value"], reading["reason"] = false, nil, "unavailable"
	document["partial"] = true
	data, _ := json.Marshal(document)
	imported, err := Read(context.Background(), bytes.NewReader(data))
	if err != nil || !imported.Snapshot.Partial() || imported.Snapshot.Readings[3].Available {
		t.Fatalf("partial observation lost: %v", err)
	}
}

type cancelingReader struct {
	cancel context.CancelFunc
	data   []byte
}

func (reader cancelingReader) Read(data []byte) (int, error) {
	reader.cancel()
	return copy(data, reader.data), nil
}

func TestReadSnapshotBoundsSyntaxAndCancellation(t *testing.T) {
	valid := snapshotFixture(t)
	for _, data := range [][]byte{[]byte(`{}`), append(append([]byte{}, valid...), []byte(` {}`)...), []byte(`{"kind":1,"kind":2}`), []byte{0xff}, []byte(strings.Repeat(" ", MaxImportBytes+1))} {
		if _, err := Read(context.Background(), bytes.NewReader(data)); err == nil {
			t.Fatal("invalid or oversized snapshot accepted")
		}
	}
	ctx, cancel := context.WithCancel(context.Background())
	if _, err := Read(ctx, cancelingReader{cancel, valid}); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation ignored: %v", err)
	}
}
