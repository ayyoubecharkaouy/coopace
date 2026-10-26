package cli

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/group"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const groupUsage = `Utilisation : coopace group <configure|show|revoke|listen|exchange> --state-dir DOSSIER
  configure --group-id ID --peer-cert FICHIER --peer-id EMPREINTE --join [--share-observations] [--name NOM]
  show       Afficher l'approbation et le consentement locaux, sans connexion.
  revoke     Retirer le consentement local (les échanges actifs sont interrompus).
  listen     [--listen 127.0.0.1:8766] Attendre un seul échange, puis quitter.
  exchange   --target IP:port Effectuer un échange, puis quitter.
Limite : 30 secondes, y compris l'attente. Identités persistantes Linux uniquement.
Le partage d'observations est désactivé par défaut. Chaque pair doit approuver l'autre.
`

func runGroup(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 || (len(args) == 1 && (args[0] == "help" || args[0] == "--help" || args[0] == "-h")) {
		if _, err := io.WriteString(stdout, groupUsage); err != nil {
			return 1
		}
		return 0
	}
	command := args[0]
	flags := flag.NewFlagSet("group "+command, flag.ContinueOnError)
	flags.SetOutput(stderr)
	directory := flags.String("state-dir", "", "dossier privé de l'identité locale")
	var groupID, peerFile, peerID, name, address string
	var join, share bool
	switch command {
	case "configure":
		flags.StringVar(&groupID, "group-id", "", "identifiant du groupe choisi sur les deux pairs")
		flags.StringVar(&peerFile, "peer-cert", "", "certificat public du pair")
		flags.StringVar(&peerID, "peer-id", "", "empreinte Ed25519 vérifiée par un canal indépendant")
		flags.StringVar(&name, "name", "Coopace agent", "nom public local")
		flags.BoolVar(&join, "join", false, "consentement explicite à participer")
		flags.BoolVar(&share, "share-observations", false, "autoriser l'envoi d'une observation locale par échange")
	case "listen":
		flags.StringVar(&address, "listen", "127.0.0.1:8766", "adresse d'écoute IP:port explicite")
	case "exchange":
		flags.StringVar(&address, "target", "", "adresse IP:port du pair")
	case "show", "revoke":
	default:
		fmt.Fprintln(stderr, "Sous-commande de groupe non reconnue.")
		return 2
	}
	if err := flags.Parse(args[1:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if strings.TrimSpace(*directory) == "" || flags.NArg() != 0 {
		fmt.Fprintln(stderr, "--state-dir est obligatoire ; aucun argument positionnel n'est accepté.")
		return 2
	}
	if command == "configure" && (!join || groupID == "" || peerFile == "" || peerID == "") {
		fmt.Fprintln(stderr, "configure exige --group-id, --peer-cert, --peer-id et --join.")
		return 2
	}
	if command == "listen" || command == "exchange" {
		if err := group.ValidateAddress(address, command == "listen"); err != nil {
			fmt.Fprintln(stderr, err)
			return 2
		}
	}
	var err error
	switch command {
	case "configure":
		info, statErr := os.Lstat(peerFile)
		if statErr != nil {
			err = statErr
			break
		}
		if !info.Mode().IsRegular() {
			err = fmt.Errorf("le certificat public doit être un fichier ordinaire")
			break
		}
		var file *os.File
		file, err = os.Open(peerFile)
		if err == nil {
			var data []byte
			data, err = io.ReadAll(io.LimitReader(file, 16385))
			file.Close()
			if err == nil {
				_, err = group.Configure(*directory, group.Configuration{GroupID: groupID, Name: name, PeerID: core.DeviceID(peerID), PeerCertificate: data, Join: join, ShareObservations: share})
			}
		}
		if err == nil {
			_, err = fmt.Fprintln(stdout, "Approbation et consentement enregistrés localement. Aucune connexion ouverte.")
		}
	case "show":
		var profile group.Profile
		profile, err = group.LoadProfile(*directory)
		if err == nil {
			_, err = fmt.Fprintf(stdout, "Groupe configuré : %s\nIdentité locale : %s\nPair approuvé : %s\nAdhésion : %t\nPartage des observations : %t\nÉtat : configuration locale, déconnecté\n", profile.Consent.GroupID, profile.Consent.DeviceID, profile.PeerID, profile.Consent.Join, profile.Consent.ShareObservations)
		}
	case "revoke":
		err = group.Revoke(*directory)
		if err == nil {
			_, err = fmt.Fprintln(stdout, "Consentement local retiré. Les échanges actifs seront interrompus lors de la détection du changement.")
		}
	case "listen", "exchange":
		var result group.Result
		if command == "listen" {
			result, err = group.Listen(ctx, *directory, address, func(bound string) error {
				_, err := fmt.Fprintf(stdout, "Écoute : %s (un échange, attente comprise dans la limite de 30 s)\n", bound)
				return err
			})
		} else {
			result, err = group.Exchange(ctx, *directory, address)
		}
		if err == nil {
			err = printGroupResult(stdout, result)
		}
	}
	if err != nil {
		fmt.Fprintf(stderr, "Erreur de groupe : %v\n", err)
		if errors.Is(ctx.Err(), context.Canceled) {
			return 130
		}
		return 1
	}
	return 0
}

func printGroupResult(output io.Writer, result group.Result) error {
	if _, err := fmt.Fprintf(output, "Pair authentifié : %s (%s)\nObservation locale envoyée : %t\n", result.Peer.Name, result.Peer.ID, result.SentObservation); err != nil {
		return err
	}
	if result.Received == nil {
		if _, err := fmt.Fprintln(output, "Observation reçue : aucune (partage désactivé chez le pair)"); err != nil {
			return err
		}
	} else {
		o := result.Received
		if _, err := fmt.Fprintf(output, "Observation reçue : %s, %s, %.3f ms, %s\n", o.Source, o.Scope, o.WindowMS, o.ObservedAt.Format("2006-01-02T15:04:05.999999999Z07:00")); err != nil {
			return err
		}
		for _, item := range o.Interfaces {
			received, sent := "indisponible", "indisponible"
			if item.ReceivedBytes != nil {
				received = *item.ReceivedBytes
			}
			if item.SentBytes != nil {
				sent = *item.SentBytes
			}
			if _, err := fmt.Fprintf(output, "  %s : RX %s octets, TX %s octets (%s)\n", item.Name, received, sent, item.State); err != nil {
				return err
			}
		}
		if _, err := fmt.Fprintln(output, "Compteurs par interface ; ils ne mesurent pas la capacité Internet et peuvent inclure cet échange."); err != nil {
			return err
		}
	}
	_, err := fmt.Fprintln(output, "Échange terminé, déconnecté. Aucune observation reçue enregistrée sur disque.")
	return err
}
