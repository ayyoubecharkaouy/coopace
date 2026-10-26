package protocol

import (
	"encoding/binary"
	"fmt"
	"io"
)

// ReadFrame checks the four-byte length before allocating the payload.
func ReadFrame(reader io.Reader) ([]byte, error) {
	var prefix [4]byte
	if _, err := io.ReadFull(reader, prefix[:]); err != nil {
		return nil, err
	}
	size := binary.BigEndian.Uint32(prefix[:])
	if size == 0 || size > MaxMessageBytes {
		return nil, fmt.Errorf("invalid frame size")
	}
	data := make([]byte, size)
	_, err := io.ReadFull(reader, data)
	return data, err
}

func WriteFrame(writer io.Writer, message Message) error {
	data, err := Encode(message)
	if err != nil {
		return err
	}
	var prefix [4]byte
	binary.BigEndian.PutUint32(prefix[:], uint32(len(data)))
	for _, part := range [][]byte{prefix[:], data} {
		for len(part) > 0 {
			n, err := writer.Write(part)
			if err != nil {
				return err
			}
			if n <= 0 || n > len(part) {
				return io.ErrShortWrite
			}
			part = part[n:]
		}
	}
	return nil
}
