package main

import (
	"context"
	"os"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/gateway/internal/labcontrol"
)

func main() {
	started := time.Now()
	os.Exit(labcontrol.RunGatewaySessionWorker(context.Background(), os.Args[1:], started, os.Stderr))
}
