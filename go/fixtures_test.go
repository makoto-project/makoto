package makoto

import (
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

const generatedRoot = "../demos/v0.2-end-to-end/generated"

func mustRead(t *testing.T, path string) []byte {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func assertSemanticRoundTrip(t *testing.T, original []byte, document any) {
	t.Helper()
	encoded, err := json.Marshal(document)
	if err != nil {
		t.Fatalf("marshal round trip: %v", err)
	}
	want, err := Canonicalize(original)
	if err != nil {
		t.Fatalf("canonicalize original: %v", err)
	}
	got, err := Canonicalize(encoded)
	if err != nil {
		t.Fatalf("canonicalize encoded: %v", err)
	}
	if !bytes.Equal(got, want) {
		t.Fatalf("semantic round trip changed document\n got: %s\nwant: %s", got, want)
	}
}

func assertCanonicalTypedBytes(t *testing.T, original []byte, document any) {
	t.Helper()
	want, err := Canonicalize(original)
	if err != nil {
		t.Fatalf("canonicalize original: %v", err)
	}
	got, err := CanonicalJSON(document)
	if err != nil {
		t.Fatalf("canonicalize typed document: %v", err)
	}
	if !bytes.Equal(got, want) {
		t.Fatalf("typed canonical bytes differ\n got: %s\nwant: %s", got, want)
	}
}

func TestPositiveBundlePolicyAndReports(t *testing.T) {
	bundlePath := filepath.Join(generatedRoot, "positive-bundle", "bundle.json")
	bundleRaw := mustRead(t, bundlePath)
	bundle, err := DecodeBundle(bytes.NewReader(bundleRaw))
	if err != nil {
		t.Fatal(err)
	}
	if err := bundle.Validate(); err != nil {
		t.Fatalf("validate positive bundle: %v", err)
	}
	assertSemanticRoundTrip(t, bundleRaw, bundle)

	policyMatches, err := filepath.Glob(filepath.Join(generatedRoot, "receiver", "*policy.json"))
	if err != nil {
		t.Fatal(err)
	}
	for _, policyPath := range policyMatches {
		policyPath := policyPath
		t.Run(filepath.Base(policyPath), func(t *testing.T) {
			raw := mustRead(t, policyPath)
			policy, decodeErr := DecodeTrustPolicy(bytes.NewReader(raw))
			if decodeErr != nil {
				t.Fatal(decodeErr)
			}
			if err := policy.Validate(); err != nil {
				t.Fatalf("validate policy: %v", err)
			}
			assertSemanticRoundTrip(t, raw, policy)
		})
	}

	reports, err := filepath.Glob(filepath.Join(generatedRoot, "reports", "*.json"))
	if err != nil {
		t.Fatal(err)
	}
	for _, reportPath := range reports {
		reportPath := reportPath
		t.Run(filepath.Base(filepath.Dir(reportPath))+"-"+filepath.Base(reportPath), func(t *testing.T) {
			raw := mustRead(t, reportPath)
			report, decodeErr := DecodeVerificationReport(bytes.NewReader(raw))
			if decodeErr != nil {
				t.Fatal(decodeErr)
			}
			if err := report.Validate(); err != nil {
				t.Fatalf("validate report: %v", err)
			}
			assertSemanticRoundTrip(t, raw, report)
		})
	}
}

func TestNegativeExpectedOutcomesAreDenials(t *testing.T) {
	matches, err := filepath.Glob("../testdata/v0.2/negative/*/expected-report.json")
	if err != nil {
		t.Fatal(err)
	}
	if len(matches) != 7 {
		t.Fatalf("found %d negative expectations, want 7", len(matches))
	}
	for _, expectationPath := range matches {
		expectationPath := expectationPath
		t.Run(filepath.Base(filepath.Dir(expectationPath)), func(t *testing.T) {
			var expectation struct {
				Decision           string   `json:"decision"`
				PrimaryError       string   `json:"primaryError"`
				RequiredErrorCodes []string `json:"requiredErrorCodes"`
			}
			if err := json.Unmarshal(mustRead(t, expectationPath), &expectation); err != nil {
				t.Fatal(err)
			}
			if expectation.Decision != "deny" {
				t.Fatalf("decision = %q, want deny", expectation.Decision)
			}
			if expectation.PrimaryError == "" || len(expectation.RequiredErrorCodes) == 0 {
				t.Fatal("negative expectation does not identify its failure")
			}
		})
	}
}

func loadPolicyKeys(t *testing.T) map[string][]byte {
	t.Helper()
	raw := mustRead(t, filepath.Join(generatedRoot, "receiver", "policy.json"))
	policy, err := DecodeTrustPolicy(bytes.NewReader(raw))
	if err != nil {
		t.Fatal(err)
	}
	keys := make(map[string][]byte, len(policy.Keys))
	for keyID, key := range policy.Keys {
		spki, err := base64.StdEncoding.DecodeString(key.PublicKey)
		if err != nil {
			t.Fatalf("decode policy key %s: %v", keyID, err)
		}
		keys[keyID] = spki
	}
	return keys
}

func demoSigningKeys(t *testing.T) map[string]ed25519.PrivateKey {
	t.Helper()
	keys := make(map[string]ed25519.PrivateKey, 4)
	for seedByte := byte(1); seedByte <= 4; seedByte++ {
		key, err := SigningKeyFromSeed(bytes.Repeat([]byte{seedByte}, ed25519.SeedSize))
		if err != nil {
			t.Fatal(err)
		}
		spki, err := PublicSPKI(key.Public().(ed25519.PublicKey))
		if err != nil {
			t.Fatal(err)
		}
		keyID, err := KeyIDFromSPKI(spki)
		if err != nil {
			t.Fatal(err)
		}
		keys[keyID] = key
	}
	return keys
}

func TestPositiveEnvelopesStatementsAndHandoff(t *testing.T) {
	keys := loadPolicyKeys(t)
	signingKeys := demoSigningKeys(t)
	patterns := []string{
		filepath.Join(generatedRoot, "positive-bundle", "manifest.dsse.json"),
		filepath.Join(generatedRoot, "positive-bundle", "attestations", "*.dsse.json"),
	}
	var paths []string
	for _, pattern := range patterns {
		matches, err := filepath.Glob(pattern)
		if err != nil {
			t.Fatal(err)
		}
		paths = append(paths, matches...)
	}
	sort.Strings(paths)
	if len(paths) != 4 {
		t.Fatalf("found %d envelope fixtures, want 4", len(paths))
	}
	for _, envelopePath := range paths {
		envelopePath := envelopePath
		t.Run(filepath.Base(envelopePath), func(t *testing.T) {
			raw := mustRead(t, envelopePath)
			envelope, err := DecodeEnvelope(bytes.NewReader(raw))
			if err != nil {
				t.Fatal(err)
			}
			if err := envelope.Validate(); err != nil {
				t.Fatalf("validate envelope: %v", err)
			}
			assertSemanticRoundTrip(t, raw, envelope)
			for index, signature := range envelope.Signatures {
				spki, ok := keys[signature.KeyID]
				if !ok {
					t.Fatalf("fixture key %s is absent from policy", signature.KeyID)
				}
				if err := VerifyEnvelopeSignature(envelope, spki, index); err != nil {
					t.Fatalf("verify signature %d: %v", index, err)
				}
			}
			payload, err := envelope.PayloadBytes()
			if err != nil {
				t.Fatal(err)
			}
			canonical, err := Canonicalize(payload)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(payload, canonical) {
				t.Fatal("signed payload is not byte-identical RFC 8785 JSON")
			}
			if len(envelope.Signatures) == 1 {
				key, ok := signingKeys[envelope.Signatures[0].KeyID]
				if !ok {
					t.Fatal("fixture does not use a deterministic demo signing key")
				}
				resigned, err := SignEnvelope(envelope.PayloadType, payload, key)
				if err != nil {
					t.Fatal(err)
				}
				assertSemanticRoundTrip(t, raw, resigned)
			}
			switch envelope.PayloadType {
			case HandoffPayloadType:
				manifest, err := DecodeHandoffManifest(bytes.NewReader(payload))
				if err != nil {
					t.Fatal(err)
				}
				if err := manifest.Validate(); err != nil {
					t.Fatalf("validate handoff: %v", err)
				}
				assertSemanticRoundTrip(t, payload, manifest)
				assertCanonicalTypedBytes(t, payload, manifest)
			case StatementPayloadType:
				statement, err := DecodeStatement(bytes.NewReader(payload))
				if err != nil {
					t.Fatal(err)
				}
				if err := statement.Validate(); err != nil {
					t.Fatalf("validate statement: %v", err)
				}
				assertSemanticRoundTrip(t, payload, statement)
				assertCanonicalTypedBytes(t, payload, statement)
				switch statement.PredicateType {
				case OriginPredicateType:
					predicate, err := DecodeOriginPredicate(bytes.NewReader(statement.Predicate))
					if err != nil {
						t.Fatal(err)
					}
					if err := predicate.Validate(); err != nil {
						t.Fatalf("validate origin predicate: %v", err)
					}
					assertSemanticRoundTrip(t, statement.Predicate, predicate)
					assertCanonicalTypedBytes(t, statement.Predicate, predicate)
				case TransformPredicateType:
					predicate, err := DecodeTransformPredicate(bytes.NewReader(statement.Predicate))
					if err != nil {
						t.Fatal(err)
					}
					if err := predicate.Validate(); err != nil {
						t.Fatalf("validate transform predicate: %v", err)
					}
					assertSemanticRoundTrip(t, statement.Predicate, predicate)
					assertCanonicalTypedBytes(t, statement.Predicate, predicate)
				default:
					t.Fatalf("unexpected predicate type %q", statement.PredicateType)
				}
			default:
				t.Fatalf("unexpected payload type %q", envelope.PayloadType)
			}
		})
	}
}

func TestDatasetManifestFromRealArtifact(t *testing.T) {
	artifact := mustRead(t, filepath.Join(generatedRoot, "data", "customers.public.json"))
	size := int64(len(artifact))
	manifest := DatasetManifest{
		Version: Version,
		Entries: []DatasetEntry{{
			Name:      "customers.public.json",
			Digest:    DigestBytes(artifact),
			Size:      &size,
			MediaType: "application/json",
		}},
	}
	if err := manifest.Validate(); err != nil {
		t.Fatalf("validate dataset manifest: %v", err)
	}
	encoded, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := DecodeDatasetManifest(bytes.NewReader(encoded))
	if err != nil {
		t.Fatal(err)
	}
	assertSemanticRoundTrip(t, encoded, decoded)
}

func TestUnknownAndExtensionFieldsSurviveRoundTrip(t *testing.T) {
	raw := []byte(`{
  "version":"0.2",
  "manifest":"manifest.dsse.json",
  "attestations":[{
    "statementDigest":{
      "sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "urn:example:digest-future":1
    },
    "path":"attestations/a.dsse.json",
    "urn:example:attestation-future":true
  }],
  "artifacts":[],
  "urn:example:future":{"enabled":true}
}`)
	bundle, err := DecodeBundle(bytes.NewReader(raw))
	if err != nil {
		t.Fatal(err)
	}
	assertSemanticRoundTrip(t, raw, bundle)
	if err := bundle.Validate(); err == nil {
		t.Fatal("schema accepted an unknown core bundle field")
	}

	predicateRaw := []byte(`{
  "schemaVersion":"0.2",
  "event":{"id":"urn:uuid:11111111-1111-4111-8111-111111111111","occurredAt":"2026-09-16T16:00:00Z"},
  "source":{"kind":"urn:example:source"},
  "extensions":{"urn:example:future":{"enabled":true}}
}`)
	predicate, err := DecodeOriginPredicate(bytes.NewReader(predicateRaw))
	if err != nil {
		t.Fatal(err)
	}
	if err := predicate.Validate(); err != nil {
		t.Fatalf("validate extension-bearing predicate: %v", err)
	}
	assertSemanticRoundTrip(t, predicateRaw, predicate)
}

func TestSchemaAndSignatureFailuresAreRejected(t *testing.T) {
	bundleRaw := mustRead(t, filepath.Join(generatedRoot, "positive-bundle", "bundle.json"))
	var invalidBundle map[string]any
	if err := json.Unmarshal(bundleRaw, &invalidBundle); err != nil {
		t.Fatal(err)
	}
	delete(invalidBundle, "version")
	invalidRaw, err := json.Marshal(invalidBundle)
	if err != nil {
		t.Fatal(err)
	}
	if err := ValidateJSON(KindBundle, invalidRaw); err == nil {
		t.Fatal("bundle without required version passed schema validation")
	}

	keys := loadPolicyKeys(t)
	envelopePath := filepath.Join(
		generatedRoot,
		"positive-bundle",
		"attestations",
		"1f28b72bcd4c1e9b7df71403ac6bb1670c2f2b09628ca6d76a2fa384db9a0848.dsse.json",
	)
	for _, fixtureName := range []string{"edited-signed-metadata", "rewired-step"} {
		t.Run(fixtureName, func(t *testing.T) {
			reportRaw := mustRead(t, filepath.Join(
				"../testdata/v0.2/negative",
				fixtureName,
				"expected-report.json",
			))
			if !bytes.Contains(reportRaw, []byte(`"primaryError": "E_SIGNATURE_INVALID"`)) {
				t.Fatal("negative fixture is not a signature-failure report")
			}
			envelope, err := DecodeEnvelope(bytes.NewReader(mustRead(t, envelopePath)))
			if err != nil {
				t.Fatal(err)
			}
			signature, err := base64.StdEncoding.DecodeString(envelope.Signatures[0].Sig)
			if err != nil {
				t.Fatal(err)
			}
			signature[0] ^= 1
			envelope.Signatures[0].Sig = base64.StdEncoding.EncodeToString(signature)
			spki := keys[envelope.Signatures[0].KeyID]
			if err := VerifyEnvelopeSignature(envelope, spki, 0); err == nil {
				t.Fatal("tampered signature passed verification")
			}
		})
	}
}

func TestEmbeddedSchemasMatchRepository(t *testing.T) {
	matches, err := filepath.Glob("../schemas/v0.2/*.json")
	if err != nil {
		t.Fatal(err)
	}
	if len(matches) == 0 {
		t.Fatal("no authoritative schemas found")
	}
	for _, sourcePath := range matches {
		name := filepath.Base(sourcePath)
		t.Run(name, func(t *testing.T) {
			source := mustRead(t, sourcePath)
			embedded, err := EmbeddedSchema(name)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(embedded, source) {
				t.Fatalf("embedded %s differs from schemas/v0.2/%s", name, name)
			}
		})
	}
}

func ExampleDigestBytes() {
	digest := DigestBytes([]byte("Makoto"))
	fmt.Println(len(digest.SHA256), strings.ToLower(digest.SHA256) == digest.SHA256)
	// Output: 64 true
}
