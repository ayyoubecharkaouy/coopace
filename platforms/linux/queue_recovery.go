package linux

import (
	"bytes"
	"encoding/json"
	"fmt"
)

const QueueRecoveryNoQueueV1 = "noqueue-root-v1"

// QueueRecoveryAssessment describes a candidate for a bounded lab test. It is
// not a restorable backup, proof of ownership, or permission to delete a qdisc.
type QueueRecoveryAssessment struct {
	Candidate bool     `json:"candidate"`
	Profile   string   `json:"profile,omitempty"`
	Reasons   []string `json:"reasons"`
}

func queueRecoveryRefusal(reason string) QueueRecoveryAssessment {
	return QueueRecoveryAssessment{Reasons: []string{reason}}
}

func AssessQueueRecovery(source GatewayQueueSnapshot) (QueueRecoveryAssessment, error) {
	if err := ValidateGatewayQueueSnapshot(source); err != nil {
		return QueueRecoveryAssessment{}, err
	}
	if source.Partial() {
		return queueRecoveryRefusal("incomplete_snapshot"), nil
	}
	// The first profile has no class hierarchy, filters, shared blocks or
	// externally supplied options to reconstruct. Extra fields fail closed.
	var rows []map[string]json.RawMessage
	if err := json.Unmarshal(source.Readings[1].Value, &rows); err != nil {
		return QueueRecoveryAssessment{}, err
	}
	if len(rows) != 1 {
		return queueRecoveryRefusal("single_noqueue_root_required"), nil
	}
	root := rows[0]
	for key, expected := range map[string]any{"kind": "noqueue", "handle": "0:", "root": true} {
		value, _ := json.Marshal(expected)
		var actual any
		if json.Unmarshal(root[key], &actual) != nil {
			return queueRecoveryRefusal("single_noqueue_root_required"), nil
		}
		encoded, _ := json.Marshal(actual)
		if string(encoded) != string(value) {
			return queueRecoveryRefusal("single_noqueue_root_required"), nil
		}
	}
	var options map[string]json.RawMessage
	if json.Unmarshal(root["options"], &options) != nil || options == nil || len(options) != 0 {
		return queueRecoveryRefusal("empty_noqueue_options_required"), nil
	}
	for key, raw := range root {
		switch key {
		case "kind", "handle", "root", "dev", "options":
		case "refcnt", "bytes", "packets", "drops", "overlimits", "requeues", "backlog", "qlen":
			var number uint64
			if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) || json.Unmarshal(raw, &number) != nil {
				return queueRecoveryRefusal("invalid_qdisc_counter"), nil
			}
		default:
			return queueRecoveryRefusal("unsupported_qdisc_field"), nil
		}
	}
	for _, reading := range source.Readings[2:] {
		var entries []json.RawMessage
		if err := json.Unmarshal(reading.Value, &entries); err != nil {
			return QueueRecoveryAssessment{}, err
		}
		if len(entries) != 0 {
			return queueRecoveryRefusal("classes_or_filters_present"), nil
		}
	}
	var links []map[string]json.RawMessage
	if err := json.Unmarshal(source.Readings[0].Value, &links); err != nil {
		return QueueRecoveryAssessment{}, err
	}
	var kind, address string
	if json.Unmarshal(links[0]["qdisc"], &kind) != nil || kind != "noqueue" {
		return queueRecoveryRefusal("link_qdisc_inconsistent"), nil
	}
	if source.Interface.HardwareAddress == "" || json.Unmarshal(links[0]["address"], &address) != nil || address != source.Interface.HardwareAddress {
		return queueRecoveryRefusal("link_identity_incomplete"), nil
	}
	return QueueRecoveryAssessment{Candidate: true, Profile: QueueRecoveryNoQueueV1, Reasons: []string{"noqueue_without_visible_dependencies"}}, nil
}

type QueueRecoveryComparison struct {
	Decision string   `json:"decision"`
	Reasons  []string `json:"reasons"`
}

// CompareQueueRecovery compares the selected state, ignoring counters/refcnt.
// It deliberately makes no claim that an intervention or rollback occurred.
func CompareQueueRecovery(before, after GatewayQueueSnapshot) (QueueRecoveryComparison, error) {
	baseline, err := AssessQueueRecovery(before)
	if err != nil {
		return QueueRecoveryComparison{}, err
	}
	observed, err := AssessQueueRecovery(after)
	if err != nil {
		return QueueRecoveryComparison{}, err
	}
	result := func(decision, reason string) (QueueRecoveryComparison, error) {
		return QueueRecoveryComparison{decision, []string{reason}}, nil
	}
	if !baseline.Candidate {
		return result("indeterminate", "baseline_not_supported")
	}
	if !after.StartedAt.After(before.FinishedAt) {
		return result("indeterminate", "later_distinct_observation_required")
	}
	if before.Interface != after.Interface {
		return result("mismatch", "interface_identity_or_state_changed")
	}
	if !observed.Candidate {
		if after.Partial() {
			return result("indeterminate", "incomplete_after_snapshot")
		}
		return QueueRecoveryComparison{Decision: "mismatch", Reasons: append([]string{"after_state_outside_baseline_profile"}, observed.Reasons...)}, nil
	}
	if baseline.Profile != observed.Profile {
		return QueueRecoveryComparison{}, fmt.Errorf("profil de comparaison interne incohérent")
	}
	return result("selected_state_matches", "noqueue_and_selected_dependencies_match")
}
