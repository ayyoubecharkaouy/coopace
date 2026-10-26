package protocol

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"unicode/utf8"
)

func Decode(data []byte) (Message, error) {
	if len(data) == 0 || len(data) > MaxMessageBytes || !utf8.Valid(data) {
		return Message{}, fmt.Errorf("invalid message size or UTF-8 encoding")
	}
	// encoding/json otherwise accepts duplicate and case-insensitive field names.
	tokens := json.NewDecoder(bytes.NewReader(data))
	if err := checkKeys(tokens, 0); err != nil {
		return Message{}, err
	}
	if _, err := tokens.Token(); err != io.EOF {
		return Message{}, fmt.Errorf("trailing data after message")
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	var message Message
	if err := decoder.Decode(&message); err != nil {
		return Message{}, err
	}
	if err := message.validate(); err != nil {
		return Message{}, err
	}
	return message, nil
}

func checkKeys(decoder *json.Decoder, depth int) error {
	if depth > 16 {
		return fmt.Errorf("message nesting exceeds limit")
	}
	token, err := decoder.Token()
	if err != nil {
		return err
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
			if !ok || !canonicalKey(key) || seen[key] {
				return fmt.Errorf("duplicate or noncanonical JSON field name")
			}
			seen[key] = true
			if err := checkKeys(decoder, depth+1); err != nil {
				return err
			}
		}
	case '[':
		for decoder.More() {
			if err := checkKeys(decoder, depth+1); err != nil {
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
		if (character < 'a' || character > 'z') && character != '_' {
			return false
		}
	}
	return true
}
