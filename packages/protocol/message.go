// Package protocol defines bounded, versioned messages for authenticated sessions.
package protocol

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"strconv"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"
)

const (
	Version         = 2
	MaxMessageBytes = 64 * 1024
	MaxSequence     = uint64(1<<53 - 1)
	HelloKind       = "hello"
	TrafficKind     = "traffic_observation"
	CompleteKind    = "complete"
)

type Message struct {
	Version     int                 `json:"version"`
	Kind        string              `json:"kind"`
	GroupID     string              `json:"group_id"`
	SenderID    string              `json:"sender_id"`
	Sequence    uint64              `json:"sequence"`
	Hello       *Hello              `json:"hello,omitempty"`
	Observation *TrafficObservation `json:"observation,omitempty"`
}

type Hello struct {
	ShareObservations bool     `json:"share_observations"`
	Name              string   `json:"name"`
	OS                string   `json:"os"`
	Roles             []string `json:"roles"`
	Capabilities      []string `json:"capabilities"`
}

type TrafficObservation struct {
	ObservedAt time.Time        `json:"observed_at"`
	Source     string           `json:"source"`
	Scope      string           `json:"scope"`
	WindowMS   float64          `json:"window_ms"`
	Interfaces []InterfaceBytes `json:"interfaces"`
}

type InterfaceBytes struct {
	Name          string  `json:"name"`
	State         string  `json:"state"`
	ReceivedBytes *string `json:"received_bytes"`
	SentBytes     *string `json:"sent_bytes"`
}

func Encode(message Message) ([]byte, error) {
	if err := message.validate(); err != nil {
		return nil, err
	}
	data, err := json.Marshal(message)
	if err != nil {
		return nil, err
	}
	if len(data) > MaxMessageBytes {
		return nil, fmt.Errorf("message exceeds size limit")
	}
	return data, nil
}

func (m Message) validate() error {
	if m.Version != Version || !validID(m.GroupID) || !validFingerprint(m.SenderID) || m.Sequence == 0 || m.Sequence > MaxSequence {
		return fmt.Errorf("invalid protocol version, group, sender or sequence")
	}
	switch m.Kind {
	case CompleteKind:
		if m.Hello != nil || m.Observation != nil {
			return fmt.Errorf("complete has no payload")
		}
		return nil
	case HelloKind:
		if m.Hello == nil || m.Observation != nil {
			return fmt.Errorf("hello requires its own payload only")
		}
		return m.Hello.validate()
	case TrafficKind:
		if m.Observation == nil || m.Hello != nil {
			return fmt.Errorf("traffic observation requires its own payload only")
		}
		return m.Observation.validate()
	default:
		return fmt.Errorf("unknown message kind")
	}
}

func (h Hello) validate() error {
	if !safeText(h.Name, 128) || (h.OS != "linux" && h.OS != "windows" && h.OS != "android") {
		return fmt.Errorf("invalid hello device description")
	}
	if len(h.Roles) == 0 || !validSet(h.Roles, []string{"agent", "gateway"}) ||
		!validSet(h.Capabilities, []string{"observe_local_traffic", "manage_gateway_traffic", "relay_traffic"}) {
		return fmt.Errorf("invalid hello roles or capabilities")
	}
	return nil
}

func (o TrafficObservation) validate() error {
	if o.ObservedAt.IsZero() || o.Source != "linux_proc_net_dev" || o.Scope != "process_network_namespace" ||
		math.IsNaN(o.WindowMS) || math.IsInf(o.WindowMS, 0) || o.WindowMS <= 0 || o.WindowMS > 60000 || len(o.Interfaces) > 128 {
		return fmt.Errorf("invalid traffic observation metadata")
	}
	names := make(map[string]bool, len(o.Interfaces))
	for _, item := range o.Interfaces {
		if !safeText(item.Name, 256) || names[item.Name] {
			return fmt.Errorf("invalid or duplicate interface name")
		}
		names[item.Name] = true
		switch item.State {
		case "measured":
			if !validCounter(item.ReceivedBytes) || !validCounter(item.SentBytes) {
				return fmt.Errorf("measured interface requires decimal byte deltas")
			}
		case "appeared", "disappeared", "counters_reset":
			if item.ReceivedBytes != nil || item.SentBytes != nil {
				return fmt.Errorf("unavailable interface cannot have measured byte deltas")
			}
		default:
			return fmt.Errorf("unknown interface observation state")
		}
	}
	return nil
}

func validCounter(value *string) bool {
	if value == nil {
		return false
	}
	number, err := strconv.ParseUint(*value, 10, 64)
	return err == nil && strconv.FormatUint(number, 10) == *value
}

func safeText(value string, limit int) bool {
	return len(value) <= limit && utf8.ValidString(value) && strings.TrimSpace(value) != "" && !strings.ContainsFunc(value, unicode.IsControl)
}

func validID(value string) bool {
	return safeText(value, 128) && !strings.ContainsFunc(value, unicode.IsSpace)
}

func validFingerprint(value string) bool {
	if !strings.HasPrefix(value, "ed25519:") || len(value) != 72 || value != strings.ToLower(value) {
		return false
	}
	_, err := hex.DecodeString(value[8:])
	return err == nil
}

func validSet(values, allowed []string) bool {
	if len(values) > len(allowed) {
		return false
	}
	seen := make(map[string]bool, len(values))
	for _, value := range values {
		found := false
		for _, candidate := range allowed {
			found = found || value == candidate
		}
		if !found || seen[value] {
			return false
		}
		seen[value] = true
	}
	return true
}
