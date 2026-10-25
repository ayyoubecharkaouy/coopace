// Package cli implements the desktop agent's command-line interface.
package cli

import (
	"context"
	"fmt"
	"io"
	"text/tabwriter"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/latency"
	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/observe"
	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/status"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const usage = `Utilisation : coopace <commande>

Commandes :
  status    Afficher la version, le système et l'état local de l'agent.
  observe   Observer le trafic local par interface pendant environ une seconde (Linux).
  latency   Mesurer l'établissement TCP vers --target IP:port (options : latency --help).
  help      Afficher cette aide.
`

// Run executes one local command. Exit codes are 0 for success, 1 for an
// execution/output failure and 2 for invalid arguments.
func Run(args []string, version string, stdout, stderr io.Writer) int {
	return RunContext(context.Background(), args, version, stdout, stderr)
}

// RunContext allows cancellation of active latency measurements.
func RunContext(ctx context.Context, args []string, version string, stdout, stderr io.Writer) int {
	if len(args) == 0 || (len(args) == 1 && (args[0] == "help" || args[0] == "--help" || args[0] == "-h")) {
		if _, err := io.WriteString(stdout, usage); err != nil {
			fmt.Fprintf(stderr, "Erreur d'affichage : %v\n", err)
			return 1
		}
		return 0
	}
	if args[0] == "latency" {
		return runLatency(ctx, args[1:], version, stdout, stderr, latency.Measure)
	}
	if len(args) != 1 || (args[0] != "status" && args[0] != "observe") {
		fmt.Fprintln(stderr, "Commande ou arguments non reconnus.")
		io.WriteString(stderr, usage)
		return 2
	}
	if args[0] == "observe" {
		return runObserve(stdout, stderr, observe.Local)
	}

	report, err := status.Local(version)
	if err != nil {
		fmt.Fprintf(stderr, "Erreur : %v\n", err)
		return 1
	}
	_, err = fmt.Fprintf(stdout,
		"Coopace %s\nSystème : %s\nArchitecture : %s\nRôle : %s\nÉtat : local (hors groupe)\n",
		report.Version, report.OS, report.Architecture, report.Role,
	)
	if err != nil {
		fmt.Fprintf(stderr, "Erreur d'affichage : %v\n", err)
		return 1
	}
	return 0
}

func runObserve(stdout, stderr io.Writer, collect func() (observe.Report, error)) int {
	report, err := collect()
	if err != nil {
		fmt.Fprintf(stderr, "Erreur d'observation : %v\n", err)
		return 1
	}
	if err := printObservation(stdout, report); err != nil {
		fmt.Fprintf(stderr, "Erreur d'affichage : %v\n", err)
		return 1
	}
	return 0
}

func printObservation(output io.Writer, report observe.Report) error {
	if _, err := fmt.Fprintf(output, "Trafic local par interface\nSource : %s\nFenêtre mesurée : %.3f s\n", report.Source, report.Elapsed.Seconds()); err != nil {
		return err
	}
	table := tabwriter.NewWriter(output, 0, 4, 2, ' ', 0)
	if _, err := fmt.Fprintln(table, "Interface\tRéception (octets/s)\tEnvoi (octets/s)\tÉtat"); err != nil {
		return err
	}
	for _, observation := range report.Interfaces {
		var err error
		if observation.State == core.TrafficMeasured && observation.Traffic != nil {
			_, err = fmt.Fprintf(table, "%s\t%.1f\t%.1f\tmesuré\n", observation.Name, observation.Traffic.ReceivedBytesPerSecond, observation.Traffic.SentBytesPerSecond)
		} else {
			reason := "indisponible"
			switch observation.State {
			case core.TrafficAppeared:
				reason = "apparue pendant la mesure"
			case core.TrafficDisappeared:
				reason = "disparue pendant la mesure"
			case core.TrafficReset:
				reason = "compteurs en baisse"
			}
			_, err = fmt.Fprintf(table, "%s\t-\t-\t%s\n", observation.Name, reason)
		}
		if err != nil {
			return err
		}
	}
	if err := table.Flush(); err != nil {
		return err
	}
	if len(report.Interfaces) == 0 {
		if _, err := fmt.Fprintln(output, "Aucune interface visible."); err != nil {
			return err
		}
	}
	_, err := fmt.Fprintln(output, "Ces compteurs peuvent inclure le LAN et la boucle locale ; ils ne mesurent pas la capacité Internet.")
	return err
}
