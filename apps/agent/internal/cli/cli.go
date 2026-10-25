// Package cli implements the desktop agent's command-line interface.
package cli

import (
	"fmt"
	"io"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/status"
)

const usage = `Utilisation : coopace <commande>

Commandes :
  status    Afficher la version, le système et l'état local de l'agent.
  help      Afficher cette aide.
`

// Run executes one local command. Exit codes are 0 for success, 1 for an
// execution/output failure and 2 for invalid arguments.
func Run(args []string, version string, stdout, stderr io.Writer) int {
	if len(args) == 0 || (len(args) == 1 && (args[0] == "help" || args[0] == "--help" || args[0] == "-h")) {
		if _, err := io.WriteString(stdout, usage); err != nil {
			fmt.Fprintf(stderr, "Erreur d'affichage : %v\n", err)
			return 1
		}
		return 0
	}
	if len(args) != 1 || args[0] != "status" {
		fmt.Fprintln(stderr, "Commande ou arguments non reconnus.")
		io.WriteString(stderr, usage)
		return 2
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
