package linux

import (
	"bytes"
	"encoding/json"
	"math"
	"os"
	"reflect"
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func cakeFixture(t *testing.T, name string) []byte {
	t.Helper()
	data, err := os.ReadFile("testdata/cake/" + name + ".json")
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func changedCake(t *testing.T, change func(map[string]any)) []byte {
	t.Helper()
	var rows []map[string]any
	if err := json.Unmarshal(cakeFixture(t, "down"), &rows); err != nil {
		t.Fatal(err)
	}
	change(rows[0])
	data, err := json.Marshal(rows)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestCakeCatalogueIsFixedAndReturnsIndependentArguments(t *testing.T) {
	profile, err := LookupCakeReference(core.CakeReferenceIPv4LabV1)
	if err != nil || profile.Interface != "wan" || profile.Handle != "10:" || profile.RateBitsPerSecond != 4000000 || profile.RTTUS != 100000 || profile.MemoryLimitBytes != 1048576 {
		t.Fatalf("unexpected catalogue entry: %+v, %v", profile, err)
	}
	want := strings.Fields("qdisc add dev wan root handle 10: cake bandwidth 4mbit besteffort flows nonat nowash raw mpu 0 rtt 100ms split-gso no-ack-filter egress memlimit 1048576 fwmark 0")
	if !reflect.DeepEqual(profile.AddArguments, want) {
		t.Fatalf("reference arguments changed: %v", profile.AddArguments)
	}
	profile.AddArguments[1] = "replace"
	again, err := LookupCakeReference(core.CakeReferenceIPv4LabV1)
	if err != nil || !reflect.DeepEqual(again.AddArguments, want) {
		t.Fatal("caller modified the shared catalogue")
	}
	for _, id := range []core.CakeReferenceID{"", "cake", "cake-ipv4-lab-8mbit-v1"} {
		value, err := LookupCakeReference(id)
		if err == nil || !reflect.DeepEqual(value, CakeReference{}) {
			t.Fatalf("unknown reference accepted: %q", id)
		}
	}
}

func TestCakeProducerRequiresIdentifiedVersionAndKeepsExactBanner(t *testing.T) {
	for _, data := range []string{"tc utility, iproute2-6.1.0\n", "tc utility, iproute2-6.1.0, libbpf 1.3.0\n"} {
		producer, err := ParseCakeProducer([]byte(data))
		if err != nil || producer.Profile != CakeIPRoute2V610 || producer.VersionOutput != data {
			t.Fatalf("banner changed: %+v, %v", producer, err)
		}
	}
	for _, data := range []string{"", "tc utility, iproute2-6.10.0\n", "tc utility, iproute2-6.1.0-custom\n", "tc utility, iproute2-6.1.0\nextra", "\xff", strings.Repeat("x", 513)} {
		if _, err := ParseCakeProducer([]byte(data)); err == nil {
			t.Fatalf("unsupported producer accepted: %q", data)
		}
	}
}

func TestCakeNativeFixturesPreserveUnitsOptionsAndAllKnownStatistics(t *testing.T) {
	for _, name := range []string{"down", "active"} {
		t.Run(name, func(t *testing.T) {
			data := cakeFixture(t, name)
			reading, err := ParseCakeReading(data, CakeIPRoute2V610)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(reading.Raw, data) || reading.Configuration.Profile != CakeIPRoute2V610 {
				t.Fatal("raw dump or producer lost")
			}
			want := CakeOptions{BandwidthBytesPerSecond: 500000, RTTUS: 100000, MemoryLimitBytes: 1048576, Diffserv: "besteffort", FlowMode: "flows", ACKFilter: "disabled", SplitGSO: true, Raw: true, FWMark: "0", ATM: "noatm"}
			if !reflect.DeepEqual(reading.Configuration.Effective, want) {
				t.Fatalf("wrong normalization: %+v", reading.Configuration)
			}
			if len(reading.Configuration.OmittedFields) != 3 || reading.Configuration.OmittedFields["mpu"] != "iproute2_6_1_0_omits_zero_mpu" {
				t.Fatal("omission justification missing")
			}
			stats := reading.Statistics
			if stats.TinCount != 1 || len(stats.TinFields) != 20 || stats.MemoryLimitBytes != 1048576 {
				t.Fatal("tin or memory limit lost")
			}
			for key, field := range stats.TinFields {
				if !field.Available || field.Value == nil || field.Reason != "" {
					t.Fatalf("native field unavailable: %s", key)
				}
			}
			if *stats.TinFields["threshold_rate"].Value != 500000 || *stats.TinFields["target_us"].Value != 5000 {
				t.Fatal("tin fields aliased or wrong units")
			}
			if name == "down" && stats.Counters != (CakeCounters{}) {
				t.Fatal("zero counters changed")
			}
			if name == "active" && (stats.Counters.Bytes != 3642 || stats.Counters.Packets != 51 || stats.Counters.Overlimits != 72 || stats.MemoryUsedReportedBytes != 2304) {
				t.Fatalf("native counters lost: %+v", stats)
			}
			data[0] = 'x'
			if reading.Raw[0] == 'x' {
				t.Fatal("caller input aliases preserved raw dump")
			}
		})
	}
}

func TestCakeConfigurationRejectsEveryMissingOrMistypedRequiredOption(t *testing.T) {
	var rows []map[string]any
	json.Unmarshal(cakeFixture(t, "down"), &rows)
	for key, value := range rows[0]["options"].(map[string]any) {
		bad := []any{nil, json.RawMessage("null")}
		switch value.(type) {
		case float64:
			bad = append(bad, true, "0", json.RawMessage("1.0"), -1)
		case bool:
			bad = append(bad, 1, "false", !value.(bool))
		case string:
			bad = append(bad, 0, false, "unexpected")
		}
		for _, replacement := range bad {
			data := changedCake(t, func(row map[string]any) {
				opts := row["options"].(map[string]any)
				if replacement == nil {
					delete(opts, key)
				} else {
					opts[key] = replacement
				}
			})
			if _, err := ParseCakeConfiguration(data, CakeIPRoute2V610); err == nil {
				t.Errorf("option %s accepted missing/wrong value %v", key, replacement)
			}
		}
	}
	for key, value := range map[string]any{"bandwidth": 4000000, "rtt": 100, "memlimit": 131072, "flowmode": "triple-isolate", "fwmark": "0x1", "mpu": 64, "atm": "atm", "autorate": false} {
		data := changedCake(t, func(row map[string]any) { row["options"].(map[string]any)[key] = value })
		if _, err := ParseCakeConfiguration(data, CakeIPRoute2V610); err == nil {
			t.Errorf("nonreference option accepted: %s", key)
		}
	}
	data := changedCake(t, func(row map[string]any) {
		opts := row["options"].(map[string]any)
		opts["mpu"] = 0
		opts["atm"] = "noatm"
	})
	config, err := ParseCakeConfiguration(data, CakeIPRoute2V610)
	if err != nil || len(config.OmittedFields) != 1 || config.OmittedFields["autorate"] == "" {
		t.Fatal("explicit optional fields rejected or omissions fabricated")
	}
	if _, err := ParseCakeConfiguration(data, "unknown"); err == nil {
		t.Fatal("unknown producer profile accepted")
	}
}

func TestCakeRootAndInitialDumpNeverAdmitAnotherQueue(t *testing.T) {
	for key, value := range map[string]any{"kind": "tbf", "root": 1, "handle": "11:", "parent": nil, "dev": "eth0", "options": nil} {
		data := changedCake(t, func(row map[string]any) { row[key] = value })
		if _, err := ParseCakeReading(data, CakeIPRoute2V610); err == nil {
			t.Errorf("unexpected root field accepted: %s", key)
		}
	}
	for _, data := range []string{"[]", "null", "{}", "[null]", "[true]", `[{"kind":"cake"},{"kind":"cake"}]`} {
		if _, err := ParseCakeReading([]byte(data), CakeIPRoute2V610); err == nil {
			t.Errorf("invalid CAKE root accepted: %s", data)
		}
	}
	for _, data := range []string{"[]", `[{"kind":"noqueue","root":true,"handle":"0:"}]`, `[{"kind":"noqueue","root":true,"handle":"0:","dev":"wan"}]`} {
		if err := ValidateCakeInitial([]byte(data)); err != nil {
			t.Fatalf("valid initial state rejected: %v", err)
		}
	}
	for _, data := range []string{"null", "[null]", `[{"kind":"noqueue","root":1,"handle":"0:"}]`, `[{"kind":"noqueue","root":true,"handle":"0:","parent":null}]`, `[{"kind":"noqueue","root":true,"handle":"0:","dev":"eth0"}]`} {
		if err := ValidateCakeInitial([]byte(data)); err == nil {
			t.Errorf("invalid initial state accepted: %s", data)
		}
	}
	if err := ValidateCakeInitial(cakeFixture(t, "down")); err == nil {
		t.Fatal("existing CAKE admitted as fresh initial state")
	}
}

func TestCakeRequiredStatisticsStayExactAndMissingNeverBecomesZero(t *testing.T) {
	for _, key := range []string{"bytes", "packets", "drops", "overlimits", "requeues", "backlog", "qlen", "memory_used", "memory_limit"} {
		for _, bad := range []any{nil, json.RawMessage("null"), true, -1, "0", json.RawMessage("0.0"), json.RawMessage("18446744073709551616")} {
			data := changedCake(t, func(row map[string]any) {
				if bad == nil {
					delete(row, key)
				} else {
					row[key] = bad
				}
			})
			if _, err := ParseCakeReading(data, CakeIPRoute2V610); err == nil {
				t.Errorf("invalid %s accepted: %v", key, bad)
			}
		}
	}
	data := changedCake(t, func(row map[string]any) { row["bytes"] = uint64(math.MaxUint64); row["memory_used"] = 1048576 + 4096 })
	reading, err := ParseCakeReading(data, CakeIPRoute2V610)
	if err != nil || reading.Statistics.Counters.Bytes != math.MaxUint64 || reading.Statistics.MemoryUsedReportedBytes != 1048576+4096 {
		t.Fatalf("uint64 precision or reported memory peak lost: %+v, %v", reading, err)
	}
	data = changedCake(t, func(row map[string]any) { row["memory_limit"] = 1 })
	if _, err := ParseCakeReading(data, CakeIPRoute2V610); err == nil {
		t.Fatal("wrong memory limit accepted")
	}
}

func TestCakeTinAvailabilityAndRawUnknownFieldsArePreserved(t *testing.T) {
	data := changedCake(t, func(row map[string]any) {
		row["tins"] = []any{map[string]any{"sent_bytes": uint64(math.MaxUint64)}}
		row["future-field"] = map[string]any{"huge": json.RawMessage(strings.Repeat("9", 400))}
	})
	reading, err := ParseCakeReading(data, CakeIPRoute2V610)
	if err != nil || !bytes.Equal(data, reading.Raw) {
		t.Fatalf("unknown data rejected or lost: %v", err)
	}
	field := reading.Statistics.TinFields["way_misses"]
	if field.Available || field.Value != nil || field.Reason != "not_reported" {
		t.Fatalf("missing tin field became zero: %+v", field)
	}
	field = reading.Statistics.TinFields["sent_bytes"]
	if !field.Available || field.Value == nil || *field.Value != math.MaxUint64 {
		t.Fatal("uint64 tin precision lost")
	}
	for _, bad := range []any{nil, []any{}, []any{true}, []any{map[string]any{}, map[string]any{}}, []any{map[string]any{"sent_packets": nil}}, []any{map[string]any{"ecn_mark": false}}, []any{map[string]any{"sent_bytes": -1}}} {
		data := changedCake(t, func(row map[string]any) { row["tins"] = bad })
		if _, err := ParseCakeReading(data, CakeIPRoute2V610); err == nil {
			t.Errorf("invalid tin accepted: %v", bad)
		}
	}
}

func TestCakeStrictProducerJSONRejectsAmbiguityAndBoundsInput(t *testing.T) {
	data := cakeFixture(t, "down")
	for _, bad := range [][]byte{append(append([]byte(nil), data...), []byte(" []")...), []byte(`[{"kind":"cake","kind":"tbf"}]`), []byte(`[{"x":1e999}]`), []byte("[NaN]"), []byte{0xff}, bytes.Repeat([]byte(" "), cakeOutputLimit+1)} {
		if _, err := ParseCakeReading(bad, CakeIPRoute2V610); err == nil {
			t.Fatal("ambiguous or oversized dump accepted")
		}
	}
	padded := append(append([]byte(nil), data...), bytes.Repeat([]byte(" "), cakeOutputLimit-len(data))...)
	if _, err := ParseCakeReading(padded, CakeIPRoute2V610); err != nil {
		t.Fatalf("exact size limit rejected: %v", err)
	}
}

func TestCakeCounterDifferencesAreUnsignedAndNeverHideResets(t *testing.T) {
	before := CakeCounters{100, 100, 100, 100, 100}
	after := CakeCounters{101, 102, 103, 104, 105}
	delta := DiffCakeCounters(before, after)
	if !delta.Available || delta.Counters == nil || *delta.Counters != (CakeCounters{1, 2, 3, 4, 5}) || delta.Reason != "" {
		t.Fatalf("wrong delta: %+v", delta)
	}
	for _, change := range []func(*CakeCounters){func(c *CakeCounters) { c.Bytes = 99 }, func(c *CakeCounters) { c.Packets = 99 }, func(c *CakeCounters) { c.Drops = 99 }, func(c *CakeCounters) { c.Overlimits = 99 }, func(c *CakeCounters) { c.Requeues = 99 }} {
		value := after
		change(&value)
		delta := DiffCakeCounters(before, value)
		if delta.Available || delta.Counters != nil || delta.Reason != "counter_decreased" {
			t.Fatal("reset became a zero or wrapped delta")
		}
	}
	delta = DiffCakeCounters(CakeCounters{}, CakeCounters{Bytes: math.MaxUint64})
	if !delta.Available || delta.Counters.Bytes != math.MaxUint64 {
		t.Fatal("large integer delta rounded")
	}
	if !DiffCakeCounters(CakeCounters{}, CakeCounters{}).Available {
		t.Fatal("known inactivity became missing")
	}
}
