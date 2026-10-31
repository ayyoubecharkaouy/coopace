package labcontrol

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"io"
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

func TestWorkerEventsHaveSeparateSchemaAndValidatedRawReading(t *testing.T) {
	reading, err := linux.ParseCakeReading(appliedFixture(t), linux.CakeIPRoute2V610)
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"ready", "applied"} {
		var supplied *linux.CakeReading
		if name == "applied" {
			supplied = &reading
		}
		data, err := eventFrame("abcd1234", name, supplied)
		if err != nil {
			t.Fatal(err)
		}
		if int(binary.BigEndian.Uint32(data)) != len(data)-4 {
			t.Fatal("incorrect frame length")
		}
		var event workerEvent
		if err := json.Unmarshal(data[4:], &event); err != nil {
			t.Fatal(err)
		}
		if event.Kind != "lab_cake_worker_event" || event.Event != name || event.Session != "abcd1234" || event.Schema != 1 {
			t.Fatalf("incorrect event: %+v", event)
		}
		if name == "applied" && !bytes.Equal(event.Raw, bytes.TrimSpace(reading.Raw)) {
			// JSON marshaling compacts whitespace; semantic/raw source fields
			// must still be preserved without number conversion.
			var compact bytes.Buffer
			if err := json.Compact(&compact, reading.Raw); err != nil || !bytes.Equal(event.Raw, compact.Bytes()) {
				t.Fatal("qdisc fields changed")
			}
		}
		if _, err := ReadCommand(bytes.NewReader(data)); err == nil {
			t.Fatal("event accepted as a control")
		}
	}
	for _, name := range []string{"apply", "finish", "cleaned", ""} {
		if _, err := eventFrame("abcd1234", name, nil); err == nil {
			t.Fatal("unsupported event accepted")
		}
	}
	if _, err := eventFrame("abcd1234", "applied", nil); err == nil {
		t.Fatal("unobserved apply accepted")
	}
	if _, err := eventFrame("abcd1234", "ready", &reading); err == nil {
		t.Fatal("ready attached an applied reading")
	}
	if _, err := eventFrame("bad", "ready", nil); err == nil {
		t.Fatal("bad session accepted")
	}
	reading.Raw = []byte("[]")
	if _, err := eventFrame("abcd1234", "applied", &reading); err == nil {
		t.Fatal("forged reading accepted")
	}
	// Escaping can expand a valid <64 KiB qdisc dump beyond the event budget.
	var rows []map[string]json.RawMessage
	if err := json.Unmarshal(appliedFixture(t), &rows); err != nil {
		t.Fatal(err)
	}
	rows[0]["extra"], _ = json.Marshal(strings.Repeat("<", 30000))
	data, _ := json.Marshal(rows)
	// Restore literal '<' to keep the input within its own parser budget.
	data = bytes.ReplaceAll(data, []byte(`\u003c`), []byte("<"))
	reading, err = linux.ParseCakeReading(data, linux.CakeIPRoute2V610)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := eventFrame("abcd1234", "applied", &reading); err == nil {
		t.Fatal("expanded event exceeded budget")
	}
}

type shortWriter struct {
	output bytes.Buffer
	zero   bool
}

func (s *shortWriter) Write(p []byte) (int, error) {
	if s.zero {
		return 0, nil
	}
	return s.output.Write(p[:1])
}

func TestWorkerFrameWritesPreservePartialWritesAndRejectNoProgress(t *testing.T) {
	s := &shortWriter{}
	if err := writeAll(s, []byte("abc")); err != nil || s.output.String() != "abc" {
		t.Fatal("partial write lost", err)
	}
	s.zero = true
	if err := writeAll(s, []byte("abc")); err != io.ErrShortWrite {
		t.Fatal("zero write did not stop", err)
	}
}
