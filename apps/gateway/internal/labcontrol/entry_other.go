//go:build !linux || android

package labcontrol

import (
	"context"
	"io"
	"time"
)

func RunInternalWorker(_ context.Context, _ []string, _ string, _ time.Time, stderr io.Writer) int {
	io.WriteString(stderr, "Le processus interne CAKE nécessite Linux amd64.\n")
	return 2
}
