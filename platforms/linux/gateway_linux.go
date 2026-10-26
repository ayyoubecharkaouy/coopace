//go:build linux && !android

package linux

import (
	"context"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"time"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

// InspectGateway queries the current process network namespace. All external
// arguments are fixed read-only queries; no shell, escalation or installation.
func InspectGateway(ctx context.Context) (core.GatewayInventory, error) {
	return collectGateway(ctx, gatewaySources{interfaces: net.Interfaces, readFile: readGatewayFile, lookPath: exec.LookPath, run: runGatewayQuery})
}

func readGatewayFile(path string) ([]byte, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, 65537))
	if err == nil && len(data) > 65536 {
		err = fmt.Errorf("fichier de diagnostic trop volumineux")
	}
	return data, err
}

type gatewayBuffer struct {
	data  []byte
	limit int
}

func (buffer *gatewayBuffer) Write(data []byte) (int, error) {
	remaining := buffer.limit - len(buffer.data)
	if len(data) > remaining {
		buffer.data = append(buffer.data, data[:remaining]...)
		return remaining, fmt.Errorf("sortie du diagnostic trop volumineuse")
	}
	buffer.data = append(buffer.data, data...)
	return len(data), nil
}

func runGatewayQuery(ctx context.Context, path string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	command := exec.CommandContext(ctx, path, args...)
	command.WaitDelay = 100 * time.Millisecond
	stdout, stderr := &gatewayBuffer{limit: gatewayOutputLimit}, &gatewayBuffer{limit: 4096}
	command.Stdout, command.Stderr = stdout, stderr
	if err := command.Run(); err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, fmt.Errorf("requête locale : %w ; détail : %q", err, stderr.data)
	}
	return stdout.data, nil
}
