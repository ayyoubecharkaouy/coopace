package linux

import (
	"encoding/json"
	"fmt"

	"github.com/ayyoubecharkaouy/coopace/internal/strictjson"
)

func validateGatewaySnapshotArray(data []byte, section string, target GatewaySnapshotInterface) error {
	if err := strictjson.CheckSyntax(data, gatewayOutputLimit); err != nil {
		return err
	}
	var entries []map[string]json.RawMessage
	if err := json.Unmarshal(data, &entries); err != nil || entries == nil {
		return fmt.Errorf("tableau d'objets JSON requis")
	}
	for _, entry := range entries {
		if entry == nil {
			return fmt.Errorf("objet JSON requis")
		}
		if device, exists := entry["dev"]; exists {
			var name string
			if json.Unmarshal(device, &name) != nil || name != target.Name {
				return fmt.Errorf("interface inattendue dans la réponse")
			}
		}
	}
	if section == "link" {
		if len(entries) != 1 {
			return fmt.Errorf("un seul lien attendu")
		}
		var index, mtu int
		var name string
		// Decode exact keys, without encoding/json's case-insensitive struct
		// matching: a differently cased producer field is not an identity proof.
		entry := entries[0]
		if json.Unmarshal(entry["ifindex"], &index) != nil || json.Unmarshal(entry["ifname"], &name) != nil || json.Unmarshal(entry["mtu"], &mtu) != nil || index != target.Index || name != target.Name || mtu != target.MTU {
			return fmt.Errorf("identité du lien JSON incohérente")
		}
	}
	return nil
}
