package cli

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/planning"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func runPlan(ctx context.Context, args []string, version string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("plan", flag.ContinueOnError)
	flags.SetOutput(stderr)
	path := flags.String("scenario", "", "scénario local JSON v1 à simuler")
	asJSON := flags.Bool("json", false, "émettre la recommandation et sa provenance en JSON")
	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if *path == "" || flags.NArg() != 0 {
		fmt.Fprintln(stderr, "Utilisation : coopace-gateway plan --scenario FICHIER [--json]")
		return 2
	}
	if err := ctx.Err(); err != nil {
		return planError(stderr, err)
	}
	file, err := openScenario(*path)
	if err != nil {
		return planError(stderr, err)
	}
	defer file.Close()
	report, err := planning.Evaluate(ctx, file, version)
	if err == nil {
		if *asJSON {
			err = planning.WriteJSON(stdout, report)
		} else {
			err = printPlan(stdout, report)
		}
	}
	if err != nil {
		return planError(stderr, err)
	}
	return 0 // A valid abstention is a successful simulation, never an activation.
}

func planError(stderr io.Writer, err error) int {
	fmt.Fprintf(stderr, "Erreur de simulation : %v\n", err)
	if errors.Is(err, context.Canceled) {
		return 130
	}
	return 1
}

func openScenario(path string) (*os.File, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() || info.Size() > planning.MaxScenarioBytes {
		return nil, fmt.Errorf("fichier de scénario ordinaire, sans lien symbolique, de 16 Kio maximum requis")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	opened, err := file.Stat()
	if err != nil || !opened.Mode().IsRegular() || !os.SameFile(info, opened) {
		file.Close()
		return nil, fmt.Errorf("identité du fichier de scénario non confirmée")
	}
	return file, nil
}

func printPlan(output io.Writer, report planning.Report) error {
	var text strings.Builder
	decision := map[core.CakePlanningDecision]string{
		core.CakePlanAbstain: "s’abstenir", core.CakePlanKeepReference: "conserver la référence conforme",
		core.CakePlanProposeReference: "proposer le profil de référence",
	}[report.Plan.Decision]
	fmt.Fprintf(&text, "Simulation CAKE statique — scénario local déclaré\nDécision : %s\n", decision)
	if report.Plan.Reference != "" {
		fmt.Fprintf(&text, "Référence : %s\n", report.Plan.Reference)
	}
	labels := map[core.CakePlanningReason]string{
		core.CakeReasonUnsupportedScope:       "Périmètre hors du laboratoire jetable pris en charge.",
		core.CakeReasonQueueUnknown:           "État de la file non évalué.",
		core.CakeReasonOtherConfiguration:     "Configuration différente conservée.",
		core.CakeReasonAlreadyReference:       "Profil de référence déclaré conforme.",
		core.CakeReasonReferenceUnvalidated:   "Référence non validée.",
		core.CakeReasonConsentUnconfirmed:     "Accord local non confirmé.",
		core.CakeReasonPathUnvalidated:        "Chemin de trafic non validé.",
		core.CakeReasonOwnershipUnvalidated:   "Propriété des ressources non validée.",
		core.CakeReasonSupervisionUnavailable: "Supervision non prête.",
		core.CakeReasonPermissionsUnchecked:   "Permissions non vérifiées.",
		core.CakeReasonPrerequisitesConfirmed: "Les six prérequis sont déclarés confirmés dans le scénario.",
	}
	fmt.Fprintln(&text, "Motifs :")
	for _, reason := range report.Plan.Reasons {
		fmt.Fprintf(&text, "  %s\n", labels[reason])
	}
	fmt.Fprintf(&text, "Scénario SHA-256 : %s\nVersion : %s (%s, %s/%s)\n", report.Scenario.SHA256,
		report.Version, report.Build.GoVersion, report.OS, report.Architecture)
	fmt.Fprintln(&text, "Mode simulation : hypothèses déclarées, aucune action réseau exécutée.")
	_, err := io.WriteString(output, text.String())
	return err
}
