package cli

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/latency"
)

func runLatency(ctx context.Context, args []string, version string, stdout, stderr io.Writer, measure func(context.Context, latency.Options) (latency.Report, error)) int {
	if len(args) > 0 && args[0] == "compare" {
		return runLatencyCompare(ctx, args[1:], stdout, stderr)
	}
	options := latency.Options{}
	jsonOutput := false
	flags := flag.NewFlagSet("latency", flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.StringVar(&options.Target, "target", "", "cible IP:port numérique, obligatoire (IPv6 : [adresse]:port)")
	flags.IntVar(&options.Count, "count", 5, "nombre d'essais, de 1 à 100")
	flags.DurationVar(&options.Timeout, "timeout", time.Second, "délai maximal par essai, positif et au plus de 10s")
	flags.DurationVar(&options.Interval, "interval", 250*time.Millisecond, "pause entre essais, de 0 à 5s")
	flags.StringVar(&options.Condition, "condition", "unspecified", "condition déclarée : unspecified, idle ou loaded")
	flags.BoolVar(&jsonOutput, "json", false, "émettre le rapport local JSON v1 sur la sortie standard")
	flags.Usage = func() {
		fmt.Fprintln(stderr, "Utilisation : coopace latency --target IP:port [options]\nComparaison hors ligne : coopace latency compare --idle FICHIER --loaded FICHIER")
		flags.PrintDefaults()
	}
	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if flags.NArg() != 0 {
		fmt.Fprintln(stderr, "Arguments positionnels non reconnus ; utiliser --target IP:port.")
		return 2
	}
	if err := options.Validate(); err != nil {
		fmt.Fprintf(stderr, "Arguments invalides : %v\n", err)
		return 2
	}
	report, err := measure(ctx, options)
	if err != nil {
		fmt.Fprintf(stderr, "Erreur de mesure : %v\n", err)
		if errors.Is(err, context.Canceled) {
			return 130
		}
		return 1
	}
	if jsonOutput {
		err = latency.WriteJSON(stdout, report, version)
	} else {
		err = printLatency(stdout, report)
	}
	if err != nil {
		fmt.Fprintf(stderr, "Erreur d'affichage : %v\n", err)
		return 1
	}
	if report.Summary.Successful == 0 {
		return 1
	}
	return 0
}

func printLatency(output io.Writer, report latency.Report) error {
	if _, err := fmt.Fprintf(output, "Établissement de connexion TCP\nCible : %s\nCondition déclarée : %s\nConnexions réussies : %d/%d ; échecs : %d\n",
		report.Options.Target, report.Options.Condition, report.Summary.Successful, report.Summary.Attempts, report.Summary.Failed); err != nil {
		return err
	}
	if distribution := report.Summary.Distribution; distribution != nil {
		ms := func(duration time.Duration) float64 { return float64(duration) / float64(time.Millisecond) }
		if _, err := fmt.Fprintf(output, "Durée des connexions réussies (ms) : min=%.3f p50=%.3f p95=%.3f p99=%.3f max=%.3f\n",
			ms(distribution.Minimum), ms(distribution.P50), ms(distribution.P95), ms(distribution.P99), ms(distribution.Maximum)); err != nil {
			return err
		}
	} else if _, err := fmt.Fprintln(output, "Durées indisponibles : aucune connexion réussie."); err != nil {
		return err
	}
	_, err := fmt.Fprintln(output, "Cette durée n'est pas un RTT ICMP ; les échecs de connexion ne mesurent pas les pertes de paquets. Les percentiles portent uniquement sur les réussites.")
	return err
}
