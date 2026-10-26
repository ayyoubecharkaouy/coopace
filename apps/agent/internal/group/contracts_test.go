package group

import (
	"strings"
	"testing"

	"github.com/ayyoubecharkaouy/coopace/packages/protocol"
)

func TestHelloConversionUsesDomainCapabilityRules(t *testing.T) {
	message := protocol.Message{Version: 1, Kind: protocol.HelloKind, GroupID: "test-group", SenderID: "ed25519:" + strings.Repeat("a", 64), Sequence: 1,
		Hello: &protocol.Hello{Name: "PC", OS: "linux", Roles: []string{"agent"}, Capabilities: []string{"manage_gateway_traffic"}}}
	data, err := protocol.Encode(message)
	if err != nil {
		t.Fatal("wire structure should be valid before domain capability validation")
	}
	decoded, err := protocol.Decode(data)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := DeviceFromHello(decoded); err == nil {
		t.Fatal("gateway capability without gateway role accepted by application")
	}
	decoded.Hello.Roles = append(decoded.Hello.Roles, "gateway")
	if device, err := DeviceFromHello(decoded); err != nil || string(device.ID) != message.SenderID {
		t.Fatalf("valid peer description rejected: %v", err)
	}
}
