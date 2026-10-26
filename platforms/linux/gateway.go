package linux

import (
	"context"
	"fmt"
	"net"
	"sort"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

const gatewayOutputLimit = 256 * 1024

type gatewaySources struct {
	interfaces func() ([]net.Interface, error)
	readFile   func(string) ([]byte, error)
	lookPath   func(string) (string, error)
	run        func(context.Context, string, ...string) ([]byte, error)
}

func gatewayReading[T any](value T, err error) core.GatewayReading[T] {
	if err != nil {
		return core.GatewayReading[T]{Reason: err.Error()}
	}
	return core.GatewayReading[T]{Available: true, Value: value}
}

func collectGateway(ctx context.Context, sources gatewaySources) (core.GatewayInventory, error) {
	var result core.GatewayInventory
	if err := ctx.Err(); err != nil {
		return result, err
	}
	interfaces, err := sources.interfaces()
	items := make([]core.GatewayInterface, 0, len(interfaces))
	if err == nil {
		for _, item := range interfaces {
			items = append(items, core.GatewayInterface{Name: item.Name, Index: item.Index, MTU: item.MTU, Up: item.Flags&net.FlagUp != 0, Loopback: item.Flags&net.FlagLoopback != 0})
		}
		sort.Slice(items, func(i, j int) bool { return items[i].Index < items[j].Index })
	}
	result.Interfaces = gatewayReading(items, err)
	for _, check := range []struct {
		path   string
		output *core.GatewayReading[bool]
	}{
		{"/proc/sys/net/ipv4/ip_forward", &result.IPv4Forwarding},
		{"/proc/sys/net/ipv6/conf/all/forwarding", &result.IPv6Forwarding},
	} {
		if err := ctx.Err(); err != nil {
			return core.GatewayInventory{}, err
		}
		data, err := sources.readFile(check.path)
		var enabled bool
		if err == nil {
			enabled, err = parseForwarding(data)
		}
		*check.output = gatewayReading(enabled, err)
	}
	if err := ctx.Err(); err != nil {
		return core.GatewayInventory{}, err
	}
	data, err := sources.readFile("/proc/self/status")
	var netAdmin bool
	if err == nil {
		netAdmin, err = parseNetAdmin(data)
	}
	result.NetAdmin = gatewayReading(netAdmin, err)
	paths := make(map[string]string)
	for _, name := range []string{"ip", "tc", "nft"} {
		path, err := sources.lookPath(name)
		result.Tools = append(result.Tools, core.GatewayTool{Name: name, Path: path, Available: err == nil})
		if err == nil {
			paths[name] = path
		}
	}
	for _, family := range []struct {
		flag   string
		output *core.GatewayReading[[]core.GatewayDefaultRoute]
	}{
		{"-4", &result.IPv4Defaults}, {"-6", &result.IPv6Defaults},
	} {
		if err := ctx.Err(); err != nil {
			return core.GatewayInventory{}, err
		}
		var routes []core.GatewayDefaultRoute
		var err error
		if paths["ip"] == "" {
			err = fmt.Errorf("ip absent du PATH")
		} else {
			data, queryErr := sources.run(ctx, paths["ip"], "-j", family.flag, "route", "show", "table", "all", "exact", "default")
			err = queryErr
			if err == nil {
				routes, err = parseGatewayRoutes(data, family.flag)
			}
		}
		*family.output = gatewayReading(routes, err)
	}
	if err := ctx.Err(); err != nil {
		return core.GatewayInventory{}, err
	}
	if paths["tc"] == "" {
		result.Queues.Reason = "tc absent du PATH"
	} else {
		data, err := sources.run(ctx, paths["tc"], "-j", "qdisc", "show")
		var queues []core.GatewayQueue
		if err == nil {
			queues, err = parseGatewayQueues(data)
		}
		result.Queues = gatewayReading(queues, err)
	}
	if err := ctx.Err(); err != nil {
		return core.GatewayInventory{}, err
	}
	return result, nil
}
