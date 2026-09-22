package makoto

import (
	"encoding/json"
	"fmt"

	"github.com/gowebpki/jcs"
)

// Canonicalize transforms one JSON value to RFC 8785 JSON Canonicalization
// Scheme bytes.
func Canonicalize(data []byte) ([]byte, error) {
	canonical, err := jcs.Transform(data)
	if err != nil {
		return nil, fmt.Errorf("canonicalize RFC 8785 JSON: %w", err)
	}
	return canonical, nil
}

// CanonicalJSON marshals value and returns its RFC 8785 representation.
func CanonicalJSON(value any) ([]byte, error) {
	data, err := json.Marshal(value)
	if err != nil {
		return nil, fmt.Errorf("marshal value for canonicalization: %w", err)
	}
	return Canonicalize(data)
}
