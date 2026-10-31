package linux

import (
	"encoding/json"
	"fmt"
)

type CakeCounters struct{ Bytes, Packets, Drops, Overlimits, Requeues uint64 }

type CakeTinField struct {
	Available bool
	Value     *uint64
	Reason    string
}

type CakeStatistics struct {
	Counters                CakeCounters
	BacklogBytes            uint64
	QueuedPackets           uint64
	MemoryUsedReportedBytes uint64
	MemoryLimitBytes        uint64
	TinCount                int
	TinFields               map[string]CakeTinField
}

type CakeReading struct {
	Raw           []byte
	Configuration CakeConfiguration
	Statistics    CakeStatistics
}

// ParseCakeReading retains the exact validated dump, including unknown fields.
// It neither runs tc nor establishes namespace ownership or counter continuity.
func ParseCakeReading(data []byte, profile CakeProducerProfile) (CakeReading, error) {
	row, err := cakeRoot(data, profile)
	if err != nil {
		return CakeReading{}, err
	}
	configuration, err := cakeConfiguration(row, profile)
	if err != nil {
		return CakeReading{}, err
	}
	var stats CakeStatistics
	for _, field := range []struct {
		key    string
		target *uint64
	}{
		{"bytes", &stats.Counters.Bytes}, {"packets", &stats.Counters.Packets}, {"drops", &stats.Counters.Drops},
		{"overlimits", &stats.Counters.Overlimits}, {"requeues", &stats.Counters.Requeues},
		{"backlog", &stats.BacklogBytes}, {"qlen", &stats.QueuedPackets},
		{"memory_used", &stats.MemoryUsedReportedBytes}, {"memory_limit", &stats.MemoryLimitBytes},
	} {
		value, err := cakeUnsigned(row, field.key)
		if err != nil {
			return CakeReading{}, err
		}
		*field.target = value
	}
	if stats.MemoryLimitBytes != cakeMemoryLimitBytes {
		return CakeReading{}, fmt.Errorf("unexpected CAKE memory limit")
	}
	tinData, err := cakeValue(row, "tins")
	if err != nil {
		return CakeReading{}, err
	}
	var tins []json.RawMessage
	if err := json.Unmarshal(tinData, &tins); err != nil || len(tins) != 1 {
		return CakeReading{}, fmt.Errorf("exactly one CAKE tin required")
	}
	tin, err := cakeObjectFrom(tins[0])
	if err != nil {
		return CakeReading{}, err
	}
	stats.TinCount = 1
	stats.TinFields = make(map[string]CakeTinField)
	for _, key := range []string{"threshold_rate", "sent_bytes", "backlog_bytes", "target_us", "interval_us",
		"peak_delay_us", "avg_delay_us", "base_delay_us", "sent_packets", "way_indirect_hits", "way_misses",
		"way_collisions", "drops", "ecn_mark", "ack_drops", "sparse_flows", "bulk_flows", "unresponsive_flows",
		"max_pkt_len", "flow_quantum"} {
		if _, present := tin[key]; !present {
			stats.TinFields[key] = CakeTinField{Reason: "not_reported"}
			continue
		}
		value, err := cakeUnsigned(tin, key)
		if err != nil {
			return CakeReading{}, err
		}
		stats.TinFields[key] = CakeTinField{Available: true, Value: &value}
	}
	return CakeReading{Raw: append([]byte(nil), data...), Configuration: configuration, Statistics: stats}, nil
}

type CakeCounterDelta struct {
	Available bool
	Counters  *CakeCounters
	Reason    string
}

// DiffCakeCounters compares only cumulative counters of the same owned queue.
// Callers must check each adjacent pair; a final pair cannot reveal a reset that
// recovered between observations. No gauge, rate or end-to-end loss is computed.
func DiffCakeCounters(before, after CakeCounters) CakeCounterDelta {
	if after.Bytes < before.Bytes || after.Packets < before.Packets || after.Drops < before.Drops ||
		after.Overlimits < before.Overlimits || after.Requeues < before.Requeues {
		return CakeCounterDelta{Reason: "counter_decreased"}
	}
	return CakeCounterDelta{Available: true, Counters: &CakeCounters{
		Bytes: after.Bytes - before.Bytes, Packets: after.Packets - before.Packets, Drops: after.Drops - before.Drops,
		Overlimits: after.Overlimits - before.Overlimits, Requeues: after.Requeues - before.Requeues}}
}
