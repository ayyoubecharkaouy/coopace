// Command lab-load transfers bounded synthetic bytes inside the disposable lab.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"net/netip"
	"os"
	"os/signal"
	"syscall"
	"time"
)

const defaultBytes = int64(8 * 1024 * 1024)
const defaultRate = int64(1024 * 1024)

type options struct {
	address  string
	bytes    int64
	rate     int64
	duration time.Duration
}

func (o options) validate(sender bool) error {
	endpoint, err := netip.ParseAddrPort(o.address)
	if err != nil || !endpoint.Addr().Is4() || endpoint.Port() < 1024 ||
		(!endpoint.Addr().IsPrivate() && !endpoint.Addr().IsLoopback()) {
		return errors.New("IPv4 privée ou de boucle locale explicite et port de 1024 à 65535 requis")
	}
	if o.bytes < 1 || o.bytes > 32*1024*1024 {
		return errors.New("volume attendu de 1 à 33554432 octets")
	}
	if o.duration < time.Second || o.duration > 30*time.Second {
		return errors.New("durée maximale attendue de 1s à 30s")
	}
	if sender {
		if o.rate < 64*1024 || o.rate > 4*1024*1024 {
			return errors.New("débit applicatif attendu de 65536 à 4194304 octets/s")
		}
		if scheduledDuration(o.bytes, o.rate) >= o.duration {
			return errors.New("volume et débit incompatibles avec la durée maximale ; prévoir une marge")
		}
	}
	return nil
}

type network struct {
	listen func(context.Context, string, string) (net.Listener, error)
	dial   func(context.Context, string, string) (net.Conn, error)
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer, transport network) int {
	if len(args) == 0 || (len(args) == 1 && (args[0] == "--help" || args[0] == "help")) {
		_, err := fmt.Fprintln(stdout, "Utilisation : coopace-lab-load <send|receive> --help\nTransfert TCP synthétique borné, réservé au laboratoire.")
		if err != nil {
			return 1
		}
		return 0
	}
	sender := args[0] == "send"
	if !sender && args[0] != "receive" {
		fmt.Fprintln(stderr, "Commande attendue : send ou receive.")
		return 2
	}
	o := options{}
	announceStart := false
	flags := flag.NewFlagSet(args[0], flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.Int64Var(&o.bytes, "bytes", defaultBytes, "volume synthétique exact, de 1 à 33554432 octets")
	if sender {
		flags.BoolVar(&announceStart, "announce-start", false, "annoncer STARTED après la première écriture, avant le JSON")
		flags.StringVar(&o.address, "target", "", "cible IPv4:port privée ou de boucle locale, obligatoire")
		flags.Int64Var(&o.rate, "rate", defaultRate, "plafond applicatif en octets/s, de 65536 à 4194304")
		flags.DurationVar(&o.duration, "duration", 12*time.Second, "durée maximale, de 1s à 30s")
	} else {
		flags.StringVar(&o.address, "listen", "", "écoute IPv4:port privée ou de boucle locale, obligatoire")
		flags.DurationVar(&o.duration, "duration", 15*time.Second, "durée maximale, de 1s à 30s")
	}
	if err := flags.Parse(args[1:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if flags.NArg() != 0 {
		fmt.Fprintln(stderr, "Arguments positionnels non reconnus.")
		return 2
	}
	if err := o.validate(sender); err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}
	ctx, cancel := context.WithTimeout(ctx, o.duration)
	defer cancel()
	if sender {
		report, err := send(ctx, o, transport.dial, func() error {
			if announceStart {
				_, err := fmt.Fprintln(stdout, "STARTED")
				return err
			}
			return nil
		})
		if err == nil {
			err = json.NewEncoder(stdout).Encode(report)
		}
		if err != nil {
			fmt.Fprintf(stderr, "Échec de l'envoi synthétique (%d octets écrits) : %v\n", report.WrittenBytes, err)
			return 1
		}
		return 0
	}
	received, err := receive(ctx, o, transport.listen, func(address string) error {
		_, err := fmt.Fprintf(stdout, "READY %s\n", address)
		return err
	})
	if err != nil {
		fmt.Fprintf(stderr, "Échec de la réception synthétique (%d octets lus) : %v\n", received, err)
		return 1
	}
	fmt.Fprintf(stderr, "Réception synthétique terminée : %d octets reçus.\n", received)
	return 0
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM, syscall.SIGHUP)
	transport := network{listen: (&net.ListenConfig{}).Listen, dial: (&net.Dialer{}).DialContext}
	code := run(ctx, os.Args[1:], os.Stdout, os.Stderr, transport)
	stop()
	os.Exit(code)
}
