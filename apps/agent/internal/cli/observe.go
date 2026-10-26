package cli

import (
	"fmt"
	"io"
	"text/tabwriter"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/observe"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

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
