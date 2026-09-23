package main

import (
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"testing"
)

func repositoryRoot() string {
	return filepath.Clean(filepath.Join("..", "..", ".."))
}

func readFixture(t *testing.T, parts ...string) []byte {
	t.Helper()
	path := filepath.Join(append([]string{repositoryRoot()}, parts...)...)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func assertGenericRoundTrip(t *testing.T, raw []byte) {
	t.Helper()
	var decoded any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatal(err)
	}
	encoded, err := json.Marshal(decoded)
	if err != nil {
		t.Fatal(err)
	}
	var roundTripped any
	if err := json.Unmarshal(encoded, &roundTripped); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(roundTripped, decoded) {
		t.Fatal("generic JSON read/write round trip changed the document")
	}
}

func TestPublishedSchemasValidatePositiveFixtures(t *testing.T) {
	schemaDir := filepath.Join(repositoryRoot(), "schemas", "v0.2")
	generated := filepath.Join(repositoryRoot(), "demos", "v0.2-end-to-end", "generated")
	pathsByKind := map[string][]string{
		"bundle": {filepath.Join(generated, "positive-bundle", "bundle.json")},
		"trust-policy": {
			filepath.Join(generated, "receiver", "policy.json"),
			filepath.Join(generated, "receiver", "attacker-known-policy.json"),
		},
	}
	reports, err := filepath.Glob(filepath.Join(generated, "reports", "*.json"))
	if err != nil {
		t.Fatal(err)
	}
	pathsByKind["verification-report"] = reports
	for kind, paths := range pathsByKind {
		for _, path := range paths {
			path := path
			t.Run(kind+"/"+filepath.Base(path), func(t *testing.T) {
				raw, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				if err := validate(schemaDir, kind, raw); err != nil {
					t.Fatal(err)
				}
				assertGenericRoundTrip(t, raw)
			})
		}
	}
}

func TestPublishedSchemasValidateEnvelopesAndPayloads(t *testing.T) {
	schemaDir := filepath.Join(repositoryRoot(), "schemas", "v0.2")
	bundle := filepath.Join(repositoryRoot(), "demos", "v0.2-end-to-end", "generated", "positive-bundle")
	paths, err := filepath.Glob(filepath.Join(bundle, "attestations", "*.dsse.json"))
	if err != nil {
		t.Fatal(err)
	}
	paths = append(paths, filepath.Join(bundle, "manifest.dsse.json"))
	sort.Strings(paths)
	if len(paths) != 4 {
		t.Fatalf("found %d envelopes, want 4", len(paths))
	}
	for _, path := range paths {
		path := path
		t.Run(filepath.Base(path), func(t *testing.T) {
			raw, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			if err := validate(schemaDir, "envelope", raw); err != nil {
				t.Fatal(err)
			}
			assertGenericRoundTrip(t, raw)
			var envelope map[string]any
			if err := json.Unmarshal(raw, &envelope); err != nil {
				t.Fatal(err)
			}
			payload, err := base64.StdEncoding.DecodeString(envelope["payload"].(string))
			if err != nil {
				t.Fatal(err)
			}
			if envelope["payloadType"] == "application/vnd.makoto.handoff.v0.2+json" {
				if err := validate(schemaDir, "handoff", payload); err != nil {
					t.Fatal(err)
				}
				assertGenericRoundTrip(t, payload)
				return
			}
			if err := validate(schemaDir, "statement", payload); err != nil {
				t.Fatal(err)
			}
			assertGenericRoundTrip(t, payload)
			var statement map[string]any
			if err := json.Unmarshal(payload, &statement); err != nil {
				t.Fatal(err)
			}
			predicate, err := json.Marshal(statement["predicate"])
			if err != nil {
				t.Fatal(err)
			}
			kind := map[string]string{
				"https://usemakoto.dev/predicate/v0.2/origin":    "origin",
				"https://usemakoto.dev/predicate/v0.2/transform": "transform",
			}[statement["predicateType"].(string)]
			if err := validate(schemaDir, kind, predicate); err != nil {
				t.Fatal(err)
			}
			assertGenericRoundTrip(t, predicate)
		})
	}
}

func TestPublishedSchemaRejectsInvalidBundle(t *testing.T) {
	raw := readFixture(t, "demos", "v0.2-end-to-end", "generated", "positive-bundle", "bundle.json")
	var bundle map[string]any
	if err := json.Unmarshal(raw, &bundle); err != nil {
		t.Fatal(err)
	}
	delete(bundle, "version")
	invalid, err := json.Marshal(bundle)
	if err != nil {
		t.Fatal(err)
	}
	schemaDir := filepath.Join(repositoryRoot(), "schemas", "v0.2")
	if err := validate(schemaDir, "bundle", invalid); err == nil {
		t.Fatal("bundle without required version passed validation")
	}
}

func TestV03SchemasValidateGenericJSON(t *testing.T) {
	schemaDir := filepath.Join(repositoryRoot(), "schemas", "v0.3")
	fixtures := map[string]string{
		"statement": filepath.Join(
			rootFixture("testdata", "v0.3", "license"),
			"positive-statement.json",
		),
		"record-declaration": filepath.Join(
			rootFixture("testdata", "v0.3", "records"),
			"byte-ranges.json",
		),
	}
	for kind, path := range fixtures {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err := validate(schemaDir, kind, raw); err != nil {
			t.Fatal(err)
		}
		assertGenericRoundTrip(t, raw)
	}
}

func rootFixture(parts ...string) string {
	return filepath.Join(append([]string{repositoryRoot()}, parts...)...)
}
