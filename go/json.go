package makoto

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
)

func decodeOne(r io.Reader, target any) error {
	decoder := json.NewDecoder(r)
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode JSON: %w", err)
	}
	var trailing json.RawMessage
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return fmt.Errorf("decode JSON: multiple values")
		}
		return fmt.Errorf("decode JSON trailing data: %w", err)
	}
	return nil
}

func unmarshalWithUnknown(
	data []byte,
	target any,
	known []string,
	unknown *map[string]json.RawMessage,
) error {
	if err := json.Unmarshal(data, target); err != nil {
		return err
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return err
	}
	for _, name := range known {
		delete(fields, name)
	}
	if len(fields) == 0 {
		*unknown = nil
	} else {
		*unknown = fields
	}
	return nil
}

func marshalWithUnknown(
	known any,
	reserved []string,
	unknown map[string]json.RawMessage,
) ([]byte, error) {
	data, err := json.Marshal(known)
	if err != nil {
		return nil, err
	}
	if len(unknown) == 0 {
		return data, nil
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return nil, err
	}
	reservedSet := make(map[string]struct{}, len(reserved))
	for _, name := range reserved {
		reservedSet[name] = struct{}{}
	}
	for name, value := range unknown {
		if _, exists := reservedSet[name]; exists {
			continue
		}
		fields[name] = bytes.Clone(value)
	}
	return json.Marshal(fields)
}

// Encode writes one JSON document followed by a newline.
func Encode(w io.Writer, document any) error {
	encoder := json.NewEncoder(w)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(document); err != nil {
		return fmt.Errorf("encode JSON: %w", err)
	}
	return nil
}
