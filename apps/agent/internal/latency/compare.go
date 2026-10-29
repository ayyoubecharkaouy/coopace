package latency

import (
	"fmt"
	"io"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

// Comparison describes two matching acquisition methods, not a causal gain or
// proof that the reports came from the same host, path or controlled experiment.
type Comparison struct {
	Target                               string
	Version, GoVersion, OS, Architecture string
	Count                                int
	Timeout, Interval                    time.Duration
	Idle, Loaded                         core.LatencySummary
}

// Compare reads files only. It never calls the active TCP measurement code.
func Compare(idleInput, loadedInput io.Reader) (Comparison, error) {
	idle, err := readBaseline(idleInput)
	if err != nil {
		return Comparison{}, fmt.Errorf("rapport au repos : %w", err)
	}
	loaded, err := readBaseline(loadedInput)
	if err != nil {
		return Comparison{}, fmt.Errorf("rapport sous charge : %w", err)
	}
	a, b := idle.report.Options, loaded.report.Options
	if a.Condition != "idle" || b.Condition != "loaded" {
		return Comparison{}, fmt.Errorf("conditions déclarées attendues : idle puis loaded")
	}
	if a.Target != b.Target || a.Count != b.Count || a.Timeout != b.Timeout || a.Interval != b.Interval || idle.version != loaded.version || idle.goVersion != loaded.goVersion || idle.os != loaded.os || idle.architecture != loaded.architecture {
		return Comparison{}, fmt.Errorf("cibles, paramètres ou provenance incompatibles pour cette comparaison")
	}
	return Comparison{Target: a.Target, Version: idle.version, GoVersion: idle.goVersion, OS: idle.os, Architecture: idle.architecture, Count: a.Count, Timeout: a.Timeout, Interval: a.Interval, Idle: idle.report.Summary, Loaded: loaded.report.Summary}, nil
}
