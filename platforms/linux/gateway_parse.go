package linux

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"

	"github.com/ayyoubecharkaouy/coopace/packages/core"
)

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
