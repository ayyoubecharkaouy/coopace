package observe

import (
	"errors"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestCollectReportsActualWindow(t *testing.T) {
	calls := 0
	read := func() ([]core.InterfaceCounters, error) {
		calls++
		return []core.InterfaceCounters{{Name: "eth0", ReceivedBytes: uint64(calls * 100)}}, nil
	}
	report, err := collect(read, time.Nanosecond)
	if err != nil {
		t.Fatal(err)
	}
	if calls != 2 || report.Source != sourceName || report.Elapsed <= 0 || report.FinishedAt.Sub(report.StartedAt) != report.Elapsed ||
		len(report.Interfaces) != 1 || report.Interfaces[0].Traffic == nil || report.Interfaces[0].Traffic.ReceivedBytes != 100 {
		t.Fatalf("incorrect observation window: %+v, calls=%d", report, calls)
	}
}

func TestCollectPropagatesSourceFailure(t *testing.T) {
	want := errors.New("source unavailable")
	for _, failOn := range []int{1, 2} {
		calls := 0
		read := func() ([]core.InterfaceCounters, error) {
			calls++
			if calls == failOn {
				return nil, want
			}
			return []core.InterfaceCounters{{Name: "eth0"}}, nil
		}
		report, err := collect(read, time.Nanosecond)
		if !errors.Is(err, want) || calls != failOn || report.Interfaces != nil {
			t.Errorf("source failure incorrectly handled: report=%+v, err=%v, calls=%d", report, err, calls)
		}
	}
}

func TestCollectRejectsInvalidPauseBeforeReading(t *testing.T) {
	for _, pause := range []time.Duration{0, -time.Second} {
		calls := 0
		_, err := collect(func() ([]core.InterfaceCounters, error) { calls++; return nil, nil }, pause)
		if err == nil || calls != 0 {
			t.Errorf("invalid pause accepted: %v, calls=%d", pause, calls)
		}
	}
}
