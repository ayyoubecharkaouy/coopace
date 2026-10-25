package core_test

import (
	"math"
	"reflect"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestTrafficRatesUseByteDeltasAndActualDuration(t *testing.T) {
	for _, tt := range []struct {
		name          string
		before, after core.InterfaceCounters
		received      uint64
		sent          uint64
	}{
		{"active", core.InterfaceCounters{Name: "eth0", ReceivedBytes: 100, SentBytes: 50}, core.InterfaceCounters{Name: "eth0", ReceivedBytes: 1100, SentBytes: 2050}, 1000, 2000},
		{"idle", core.InterfaceCounters{Name: "eth0", ReceivedBytes: 100}, core.InterfaceCounters{Name: "eth0", ReceivedBytes: 100}, 0, 0},
		{"large counters with small delta", core.InterfaceCounters{Name: "eth0", ReceivedBytes: math.MaxUint64 - 5}, core.InterfaceCounters{Name: "eth0", ReceivedBytes: math.MaxUint64 - 1}, 4, 0},
	} {
		t.Run(tt.name, func(t *testing.T) {
			observations, err := core.MeasureTraffic([]core.InterfaceCounters{tt.before}, []core.InterfaceCounters{tt.after}, 2*time.Second)
			if err != nil {
				t.Fatal(err)
			}
			if len(observations) != 1 || observations[0].State != core.TrafficMeasured || observations[0].Traffic == nil {
				t.Fatalf("missing valid traffic measurement: %+v", observations)
			}
			rate := observations[0].Traffic
			if rate.ReceivedBytes != tt.received || rate.SentBytes != tt.sent || rate.ReceivedBytesPerSecond != float64(tt.received)/2 || rate.SentBytesPerSecond != float64(tt.sent)/2 {
				t.Fatalf("incorrect delta or rate: %+v", rate)
			}
		})
	}
}

func TestTrafficChangesAreUnavailableInsteadOfZero(t *testing.T) {
	before := []core.InterfaceCounters{
		{Name: "gone"}, {Name: "reset-rx", ReceivedBytes: 100}, {Name: "reset-tx", SentBytes: 100},
	}
	after := []core.InterfaceCounters{
		{Name: "new"}, {Name: "reset-rx", ReceivedBytes: 1}, {Name: "reset-tx", SentBytes: 1},
	}
	observations, err := core.MeasureTraffic(before, after, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]core.TrafficState{
		"gone": core.TrafficDisappeared, "new": core.TrafficAppeared,
		"reset-rx": core.TrafficReset, "reset-tx": core.TrafficReset,
	}
	if len(observations) != len(want) {
		t.Fatalf("missing interface changes: %+v", observations)
	}
	for _, observation := range observations {
		if observation.State != want[observation.Name] || observation.Traffic != nil {
			t.Errorf("unavailable sample incorrectly measured: %+v", observation)
		}
	}
}

func TestTrafficRejectsInvalidSnapshots(t *testing.T) {
	valid := []core.InterfaceCounters{{Name: "eth0"}}
	for _, invalid := range [][]core.InterfaceCounters{
		{{Name: ""}}, {{Name: "bad\nname"}}, {{Name: "bad\xff"}}, {{Name: "eth0"}, {Name: "eth0"}},
	} {
		if _, err := core.MeasureTraffic(invalid, valid, time.Second); err == nil {
			t.Errorf("invalid initial snapshot accepted: %+v", invalid)
		}
		if _, err := core.MeasureTraffic(valid, invalid, time.Second); err == nil {
			t.Errorf("invalid final snapshot accepted: %+v", invalid)
		}
	}
	for _, elapsed := range []time.Duration{0, -time.Second} {
		if _, err := core.MeasureTraffic(valid, valid, elapsed); err == nil {
			t.Errorf("invalid duration accepted: %v", elapsed)
		}
	}
}

func TestTrafficDoesNotMutateSnapshots(t *testing.T) {
	counters := []core.InterfaceCounters{{Name: "z"}, {Name: "a"}}
	want := append([]core.InterfaceCounters(nil), counters...)
	if _, err := core.MeasureTraffic(counters, counters, time.Second); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(counters, want) {
		t.Fatal("input snapshot was changed")
	}
}
