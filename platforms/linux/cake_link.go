package linux

import (
	"encoding/json"
	"fmt"
	"net"
)

func cakeLinkFlags(row cakeObject, loopback bool) error {
	data, err := cakeValue(row, "flags")
	if err != nil {
		return err
	}
	var flags []string
	if err := json.Unmarshal(data, &flags); err != nil || flags == nil {
		return fmt.Errorf("link flags unavailable")
	}
	seen := map[string]bool{}
	for _, flag := range flags {
		if flag == "" || seen[flag] || flag == "UP" {
			return fmt.Errorf("laboratory interfaces must be DOWN with unambiguous flags")
		}
		seen[flag] = true
	}
	if seen["LOOPBACK"] != loopback {
		return fmt.Errorf("unexpected loopback flag")
	}
	return nil
}

func cakeLabLinks(raw []byte) (CakeLabLink, error) {
	rows, err := cakeRows(raw)
	if err != nil {
		return CakeLabLink{}, err
	}
	if len(rows) != 2 {
		return CakeLabLink{}, fmt.Errorf("only lo and wan are allowed in the laboratory gateway")
	}
	var result CakeLabLink
	for _, row := range rows {
		var name string
		if err := json.Unmarshal(row["ifname"], &name); err != nil {
			return result, err
		}
		index, err := cakeUnsigned(row, "ifindex")
		if err != nil || index == 0 || index > 1<<31-1 {
			return result, fmt.Errorf("invalid interface index")
		}
		switch name {
		case "lo":
			if result.LoopbackIndex != 0 {
				return result, fmt.Errorf("duplicate lo interface")
			}
			if err := cakeLinkFlags(row, true); err != nil {
				return result, err
			}
			result.LoopbackIndex = index
		case "wan":
			if result.Index != 0 {
				return result, fmt.Errorf("duplicate wan interface")
			}
			if err := cakeLinkFlags(row, false); err != nil {
				return result, err
			}
			if err := cakeExpected(row, "operstate", "DOWN"); err != nil {
				return result, err
			}
			if err := cakeExpected(row, "link_type", "ether"); err != nil {
				return result, err
			}
			info, err := cakeObjectFrom(row["linkinfo"])
			if err != nil {
				return result, err
			}
			if err := cakeExpected(info, "info_kind", "veth"); err != nil {
				return result, err
			}
			mtu, err := cakeUnsigned(row, "mtu")
			if err != nil || mtu == 0 || mtu > 65535 {
				return result, fmt.Errorf("invalid veth MTU")
			}
			peer, err := cakeUnsigned(row, "link_index")
			if err != nil || peer == 0 || peer > 1<<31-1 {
				return result, fmt.Errorf("veth peer index unavailable")
			}
			var address string
			if err := json.Unmarshal(row["address"], &address); err != nil {
				return result, err
			}
			mac, err := net.ParseMAC(address)
			if err != nil || len(mac) != 6 || mac[0]&1 != 0 || mac.String() == "00:00:00:00:00:00" {
				return result, fmt.Errorf("invalid veth MAC address")
			}
			result.Index, result.PeerIndex, result.MTU, result.MAC = index, peer, mtu, mac.String()
		default:
			return result, fmt.Errorf("unexpected laboratory interface")
		}
	}
	if result.Index == 0 || result.LoopbackIndex == 0 || result.Index == result.LoopbackIndex {
		return result, fmt.Errorf("laboratory interface identities are incomplete")
	}
	return result, nil
}

func cakeLabAddresses(raw []byte, link CakeLabLink) error {
	rows, err := cakeRows(raw)
	if err != nil {
		return err
	}
	if len(rows) != 1 {
		return fmt.Errorf("one wan address record required")
	}
	row := rows[0]
	if err := cakeExpected(row, "ifname", "wan"); err != nil {
		return err
	}
	index, err := cakeUnsigned(row, "ifindex")
	if err != nil || index != link.Index {
		return fmt.Errorf("wan address identity changed")
	}
	if err := cakeLinkFlags(row, false); err != nil {
		return err
	}
	if err := cakeExpected(row, "operstate", "DOWN"); err != nil {
		return err
	}
	var addresses []json.RawMessage
	if err := json.Unmarshal(row["addr_info"], &addresses); err != nil || addresses == nil || len(addresses) != 0 {
		return fmt.Errorf("wan must have an explicit empty IPv4/IPv6 address list")
	}
	return nil
}
