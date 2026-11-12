package snapshot

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"

	"github.com/ayyoubecharkaouy/coopace/internal/strictjson"
	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

const MaxImportBytes = 8 * 1024 * 1024

// Imported is untrusted local evidence. SHA256 binds the exact file bytes and
// is not a signature, device identity or authorization for an executor.
type Imported struct {
	Snapshot linux.GatewayQueueSnapshot
	SHA256   string
}

type contextReader struct {
	ctx   context.Context
	input io.Reader
}

func (reader contextReader) Read(data []byte) (int, error) {
	if err := reader.ctx.Err(); err != nil {
		return 0, err
	}
	n, err := reader.input.Read(data)
	if canceled := reader.ctx.Err(); canceled != nil {
		return n, canceled
	}
	return n, err
}

// exactObject rejects missing/null required metadata and case aliases, while
// raw producer objects retain their own field names (for example ack-filter).
func exactObject(data []byte, required, optional []string) (map[string]json.RawMessage, error) {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil || fields == nil {
		return nil, fmt.Errorf("objet JSON requis")
	}
	allowed := make(map[string]bool)
	for _, key := range required {
		allowed[key] = true
		if len(fields[key]) == 0 || bytes.Equal(bytes.TrimSpace(fields[key]), []byte("null")) {
			return nil, fmt.Errorf("champ requis absent ou nul : %s", key)
		}
	}
	for _, key := range optional {
		allowed[key] = true
	}
	for key := range fields {
		if !allowed[key] {
			return nil, fmt.Errorf("champ non reconnu : %s", key)
		}
	}
	return fields, nil
}

func checkSnapshotFields(data []byte) error {
	fields, err := exactObject(data, []string{"interface", "started_at", "finished_at", "readings"}, nil)
	if err != nil {
		return err
	}
	if _, err = exactObject(fields["interface"], []string{"name", "index", "mtu", "flags", "hardware_address"}, nil); err != nil {
		return err
	}
	var readings []json.RawMessage
	if err = json.Unmarshal(fields["readings"], &readings); err != nil {
		return err
	}
	for _, raw := range readings {
		reading, err := exactObject(raw, []string{"section", "tool", "path", "arguments", "started_at", "finished_at", "available"}, []string{"value", "reason", "normalization", "source_output", "classes_text_fallback"})
		if err != nil {
			return err
		}
		if len(reading["value"]) == 0 {
			return fmt.Errorf("champ value absent")
		}
		for _, key := range []string{"reason", "normalization", "source_output", "classes_text_fallback"} {
			if value, exists := reading[key]; exists && bytes.Equal(bytes.TrimSpace(value), []byte("null")) {
				return fmt.Errorf("champ optionnel nul : %s", key)
			}
		}
		if raw := reading["classes_text_fallback"]; len(raw) != 0 {
			fallback, err := exactObject(raw, []string{"arguments", "started_at", "finished_at", "succeeded"}, []string{"stdout_base64", "reason"})
			if err != nil {
				return err
			}
			if len(fallback["stdout_base64"]) == 0 {
				return fmt.Errorf("sortie de confirmation absente")
			}
		}
	}
	return nil
}

// Read imports only a bounded v1 local queue snapshot. Overall nesting is
// limited by strictjson; no executable or arbitrary argument is trusted.
func Read(ctx context.Context, input io.Reader) (Imported, error) {
	data, err := io.ReadAll(io.LimitReader(contextReader{ctx, input}, MaxImportBytes+1))
	if err != nil {
		return Imported{}, err
	}
	if err := strictjson.CheckSyntax(data, MaxImportBytes); err != nil {
		return Imported{}, err
	}
	fields, err := exactObject(data, []string{"schema_version", "kind", "coopace_version", "os", "architecture", "build", "scope", "mode", "partial", "atomic", "completeness", "traffic_coverage", "restoration", "snapshot"}, nil)
	if err != nil {
		return Imported{}, err
	}
	for key, expected := range map[string]string{"kind": "gateway_queue_snapshot", "os": "linux", "scope": "process_network_namespace", "mode": "read_only", "completeness": "selected_queries_only", "traffic_coverage": "unverified", "restoration": "not_implemented"} {
		var value string
		if json.Unmarshal(fields[key], &value) != nil || value != expected {
			return Imported{}, fmt.Errorf("capture incompatible : %s", key)
		}
	}
	var schema int
	var partial, atomic bool
	if json.Unmarshal(fields["schema_version"], &schema) != nil || schema != 1 || json.Unmarshal(fields["partial"], &partial) != nil || json.Unmarshal(fields["atomic"], &atomic) != nil || atomic {
		return Imported{}, fmt.Errorf("version ou indicateurs de capture incompatibles")
	}
	for _, key := range []string{"coopace_version", "architecture"} {
		var value string
		if json.Unmarshal(fields[key], &value) != nil || value == "" {
			return Imported{}, fmt.Errorf("métadonnée invalide : %s", key)
		}
	}
	build, err := exactObject(fields["build"], nil, []string{"go_version", "vcs", "vcs_revision", "vcs_modified"})
	if err != nil {
		return Imported{}, err
	}
	for _, key := range []string{"go_version", "vcs", "vcs_revision"} {
		if raw := build[key]; len(raw) == 0 {
			return Imported{}, fmt.Errorf("provenance absente : %s", key)
		} else {
			var value *string
			if json.Unmarshal(raw, &value) != nil {
				return Imported{}, fmt.Errorf("provenance invalide : %s", key)
			}
		}
	}
	var modified *bool
	if raw := build["vcs_modified"]; len(raw) == 0 || json.Unmarshal(raw, &modified) != nil {
		return Imported{}, fmt.Errorf("provenance modifiée absente ou invalide")
	}
	if err := checkSnapshotFields(fields["snapshot"]); err != nil {
		return Imported{}, err
	}
	var source linux.GatewayQueueSnapshot
	if err := json.Unmarshal(fields["snapshot"], &source); err != nil {
		return Imported{}, err
	}
	if err := linux.ValidateGatewayQueueSnapshot(source); err != nil {
		return Imported{}, err
	}
	if source.Partial() != partial {
		return Imported{}, fmt.Errorf("indicateur partial incohérent")
	}
	if err := ctx.Err(); err != nil {
		return Imported{}, err
	}
	return Imported{Snapshot: source, SHA256: fmt.Sprintf("%x", sha256.Sum256(data))}, nil
}

// ImportReport applies the same validation to a live collection and file input.
func ImportReport(ctx context.Context, report Report) (Imported, error) {
	var data bytes.Buffer
	if err := WriteJSON(&data, report); err != nil {
		return Imported{}, err
	}
	return Read(ctx, &data)
}
