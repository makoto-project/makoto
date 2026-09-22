package makoto

import (
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"testing"
)

func TestDSSESignVerifyAndPAE(t *testing.T) {
	seed := make([]byte, ed25519.SeedSize)
	for index := range seed {
		seed[index] = byte(index)
	}
	key, err := SigningKeyFromSeed(seed)
	if err != nil {
		t.Fatal(err)
	}
	payload := []byte(`{"source":"exact bytes"}`)
	envelope, err := SignEnvelope(StatementPayloadType, payload, key)
	if err != nil {
		t.Fatal(err)
	}
	spki, err := PublicSPKI(key.Public().(ed25519.PublicKey))
	if err != nil {
		t.Fatal(err)
	}
	if err := VerifyEnvelopeSignature(envelope, spki, 0); err != nil {
		t.Fatalf("verify signed envelope: %v", err)
	}
	if got, want := PAE(StatementPayloadType, []byte("{}")), []byte(
		"DSSEv1 28 application/vnd.in-toto+json 2 {}",
	); !bytes.Equal(got, want) {
		t.Fatalf("PAE = %q, want %q", got, want)
	}
}

func TestDSSERejectsMutationAndDuplicateKey(t *testing.T) {
	key, err := SigningKeyFromSeed(make([]byte, ed25519.SeedSize))
	if err != nil {
		t.Fatal(err)
	}
	envelope, err := SignEnvelope(StatementPayloadType, []byte(`{"value":1}`), key)
	if err != nil {
		t.Fatal(err)
	}
	spki, err := PublicSPKI(key.Public().(ed25519.PublicKey))
	if err != nil {
		t.Fatal(err)
	}
	envelope.Payload = base64.StdEncoding.EncodeToString([]byte(`{"value":2}`))
	if err := VerifyEnvelopeSignature(envelope, spki, 0); err == nil {
		t.Fatal("payload mutation passed signature verification")
	}
	if _, err := SignEnvelope(StatementPayloadType, nil, key, key); err == nil {
		t.Fatal("duplicate signing keys were accepted")
	}
	envelope, err = SignEnvelope(StatementPayloadType, []byte("{}"), key)
	if err != nil {
		t.Fatal(err)
	}
	envelope.Signatures[0].UnknownFields = map[string]json.RawMessage{
		"future": json.RawMessage("true"),
	}
	if err := VerifyEnvelopeSignature(envelope, spki, 0); err == nil {
		t.Fatal("signature entry with an unknown field was accepted")
	}
}

func TestDSSERejectsNoncanonicalScalarAndIdentity(t *testing.T) {
	key, err := SigningKeyFromSeed(make([]byte, ed25519.SeedSize))
	if err != nil {
		t.Fatal(err)
	}
	envelope, err := SignEnvelope(StatementPayloadType, []byte("{}"), key)
	if err != nil {
		t.Fatal(err)
	}
	spki, err := PublicSPKI(key.Public().(ed25519.PublicKey))
	if err != nil {
		t.Fatal(err)
	}
	signature, err := base64.StdEncoding.DecodeString(envelope.Signatures[0].Sig)
	if err != nil {
		t.Fatal(err)
	}
	copy(signature[32:], ed25519Order[:])
	envelope.Signatures[0].Sig = base64.StdEncoding.EncodeToString(signature)
	if err := VerifyEnvelopeSignature(envelope, spki, 0); err == nil {
		t.Fatal("noncanonical Ed25519 scalar was accepted")
	}
}

func TestDSSERejectsNonPrimeOrderPoints(t *testing.T) {
	key, err := SigningKeyFromSeed(make([]byte, ed25519.SeedSize))
	if err != nil {
		t.Fatal(err)
	}
	envelope, err := SignEnvelope(StatementPayloadType, []byte("{}"), key)
	if err != nil {
		t.Fatal(err)
	}
	spki, err := PublicSPKI(key.Public().(ed25519.PublicKey))
	if err != nil {
		t.Fatal(err)
	}
	signature, err := base64.StdEncoding.DecodeString(envelope.Signatures[0].Sig)
	if err != nil {
		t.Fatal(err)
	}
	orderTwoPoint := bytes.Repeat([]byte{0xff}, 32)
	orderTwoPoint[0] = 0xec
	orderTwoPoint[31] = 0x7f
	copy(signature[:32], orderTwoPoint)
	envelope.Signatures[0].Sig = base64.StdEncoding.EncodeToString(signature)
	if err := VerifyEnvelopeSignature(envelope, spki, 0); err == nil {
		t.Fatal("non-prime-order signature point was accepted")
	}

	badSPKI, err := PublicSPKI(ed25519.PublicKey(orderTwoPoint))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ParsePublicSPKI(badSPKI); err == nil {
		t.Fatal("non-prime-order public key was accepted")
	}
}
