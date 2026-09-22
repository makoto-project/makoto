package makoto

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"regexp"
	"sort"
	"strconv"

	"filippo.io/edwards25519"
)

var payloadTypePattern = regexp.MustCompile(
	`^[a-z0-9][a-z0-9!#$&^_.+\-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+\-]{0,126}$`,
)

var keyIDPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

var supportedPayloadTypes = map[string]struct{}{
	StatementPayloadType: {},
	HandoffPayloadType:   {},
}

var ed25519Order = [32]byte{
	0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58,
	0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14,
	0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
	0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10,
}

// PAE returns the DSSE v1 pre-authentication encoding.
func PAE(payloadType string, payload []byte) []byte {
	return bytes.Join(
		[][]byte{
			[]byte("DSSEv1"),
			[]byte(strconv.Itoa(len([]byte(payloadType)))),
			[]byte(payloadType),
			[]byte(strconv.Itoa(len(payload))),
			payload,
		},
		[]byte(" "),
	)
}

// ValidatePayloadType checks the Makoto v0.2 DSSE media-type grammar and
// allowlist.
func ValidatePayloadType(payloadType string) error {
	if !payloadTypePattern.MatchString(payloadType) {
		return fmt.Errorf("payload type is not a lowercase parameter-free media type")
	}
	if _, ok := supportedPayloadTypes[payloadType]; !ok {
		return fmt.Errorf("payload type is not supported by Makoto v0.2")
	}
	return nil
}

func canonicalBase64Decode(value string, expectedLength int) ([]byte, error) {
	decoded, err := base64.StdEncoding.DecodeString(value)
	if err != nil || base64.StdEncoding.EncodeToString(decoded) != value {
		return nil, fmt.Errorf("value is not canonical RFC 4648 standard base64")
	}
	if expectedLength >= 0 && len(decoded) != expectedLength {
		return nil, fmt.Errorf("decoded value must be exactly %d bytes", expectedLength)
	}
	return decoded, nil
}

// GenerateSigningKey creates a new Ed25519 private key.
func GenerateSigningKey() (ed25519.PrivateKey, error) {
	_, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, fmt.Errorf("generate Ed25519 key: %w", err)
	}
	return privateKey, nil
}

// SigningKeyFromSeed creates an Ed25519 private key from a 32-byte seed.
func SigningKeyFromSeed(seed []byte) (ed25519.PrivateKey, error) {
	if len(seed) != ed25519.SeedSize {
		return nil, fmt.Errorf("Ed25519 seed must be exactly 32 bytes")
	}
	return ed25519.NewKeyFromSeed(seed), nil
}

// PublicSPKI returns canonical DER SubjectPublicKeyInfo for an Ed25519 key.
func PublicSPKI(publicKey ed25519.PublicKey) ([]byte, error) {
	if len(publicKey) != ed25519.PublicKeySize {
		return nil, fmt.Errorf("Ed25519 public key must be exactly 32 bytes")
	}
	der, err := x509.MarshalPKIXPublicKey(publicKey)
	if err != nil {
		return nil, fmt.Errorf("marshal Ed25519 SubjectPublicKeyInfo: %w", err)
	}
	return der, nil
}

// ParsePublicSPKI parses canonical DER Ed25519 SubjectPublicKeyInfo.
func ParsePublicSPKI(spki []byte) (ed25519.PublicKey, error) {
	parsed, err := x509.ParsePKIXPublicKey(spki)
	if err != nil {
		return nil, fmt.Errorf("public key is not SubjectPublicKeyInfo DER: %w", err)
	}
	publicKey, ok := parsed.(ed25519.PublicKey)
	if !ok {
		return nil, fmt.Errorf("public key is not Ed25519")
	}
	canonical, err := PublicSPKI(publicKey)
	if err != nil || !bytes.Equal(canonical, spki) {
		return nil, fmt.Errorf("public key is not canonical Ed25519 SubjectPublicKeyInfo")
	}
	if err := validatePrimeOrderPoint(publicKey); err != nil {
		return nil, fmt.Errorf("invalid Ed25519 public key: %w", err)
	}
	return publicKey, nil
}

func validatePrimeOrderPoint(encoded []byte) error {
	point, err := new(edwards25519.Point).SetBytes(encoded)
	if err != nil {
		return fmt.Errorf("point is not on the Edwards25519 curve: %w", err)
	}
	if !bytes.Equal(point.Bytes(), encoded) {
		return fmt.Errorf("point encoding is noncanonical")
	}
	identity := edwards25519.NewIdentityPoint()
	if point.Equal(identity) == 1 {
		return fmt.Errorf("identity Edwards25519 point is forbidden")
	}
	result := edwards25519.NewIdentityPoint()
	addend := new(edwards25519.Point).Set(point)
	for _, scalarByte := range ed25519Order {
		for bit := 0; bit < 8; bit++ {
			if scalarByte&(1<<bit) != 0 {
				result.Add(result, addend)
			}
			addend.Double(addend)
		}
	}
	if result.Equal(identity) != 1 {
		return fmt.Errorf("Edwards25519 point is not prime order")
	}
	return nil
}

