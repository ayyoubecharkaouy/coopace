package group

import "testing"

func TestGroupAddressesRejectNonUnicastBeforeNetworkIO(t *testing.T) {
	for _, address := range []string{
		"", "example.com:8766", "127.0.0.1", "224.0.0.1:8766", "255.255.255.255:8766",
		"[ff02::1]:8766", "[::ffff:255.255.255.255]:8766", "[::ffff:224.0.0.1]:8766", "[fe80::1%eth0]:8766",
	} {
		for _, listener := range []bool{false, true} {
			if err := ValidateAddress(address, listener); err == nil {
				t.Errorf("invalid address accepted: %q listener=%t", address, listener)
			}
		}
	}
	for _, address := range []string{"0.0.0.0:8766", "[::]:8766", "[::ffff:0.0.0.0]:8766", "127.0.0.1:0"} {
		if err := ValidateAddress(address, false); err == nil {
			t.Errorf("wildcard address or port accepted as a destination: %q", address)
		}
		if err := ValidateAddress(address, true); err != nil {
			t.Errorf("explicit wildcard listener rejected: %q: %v", address, err)
		}
	}
	for _, address := range []string{"127.0.0.1:8766", "192.168.1.42:8766", "[::1]:8766", "[2001:db8::1]:8766", "[::ffff:127.0.0.1]:8766"} {
		for _, listener := range []bool{false, true} {
			if err := ValidateAddress(address, listener); err != nil {
				t.Errorf("unicast address rejected: %q listener=%t: %v", address, listener, err)
			}
		}
	}
}
