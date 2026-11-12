package cli

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/recovery"
	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/snapshot"
)

type snapshotCollector func(context.Context, string, string) (snapshot.Report, error)

func runRecovery(ctx context.Context, command string, args []string, version string, stdout, stderr io.Writer, collect snapshotCollector) int {
	flags := flag.NewFlagSet(command, flag.ContinueOnError)
	flags.SetOutput(stderr)
	name := flags.String("interface", "", "interface à observer en lecture seule")
	asJSON := flags.Bool("json", false, "émettre l'évaluation JSON")
	var source, after *string
	if command == "restore-plan" {
		source = flags.String("snapshot", "", "capture locale v1 à analyser")
	} else {
		source = flags.String("before", "", "capture de référence locale v1")
		after = flags.String("after", "", "capture locale v1 après intervention")
	}
	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	valid := flags.NArg() == 0
	if command == "restore-plan" {
		valid = valid && ((*source != "") != (*name != ""))
	} else {
		valid = valid && *source != "" && ((*after != "") != (*name != ""))
	}
	if !valid {
		fmt.Fprintln(stderr, "Choisir exactement une source de capture ; consulter coopace-gateway help.")
		return 2
	}
	if *name != "" {
		if err := snapshot.ValidateInterface(*name); err != nil {
			fmt.Fprintln(stderr, err)
			return 2
		}
	}
	if err := ctx.Err(); err != nil {
		return recoveryError(stderr, err)
	}
	load := func(path, name string) (snapshot.Imported, error) {
		if name != "" {
			report, err := collect(ctx, version, name)
			if err != nil {
				return snapshot.Imported{}, err
			}
			return snapshot.ImportReport(ctx, report)
		}
		file, err := openRecoverySnapshot(path)
		if err != nil {
			return snapshot.Imported{}, err
		}
		defer file.Close()
		return snapshot.Read(ctx, file)
	}
	var before snapshot.Imported
	var err error
	if command == "restore-plan" {
		before, err = load(*source, *name)
	} else {
		before, err = load(*source, "")
	}
	if err != nil {
		return recoveryError(stderr, err)
	}
	var report recovery.Report
	if command == "restore-plan" {
		report, err = recovery.Plan(ctx, before, version)
	} else {
		var observed snapshot.Imported
		observed, err = load(*after, *name)
		if err == nil {
			report, err = recovery.Check(ctx, before, observed, version)
		}
	}
	if err == nil {
		if *asJSON {
			err = recovery.WriteJSON(stdout, report)
		} else {
			err = printRecovery(stdout, report)
		}
	}
	if err != nil {
		return recoveryError(stderr, err)
	}
	if report.Decision == "candidate_for_lab_validation" || report.Decision == "selected_state_matches" {
		return 0
	}
	return 3 // Valid evidence, but a refusal, mismatch or indeterminate comparison.
}

func openRecoverySnapshot(path string) (*os.File, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > snapshot.MaxImportBytes {
		return nil, fmt.Errorf("capture ordinaire, sans lien symbolique, de 8 Mio maximum requise")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	opened, err := file.Stat()
	if err != nil || !opened.Mode().IsRegular() || !os.SameFile(info, opened) {
		file.Close()
		return nil, fmt.Errorf("identité du fichier de capture non confirmée")
	}
	return file, nil
}

func recoveryError(output io.Writer, err error) int {
	fmt.Fprintf(output, "Erreur d'évaluation de restauration : %v\n", err)
	if errors.Is(err, context.Canceled) {
		return 130
	}
	return 1
}

func printRecovery(output io.Writer, report recovery.Report) error {
	labels := map[string]string{"candidate_for_lab_validation": "profil initial reconnu, candidat aux essais de restauration", "refused": "configuration non prise en charge", "selected_state_matches": "état sélectionné conforme à la référence", "mismatch": "différence avec la référence", "indeterminate": "comparaison non concluante"}
	var text strings.Builder
	fmt.Fprintf(&text, "Préparation de restauration — lecture seule\nInterface : %q\nRésultat : %s\n", report.Interface, labels[report.Decision])
	if report.Profile != "" {
		fmt.Fprintf(&text, "Profil : %s\n", report.Profile)
	}
	for _, reason := range report.Reasons {
		fmt.Fprintf(&text, "  %s\n", recovery.ReasonLabel(reason))
	}
	if len(report.Steps) != 0 {
		fmt.Fprintln(&text, "Plan à valider dans le laboratoire :")
		for _, step := range report.Steps {
			fmt.Fprintf(&text, "  %s\n", recovery.StepLabel(step))
		}
	}
	fmt.Fprintf(&text, "Référence SHA-256 : %s\n", report.BeforeSHA256)
	if report.AfterSHA256 != nil {
		fmt.Fprintf(&text, "Observation SHA-256 : %s\n", *report.AfterSHA256)
	}
	fmt.Fprintln(&text, "Restauration réseau non implémentée ; cette évaluation n'autorise aucune application.")
	fmt.Fprintln(&text, "Continuité de l'espace réseau et couverture du foyer : non établies.")
	_, err := io.WriteString(output, text.String())
	return err
}
