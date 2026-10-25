package cli

import (
	"bytes"
	"errors"
	"regexp"
	"testing"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/observe"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func TestObserveDistinguishesIdleAndUnavailable(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := runObserve(&stdout, &stderr, func() (observe.Report, error) {
		return observe.Report{
			Source: "test counters", Elapsed: time.Second,
			Interfaces: []core.InterfaceObservation{
				{Name: "idle", State: core.TrafficMeasured, Traffic: &core.InterfaceTraffic{}},
				{Name: "reset", State: core.TrafficReset},
			},
		}, nil
	})
	if code != 0 || stderr.Len() != 0 || !regexp.MustCompile(`idle\s+0\.0\s+0\.0\s+mesuré`).MatchString(stdout.String()) ||
		!regexp.MustCompile(`reset\s+-\s+-\s+compteurs en baisse`).MatchString(stdout.String()) {
		t.Fatalf("incorrect observation output: code=%d stdout=%q stderr=%q", code, stdout.String(), stderr.String())
	}
}

func TestObserveSourceFailureDoesNotPrintMeasurements(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := runObserve(&stdout, &stderr, func() (observe.Report, error) {
		return observe.Report{}, errors.New("source unavailable")
	})
	if code != 1 || stdout.Len() != 0 || stderr.Len() == 0 {
		t.Fatalf("source failure incorrectly displayed: code=%d stdout=%q stderr=%q", code, stdout.String(), stderr.String())
	}
}

func TestObserveOutputFailure(t *testing.T) {
	var stderr bytes.Buffer
	code := runObserve(failingWriter{}, &stderr, func() (observe.Report, error) { return observe.Report{}, nil })
	if code != 1 || stderr.Len() == 0 {
		t.Fatalf("output failure ignored: code=%d stderr=%q", code, stderr.String())
	}
}
