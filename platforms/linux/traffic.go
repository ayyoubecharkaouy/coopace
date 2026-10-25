// Package linux implements Linux-specific network integrations.
package linux

import (
	"bufio"
	"fmt"
	"io"
	"strconv"
	"strings"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

func parseTrafficCounters(reader io.Reader) ([]core.InterfaceCounters, error) {
	scanner := bufio.NewScanner(reader)
	for _, marker := range []string{"Inter-|", "face |"} {
		if !scanner.Scan() {
			if err := scanner.Err(); err != nil {
				return nil, err
			}
			return nil, fmt.Errorf("missing /proc/net/dev header")
		}
		if !strings.HasPrefix(strings.TrimSpace(scanner.Text()), marker) {
			return nil, fmt.Errorf("invalid /proc/net/dev header")
		}
	}
	counters := make([]core.InterfaceCounters, 0)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		separator := strings.LastIndex(line, ":")
		if separator < 1 {
			return nil, fmt.Errorf("invalid /proc/net/dev interface row")
		}
		name := strings.TrimSpace(line[:separator])
		fields := strings.Fields(line[separator+1:])
		if len(fields) != 16 {
			return nil, fmt.Errorf("invalid counter count for interface %q", name)
		}
		received, err := strconv.ParseUint(fields[0], 10, 64)
		if err != nil {
			return nil, fmt.Errorf("invalid received-byte counter for %q: %w", name, err)
		}
		sent, err := strconv.ParseUint(fields[8], 10, 64)
		if err != nil {
			return nil, fmt.Errorf("invalid sent-byte counter for %q: %w", name, err)
		}
		counters = append(counters, core.InterfaceCounters{Name: name, ReceivedBytes: received, SentBytes: sent})
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("reading interface counters: %w", err)
	}
	return counters, nil
}
