package protocol

import (
	"bytes"
	"encoding/json"
	"github.com/ayyoubecharkaouy/coopace/internal/strictjson"
)

func Decode(data []byte) (Message, error) {
	if err := strictjson.Check(data, MaxMessageBytes); err != nil {
		return Message{}, err
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
