package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"testing"

	"github.com/gowebpki/jcs"
)

func root() string {
	return filepath.Clean(filepath.Join("..", "..", ".."))
}

func fixtureEnvelopes(t *testing.T) []string {
	t.Helper()
	bundle := filepath.Join(root(), "demos", "v0.2-end-to-end", "generated", "positive-bundle")
	paths, err := filepath.Glob(filepath.Join(bundle, "attestations", "*.dsse.json"))
	if err != nil {
		t.Fatal(err)
	}
	paths = append(paths, filepath.Join(bundle, "manifest.dsse.json"))
	sort.Strings(paths)
	if len(paths) != 4 {
		t.Fatalf("found %d envelopes, want 4", len(paths))
	}
	return paths
}

func readJSON(t *testing.T, path string) ([]byte, map[string]any) {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var value map[string]any
	if err := json.Unmarshal(raw, &value); err != nil {
		t.Fatal(err)
	}
	return raw, value
}

func policyKeys(t *testing.T) map[string]ed25519.PublicKey {
	t.Helper()
	path := filepath.Join(root(), "demos", "v0.2-end-to-end", "generated", "receiver", "policy.json")
	_, policy := readJSON(t, path)
	result := make(map[string]ed25519.PublicKey)
	for id, rawKey := range policy["keys"].(map[string]any) {
		encoded := rawKey.(map[string]any)["publicKey"].(string)
		spki, err := base64.StdEncoding.DecodeString(encoded)
		if err != nil {
			t.Fatal(err)
		}
		parsed, err := x509.ParsePKIXPublicKey(spki)
		if err != nil {
			t.Fatal(err)
		}
		publicKey, ok := parsed.(ed25519.PublicKey)
		if !ok {
			t.Fatalf("policy key %s is not Ed25519", id)
		}
		result[id] = publicKey
	}
	return result
}

func TestVerifyAndReSignFixtureEnvelopes(t *testing.T) {
	publicKeys := policyKeys(t)
	privateKeys := make(map[string]ed25519.PrivateKey)
	for seedByte := byte(1); seedByte <= 4; seedByte++ {
		privateKey := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{seedByte}, ed25519.SeedSize))
		id, err := keyID(privateKey.Public().(ed25519.PublicKey))
		if err != nil {
			t.Fatal(err)
		}
		privateKeys[id] = privateKey
	}
	for _, path := range fixtureEnvelopes(t) {
		path := path
		t.Run(filepath.Base(path), func(t *testing.T) {
			raw, envelope := readJSON(t, path)
			if err := verifyEnvelope(envelope, publicKeys); err != nil {
				t.Fatal(err)
			}
			payload, err := base64.StdEncoding.DecodeString(envelope["payload"].(string))
			if err != nil {
				t.Fatal(err)
			}
			canonicalPayload, err := jcs.Transform(payload)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(payload, canonicalPayload) {
				t.Fatal("signed fixture payload is not byte-identical RFC 8785 JSON")
			}
			signature := envelope["signatures"].([]any)[0].(map[string]any)
			privateKey, ok := privateKeys[signature["keyid"].(string)]
			if !ok {
				t.Fatal("fixture key does not match a deterministic demo seed")
			}
			resigned, err := signEnvelope(envelope["payloadType"].(string), payload, privateKey)
			if err != nil {
				t.Fatal(err)
			}
			resignedRaw, err := json.Marshal(resigned)
			if err != nil {
				t.Fatal(err)
			}
			want, err := jcs.Transform(raw)
			if err != nil {
				t.Fatal(err)
			}
			got, err := jcs.Transform(resignedRaw)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(got, want) {
				t.Fatal("re-signed envelope differs from checked-in fixture")
			}
		})
	}
}

func TestSignatureFailuresNamedByNegativeFixtures(t *testing.T) {
	publicKeys := policyKeys(t)
	envelopePath := fixtureEnvelopes(t)[0]
	for _, name := range []string{"edited-signed-metadata", "rewired-step"} {
		name := name
		t.Run(name, func(t *testing.T) {
			expectationPath := filepath.Join(root(), "testdata", "v0.2", "negative", name, "expected-report.json")
			_, expectation := readJSON(t, expectationPath)
			codes := expectation["requiredErrorCodes"].([]any)
			found := false
			for _, code := range codes {
				found = found || code == "E_SIGNATURE_INVALID"
			}
			if !found {
				t.Fatal("negative fixture does not require E_SIGNATURE_INVALID")
			}
			_, envelope := readJSON(t, envelopePath)
			payload, err := base64.StdEncoding.DecodeString(envelope["payload"].(string))
			if err != nil {
				t.Fatal(err)
			}
			payload = append(payload, '\n')
			envelope["payload"] = base64.StdEncoding.EncodeToString(payload)
			if err := verifyEnvelope(envelope, publicKeys); err == nil {
				t.Fatal("mutated signed payload passed Ed25519 verification")
			}
		})
	}
}
