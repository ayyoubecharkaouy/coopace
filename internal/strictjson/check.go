// Package strictjson checks bounded JSON syntax and field ambiguity, optionally
// requiring lowercase ASCII field names containing letters, digits and underscores.
// It is shared implementation code, independent of any report or network schema.
package strictjson

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"strconv"
	"strings"
	"unicode/utf8"
)

// Check rejects duplicate/noncanonical keys, excessive nesting and trailing data.
// Callers must additionally decode their schema and validate its required fields.
func Check(data []byte, maxBytes int) error {
	return check(data, maxBytes, true)
}

// CheckSyntax checks bounded UTF-8 JSON, duplicate keys, depth and trailing data,
// while allowing producer-specific field names such as tc's "ack-filter".
// It preserves integer precision; callers still validate their own schema.
func CheckSyntax(data []byte, maxBytes int) error {
	return check(data, maxBytes, false)
}

func check(data []byte, maxBytes int, canonical bool) error {
	if len(data) == 0 || len(data) > maxBytes || !utf8.Valid(data) {
		return fmt.Errorf("invalid JSON size or UTF-8 encoding")
	}
	tokens := json.NewDecoder(bytes.NewReader(data))
	if !canonical {
		tokens.UseNumber()
	}
	if err := checkKeys(tokens, 0, canonical); err != nil {
		return err
	}
	if _, err := tokens.Token(); err != io.EOF {
		return fmt.Errorf("trailing data after JSON")
	}
	return nil
}

func checkKeys(decoder *json.Decoder, depth int, canonical bool) error {
	if depth > 16 {
		return fmt.Errorf("message nesting exceeds limit")
	}
	token, err := decoder.Token()
	if err != nil {
		return err
	}
	if number, ok := token.(json.Number); ok && strings.ContainsAny(string(number), ".eE") {
		if _, err := strconv.ParseFloat(string(number), 64); err != nil {
			return fmt.Errorf("non-finite JSON number")
		}
	}
	delimiter, ok := token.(json.Delim)
	if !ok {
		return nil
	}
	switch delimiter {
	case '{':
		seen := make(map[string]bool)
		for decoder.More() {
			token, err := decoder.Token()
			if err != nil {
				return err
			}
			key, ok := token.(string)
			if !ok || (canonical && !canonicalKey(key)) || seen[key] {
				return fmt.Errorf("duplicate or noncanonical JSON field name")
			}
			seen[key] = true
			if err := checkKeys(decoder, depth+1, canonical); err != nil {
				return err
			}
		}
	case '[':
		for decoder.More() {
			if err := checkKeys(decoder, depth+1, canonical); err != nil {
				return err
			}
		}
	default:
		return fmt.Errorf("unexpected JSON delimiter")
	}
	_, err = decoder.Token()
	return err
}

func canonicalKey(key string) bool {
	if key == "" {
		return false
	}
	for _, character := range key {
		if (character < 'a' || character > 'z') && (character < '0' || character > '9') && character != '_' {
			return false
		}
	}
	return true
}
