package main

import (
	"context"
	"os"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/labcontrol"
)

var version = "dev"

func main() {
	started := time.Now()
	os.Exit(labcontrol.RunInternalWorker(context.Background(), os.Args[1:], version, started, os.Stderr))
}
