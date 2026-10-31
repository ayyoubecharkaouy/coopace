package labcontrol

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"io"
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const requestJSON = `{"schema_version":1,"kind":"lab_cake_worker_request","session_id":"abcd1234","purpose":"cake_down_control","reference":"cake-ipv4-lab-4mbit-v1","namespace_identity":{"device":11,"inode":21}}`

func frame(data string) []byte {
	result := make([]byte, 4+len(data))
	binary.BigEndian.PutUint32(result, uint32(len(data)))
	copy(result[4:], data)
	return result
}

func commandJSON(action, session string) string {
	return `{"schema_version":1,"kind":"lab_cake_worker_control","session_id":"` + session + `","action":"` + action + `"}`
}

func TestInternalRequestPreservesExactUnsignedIdentityAndKnownReference(t *testing.T) {
	data := strings.Replace(requestJSON, `"inode":21`, `"inode":18446744073709551615`, 1)
	request, err := ReadRequest(bytes.NewReader(frame(data)))
	if err != nil || request.SessionID() != "abcd1234" || request.Reference() != core.CakeReferenceIPv4LabV1 || request.NamespaceIdentity().Inode != ^uint64(0) {
		t.Fatalf("request changed: %+v, %v", request, err)
	}
	for _, action := range []string{"apply", "finish"} {
		command, err := ReadCommand(bytes.NewReader(frame(commandJSON(action, "abcd1234"))))
		if err != nil || command.Action() != action || command.SessionID() != "abcd1234" {
			t.Fatalf("command changed: %+v, %v", command, err)
		}
	}
}

func TestInternalRequestRequiresEveryFieldAndRejectsNull(t *testing.T) {
	for _, nested := range []bool{false, true} {
		names := []string{"schema_version", "kind", "session_id", "purpose", "reference", "namespace_identity"}
		if nested {
			names = []string{"device", "inode"}
		}
		for _, name := range names {
			for _, omit := range []bool{false, true} {
				var value map[string]any
				json.Unmarshal([]byte(requestJSON), &value)
				fields := value
				if nested {
					fields = value["namespace_identity"].(map[string]any)
				}
				if omit {
					delete(fields, name)
				} else {
					fields[name] = nil
				}
				data, _ := json.Marshal(value)
				if _, err := ReadRequest(bytes.NewReader(frame(string(data)))); err == nil {
					t.Fatalf("missing/null field admitted: %s", data)
				}
			}
		}
	}
}

func TestInternalMessagesRejectSimulationScopeAndAmbiguousOrMalformedFields(t *testing.T) {
	bad := []string{
		`{"schema_version":1,"kind":"static_cake_plan","execution_authorized":true}`,
		`{"schema_version":1,"kind":"static_cake_scenario","checks":{"permissions_checked":true}}`,
		strings.Replace(requestJSON, `"purpose":"cake_down_control"`, `"purpose":"existing_gateway"`, 1),
		strings.Replace(requestJSON, "cake-ipv4-lab-4mbit-v1", "cake-ipv4-lab-8mbit-v1", 1),
		strings.Replace(requestJSON, "abcd1234", "ABCD1234", 1), strings.Replace(requestJSON, "abcd1234", "short", 1),
		strings.Replace(requestJSON, `"device":11`, `"device":true`, 1), strings.Replace(requestJSON, `"inode":21`, `"inode":-1`, 1),
		strings.Replace(requestJSON, `"inode":21`, `"inode":21.0`, 1), strings.Replace(requestJSON, `"inode":21`, `"inode":18446744073709551616`, 1),
		strings.Replace(requestJSON, `"schema_version":1`, `"schema_version":1,"schema_version":1`, 1),
		strings.Replace(requestJSON, `"schema_version":1`, `"Schema_version":1`, 1),
		strings.Replace(requestJSON, `"schema_version":1`, `"execution_authorized":true,"schema_version":1`, 1),
		requestJSON + " {}", "null", "[]", string([]byte{0xff}),
	}
	for _, data := range bad {
		if _, err := ReadRequest(bytes.NewReader(frame(data))); err == nil {
			t.Fatalf("unsafe request admitted: %s", data)
		}
	}
	for _, data := range []string{commandJSON("replace", "abcd1234"), commandJSON("apply", "other"), requestJSON,
		strings.Replace(commandJSON("apply", "abcd1234"), `"action":"apply"`, `"action":null`, 1),
		strings.Replace(commandJSON("apply", "abcd1234"), `"action":"apply"`, `"action":"apply","rate":1000`, 1)} {
		if _, err := ReadCommand(bytes.NewReader(frame(data))); err == nil {
			t.Fatalf("unsafe command admitted: %s", data)
		}
	}
}

type countReader struct {
	input io.Reader
	bytes int
}

func (r *countReader) Read(data []byte) (int, error) {
	n, err := r.input.Read(data)
	r.bytes += n
	return n, err
}

func TestInternalFramesBoundAllocationAndDoNotConsumeTheNextFrame(t *testing.T) {
	for _, size := range []uint32{0, MaxRequestBytes + 1, ^uint32(0)} {
		var prefix [4]byte
		binary.BigEndian.PutUint32(prefix[:], size)
		input := &countReader{input: bytes.NewReader(append(prefix[:], bytes.Repeat([]byte("x"), 100)...))}
		if _, err := ReadRequest(input); err == nil || input.bytes != 4 {
			t.Fatalf("oversized frame payload consumed: %d, %v", input.bytes, err)
		}
	}
	for _, data := range [][]byte{nil, {0}, {0, 0, 0}, frame(requestJSON)[:len(frame(requestJSON))-1]} {
		if _, err := ReadRequest(bytes.NewReader(data)); err == nil {
			t.Fatal("truncated frame accepted")
		}
	}
	for _, entry := range []struct {
		limit int
		data  string
		read  func(io.Reader) error
	}{
		{MaxRequestBytes, requestJSON, func(r io.Reader) error { _, err := ReadRequest(r); return err }},
		{MaxCommandBytes, commandJSON("apply", "abcd1234"), func(r io.Reader) error { _, err := ReadCommand(r); return err }},
	} {
		padded := entry.data + strings.Repeat(" ", entry.limit-len(entry.data))
		if err := entry.read(bytes.NewReader(frame(padded))); err != nil {
			t.Fatal(err)
		}
		if err := entry.read(bytes.NewReader(frame(padded + " "))); err == nil {
			t.Fatal("frame size limit ignored")
		}
	}
	data := append(frame(commandJSON("apply", "abcd1234")), frame(commandJSON("finish", "abcd1234"))...)
	input := bytes.NewReader(data)
	first, err := ReadCommand(input)
	if err != nil || first.Action() != "apply" {
		t.Fatal(err)
	}
	second, err := ReadCommand(input)
	if err != nil || second.Action() != "finish" || input.Len() != 0 {
		t.Fatal("frame boundary lost")
	}
}
