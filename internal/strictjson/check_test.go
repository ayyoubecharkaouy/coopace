package strictjson

import (
	"strings"
	"testing"
)

func TestChecksNestedKeyAmbiguityAndCallerSizeLimit(t *testing.T) {
	valid := []byte(`{"section":{"value":0,"p50":1},"items":[]}`)
	if err := Check(valid, len(valid)); err != nil {
		t.Fatal(err)
	}
	if err := Check(valid, len(valid)-1); err == nil {
		t.Fatal("caller size limit ignored")
	}
	for _, data := range [][]byte{
		[]byte(`{"section":{"value":0,"value":1}}`),
		[]byte(`{"Value":1}`), []byte(`{"ſequence":1}`),
		[]byte(`{} {}`), []byte(`{"value":`), []byte{'{', 0xff, '}'},
		[]byte(strings.Repeat("[", 20) + "0" + strings.Repeat("]", 20)),
	} {
		if err := Check(data, 1024); err == nil {
			t.Fatalf("ambiguous or unbounded JSON accepted: %q", data)
		}
	}
}

func TestProducerSyntaxAllowsNativeKeysWithoutRelaxingCanonicalContracts(t *testing.T) {
	data := []byte(`[{"ack-filter":"disabled","Future Field":{"値":18446744073709551615}}]`)
	if err := CheckSyntax(data, len(data)); err != nil {
		t.Fatal(err)
	}
	if err := Check(data, len(data)); err == nil {
		t.Fatal("canonical contract accepted producer-specific keys")
	}
	if err := CheckSyntax(data, len(data)-1); err == nil {
		t.Fatal("producer size limit ignored")
	}
	for _, input := range []string{`[{"ack-filter":0,"ack-filter":1}]`, `[{"x":1,"\u0078":2}]`,
		`[{"x":1e999}]`, `[NaN]`, `[] []`, strings.Repeat("[", 20) + "0" + strings.Repeat("]", 20)} {
		if err := CheckSyntax([]byte(input), 2048); err == nil {
			t.Fatalf("ambiguous or unbounded producer JSON accepted: %s", input)
		}
	}
	for _, input := range []string{`{"huge_integer":` + strings.Repeat("9", 400) + `}`, `{"tiny":1e-999}`} {
		if err := CheckSyntax([]byte(input), 2048); err != nil {
			t.Fatalf("finite producer JSON rejected: %v", err)
		}
	}
}
