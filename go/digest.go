package makoto

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
)

// SHA256Bytes returns the lowercase hexadecimal SHA-256 digest of exact bytes.
func SHA256Bytes(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

// SHA256Reader streams exact bytes into SHA-256.
func SHA256Reader(r io.Reader) (string, error) {
	digest := sha256.New()
	if _, err := io.Copy(digest, r); err != nil {
		return "", fmt.Errorf("hash bytes: %w", err)
	}
	return hex.EncodeToString(digest.Sum(nil)), nil
}

// NewDigest validates and wraps a lowercase hexadecimal SHA-256 digest.
func NewDigest(hexDigest string) (Digest, error) {
	if len(hexDigest) != sha256.Size*2 {
		return Digest{}, fmt.Errorf("SHA-256 digest must be 64 lowercase hexadecimal characters")
	}
	decoded, err := hex.DecodeString(hexDigest)
	if err != nil || hex.EncodeToString(decoded) != hexDigest {
		return Digest{}, fmt.Errorf("SHA-256 digest must be 64 lowercase hexadecimal characters")
	}
	return Digest{SHA256: hexDigest}, nil
}

// DigestBytes hashes exact bytes and returns a Makoto digest object.
func DigestBytes(data []byte) Digest {
	return Digest{SHA256: SHA256Bytes(data)}
}
