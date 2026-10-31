package labcontrol

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
	"github.com/ayyoubecharkaouy/coopace/platforms/linux"
)

const (
	MaxEventBytes  = 128 * 1024
	MaxOutputBytes = 512 * 1024
)

// Events are internal protocol observations, never cleanup attestations. The
// future supervisor must validate their order and provenance independently.
type workerEvent struct {
	Schema    int                       `json:"schema_version"`
	Kind      string                    `json:"kind"`
	Session   string                    `json:"session_id"`
	Event     string                    `json:"event"`
	Reference core.CakeReferenceID      `json:"reference"`
	Producer  linux.CakeProducerProfile `json:"producer_profile,omitempty"`
	Raw       json.RawMessage           `json:"qdisc,omitempty"`
}

func eventFrame(session string, name string, reading *linux.CakeReading) ([]byte, error) {
	if !validSession(session) || (name != "ready" && name != "applied") || (name == "applied") != (reading != nil) {
		return nil, fmt.Errorf("invalid worker event")
	}
	value := workerEvent{Schema: 1, Kind: "lab_cake_worker_event", Session: session,
		Event: name, Reference: core.CakeReferenceIPv4LabV1}
	if reading != nil {
		// Revalidate even an in-process value; raw data and producer are not
		// accepted just because a caller populated an exported Go structure.
		if _, err := linux.ParseCakeReading(reading.Raw, reading.Configuration.Profile); err != nil {
			return nil, err
		}
		value.Producer, value.Raw = reading.Configuration.Profile, reading.Raw
	}
	data, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	if len(data) > MaxEventBytes {
		return nil, fmt.Errorf("worker event exceeds output limit")
	}
	frame := make([]byte, 4+len(data))
	binary.BigEndian.PutUint32(frame, uint32(len(data)))
	copy(frame[4:], data)
	return frame, nil
}

func writeAll(output io.Writer, data []byte) error {
	for len(data) > 0 {
		n, err := output.Write(data)
		if n < 0 || n > len(data) {
			return fmt.Errorf("invalid write count")
		}
		data = data[n:]
		if err != nil {
			return err
		}
		if n == 0 {
			return io.ErrShortWrite
		}
	}
	return nil
}
