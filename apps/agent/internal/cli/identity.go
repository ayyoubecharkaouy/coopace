package cli

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"strings"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/identity"
)

func runIdentity(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 || (len(args) == 1 && (args[0] == "--help" || args[0] == "help" || args[0] == "-h")) {
		if _, err := fmt.Fprintln(stdout, "Utilisation : coopace identity <init|show> --state-dir DOSSIER\nAffiche uniquement l'identifiant et la clé publique. Stockage persistant Linux."); err != nil {
			return 1
		}
		return 0
	}
	if args[0] != "init" && args[0] != "show" {
		fmt.Fprintln(stderr, "Sous-commande d'identité non reconnue : utiliser init ou show.")
		return 2
	}
	flags := flag.NewFlagSet("identity "+args[0], flag.ContinueOnError)
	flags.SetOutput(stderr)
	directory := flags.String("state-dir", "", "dossier privé explicite pour l'identité locale")
	if err := flags.Parse(args[1:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if strings.TrimSpace(*directory) == "" || flags.NArg() != 0 {
		fmt.Fprintln(stderr, "Le dossier --state-dir est obligatoire ; aucun argument positionnel n'est accepté.")
		return 2
	}
	var local identity.Identity
	var err error
	if args[0] == "init" {
		local, err = identity.Init(*directory)
	} else {
		local, err = identity.Load(*directory)
	}
	if err != nil {
		fmt.Fprintf(stderr, "Erreur d'identité : %v\n", err)
		return 1
	}
	public, err := local.Public()
	if err != nil {
		fmt.Fprintf(stderr, "Erreur d'identité publique : %v\n", err)
		return 1
	}
	if _, err := fmt.Fprintf(stdout, "Identifiant : %s\nClé publique Ed25519 (base64) : %s\nÉtat : identité locale, hors groupe\n", public.DeviceID, public.PublicKey); err != nil {
		fmt.Fprintf(stderr, "Erreur d'affichage : %v\n", err)
		return 1
	}
	return 0
}
