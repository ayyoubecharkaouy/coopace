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
