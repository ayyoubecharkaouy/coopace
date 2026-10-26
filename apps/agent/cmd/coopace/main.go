package main

import (
	"context"
	"os"
	"os/signal"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/cli"
)

var version = "dev"

func main() {
	ctx := context.Background()
	stop := func() {}
	if len(os.Args) > 1 && (os.Args[1] == "latency" || os.Args[1] == "group") {
		ctx, stop = signal.NotifyContext(ctx, os.Interrupt)
	}
	code := cli.RunContext(ctx, os.Args[1:], version, os.Stdout, os.Stderr)
	stop()
	os.Exit(code)
}
