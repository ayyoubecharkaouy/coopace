package protocol

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

const testPeer = "ed25519:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func helloMessage() Message {
	return Message{Version: Version, Kind: HelloKind, GroupID: "test-group", SenderID: testPeer, Sequence: 1,
		Hello: &Hello{ShareObservations: true, Name: "PC été", OS: "linux", Roles: []string{"agent"}, Capabilities: []string{"observe_local_traffic"}}}
}

func trafficMessage(sequence uint64) Message {
	zero := "0"
	maximum := "18446744073709551615"
	return Message{Version: Version, Kind: TrafficKind, GroupID: "test-group", SenderID: testPeer, Sequence: sequence,
		Observation: &TrafficObservation{
			ObservedAt: time.Date(2026, 10, 25, 12, 0, 0, 0, time.UTC), Source: "linux_proc_net_dev", Scope: "process_network_namespace", WindowMS: 1000.5,
			Interfaces: []InterfaceBytes{{Name: "eth0", State: "measured", ReceivedBytes: &maximum, SentBytes: &zero}, {Name: "gone", State: "disappeared"}},
		}}
}

func encodeForTest(t *testing.T, message Message) []byte {
	t.Helper()
	data, err := Encode(message)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestMessageRoundTripsPreserveLargeByteCounters(t *testing.T) {
	for _, message := range []Message{helloMessage(), trafficMessage(2)} {
		data := encodeForTest(t, message)
		decoded, err := Decode(data)
		if err != nil || decoded.Kind != message.Kind || decoded.SenderID != testPeer {
			t.Fatalf("message not decoded: %v", err)
		}
		if decoded.Observation != nil && (*decoded.Observation.Interfaces[0].ReceivedBytes != "18446744073709551615" || decoded.Observation.Interfaces[1].ReceivedBytes != nil) {
			t.Fatal("large counter or unavailable value changed")
		}
	}
}

func TestDecodeRejectsAmbiguousAndOversizedJSON(t *testing.T) {
	valid := encodeForTest(t, helloMessage())
	for _, data := range [][]byte{
		nil, []byte("null"), bytes.Repeat([]byte(" "), MaxMessageBytes+1), append(append([]byte(nil), valid...), valid...),
		bytes.Replace(valid, []byte(`"version":2`), []byte(`"version":2,"version":2`), 1),
		bytes.Replace(valid, []byte(`"version"`), []byte(`"Version"`), 1),
		bytes.Replace(valid, []byte(`"name"`), []byte(`"Name"`), 1),
		bytes.Replace(valid, []byte(`"sequence"`), []byte(`"ſequence"`), 1),
		bytes.Replace(valid, []byte(`"version":2`), []byte(`"version":2,"unknown":true`), 1),
		bytes.Replace(valid, []byte("PC été"), []byte{0xff}, 1),
		[]byte(strings.Repeat("[", 20) + "0" + strings.Repeat("]", 20)),
	} {
		if _, err := Decode(data); err == nil {
			t.Errorf("invalid JSON accepted (length %d)", len(data))
		}
	}
}

func TestMessageRejectsInvalidPayloads(t *testing.T) {
	for _, change := range []func(*Message){
		func(m *Message) { m.Version = Version + 1 }, func(m *Message) { m.Sequence = 0 }, func(m *Message) { m.Sequence = MaxSequence + 1 },
		func(m *Message) { m.SenderID = "unbound-device" }, func(m *Message) { m.Kind = "execute_command" },
		func(m *Message) { m.Hello.Roles = []string{"agent", "agent"} }, func(m *Message) { m.Hello.Capabilities = []string{"universal_acceleration"} },
		func(m *Message) { m.Observation = trafficMessage(2).Observation },
	} {
		message := helloMessage()
		change(&message)
		data, err := json.Marshal(message)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := Decode(data); err == nil {
			t.Fatal("invalid message accepted")
		}
	}
	for _, change := range []func(*TrafficObservation){
		func(o *TrafficObservation) { o.WindowMS = 0 }, func(o *TrafficObservation) { o.Source = "guessed_app" },
		func(o *TrafficObservation) { o.Interfaces[0].ReceivedBytes = nil },
		func(o *TrafficObservation) { value := "01"; o.Interfaces[0].ReceivedBytes = &value },
		func(o *TrafficObservation) { o.Interfaces[1].SentBytes = o.Interfaces[0].SentBytes },
		func(o *TrafficObservation) { o.Interfaces[1].Name = o.Interfaces[0].Name },
	} {
		message := trafficMessage(2)
		change(message.Observation)
		if _, err := Encode(message); err == nil {
			t.Fatal("invalid observation accepted")
		}
	}
}

func TestSessionBindsPeerGroupAndSequence(t *testing.T) {
	session, err := NewSession("test-group", testPeer)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := session.Next(encodeForTest(t, trafficMessage(1))); err == nil {
		t.Fatal("observation before hello accepted")
	}
	for _, change := range []func(*Message){
		func(m *Message) { m.GroupID = "other-group" },
		func(m *Message) { m.SenderID = "ed25519:" + strings.Repeat("b", 64) },
	} {
		message := helloMessage()
		change(&message)
		if _, err := session.Next(encodeForTest(t, message)); err == nil {
			t.Fatal("message from another peer or group accepted")
		}
	}
	hello := encodeForTest(t, helloMessage())
	if _, err := session.Next(hello); err != nil {
		t.Fatal(err)
	}
	if _, err := session.Next(hello); err == nil {
		t.Fatal("repeated hello or sequence accepted")
	}
	if _, err := session.Next(encodeForTest(t, trafficMessage(3))); err == nil {
		t.Fatal("skipped sequence accepted")
	}
	if _, err := session.Next(encodeForTest(t, trafficMessage(2))); err != nil {
		t.Fatal("rejected frames advanced session state")
	}
}

func FuzzDecode(f *testing.F) {
	data, _ := Encode(helloMessage())
	f.Add(data)
	f.Add([]byte(`{"version":1,"version":2}`))
	f.Fuzz(func(t *testing.T, input []byte) { _, _ = Decode(input) })
}
