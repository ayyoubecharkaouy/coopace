package cli

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"strings"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/snapshot"
)

func runSnapshot(ctx context.Context, args []string, version string, stdout, stderr io.Writer, collect func(context.Context, string, string) (snapshot.Report, error)) int {
	flags := flag.NewFlagSet("snapshot", flag.ContinueOnError)
	flags.SetOutput(stderr)
	name := flags.String("interface", "", "interface Linux à observer explicitement")
	asJSON := flags.Bool("json", false, "émettre les options détaillées en JSON local v1")
	outputPath := flags.String("output", "", "enregistrer un nouveau fichier JSON local, sans écraser un fichier existant")
	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if flags.NArg() != 0 {
		fmt.Fprintln(stderr, "Aucun argument positionnel n'est accepté après snapshot.")
		return 2
	}
	if err := snapshot.ValidateInterface(*name); err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}
	report, err := collect(ctx, version, *name)
	if err == nil && *outputPath != "" {
		err = snapshot.SaveExclusive(ctx, *outputPath, report)
	}
	if err == nil {
		if *asJSON {
			err = snapshot.WriteJSON(stdout, report)
		} else {
			err = printSnapshot(stdout, report)
			if err == nil && *outputPath != "" {
				_, err = fmt.Fprintf(stdout, "Capture JSON enregistrée dans %q\n", *outputPath)
			}
		}
	}
	if err != nil {
		fmt.Fprintf(stderr, "Erreur de capture : %v\n", err)
		if errors.Is(err, context.Canceled) {
			return 130
		}
		return 1
	}
	return 0 // A partial observation is still a report, never a restoration check.
}

func printSnapshot(output io.Writer, report snapshot.Report) error {
	var text strings.Builder
	fmt.Fprintf(&text, "Coopace passerelle %s — capture des files en lecture seule\nInterface : %q (index %d)\n", report.Version, report.Snapshot.Interface.Name, report.Snapshot.Interface.Index)
	for _, reading := range report.Snapshot.Readings {
		if reading.Available {
			fmt.Fprintf(&text, "  %s : disponible\n", reading.Section)
		} else {
			fmt.Fprintf(&text, "  %s : indisponible (%q)\n", reading.Section, reading.Reason)
		}
	}
	fmt.Fprintf(&text, "Capture partielle : %t ; lectures successives, non atomiques.\n", report.Snapshot.Partial())
	fmt.Fprintln(&text, "Utiliser --json pour conserver les options détaillées localement (adresses et identifiants possibles).")
	fmt.Fprintln(&text, "Restauration non implémentée ; couverture du trafic du foyer non établie.")
	_, err := io.WriteString(output, text.String())
	return err
}
