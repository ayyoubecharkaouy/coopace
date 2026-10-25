// Package observe samples local counters without generating network traffic.
package observe

import (
	"fmt"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

type Report struct {
	StartedAt  time.Time
	FinishedAt time.Time
	Elapsed    time.Duration
	Source     string
	Interfaces []core.InterfaceObservation
}

// Local takes two read-only samples with a requested one-second pause.
func Local() (Report, error) {
	return collect(readCounters, time.Second)
}

func collect(read func() ([]core.InterfaceCounters, error), pause time.Duration) (Report, error) {
	if pause <= 0 {
		return Report{}, fmt.Errorf("observation pause must be positive")
	}
	before, err := read()
	if err != nil {
		return Report{}, fmt.Errorf("première lecture : %w", err)
	}
	started := time.Now()
	time.Sleep(pause)
	after, err := read()
	finished := time.Now()
	if err != nil {
		return Report{}, fmt.Errorf("seconde lecture : %w", err)
	}
	elapsed := finished.Sub(started)
	interfaces, err := core.MeasureTraffic(before, after, elapsed)
	if err != nil {
		return Report{}, err
	}
	return Report{
		StartedAt: started, FinishedAt: finished, Elapsed: elapsed,
		Source: sourceName, Interfaces: interfaces,
	}, nil
}
