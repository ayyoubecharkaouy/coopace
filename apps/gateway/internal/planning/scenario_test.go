package planning

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const sampleScenario = `{"schema_version":1,"kind":"static_cake_scenario","scope":"owned_ipv4_lab","queue":"unconfigured","checks":{"reference_validated":true,"local_consent":false,"path_validated":true,"ownership_validated":true,"supervision_ready":true,"permissions_checked":true}}`

func TestScenarioPreservesFalseAssumptionsAndExactInputHash(t *testing.T) {
	data := " \n" + sampleScenario + "\n"
	scenario, err := ReadScenario(context.Background(), strings.NewReader(data))
	if err != nil || scenario.Input.Checks.LocalConsent || scenario.Bytes != len(data) || scenario.SHA256 != fmt.Sprintf("%x", sha256.Sum256([]byte(data))) {
		t.Fatalf("scenario or provenance lost: %+v, %v", scenario, err)
	}
	plan, err := core.PlanStaticCake(scenario.Input)
	if err != nil || plan.Decision != core.CakePlanAbstain || len(plan.Reasons) != 1 || plan.Reasons[0] != core.CakeReasonConsentUnconfirmed {
		t.Fatalf("explicit false became permission: %+v, %v", plan, err)
	}
}

func TestScenarioRequiresAllFieldsIncludingExplicitBooleans(t *testing.T) {
	for _, nested := range []bool{false, true} {
		names := []string{"schema_version", "kind", "scope", "queue", "checks"}
		if nested {
			names = []string{"reference_validated", "local_consent", "path_validated", "ownership_validated", "supervision_ready", "permissions_checked"}
		}
		for _, name := range names {
			for _, missing := range []bool{false, true} {
				t.Run(fmt.Sprintf("%t/%s/omitted=%t", nested, name, missing), func(t *testing.T) {
					var value map[string]any
					json.Unmarshal([]byte(sampleScenario), &value)
					fields := value
					if nested {
						fields = value["checks"].(map[string]any)
					}
					if missing {
						delete(fields, name)
					} else {
						fields[name] = nil
					}
					data, _ := json.Marshal(value)
					if _, err := ReadScenario(context.Background(), bytes.NewReader(data)); err == nil {
						t.Fatalf("missing/null field accepted: %s", data)
					}
				})
			}
		}
	}
}

func TestScenarioRejectsUnknownFieldsTypesEnumsAndNoncanonicalJSON(t *testing.T) {
	bad := []string{
		"null", "[]", sampleScenario + " {}", strings.Replace(sampleScenario, `"schema_version":1`, `"schema_version":1,"schema_version":1`, 1),
		strings.Replace(sampleScenario, `"kind"`, `"Kind"`, 1), strings.Replace(sampleScenario, `"schema_version":1`, `"schema_version":true`, 1),
		strings.Replace(sampleScenario, `"schema_version":1`, `"schema_version":2`, 1), strings.Replace(sampleScenario, `"schema_version":1`, `"schema_version":1.0`, 1),
		strings.Replace(sampleScenario, `"static_cake_scenario"`, `"gateway_inventory"`, 1),
		strings.Replace(sampleScenario, `"owned_ipv4_lab"`, `"new_scope"`, 1), strings.Replace(sampleScenario, `"unconfigured"`, `"cake"`, 1),
		strings.Replace(sampleScenario, `"checks":{`, `"checks":{"apply":true,`, 1), strings.Replace(sampleScenario, `"schema_version":1`, `"apply":true,"schema_version":1`, 1),
		strings.Replace(sampleScenario, `"local_consent":false`, `"local_consent":0`, 1),
		strings.Replace(sampleScenario, `"local_consent":false`, `"local_consent":"true"`, 1),
		strings.Replace(sampleScenario, `"local_consent":false`, `"local_consent":true,"local_consent":false`, 1),
		strings.Repeat("[", 18) + "0" + strings.Repeat("]", 18),
		string([]byte{0xff}), strings.Replace(sampleScenario, `"schema_version":1`, `"schema_version":NaN`, 1),
	}
	for _, data := range bad {
		if _, err := ReadScenario(context.Background(), strings.NewReader(data)); err == nil {
			t.Errorf("invalid scenario accepted: %q", data)
		}
	}
	for _, value := range []string{"", "existing_gateway"} {
		data := strings.Replace(sampleScenario, "owned_ipv4_lab", value, 1)
		scenario, err := ReadScenario(context.Background(), strings.NewReader(data))
		if err != nil {
			t.Fatal(err)
		}
		plan, err := core.PlanStaticCake(scenario.Input)
		if err != nil || plan.Decision != core.CakePlanAbstain {
			t.Fatal("unsupported declared scope proposed a change")
		}
	}
}

type trackedReader struct {
	input io.Reader
	read  int
}

func (r *trackedReader) Read(p []byte) (int, error) {
	n, err := r.input.Read(p)
	r.read += n
	return n, err
}

type readerFunc func([]byte) (int, error)

func (f readerFunc) Read(p []byte) (int, error) { return f(p) }

func TestScenarioBoundsReadsAndPropagatesErrorsAndCancellation(t *testing.T) {
	boundary := sampleScenario + strings.Repeat(" ", MaxScenarioBytes-len(sampleScenario))
	if value, err := ReadScenario(context.Background(), strings.NewReader(boundary)); err != nil || value.Bytes != MaxScenarioBytes {
		t.Fatalf("valid scenario at the size limit rejected: %v", err)
	}
	reader := &trackedReader{input: strings.NewReader(strings.Repeat(" ", MaxScenarioBytes*2))}
	if _, err := ReadScenario(context.Background(), reader); err == nil || reader.read != MaxScenarioBytes+1 {
		t.Fatalf("unbounded or accepted oversized input: %d, %v", reader.read, err)
	}
	errInput := errors.New("broken reader")
	if _, err := ReadScenario(context.Background(), readerFunc(func([]byte) (int, error) { return 0, errInput })); !errors.Is(err, errInput) {
		t.Fatalf("reader error ignored: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := ReadScenario(ctx, readerFunc(func([]byte) (int, error) { t.Fatal("read after cancellation"); return 0, nil })); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation ignored: %v", err)
	}
	ctx, cancel = context.WithCancel(context.Background())
	if _, err := ReadScenario(ctx, readerFunc(func(p []byte) (int, error) { cancel(); return copy(p, sampleScenario), io.EOF })); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation during read ignored: %v", err)
	}
}
