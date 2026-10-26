package linux

import (
	"context"
	"errors"
	"net"
	"strings"
	"testing"
)

func TestGatewayInventoryUsesOnlyReadQueriesAndPreservesPartialFailures(t *testing.T) {
	var queries []string
	sources := gatewaySources{
		interfaces: func() ([]net.Interface, error) {
			return []net.Interface{{Name: "eth0", Index: 2, MTU: 1500, Flags: net.FlagUp}}, nil
		},
		readFile: func(path string) ([]byte, error) {
			switch path {
			case "/proc/sys/net/ipv4/ip_forward":
				return []byte("0\n"), nil
			case "/proc/sys/net/ipv6/conf/all/forwarding":
				return nil, errors.New("refus de lecture IPv6")
			case "/proc/self/status":
				return []byte("CapEff:\t0000000000000000\n"), nil
			default:
				t.Fatalf("unexpected file read: %q", path)
				return nil, nil
			}
		},
		lookPath: func(name string) (string, error) { return "/tools/" + name, nil },
		run: func(ctx context.Context, path string, args ...string) ([]byte, error) {
			query := path + " " + strings.Join(args, " ")
			queries = append(queries, query)
			switch query {
			case "/tools/ip -j -4 route show table all exact default":
				return []byte(`[]`), nil
			case "/tools/ip -j -6 route show table all exact default":
				return nil, errors.New("netlink interdit")
			case "/tools/tc -j qdisc show":
				return []byte(`[]`), nil
			default:
				t.Fatalf("query outside read-only allowlist: %q", query)
				return nil, nil
			}
		},
	}
	result, err := collectGateway(context.Background(), sources)
	if err != nil {
		t.Fatal(err)
	}
	if !result.Interfaces.Available || len(result.Interfaces.Value) != 1 || !result.IPv4Forwarding.Available || result.IPv4Forwarding.Value || result.IPv6Forwarding.Available || result.IPv6Forwarding.Reason == "" || !result.NetAdmin.Available || result.NetAdmin.Value || !result.IPv4Defaults.Available || len(result.IPv4Defaults.Value) != 0 || result.IPv6Defaults.Available || !result.Queues.Available || len(queries) != 3 {
		t.Fatalf("missing, empty and false values confused: %+v", result)
	}
	sources.interfaces = func() ([]net.Interface, error) { return nil, errors.New("interfaces interdites") }
	sources.lookPath = func(string) (string, error) { return "", errors.New("absent") }
	queries = nil
	result, err = collectGateway(context.Background(), sources)
	if err != nil || result.Interfaces.Available || result.IPv4Defaults.Available || result.Queues.Available || len(queries) != 0 {
		t.Fatalf("invented available results or ran missing tools: %+v %v", result, err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	sources.interfaces = func() ([]net.Interface, error) { t.Fatal("read after cancellation"); return nil, nil }
	if _, err := collectGateway(ctx, sources); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation ignored: %v", err)
	}
}
