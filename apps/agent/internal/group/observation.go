package group

import (
	"fmt"
	"strconv"
	"time"

	"github.com/ayyoubecharkaouy/coopace/apps/agent/internal/observe"
	"github.com/ayyoubecharkaouy/coopace/packages/core"
	"github.com/ayyoubecharkaouy/coopace/packages/protocol"
)

func wireObservation(report observe.Report) (*protocol.TrafficObservation, error) {
	if report.Source != "Linux /proc/net/dev" {
		return nil, fmt.Errorf("unsupported observation source")
	}
	observation := &protocol.TrafficObservation{ObservedAt: report.FinishedAt.UTC(), Source: "linux_proc_net_dev", Scope: "process_network_namespace",
		WindowMS: float64(report.Elapsed) / float64(time.Millisecond), Interfaces: make([]protocol.InterfaceBytes, 0, len(report.Interfaces))}
	for _, item := range report.Interfaces {
		value := protocol.InterfaceBytes{Name: item.Name, State: string(item.State)}
		if item.State == core.TrafficMeasured {
			if item.Traffic == nil {
				return nil, fmt.Errorf("measured interface has no deltas")
			}
			received, sent := strconv.FormatUint(item.Traffic.ReceivedBytes, 10), strconv.FormatUint(item.Traffic.SentBytes, 10)
			value.ReceivedBytes, value.SentBytes = &received, &sent
		}
		observation.Interfaces = append(observation.Interfaces, value)
	}
	return observation, nil // Encode applies all wire bounds before transmission.
}
