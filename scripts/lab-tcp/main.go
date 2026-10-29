// Command lab-tcp is a bounded TCP endpoint for the disposable IPv4 lab.
package main

import (
	"context"
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

type options struct {
	address     string
	connections int
	duration    time.Duration
}

func (o options) validate() error {
	endpoint, err := netip.ParseAddrPort(o.address)
	if err != nil || !endpoint.Addr().Is4() || endpoint.Port() < 1024 ||
		(!endpoint.Addr().IsPrivate() && !endpoint.Addr().IsLoopback()) {
		return errors.New("adresse IPv4 privée ou de boucle locale explicite et port de 1024 à 65535 requis")
	}
	if o.connections < 1 || o.connections > 100 {
		return errors.New("nombre de connexions attendu de 1 à 100")
	}
	if o.duration < time.Second || o.duration > 30*time.Second {
		return errors.New("durée maximale attendue de 1s à 30s")
	}
	return nil
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer, listen listenFunc) int {
	o := options{}
	flags := flag.NewFlagSet("lab-tcp", flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.StringVar(&o.address, "listen", "", "adresse IPv4:port privée ou de boucle locale, obligatoire")
	flags.IntVar(&o.connections, "connections", 5, "connexions à accepter avant de terminer, de 1 à 100")
	flags.DurationVar(&o.duration, "duration", 15*time.Second, "durée maximale, de 1s à 30s")
	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if flags.NArg() != 0 {
		fmt.Fprintln(stderr, "Arguments positionnels non reconnus.")
		return 2
	}
	if err := o.validate(); err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}
	ctx, cancel := context.WithTimeout(ctx, o.duration)
	defer cancel()
	err := serve(ctx, o, listen, func(address string) error {
		_, err := fmt.Fprintf(stdout, "READY %s\n", address)
		return err
	})
	if err != nil {
		fmt.Fprintf(stderr, "Serveur TCP de laboratoire arrêté : %v\n", err)
		return 1
	}
	fmt.Fprintf(stderr, "Serveur TCP de laboratoire terminé : %d connexions acceptées.\n", o.connections)
	return 0
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM, syscall.SIGHUP)
	config := net.ListenConfig{}
	code := run(ctx, os.Args[1:], os.Stdout, os.Stderr, config.Listen)
	stop()
	os.Exit(code)
}
