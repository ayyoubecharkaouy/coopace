package main

import (
	"context"
	"fmt"
	"net"
)

type listenFunc func(context.Context, string, string) (net.Listener, error)

// serve closes each connection immediately, without reading or writing payload.
// Closing the listener releases Accept when the context expires or is cancelled.
func serve(ctx context.Context, o options, listen listenFunc, ready func(string) error) error {
	if err := o.validate(); err != nil {
		return err
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	listener, err := listen(ctx, "tcp4", o.address)
	if err != nil {
		return fmt.Errorf("écoute : %w", err)
	}
	defer listener.Close()
	stop := context.AfterFunc(ctx, func() { listener.Close() })
	defer stop()
	if err := ready(listener.Addr().String()); err != nil {
		return fmt.Errorf("annonce de disponibilité : %w", err)
	}
	for accepted := 0; accepted < o.connections; accepted++ {
		if err := ctx.Err(); err != nil {
			return err
		}
		connection, err := listener.Accept()
		if err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			return fmt.Errorf("acceptation : %w", err)
		}
		if err := connection.Close(); err != nil {
			return fmt.Errorf("fermeture de connexion : %w", err)
		}
	}
	return nil
}
