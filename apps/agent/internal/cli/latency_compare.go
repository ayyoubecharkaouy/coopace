package cli

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"text/tabwriter"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/latency"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func runLatencyCompare(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("latency compare", flag.ContinueOnError)
	flags.SetOutput(stderr)
	idlePath := flags.String("idle", "", "rapport JSON local v1 au repos")
	loadedPath := flags.String("loaded", "", "rapport JSON local v1 sous charge")
	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if *idlePath == "" || *loadedPath == "" || flags.NArg() != 0 {
		fmt.Fprintln(stderr, "Utilisation : coopace latency compare --idle FICHIER --loaded FICHIER")
		return 2
	}
	if err := ctx.Err(); err != nil {
		fmt.Fprintf(stderr, "Comparaison annulée : %v\n", err)
		return 130
	}
	idle, err := openBaseline(*idlePath)
	if err != nil {
		fmt.Fprintf(stderr, "Erreur de rapport : %v\n", err)
		return 1
	}
	defer idle.Close()
	loaded, err := openBaseline(*loadedPath)
	if err != nil {
		fmt.Fprintf(stderr, "Erreur de rapport : %v\n", err)
		return 1
	}
	defer loaded.Close()
	comparison, err := latency.Compare(idle, loaded)
	if ctx.Err() != nil {
		err = ctx.Err()
	}
	if err == nil {
		err = printLatencyComparison(stdout, comparison)
	}
	if err != nil {
		fmt.Fprintf(stderr, "Erreur de comparaison : %v\n", err)
		if errors.Is(err, context.Canceled) {
			return 130
		}
		return 1
	}
	return 0
}

func openBaseline(path string) (*os.File, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("le rapport doit être un fichier ordinaire, sans lien symbolique")
	}
	return os.Open(path)
}

func printLatencyComparison(output io.Writer, comparison latency.Comparison) error {
	if _, err := fmt.Fprintf(output, "Comparaison descriptive : établissement TCP au repos et sous charge\nCible : %q\nProvenance déclarée : %q, %q, %q/%q\nParamètres : %d essais, timeout=%s, intervalle=%s\nConnexions réussies : repos=%d/%d, charge=%d/%d\nÉchecs : repos=%d, charge=%d (ne sont pas des pertes de paquets)\n", comparison.Target, comparison.Version, comparison.GoVersion, comparison.OS, comparison.Architecture, comparison.Count, comparison.Timeout, comparison.Interval, comparison.Idle.Successful, comparison.Idle.Attempts, comparison.Loaded.Successful, comparison.Loaded.Attempts, comparison.Idle.Failed, comparison.Loaded.Failed); err != nil {
		return err
	}
	table := tabwriter.NewWriter(output, 0, 4, 2, ' ', 0)
	if _, err := fmt.Fprintln(table, "Statistique\tRepos (ms)\tCharge (ms)\tÉcart charge - repos (ms)"); err != nil {
		return err
	}
	selectValue := func(value *core.LatencyDistribution, index int) *time.Duration {
		if value == nil {
			return nil
		}
		values := []time.Duration{value.Minimum, value.P50, value.P95, value.P99, value.Maximum}
		return &values[index]
	}
	for index, name := range []string{"min", "p50", "p95", "p99", "max"} {
		a, b := selectValue(comparison.Idle.Distribution, index), selectValue(comparison.Loaded.Distribution, index)
		left, right, delta := "indisponible", "indisponible", "indisponible"
		if a != nil {
			left = fmt.Sprintf("%.6f", float64(*a)/float64(time.Millisecond))
		}
		if b != nil {
			right = fmt.Sprintf("%.6f", float64(*b)/float64(time.Millisecond))
		}
		if a != nil && b != nil {
			delta = fmt.Sprintf("%+.6f", float64(*b-*a)/float64(time.Millisecond))
		}
		if _, err := fmt.Fprintf(table, "%s\t%s\t%s\t%s\n", name, left, right, delta); err != nil {
			return err
		}
	}
	if err := table.Flush(); err != nil {
		return err
	}
	if _, err := fmt.Fprintln(output, "Les percentiles portent sur les seules réussites ; avec peu d'essais, p95/p99 restent exploratoires."); err != nil {
		return err
	}
	_, err := fmt.Fprintln(output, "Conditions idle/loaded déclarées ; appareil, chemin et charge non vérifiés. Aucun gain causal ni diagnostic de congestion déduit. Aucun essai réseau lancé.")
	return err
}
