package linux

import (
	"encoding/json"
	"os"
	"testing"
	"time"
)

func recoveryFixture(t *testing.T) GatewayQueueSnapshot {
	t.Helper()
	data, err := os.ReadFile("../../docs/examples/queue-snapshot-noqueue.json")
	if err != nil {
		t.Fatal(err)
	}
	var source struct {
		Snapshot GatewayQueueSnapshot `json:"snapshot"`
	}
	if err := json.Unmarshal(data, &source); err != nil {
		t.Fatal(err)
	}
	return source.Snapshot
}

func mutateRecoveryRoot(t *testing.T, source *GatewayQueueSnapshot, change func(map[string]json.RawMessage)) {
	t.Helper()
	var rows []map[string]json.RawMessage
	if err := json.Unmarshal(source.Readings[1].Value, &rows); err != nil {
		t.Fatal(err)
	}
	change(rows[0])
	source.Readings[1].Value, _ = json.Marshal(rows)
}

func laterRecoveryFixture(t *testing.T) GatewayQueueSnapshot {
	source := recoveryFixture(t)
	delta := 3 * time.Second
	source.StartedAt = source.StartedAt.Add(delta)
	source.FinishedAt = source.FinishedAt.Add(delta)
	for index := range source.Readings {
		reading := &source.Readings[index]
		reading.StartedAt = reading.StartedAt.Add(delta)
		reading.FinishedAt = reading.FinishedAt.Add(delta)
		if proof := reading.ClassesTextFallback; proof != nil {
			proof.StartedAt = proof.StartedAt.Add(delta)
			proof.FinishedAt = proof.FinishedAt.Add(delta)
		}
	}
	return source
}

func TestQueueRecoveryCandidateAndRefusals(t *testing.T) {
	for name, change := range map[string]func(*GatewayQueueSnapshot){
		"candidate": func(*GatewayQueueSnapshot) {},
		"partial": func(s *GatewayQueueSnapshot) {
			s.Readings[3].Available = false
			s.Readings[3].Value = nil
			s.Readings[3].Reason = "missing"
		},
		"class_hierarchy": func(s *GatewayQueueSnapshot) {
			s.Readings[2].Normalization = ""
			s.Readings[2].SourceOutput = nil
			s.Readings[2].ClassesTextFallback = nil
			s.Readings[2].Value = json.RawMessage(`[{"class":"htb"}]`)
		},
		"filter": func(s *GatewayQueueSnapshot) { s.Readings[3].Value = json.RawMessage(`[{}]`) },
		"cake": func(s *GatewayQueueSnapshot) {
			mutateRecoveryRoot(t, s, func(r map[string]json.RawMessage) { r["kind"] = json.RawMessage(`"cake"`) })
		},
		"shared_block": func(s *GatewayQueueSnapshot) {
			mutateRecoveryRoot(t, s, func(r map[string]json.RawMessage) { r["ingress_block"] = json.RawMessage(`42`) })
		},
		"options": func(s *GatewayQueueSnapshot) {
			mutateRecoveryRoot(t, s, func(r map[string]json.RawMessage) { r["options"] = json.RawMessage(`{"unknown":1}`) })
		},
		"missing_options": func(s *GatewayQueueSnapshot) {
			mutateRecoveryRoot(t, s, func(r map[string]json.RawMessage) { delete(r, "options") })
		},
		"unknown_qdisc_field": func(s *GatewayQueueSnapshot) {
			mutateRecoveryRoot(t, s, func(r map[string]json.RawMessage) { r["offloaded"] = json.RawMessage(`true`) })
		},
		"counter_null": func(s *GatewayQueueSnapshot) {
			mutateRecoveryRoot(t, s, func(r map[string]json.RawMessage) { r["bytes"] = json.RawMessage(`null`) })
		},
		"counter_float": func(s *GatewayQueueSnapshot) {
			mutateRecoveryRoot(t, s, func(r map[string]json.RawMessage) { r["bytes"] = json.RawMessage(`1.5`) })
		},
		"parent": func(s *GatewayQueueSnapshot) {
			mutateRecoveryRoot(t, s, func(r map[string]json.RawMessage) { r["parent"] = json.RawMessage(`"1:"`) })
		},
		"link_disagrees": func(s *GatewayQueueSnapshot) {
			var rows []map[string]any
			json.Unmarshal(s.Readings[0].Value, &rows)
			rows[0]["qdisc"] = "fq_codel"
			s.Readings[0].Value, _ = json.Marshal(rows)
		},
	} {
		t.Run(name, func(t *testing.T) {
			source := recoveryFixture(t)
			change(&source)
			assessment, err := AssessQueueRecovery(source)
			if err != nil {
				t.Fatal(err)
			}
			if assessment.Candidate != (name == "candidate") || len(assessment.Reasons) == 0 {
				t.Fatalf("wrong assessment: %+v", assessment)
			}
		})
	}
}

func TestQueueRecoveryComparisonDetectsChangesAndIgnoresOnlyVolatileCounters(t *testing.T) {
	for name, change := range map[string]func(*GatewayQueueSnapshot){
		"same_selected_state": func(s *GatewayQueueSnapshot) {
			mutateRecoveryRoot(t, s, func(r map[string]json.RawMessage) {
				r["bytes"] = json.RawMessage(`18446744073709551615`)
				r["refcnt"] = json.RawMessage(`3`)
			})
		},
		"identity_changed": func(s *GatewayQueueSnapshot) { s.Interface.HardwareAddress = "02:00:00:00:00:02" },
		"flags_changed":    func(s *GatewayQueueSnapshot) { s.Interface.Flags = 2 },
		"other_queue": func(s *GatewayQueueSnapshot) {
			mutateRecoveryRoot(t, s, func(r map[string]json.RawMessage) { r["kind"] = json.RawMessage(`"fq_codel"`) })
		},
		"filter_added": func(s *GatewayQueueSnapshot) { s.Readings[4].Value = json.RawMessage(`[{}]`) },
	} {
		t.Run(name, func(t *testing.T) {
			before, after := recoveryFixture(t), laterRecoveryFixture(t)
			change(&after)
			result, err := CompareQueueRecovery(before, after)
			if err != nil {
				t.Fatal(err)
			}
			want := "mismatch"
			if name == "same_selected_state" {
				want = "selected_state_matches"
			}
			if result.Decision != want {
				t.Fatalf("want %s got %+v", want, result)
			}
		})
	}
	before := recoveryFixture(t)
	result, err := CompareQueueRecovery(before, before)
	if err != nil || result.Decision != "indeterminate" {
		t.Fatalf("same observation accepted: %+v %v", result, err)
	}
	after := laterRecoveryFixture(t)
	after.Readings[3].Available = false
	after.Readings[3].Value = nil
	after.Readings[3].Reason = "missing"
	result, err = CompareQueueRecovery(before, after)
	if err != nil || result.Decision != "indeterminate" {
		t.Fatalf("missing after evidence accepted: %+v %v", result, err)
	}
}
