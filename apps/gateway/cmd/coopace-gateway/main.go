package main

import (
	"context"
	"os"
	"os/signal"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/cli"
)

var version = "dev"

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	code := cli.RunContext(ctx, os.Args[1:], version, os.Stdout, os.Stderr)
	stop()
	os.Exit(code)
}
