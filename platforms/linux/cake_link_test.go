package linux

import (
	"strings"
	"testing"
)

const labLinksJSON = `[{"ifindex":1,"ifname":"lo","flags":["LOOPBACK"]},{"ifindex":2,"ifname":"wan","flags":["BROADCAST","MULTICAST"],"operstate":"DOWN","link_type":"ether","linkinfo":{"info_kind":"veth"},"mtu":1500,"link_index":3,"address":"02:00:00:00:00:01"}]`
const labAddressesJSON = `[{"ifindex":2,"ifname":"wan","flags":["BROADCAST","MULTICAST"],"operstate":"DOWN","addr_info":[]}]`

func TestCakeLabLinkIdentityRequiresDownVethWithoutAddresses(t *testing.T) {
	link, err := cakeLabLinks([]byte(labLinksJSON))
	if err != nil {
		t.Fatal(err)
	}
	if link.Index != 2 || link.PeerIndex != 3 || link.LoopbackIndex != 1 || link.MTU != 1500 {
		t.Fatalf("identity changed: %+v", link)
	}
	if err := cakeLabAddresses([]byte(labAddressesJSON), link); err != nil {
		t.Fatal(err)
	}
	for _, bad := range []string{
		`[]`, `null`, strings.Replace(labLinksJSON, `"wan"`, `"eth0"`, 1),
		strings.Replace(labLinksJSON, `"BROADCAST"`, `"UP"`, 1),
		strings.Replace(labLinksJSON, `"LOOPBACK"`, `"LOOPBACK","UP"`, 1),
		strings.Replace(labLinksJSON, `"veth"`, `"bridge"`, 1),
		strings.Replace(labLinksJSON, `"DOWN"`, `"UP"`, 1),
		strings.Replace(labLinksJSON, `"mtu":1500`, `"mtu":null`, 1),
		strings.Replace(labLinksJSON, `"ifindex":2`, `"ifindex":1`, 1),
		strings.Replace(labLinksJSON, `"link_index":3`, `"link_index":0`, 1),
		strings.Replace(labLinksJSON, `"02:00:00:00:00:01"`, `"01:00:00:00:00:01"`, 1),
		strings.Replace(labLinksJSON, `"02:00:00:00:00:01"`, `"00:00:00:00:00:00"`, 1),
		strings.Replace(labLinksJSON, `"02:00:00:00:00:01"`, `"0000.0000.0000"`, 1),
		strings.Replace(labLinksJSON, `"flags":["BROADCAST","MULTICAST"]`, `"flags":null`, 1),
		strings.Replace(labLinksJSON, `"ifindex":2`, `"ifindex":2,"ifindex":2`, 1),
	} {
		if _, err := cakeLabLinks([]byte(bad)); err == nil {
			t.Fatalf("invalid link accepted: %s", bad)
		}
	}
	for _, bad := range []string{`[]`, strings.Replace(labAddressesJSON, `"addr_info":[]`, `"addr_info":null`, 1), strings.Replace(labAddressesJSON, `"addr_info":[]`, `"addr_info":[{"family":"inet6"}]`, 1), strings.Replace(labAddressesJSON, `"ifindex":2`, `"ifindex":3`, 1), strings.Replace(labAddressesJSON, `"MULTICAST"`, `"UP"`, 1)} {
		if err := cakeLabAddresses([]byte(bad), link); err == nil {
			t.Fatalf("invalid addresses accepted: %s", bad)
		}
	}
}
