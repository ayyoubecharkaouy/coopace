package core

import (
	"fmt"
	"sort"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"
)

// InterfaceCounters contains cumulative byte counters, not Internet capacity.
type InterfaceCounters struct {
	Name          string
	ReceivedBytes uint64
	SentBytes     uint64
}

type TrafficState string

const (
	TrafficMeasured    TrafficState = "measured"
	TrafficAppeared    TrafficState = "appeared"
	TrafficDisappeared TrafficState = "disappeared"
	TrafficReset       TrafficState = "counters_reset"
)

// InterfaceTraffic contains deltas and average rates over one sampling window.
type InterfaceTraffic struct {
	ReceivedBytes          uint64
	SentBytes              uint64
	ReceivedBytesPerSecond float64
	SentBytesPerSecond     float64
}

// InterfaceObservation has no Traffic value when a rate cannot be calculated.
type InterfaceObservation struct {
	Name    string
	State   TrafficState
	Traffic *InterfaceTraffic
}

// MeasureTraffic compares two snapshots without summing interfaces or doing I/O.
// A counter decrease invalidates both directions for that interface's window.
func MeasureTraffic(before, after []InterfaceCounters, elapsed time.Duration) ([]InterfaceObservation, error) {
	if elapsed <= 0 {
		return nil, fmt.Errorf("traffic sampling interval must be positive")
	}
	previous, err := indexCounters(before)
	if err != nil {
		return nil, fmt.Errorf("initial traffic snapshot: %w", err)
	}
	current, err := indexCounters(after)
	if err != nil {
		return nil, fmt.Errorf("final traffic snapshot: %w", err)
	}
	names := make(map[string]struct{}, len(previous)+len(current))
	for name := range previous {
		names[name] = struct{}{}
	}
	for name := range current {
		names[name] = struct{}{}
	}
	ordered := make([]string, 0, len(names))
	for name := range names {
		ordered = append(ordered, name)
	}
	sort.Strings(ordered)
	observations := make([]InterfaceObservation, 0, len(ordered))
	for _, name := range ordered {
		start, existed := previous[name]
		end, exists := current[name]
		observation := InterfaceObservation{Name: name}
		switch {
		case !existed:
			observation.State = TrafficAppeared
		case !exists:
			observation.State = TrafficDisappeared
		case end.ReceivedBytes < start.ReceivedBytes || end.SentBytes < start.SentBytes:
			observation.State = TrafficReset
		default:
			received := end.ReceivedBytes - start.ReceivedBytes
			sent := end.SentBytes - start.SentBytes
			observation.State = TrafficMeasured
			observation.Traffic = &InterfaceTraffic{
				ReceivedBytes:          received,
				SentBytes:              sent,
				ReceivedBytesPerSecond: float64(received) / elapsed.Seconds(),
				SentBytesPerSecond:     float64(sent) / elapsed.Seconds(),
			}
		}
		observations = append(observations, observation)
	}
	return observations, nil
}

func indexCounters(counters []InterfaceCounters) (map[string]InterfaceCounters, error) {
	indexed := make(map[string]InterfaceCounters, len(counters))
	for _, counter := range counters {
		if !utf8.ValidString(counter.Name) || strings.TrimSpace(counter.Name) == "" || strings.ContainsFunc(counter.Name, unicode.IsControl) {
			return nil, fmt.Errorf("invalid interface name")
		}
		if _, exists := indexed[counter.Name]; exists {
			return nil, fmt.Errorf("duplicate interface: %q", counter.Name)
		}
		indexed[counter.Name] = counter
	}
	return indexed, nil
}
