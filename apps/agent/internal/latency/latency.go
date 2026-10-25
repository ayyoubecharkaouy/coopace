// Package latency measures TCP connection setup to one explicitly chosen endpoint.
package latency

import (
	"context"
	"fmt"
	"net/netip"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

type Options struct {
	Target    string
	Count     int
	Timeout   time.Duration
	Interval  time.Duration
	Condition string
}

func (o Options) Validate() error {
	target, err := netip.ParseAddrPort(o.Target)
	if err != nil || !target.IsValid() || target.Port() == 0 {
		return fmt.Errorf("cible IP:port numérique requise, avec un port de 1 à 65535 et une adresse unicast")
	}
	address := target.Addr().Unmap()
	if !address.IsGlobalUnicast() && !address.IsLoopback() && !address.IsLinkLocalUnicast() {
		return fmt.Errorf("cible IP:port numérique requise, avec un port de 1 à 65535 et une adresse unicast")
	}
	if o.Count < 1 || o.Count > 100 {
		return fmt.Errorf("le nombre d'essais doit être compris entre 1 et 100")
	}
	if o.Timeout <= 0 || o.Timeout > 10*time.Second {
		return fmt.Errorf("le délai maximal par essai doit être positif et au plus de 10 s")
	}
	if o.Interval < 0 || o.Interval > 5*time.Second {
		return fmt.Errorf("la pause entre essais doit être comprise entre 0 et 5 s")
	}
	if o.Condition != "unspecified" && o.Condition != "idle" && o.Condition != "loaded" {
		return fmt.Errorf("condition attendue : unspecified, idle ou loaded")
	}
	return nil
}

type Attempt struct {
	StartedAt time.Time
	Sample    core.LatencySample
}

type Report struct {
	Options    Options
	StartedAt  time.Time
	FinishedAt time.Time
	Attempts   []Attempt
	Summary    core.LatencySummary
}

func Measure(ctx context.Context, options Options) (Report, error) {
	return measure(ctx, options, probeTCP)
}

func measure(ctx context.Context, options Options, probe func(context.Context, string, time.Duration) core.LatencySample) (Report, error) {
	if err := options.Validate(); err != nil {
		return Report{}, err
	}
	report := Report{Options: options, StartedAt: time.Now(), Attempts: make([]Attempt, 0, options.Count)}
	samples := make([]core.LatencySample, 0, options.Count)
	for i := 0; i < options.Count; i++ {
		if err := ctx.Err(); err != nil {
			return Report{}, err
		}
		if i > 0 && options.Interval > 0 {
			timer := time.NewTimer(options.Interval)
			select {
			case <-ctx.Done():
				timer.Stop()
				return Report{}, ctx.Err()
			case <-timer.C:
			}
		}
		started := time.Now()
		sample := probe(ctx, options.Target, options.Timeout)
		if err := ctx.Err(); err != nil {
			return Report{}, err
		}
		report.Attempts = append(report.Attempts, Attempt{StartedAt: started, Sample: sample})
		samples = append(samples, sample)
	}
	report.FinishedAt = time.Now()
	var err error
	report.Summary, err = core.SummarizeLatency(samples)
	if err != nil {
		return Report{}, err
	}
	return report, nil
}
