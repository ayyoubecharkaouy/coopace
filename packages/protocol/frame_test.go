package protocol

import (
	"bytes"
	"encoding/binary"
	"io"
	"testing"
)

type partialWriter struct{ bytes.Buffer }

func (w *partialWriter) Write(data []byte) (int, error) {
	if len(data) > 3 {
		data = data[:3]
	}
	return w.Buffer.Write(data)
}

func TestFramingHandlesPartialWritesAndRejectsInvalidLengths(t *testing.T) {
	var writer partialWriter
	if err := WriteFrame(&writer, helloMessage()); err != nil {
		t.Fatal(err)
	}
	data, err := ReadFrame(&writer)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := Decode(data); err != nil {
		t.Fatal(err)
	}
	for _, size := range []uint32{0, MaxMessageBytes + 1, ^uint32(0)} {
		var prefix [4]byte
		binary.BigEndian.PutUint32(prefix[:], size)
		if _, err := ReadFrame(bytes.NewReader(prefix[:])); err == nil {
			t.Fatalf("accepted frame size %d", size)
		}
	}
	for _, data := range [][]byte{{0, 1}, {0, 0, 0, 4, 'x'}} {
		if _, err := ReadFrame(bytes.NewReader(data)); err == nil {
			t.Fatal("accepted truncated frame")
		}
	}
}

type stalledWriter struct{}

func (stalledWriter) Write([]byte) (int, error) { return 0, nil }

func TestFramingRejectsStalledWriter(t *testing.T) {
	if err := WriteFrame(stalledWriter{}, helloMessage()); err != io.ErrShortWrite {
		t.Fatalf("got %v", err)
	}
}

func TestSessionEnforcesSharingAndTerminalCompletion(t *testing.T) {
	complete := helloMessage()
	complete.Kind, complete.Hello, complete.Sequence = CompleteKind, nil, 2
	for _, share := range []bool{false, true} {
		session, _ := NewSession("test-group", testPeer)
		hello := helloMessage()
		hello.Hello.ShareObservations = share
		if _, err := session.Next(encodeForTest(t, hello)); err != nil {
			t.Fatal(err)
		}
		if share {
			if _, err := session.Next(encodeForTest(t, complete)); err == nil {
				t.Fatal("completed before promised observation")
			}
			if _, err := session.Next(encodeForTest(t, trafficMessage(2))); err != nil {
				t.Fatal(err)
			}
			if _, err := session.Next(encodeForTest(t, trafficMessage(3))); err == nil {
				t.Fatal("repeated observation accepted")
			}
			complete.Sequence = 3
		} else {
			if _, err := session.Next(encodeForTest(t, trafficMessage(2))); err == nil {
				t.Fatal("unannounced observation accepted")
			}
		}
		if _, err := session.Next(encodeForTest(t, complete)); err != nil {
			t.Fatal(err)
		}
		complete.Sequence++
		if _, err := session.Next(encodeForTest(t, complete)); err == nil {
			t.Fatal("message accepted after completion")
		}
	}
}
