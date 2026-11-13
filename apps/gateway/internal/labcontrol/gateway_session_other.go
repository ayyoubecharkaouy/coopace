//go:build !linux || android

package labcontrol

import (
	"context"
	"fmt"
	"io"
	"time"
)

func RunGatewaySessionWorker(_ context.Context, _ []string, _ time.Time, stderr io.Writer) int {
	fmt.Fprintln(stderr, "Coopace : pilote de session réservé au laboratoire Linux amd64.")
	return 1
}