// KeyIDFromSPKI returns the Makoto v0.2 key ID for canonical Ed25519 SPKI.
func KeyIDFromSPKI(spki []byte) (string, error) {
	if _, err := ParsePublicSPKI(spki); err != nil {
		return "", err
	}
	sum := sha256.Sum256(spki)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

// SignEnvelope signs exact payload bytes with distinct Ed25519 keys. Signature
// order is canonical by key ID.
func SignEnvelope(
	payloadType string,
	payload []byte,
	privateKeys ...ed25519.PrivateKey,
) (*Envelope, error) {
	if err := ValidatePayloadType(payloadType); err != nil {
		return nil, err
	}
	if len(privateKeys) == 0 {
		return nil, fmt.Errorf("at least one signing key is required")
	}
	message := PAE(payloadType, payload)
	signatures := make([]Signature, 0, len(privateKeys))
	seen := make(map[string]struct{}, len(privateKeys))
	for _, privateKey := range privateKeys {
		if len(privateKey) != ed25519.PrivateKeySize {
			return nil, fmt.Errorf("Ed25519 private key must be exactly 64 bytes")
		}
		publicKey := privateKey.Public().(ed25519.PublicKey)
		spki, err := PublicSPKI(publicKey)
		if err != nil {
			return nil, err
		}
		keyID, err := KeyIDFromSPKI(spki)
		if err != nil {
			return nil, err
		}
		if _, duplicate := seen[keyID]; duplicate {
			return nil, fmt.Errorf("signing key IDs must be unique")
		}
		seen[keyID] = struct{}{}
		signatures = append(signatures, Signature{
			KeyID: keyID,
			Sig:   base64.StdEncoding.EncodeToString(ed25519.Sign(privateKey, message)),
		})
	}
	sort.Slice(signatures, func(i, j int) bool {
		return signatures[i].KeyID < signatures[j].KeyID
	})
	return &Envelope{
		PayloadType: payloadType,
		Payload:     base64.StdEncoding.EncodeToString(payload),
		Signatures:  signatures,
	}, nil
}

func scalarIsCanonical(scalar []byte) bool {
	for index := len(ed25519Order) - 1; index >= 0; index-- {
		if scalar[index] < ed25519Order[index] {
			return true
		}
		if scalar[index] > ed25519Order[index] {
			return false
		}
	}
	return false
}

// VerifyEnvelopeSignature verifies one selected Ed25519 signature over the
// envelope's exact payload bytes.
func VerifyEnvelopeSignature(
	envelope *Envelope,
	publicSPKI []byte,
	signatureIndex int,
) error {
	if envelope == nil {
		return fmt.Errorf("envelope is nil")
	}
	if err := ValidatePayloadType(envelope.PayloadType); err != nil {
		return err
	}
	payload, err := canonicalBase64Decode(envelope.Payload, -1)
	if err != nil {
		return fmt.Errorf("decode payload: %w", err)
	}
	if signatureIndex < 0 || signatureIndex >= len(envelope.Signatures) {
		return fmt.Errorf("signature index is unavailable")
	}
	seen := make(map[string]struct{}, len(envelope.Signatures))
	decodedSignatures := make([][]byte, len(envelope.Signatures))
	for index, signature := range envelope.Signatures {
		if len(signature.UnknownFields) != 0 {
			return fmt.Errorf("signature entry is malformed")
		}
		if !keyIDPattern.MatchString(signature.KeyID) {
			return fmt.Errorf("signature key ID is malformed")
		}
		if _, duplicate := seen[signature.KeyID]; duplicate {
			return fmt.Errorf("signature key IDs must be unique")
		}
		seen[signature.KeyID] = struct{}{}
		decoded, decodeErr := canonicalBase64Decode(signature.Sig, ed25519.SignatureSize)
		if decodeErr != nil {
			return fmt.Errorf("decode signature: %w", decodeErr)
		}
		decodedSignatures[index] = decoded
	}
	publicKey, err := ParsePublicSPKI(publicSPKI)
	if err != nil {
		return err
	}
	expectedKeyID, err := KeyIDFromSPKI(publicSPKI)
	if err != nil {
		return err
	}
	entry := envelope.Signatures[signatureIndex]
	if entry.KeyID != expectedKeyID {
		return fmt.Errorf("signature key ID does not match the supplied public key")
	}
	signature := decodedSignatures[signatureIndex]
	if err := validatePrimeOrderPoint(signature[:32]); err != nil {
		return fmt.Errorf("invalid Ed25519 signature point: %w", err)
	}
	if !scalarIsCanonical(signature[32:]) {
		return fmt.Errorf("noncanonical Ed25519 scalar")
	}
	if !ed25519.Verify(publicKey, PAE(envelope.PayloadType, payload), signature) {
		return fmt.Errorf("Ed25519 signature verification failed")
	}
	return nil
}

// PayloadBytes decodes the envelope's canonical base64 payload.
func (e Envelope) PayloadBytes() ([]byte, error) {
	return canonicalBase64Decode(e.Payload, -1)
}
