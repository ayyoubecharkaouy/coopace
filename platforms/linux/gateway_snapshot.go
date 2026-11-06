package linux

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"time"
)

// GatewaySnapshotInterface records identity before and after sequential queries.
// Equality at these endpoints does not establish an atomic or exhaustive dump.
type GatewaySnapshotInterface struct {
	Name            string `json:"name"`
	Index           int    `json:"index"`
	MTU             int    `json:"mtu"`
	Flags           uint   `json:"flags"`
	HardwareAddress string `json:"hardware_address"`
}

// GatewaySnapshotReading retains producer-specific options as JSON, including
// integer precision. Unavailable output is null; a successful empty list is [].
type GatewaySnapshotReading struct {
	Section    string          `json:"section"`
	Tool       string          `json:"tool"`
	Path       string          `json:"path"`
	Arguments  []string        `json:"arguments"`
	StartedAt  time.Time       `json:"started_at"`
	FinishedAt time.Time       `json:"finished_at"`
	Available  bool            `json:"available"`
	Value      json.RawMessage `json:"value"`
	Reason     string          `json:"reason,omitempty"`
}

type GatewayQueueSnapshot struct {
	Interface  GatewaySnapshotInterface `json:"interface"`
	StartedAt  time.Time                `json:"started_at"`
	FinishedAt time.Time                `json:"finished_at"`
	Readings   []GatewaySnapshotReading `json:"readings"`
}

// Partial refers only to the six selected queries, not restoration completeness.
func (snapshot GatewayQueueSnapshot) Partial() bool {
	if len(snapshot.Readings) != 6 {
		return true
	}
	for _, reading := range snapshot.Readings {
		if !reading.Available {
			return true
		}
	}
	return false
}

// ValidateGatewaySnapshotInterfaceName deliberately supports a conservative
// subset of Linux interface names. No name or WAN is selected automatically.
func ValidateGatewaySnapshotInterfaceName(name string) error {
	if len(name) == 0 || len(name) > 15 || name == "." || name == ".." || name[0] == '-' {
		return fmt.Errorf("nom d'interface explicite requis (1 à 15 caractères ASCII)")
	}
	for _, c := range name {
		if (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.' || c == ':' {
			continue
		}
		return fmt.Errorf("caractère non pris en charge dans le nom d'interface")
	}
	return nil
}

type gatewaySnapshotSources struct {
	interfaceByName func(string) (*net.Interface, error)
	lookPath        func(string) (string, error)
	run             func(context.Context, string, ...string) ([]byte, error)
}

func snapshotIdentity(item *net.Interface) GatewaySnapshotInterface {
	return GatewaySnapshotInterface{Name: item.Name, Index: item.Index, MTU: item.MTU, Flags: uint(item.Flags), HardwareAddress: item.HardwareAddr.String()}
}

func collectGatewayQueueSnapshot(ctx context.Context, name string, sources gatewaySnapshotSources) (GatewayQueueSnapshot, error) {
	if err := ValidateGatewaySnapshotInterfaceName(name); err != nil {
		return GatewayQueueSnapshot{}, err
	}
	if err := ctx.Err(); err != nil {
		return GatewayQueueSnapshot{}, err
	}
	result := GatewayQueueSnapshot{StartedAt: time.Now().UTC()}
	item, err := sources.interfaceByName(name)
	if err != nil {
		return GatewayQueueSnapshot{}, fmt.Errorf("interface choisie indisponible : %w", err)
	}
	if item == nil || item.Name != name || item.Index <= 0 || item.Flags&net.FlagLoopback != 0 {
		return GatewayQueueSnapshot{}, fmt.Errorf("interface choisie invalide ou boucle locale")
	}
	result.Interface = snapshotIdentity(item)
	type resolvedTool struct {
		path string
		err  error
	}
	tools := make(map[string]resolvedTool)
	for _, tool := range []string{"ip", "tc"} {
		path, err := sources.lookPath(tool)
		if err == nil && path == "" {
			err = fmt.Errorf("chemin de l'outil vide")
		}
		tools[tool] = resolvedTool{path, err}
	}
	queries := []struct {
		section, tool string
		args          []string
	}{
		{"link", "ip", []string{"-j", "-d", "link", "show", "dev", name}},
		{"qdiscs", "tc", []string{"-j", "-s", "-d", "qdisc", "show", "dev", name}},
		{"classes", "tc", []string{"-j", "-s", "-d", "class", "show", "dev", name}},
		{"filters_root", "tc", []string{"-j", "-s", "-d", "filter", "show", "dev", name, "root"}},
		{"filters_ingress", "tc", []string{"-j", "-s", "-d", "filter", "show", "dev", name, "ingress"}},
		{"filters_egress", "tc", []string{"-j", "-s", "-d", "filter", "show", "dev", name, "egress"}},
	}
	for _, query := range queries {
		if err := ctx.Err(); err != nil {
			return GatewayQueueSnapshot{}, err
		}
		tool := tools[query.tool]
		reading := GatewaySnapshotReading{Section: query.section, Tool: query.tool, Path: tool.path, Arguments: query.args, StartedAt: time.Now().UTC()}
		var data []byte
		err := tool.err
		if err == nil {
			data, err = sources.run(ctx, tool.path, query.args...)
		}
		if err == nil {
			err = validateGatewaySnapshotArray(data, query.section, result.Interface)
		}
		reading.FinishedAt = time.Now().UTC()
		if err != nil {
			reading.Reason = err.Error()
		} else {
			reading.Available = true
			reading.Value = append(json.RawMessage(nil), data...)
		}
		result.Readings = append(result.Readings, reading)
	}
	if err := ctx.Err(); err != nil {
		return GatewayQueueSnapshot{}, err
	}
	item, err = sources.interfaceByName(name)
	if err != nil || item == nil || snapshotIdentity(item) != result.Interface {
		return GatewayQueueSnapshot{}, fmt.Errorf("identité ou état de l'interface modifié pendant la capture")
	}
	if err := ctx.Err(); err != nil {
		return GatewayQueueSnapshot{}, err
	}
	result.FinishedAt = time.Now().UTC()
	return result, nil
}
