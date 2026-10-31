package linux

import (
	"bytes"
	"encoding/json"
	"fmt"

	"github.com/ayyoubecharkaouy/coopace/internal/strictjson"
)

type cakeObject map[string]json.RawMessage

func cakeObjectFrom(data []byte) (cakeObject, error) {
	var value cakeObject
	if err := json.Unmarshal(data, &value); err != nil || value == nil {
		return nil, fmt.Errorf("CAKE JSON object required")
	}
	return value, nil
}

func cakeRows(data []byte) ([]cakeObject, error) {
	if err := strictjson.CheckSyntax(data, cakeOutputLimit); err != nil {
		return nil, err
	}
	if !bytes.HasPrefix(bytes.TrimSpace(data), []byte("[")) {
		return nil, fmt.Errorf("tc JSON array required")
	}
	var raw []json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, err
	}
	rows := make([]cakeObject, 0, len(raw))
	for _, data := range raw {
		row, err := cakeObjectFrom(data)
		if err != nil {
			return nil, err
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func cakeValue(row cakeObject, key string) (json.RawMessage, error) {
	data, ok := row[key]
	if !ok || bytes.Equal(bytes.TrimSpace(data), []byte("null")) {
		return nil, fmt.Errorf("missing or null CAKE field: %s", key)
	}
	return data, nil
}

func cakeUnsigned(row cakeObject, key string) (uint64, error) {
	data, err := cakeValue(row, key)
	if err != nil {
		return 0, err
	}
	// JSON -0 is the integer zero in the reviewed Python reference as well.
	if bytes.Equal(bytes.TrimSpace(data), []byte("-0")) {
		return 0, nil
	}
	var value uint64
	if err := json.Unmarshal(data, &value); err != nil {
		return 0, fmt.Errorf("CAKE field %s must be an unsigned 64-bit integer", key)
	}
	return value, nil
}

func cakeExpected(row cakeObject, key string, expected any) error {
	data, err := cakeValue(row, key)
	if err != nil {
		return err
	}
	valid := false
	switch want := expected.(type) {
	case uint64:
		got, err := cakeUnsigned(row, key)
		valid = err == nil && got == want
	case string:
		var got string
		valid = json.Unmarshal(data, &got) == nil && got == want
	case bool:
		var got bool
		valid = json.Unmarshal(data, &got) == nil && got == want
	}
	if !valid {
		return fmt.Errorf("unexpected CAKE field: %s", key)
	}
	return nil
}

func cakeRoot(data []byte, profile CakeProducerProfile) (cakeObject, error) {
	if profile != CakeIPRoute2V610 {
		return nil, fmt.Errorf("unknown CAKE producer profile")
	}
	rows, err := cakeRows(data)
	if err != nil {
		return nil, err
	}
	if len(rows) != 1 {
		return nil, fmt.Errorf("exactly one CAKE root required")
	}
	row := rows[0]
	for key, value := range map[string]any{"kind": "cake", "root": true, "handle": "10:"} {
		if err := cakeExpected(row, key, value); err != nil {
			return nil, err
		}
	}
	if _, ok := row["parent"]; ok {
		return nil, fmt.Errorf("CAKE root must not have a parent")
	}
	if _, ok := row["dev"]; ok {
		if err := cakeExpected(row, "dev", "wan"); err != nil {
			return nil, err
		}
	}
	return row, nil
}

// ValidateCakeInitial only validates a dump from an already owned, fresh DOWN
// link. An empty dump does not itself establish ownership or interface state.
func ValidateCakeInitial(data []byte) error {
	rows, err := cakeRows(data)
	if err != nil {
		return err
	}
	if len(rows) == 0 {
		return nil
	}
	if len(rows) != 1 {
		return fmt.Errorf("empty dump or one noqueue root required")
	}
	row := rows[0]
	for key, value := range map[string]any{"kind": "noqueue", "root": true, "handle": "0:"} {
		if err := cakeExpected(row, key, value); err != nil {
			return err
		}
	}
	if _, ok := row["parent"]; ok {
		return fmt.Errorf("initial root must not have a parent")
	}
	if _, ok := row["dev"]; ok {
		return cakeExpected(row, "dev", "wan")
	}
	return nil
}

func cakeConfiguration(row cakeObject, profile CakeProducerProfile) (CakeConfiguration, error) {
	options, err := cakeObjectFrom(row["options"])
	if err != nil {
		return CakeConfiguration{}, err
	}
	effective := CakeOptions{BandwidthBytesPerSecond: cakeRateBytesPerSecond, RTTUS: cakeRTTUS,
		MemoryLimitBytes: cakeMemoryLimitBytes, Diffserv: "besteffort", FlowMode: "flows", ACKFilter: "disabled",
		SplitGSO: true, Raw: true, FWMark: "0", ATM: "noatm"}
	for key, value := range map[string]any{
		"bandwidth": effective.BandwidthBytesPerSecond, "rtt": effective.RTTUS, "memlimit": effective.MemoryLimitBytes,
		"diffserv": effective.Diffserv, "flowmode": effective.FlowMode, "nat": false, "wash": false, "ingress": false,
		"ack-filter": effective.ACKFilter, "split_gso": true, "raw": true, "overhead": uint64(0), "fwmark": effective.FWMark,
	} {
		if err := cakeExpected(options, key, value); err != nil {
			return CakeConfiguration{}, err
		}
	}
	if _, ok := options["autorate"]; ok {
		return CakeConfiguration{}, fmt.Errorf("unexpected CAKE autorate field")
	}
	omitted := map[string]string{"autorate": "iproute2_6_1_0_omits_disabled_autorate"}
	for _, field := range []struct {
		key    string
		value  any
		reason string
	}{
		{"mpu", uint64(0), "iproute2_6_1_0_omits_zero_mpu"},
		{"atm", "noatm", "iproute2_6_1_0_omits_noatm_when_raw"},
	} {
		if _, present := options[field.key]; present {
			if err := cakeExpected(options, field.key, field.value); err != nil {
				return CakeConfiguration{}, err
			}
		} else {
			omitted[field.key] = field.reason
		}
	}
	return CakeConfiguration{Profile: profile, Effective: effective, OmittedFields: omitted}, nil
}

func ParseCakeConfiguration(data []byte, profile CakeProducerProfile) (CakeConfiguration, error) {
	row, err := cakeRoot(data, profile)
	if err != nil {
		return CakeConfiguration{}, err
	}
	return cakeConfiguration(row, profile)
}
