// Package planning evaluates declared local scenarios without network operations.
package planning

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"

	"github.com/ayyoubecharkaouy/coopace/internal/strictjson"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const MaxScenarioBytes = 16 * 1024

type scenarioChecks struct {
	ReferenceValidated bool `json:"reference_validated"`
	LocalConsent       bool `json:"local_consent"`
	PathValidated      bool `json:"path_validated"`
	OwnershipValidated bool `json:"ownership_validated"`
	SupervisionReady   bool `json:"supervision_ready"`
	PermissionsChecked bool `json:"permissions_checked"`
}

type scenarioDocument struct {
	SchemaVersion int                    `json:"schema_version"`
	Kind          string                 `json:"kind"`
	Scope         core.CakePlanningScope `json:"scope"`
	Queue         core.CakePlanningQueue `json:"queue"`
	Checks        scenarioChecks         `json:"checks"`
}

// Scenario preserves the exact input digest and validated, declared assumptions.
type Scenario struct {
	Input  core.CakePlanningInput
	SHA256 string
	Bytes  int
}

func required(data []byte, names ...string) error {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return err
	}
	for _, name := range names {
		if len(fields[name]) == 0 || bytes.Equal(bytes.TrimSpace(fields[name]), []byte("null")) {
			return fmt.Errorf("champ requis absent ou nul : %s", name)
		}
	}
	return nil
}

type contextReader struct {
	ctx   context.Context
	input io.Reader
}

func (r contextReader) Read(buffer []byte) (int, error) {
	if err := r.ctx.Err(); err != nil {
		return 0, err
	}
	n, err := r.input.Read(buffer)
	if canceled := r.ctx.Err(); canceled != nil {
		return n, canceled
	}
	return n, err
}

func ReadScenario(ctx context.Context, input io.Reader) (Scenario, error) {
	data, err := io.ReadAll(io.LimitReader(contextReader{ctx: ctx, input: input}, MaxScenarioBytes+1))
	if err != nil {
		return Scenario{}, err
	}
	if err := strictjson.Check(data, MaxScenarioBytes); err != nil {
		return Scenario{}, err
	}
	if err := required(data, "schema_version", "kind", "scope", "queue", "checks"); err != nil {
		return Scenario{}, err
	}
	var fields struct {
		Checks json.RawMessage `json:"checks"`
	}
	if err := json.Unmarshal(data, &fields); err != nil {
		return Scenario{}, err
	}
	if err := required(fields.Checks, "reference_validated", "local_consent", "path_validated", "ownership_validated", "supervision_ready", "permissions_checked"); err != nil {
		return Scenario{}, err
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var source scenarioDocument
	if err := decoder.Decode(&source); err != nil {
		return Scenario{}, err
	}
	if source.SchemaVersion != 1 || source.Kind != "static_cake_scenario" {
		return Scenario{}, fmt.Errorf("version ou type de scénario incompatible")
	}
	checks := source.Checks
	value := core.CakePlanningInput{Scope: source.Scope, Queue: source.Queue, Checks: core.CakePlanningChecks{
		ReferenceValidated: checks.ReferenceValidated, LocalConsent: checks.LocalConsent, PathValidated: checks.PathValidated,
		OwnershipValidated: checks.OwnershipValidated, SupervisionReady: checks.SupervisionReady, PermissionsChecked: checks.PermissionsChecked,
	}}
	if _, err := core.PlanStaticCake(value); err != nil {
		return Scenario{}, err
	}
	return Scenario{Input: value, SHA256: fmt.Sprintf("%x", sha256.Sum256(data)), Bytes: len(data)}, nil
}

func exportScenario(value core.CakePlanningInput) scenarioDocument {
	c := value.Checks
	return scenarioDocument{SchemaVersion: 1, Kind: "static_cake_scenario", Scope: value.Scope, Queue: value.Queue,
		Checks: scenarioChecks{ReferenceValidated: c.ReferenceValidated, LocalConsent: c.LocalConsent, PathValidated: c.PathValidated,
			OwnershipValidated: c.OwnershipValidated, SupervisionReady: c.SupervisionReady, PermissionsChecked: c.PermissionsChecked}}
}
