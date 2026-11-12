package linux

import (
	"bytes"
	"fmt"
	"net"
	"path"
	"reflect"
	"strings"
)

// ValidateGatewayQueueSnapshot checks the declared observation, never its
// authenticity, namespace continuity, freshness or permission to change a link.
func ValidateGatewayQueueSnapshot(source GatewayQueueSnapshot) error {
	target := source.Interface
	if err := ValidateGatewaySnapshotInterfaceName(target.Name); err != nil {
		return err
	}
	if target.Index <= 0 || target.MTU <= 0 || target.Flags&uint(net.FlagLoopback) != 0 {
		return fmt.Errorf("identité d'interface invalide")
	}
	if target.HardwareAddress != "" {
		address, err := net.ParseMAC(target.HardwareAddress)
		if err != nil || address.String() != target.HardwareAddress {
			return fmt.Errorf("adresse matérielle invalide")
		}
	}
	if source.StartedAt.IsZero() || source.FinishedAt.Before(source.StartedAt) {
		return fmt.Errorf("horaires de capture incohérents")
	}
	queries := gatewaySnapshotQueries(target.Name)
	if len(source.Readings) != len(queries) {
		return fmt.Errorf("six sections ordonnées requises")
	}
	previous := source.StartedAt
	for index, reading := range source.Readings {
		query := queries[index]
		if reading.Section != query.section || reading.Tool != query.tool || !reflect.DeepEqual(reading.Arguments, query.args) {
			return fmt.Errorf("section ou commande incohérente : %s", query.section)
		}
		if reading.StartedAt.Before(previous) || reading.FinishedAt.Before(reading.StartedAt) || reading.FinishedAt.After(source.FinishedAt) {
			return fmt.Errorf("horaires de section incohérents : %s", query.section)
		}
		previous = reading.FinishedAt
		if reading.Path != "" && (!path.IsAbs(reading.Path) || path.Clean(reading.Path) != reading.Path || strings.ContainsRune(reading.Path, 0)) {
			return fmt.Errorf("chemin d'outil invalide")
		}
		if reading.Available {
			if reading.Path == "" || reading.Reason != "" {
				return fmt.Errorf("disponibilité incohérente : %s", query.section)
			}
			if err := validateGatewaySnapshotArray(reading.Value, reading.Section, target); err != nil {
				return fmt.Errorf("section %s : %w", query.section, err)
			}
		} else if (len(reading.Value) != 0 && !bytes.Equal(bytes.TrimSpace(reading.Value), []byte("null"))) || reading.Reason == "" {
			return fmt.Errorf("valeur indisponible incohérente : %s", query.section)
		}
		fallback := reading.ClassesTextFallback
		if reading.Normalization == "" && reading.SourceOutput == nil && fallback == nil {
			continue
		}
		if reading.Section != "classes" || reading.SourceOutput == nil || !emptyGatewaySnapshotOutput([]byte(*reading.SourceOutput)) || fallback == nil {
			return fmt.Errorf("preuves de compatibilité des classes incohérentes")
		}
		if !reflect.DeepEqual(fallback.Arguments, []string{"-s", "-d", "class", "show", "dev", target.Name}) || fallback.StartedAt.Before(reading.StartedAt) || fallback.FinishedAt.Before(fallback.StartedAt) || fallback.FinishedAt.After(reading.FinishedAt) || len(fallback.StdoutBase64) > gatewayOutputLimit {
			return fmt.Errorf("confirmation des classes incohérente")
		}
		if reading.Available {
			if reading.Normalization != "empty_classes_confirmed_by_text" || !bytes.Equal(bytes.TrimSpace(reading.Value), []byte("[]")) || !fallback.Succeeded || fallback.StdoutBase64 == nil || !emptyGatewaySnapshotOutput(fallback.StdoutBase64) || fallback.Reason != "" {
				return fmt.Errorf("classes vides non confirmées")
			}
		} else if reading.Normalization != "" || fallback.Reason == "" {
			return fmt.Errorf("échec de confirmation incohérent")
		}
	}
	return nil
}
