package linux

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"sort"
	"strconv"
	"strings"

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

func parseForwarding(data []byte) (bool, error) {
	switch strings.TrimSpace(string(data)) {
	case "0":
		return false, nil
	case "1":
		return true, nil
	default:
		return false, fmt.Errorf("valeur de forwarding invalide")
	}
}

func parseNetAdmin(data []byte) (bool, error) {
	found := false
	var capabilities uint64
	for _, line := range strings.Split(string(data), "\n") {
		if !strings.HasPrefix(line, "CapEff:") {
			continue
		}
		if found {
			return false, fmt.Errorf("CapEff dupliqué")
		}
		found = true
		var err error
		capabilities, err = strconv.ParseUint(strings.TrimSpace(strings.TrimPrefix(line, "CapEff:")), 16, 64)
		if err != nil {
			return false, fmt.Errorf("CapEff invalide")
		}
	}
	if !found {
		return false, fmt.Errorf("CapEff absent")
	}
	return capabilities&(1<<12) != 0, nil // CAP_NET_ADMIN, Linux UAPI capability.h.
}

func decodeGatewayArray(data []byte, output any) error {
	if len(data) > gatewayOutputLimit || !bytes.HasPrefix(bytes.TrimSpace(data), []byte("[")) {
		return fmt.Errorf("tableau JSON absent ou sortie trop volumineuse")
	}
	return json.Unmarshal(data, output)
}

func parseGatewayRoutes(data []byte, family string) ([]core.GatewayDefaultRoute, error) {
	var entries []struct {
		Destination string          `json:"dst"`
		Device      string          `json:"dev"`
		Kind        string          `json:"type"`
		Table       json.RawMessage `json:"table"`
		NexthopID   json.RawMessage `json:"nhid"`
		Nexthops    []struct {
			Device string `json:"dev"`
		} `json:"nexthops"`
	}
	if err := decodeGatewayArray(data, &entries); err != nil {
		return nil, err
	}
	result := make([]core.GatewayDefaultRoute, 0, len(entries))
	for _, entry := range entries {
		defaultPrefix := "0.0.0.0/0"
		if family == "-6" {
			defaultPrefix = "::/0"
		}
		if entry.Destination != "default" && entry.Destination != defaultPrefix {
			return nil, fmt.Errorf("route inattendue dans la sélection des routes par défaut")
		}
		item := core.GatewayDefaultRoute{Kind: entry.Kind, UnresolvedNexthop: len(entry.NexthopID) != 0}
		if item.Kind == "" {
			item.Kind = "unicast"
		}
		// ip omits the main table identifier in its JSON output.
		item.Table = "main"
		if len(entry.Table) != 0 {
			if bytes.Equal(bytes.TrimSpace(entry.Table), []byte("null")) {
				return nil, fmt.Errorf("identifiant de table absent")
			}
			if err := json.Unmarshal(entry.Table, &item.Table); err != nil {
				var table uint32
				if err := json.Unmarshal(entry.Table, &table); err != nil {
					return nil, fmt.Errorf("identifiant de table invalide")
				}
				item.Table = strconv.FormatUint(uint64(table), 10)
			}
			if item.Table == "" {
				return nil, fmt.Errorf("identifiant de table vide")
			}
		}
		if entry.Device != "" {
			item.Interfaces = append(item.Interfaces, entry.Device)
		}
		for _, next := range entry.Nexthops {
			if next.Device == "" {
				item.UnresolvedNexthop = true
			} else {
				item.Interfaces = append(item.Interfaces, next.Device)
			}
		}
		result = append(result, item)
	}
	return result, nil
}

func parseGatewayQueues(data []byte) ([]core.GatewayQueue, error) {
	var entries []struct {
		Kind   string `json:"kind"`
		Device string `json:"dev"`
		Handle string `json:"handle"`
		Parent string `json:"parent"`
		Root   bool   `json:"root"`
	}
	if err := decodeGatewayArray(data, &entries); err != nil {
		return nil, err
	}
	result := make([]core.GatewayQueue, 0, len(entries))
	for _, entry := range entries {
		if entry.Kind == "" || entry.Device == "" {
			return nil, fmt.Errorf("file sans type ou interface")
		}
		result = append(result, core.GatewayQueue{Kind: entry.Kind, Interface: entry.Device, Handle: entry.Handle, Parent: entry.Parent, Root: entry.Root})
	}
	return result, nil
}
