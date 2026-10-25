package latency

import (
	"context"
	"errors"
	"net"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func probeTCP(ctx context.Context, target string, timeout time.Duration) core.LatencySample {
	dialer := net.Dialer{Timeout: timeout}
	started := time.Now()
	connection, err := dialer.DialContext(ctx, "tcp", target)
	duration := time.Since(started)
	if err != nil {
		var networkError net.Error
		if errors.As(err, &networkError) && networkError.Timeout() {
			return core.LatencySample{Failure: core.LatencyTimeout}
		}
		return core.LatencySample{Failure: core.LatencyConnectionFailed}
	}
	connection.Close()
	return core.LatencySample{Duration: duration}
}
