package linux

import (
	"context"
	"errors"
	"net"
	"reflect"
	"strings"
	"testing"
)

func TestGatewayRoutesKeepAllTablesAndUnresolvedPaths(t *testing.T) {
	data := []byte(`[
	 {"dst":"default","gateway":"192.0.2.1","dev":"eth0","table":254},
	 {"dst":"default","table":"vpn","nexthops":[{"dev":"tun0"},{"dev":"eth1"}]},
	 {"dst":"default","type":"blackhole"},
	 {"dst":"default","table":100,"nhid":12}
	]`)
	routes, err := parseGatewayRoutes(data, "-4")
	if err != nil {
		t.Fatal(err)
	}
	if len(routes) != 4 || routes[0].Table != "254" || routes[0].Kind != "unicast" || !reflect.DeepEqual(routes[1].Interfaces, []string{"tun0", "eth1"}) || routes[2].Kind != "blackhole" || len(routes[2].Interfaces) != 0 || !routes[3].UnresolvedNexthop {
		t.Fatalf("route information lost or inferred: %+v", routes)
	}
	for _, input := range []string{`[]`, `[{"dst":"::/0","dev":"eth0"}]`} {
		if _, err := parseGatewayRoutes([]byte(input), "-6"); err != nil {
			t.Fatal(err)
		}
	}
	for _, input := range []string{`null`, `{}`, `[{"dst":"192.0.2.0/24"}]`, `[{"dst":"default","table":true}]`, `[{"dst":"default","table":null}]`, `[{"dst":"default","table":""}]`, `[] []`, strings.Repeat(" ", gatewayOutputLimit+1)} {
		if _, err := parseGatewayRoutes([]byte(input), "-4"); err == nil {
			t.Fatalf("invalid route output accepted: %.80s", input)
		}
	}
}

func TestGatewayFlagsDistinguishFalseFromMissingAndInvalid(t *testing.T) {
	for _, value := range []string{"0\n", "1\n"} {
		enabled, err := parseForwarding([]byte(value))
		if err != nil || enabled != strings.HasPrefix(value, "1") {
			t.Fatalf("invalid flag: %t %v", enabled, err)
		}
	}
	for _, value := range []string{"", "2", "true", "0 1"} {
		if _, err := parseForwarding([]byte(value)); err == nil {
			t.Fatal("invalid forwarding value accepted")
		}
	}
	for _, entry := range []struct {
		data     string
		expected bool
	}{
		{"CapEff:\t0000000000001000\n", true}, {"CapEff:\t0000000000000000\n", false}, {"CapEff:\t0000000000000001\n", false},
	} {
		value, err := parseNetAdmin([]byte(entry.data))
		if err != nil || value != entry.expected {
			t.Fatalf("wrong capability: %t %v", value, err)
		}
	}
	for _, value := range []string{"Name:\ttest\n", "CapEff:\tno\n", "CapEff: 0\nCapEff: 1000\n"} {
		if _, err := parseNetAdmin([]byte(value)); err == nil {
			t.Fatal("invalid capability data accepted")
		}
	}
}

func TestGatewayQueuesIgnoreOptionsWithoutInventingKernelSupport(t *testing.T) {
	queues, err := parseGatewayQueues([]byte(`[{"kind":"noqueue","dev":"lo","handle":"0:","root":true},{"kind":"cake","dev":"eth0","handle":"1:","root":true,"options":{"bandwidth":1000000}}]`))
	if err != nil || len(queues) != 2 || queues[1].Kind != "cake" || queues[1].Interface != "eth0" {
		t.Fatalf("invalid queues: %+v %v", queues, err)
	}
	for _, input := range []string{`null`, `[{}]`, `[{"kind":"cake"}]`} {
		if _, err := parseGatewayQueues([]byte(input)); err == nil {
			t.Fatal("malformed queue output accepted")
		}
	}
}

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
