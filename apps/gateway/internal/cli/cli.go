// Package cli presents the gateway's local diagnostic command.
package cli

import (
	"context"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/diagnostic"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const usage = `Utilisation : coopace-gateway <inspect|help>
  inspect  Inventorier interfaces, forwarding, droits et files visibles (Linux).
  help     Afficher cette aide.
Diagnostic local en lecture seule, sans configuration réseau ni trafic de test.
Les informations manquantes sont affichées comme indisponibles.
`

func RunContext(ctx context.Context, args []string, version string, stdout, stderr io.Writer) int {
	return run(ctx, args, version, stdout, stderr, diagnostic.Local)
}

func run(ctx context.Context, args []string, version string, stdout, stderr io.Writer, collect func(context.Context, string) (diagnostic.Report, error)) int {
	if len(args) == 0 || (len(args) == 1 && (args[0] == "help" || args[0] == "--help" || args[0] == "-h")) || (len(args) == 2 && args[0] == "inspect" && (args[1] == "--help" || args[1] == "-h")) {
		if _, err := io.WriteString(stdout, usage); err != nil {
			return 1
		}
		return 0
	}
	if len(args) != 1 || args[0] != "inspect" {
		fmt.Fprintln(stderr, "Commande ou arguments non reconnus ; utiliser coopace-gateway inspect.")
		return 2
	}
	report, err := collect(ctx, version)
	if err == nil {
		err = printReport(stdout, report)
	}
	if err != nil {
		fmt.Fprintf(stderr, "Erreur de diagnostic : %v\n", err)
		if errors.Is(err, context.Canceled) {
			return 130
		}
		return 1
	}
	return 0 // A report with unavailable sections is a successful partial inventory.
}

func printReport(output io.Writer, report diagnostic.Report) error {
	// Build once, then propagate output errors rather than losing a partial table.
	var text strings.Builder
	fmt.Fprintf(&text, "Coopace passerelle %s — diagnostic en lecture seule\nSystème : %s/%s\nCollecté : %s\nPortée : espace réseau visible par le processus\n", report.Version, report.OS, report.Architecture, report.CollectedAt.Format(time.RFC3339Nano))
	inventory := report.Inventory
	fmt.Fprintln(&text, "\nInterfaces (net.Interfaces) :")
	if !inventory.Interfaces.Available {
		unavailable(&text, inventory.Interfaces.Reason)
	} else {
		if len(inventory.Interfaces.Value) == 0 {
			fmt.Fprintln(&text, "  Aucune interface renvoyée par la source.")
		}
		for _, item := range inventory.Interfaces.Value {
			fmt.Fprintf(&text, "  %q : index=%d, MTU=%d, active administrativement=%t, boucle locale=%t\n", item.Name, item.Index, item.MTU, item.Up, item.Loopback)
		}
	}
	flag(&text, "Forwarding IPv4 (/proc/sys/net/ipv4/ip_forward)", inventory.IPv4Forwarding)
	flag(&text, "Forwarding IPv6 global (/proc/sys/net/ipv6/conf/all/forwarding)", inventory.IPv6Forwarding)
	flag(&text, "CAP_NET_ADMIN effective (/proc/self/status)", inventory.NetAdmin)
	fmt.Fprintln(&text, "\nOutils dans le PATH :")
	for _, tool := range inventory.Tools {
		if tool.Available {
			fmt.Fprintf(&text, "  %s : trouvé (%q)\n", tool.Name, tool.Path)
		} else {
			fmt.Fprintf(&text, "  %s : absent\n", tool.Name)
		}
	}
	for _, family := range []struct {
		label   string
		reading core.GatewayReading[[]core.GatewayDefaultRoute]
	}{
		{"IPv4", inventory.IPv4Defaults}, {"IPv6", inventory.IPv6Defaults},
	} {
		fmt.Fprintf(&text, "\nRoutes par défaut %s (ip, toutes tables) :\n", family.label)
		if !family.reading.Available {
			unavailable(&text, family.reading.Reason)
			continue
		}
		if len(family.reading.Value) == 0 {
			fmt.Fprintln(&text, "  Aucune route par défaut renvoyée ; cela ne prouve pas une absence d'accès Internet.")
		}
		for _, route := range family.reading.Value {
			fmt.Fprintf(&text, "  table=%q, type=%q, interfaces=%q, nexthop non résolu=%t\n", route.Table, route.Kind, route.Interfaces, route.UnresolvedNexthop)
		}
	}
	fmt.Fprintln(&text, "\nFiles visibles (tc qdisc show) :")
	if !inventory.Queues.Available {
		unavailable(&text, inventory.Queues.Reason)
	} else {
		if len(inventory.Queues.Value) == 0 {
			fmt.Fprintln(&text, "  Aucune file renvoyée par la source.")
		}
		for _, queue := range inventory.Queues.Value {
			fmt.Fprintf(&text, "  interface=%q, type=%q, handle=%q, parent=%q, racine=%t\n", queue.Interface, queue.Kind, queue.Handle, queue.Parent, queue.Root)
		}
	}
	fmt.Fprintln(&text, "\nCouverture du trafic du foyer : non établie. Aucune interface WAN sélectionnée.")
	fmt.Fprintln(&text, "Prise en charge de CAKE, permissions d'intervention et restauration : non validées.")
	fmt.Fprintln(&text, "Aucune configuration modifiée, aucun trafic de test généré, aucun rapport enregistré automatiquement.")
	_, err := io.WriteString(output, text.String())
	return err
}

func unavailable(output io.Writer, reason string) {
	if reason == "" {
		reason = "non collecté"
	}
	fmt.Fprintf(output, "  Indisponible : %q\n", reason)
}

func flag(output io.Writer, label string, reading core.GatewayReading[bool]) {
	fmt.Fprintf(output, "\n%s :\n", label)
	if !reading.Available {
		unavailable(output, reading.Reason)
	} else {
		fmt.Fprintf(output, "  %t\n", reading.Value)
	}
}
