package linux

import (
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
