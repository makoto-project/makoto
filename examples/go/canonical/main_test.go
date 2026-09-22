package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestCanonicalJSONAndDigest(t *testing.T) {
	canonical, err := canonicalize([]byte(`{"z":1,"a":"誠"}`))
	if err != nil {
		t.Fatal(err)
	}
	if got, want := string(canonical), `{"a":"誠","z":1}`; got != want {
		t.Fatalf("canonical JSON = %q, want %q", got, want)
	}
	if got, want := digest(canonical), "9dcdad6bcf0b1eb43e24b39fcabe5e88a7e334426043297549e60c9ffbc6f9a1"; got != want {
		t.Fatalf("digest = %s, want %s", got, want)
	}
}

func TestCanonicalizationMatchesPythonFixtures(t *testing.T) {
	uv, err := exec.LookPath("uv")
	if err != nil {
		t.Skip("uv is not installed; skipping Go/Python canonical JSON comparison")
	}
	root := filepath.Clean(filepath.Join("..", "..", ".."))
	fixtures := []string{
		"demos/v0.2-end-to-end/generated/positive-bundle/bundle.json",
		"demos/v0.2-end-to-end/generated/receiver/policy.json",
		"demos/v0.2-end-to-end/generated/reports/positive.json",
	}
	python := `
import base64, json, sys
from pathlib import Path
from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes
value = json.loads(Path(sys.argv[1]).read_bytes())
canonical = canonical_json(value)
print(json.dumps({"canonical": base64.b64encode(canonical).decode(), "digest": sha256_bytes(canonical)}))
`
	for _, fixture := range fixtures {
		fixture := fixture
		t.Run(filepath.Base(fixture), func(t *testing.T) {
			raw, err := os.ReadFile(filepath.Join(root, fixture))
			if err != nil {
				t.Fatal(err)
			}
			got, err := canonicalize(raw)
			if err != nil {
				t.Fatal(err)
			}
			command := exec.Command(uv, "run", "python", "-c", python, fixture)
			command.Dir = root
			output, err := command.Output()
			if err != nil {
				t.Fatalf("run Python implementation: %v", err)
			}
			var result map[string]string
			if err := json.Unmarshal(output, &result); err != nil {
				t.Fatal(err)
			}
			want, err := base64.StdEncoding.DecodeString(result["canonical"])
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(got, want) {
				t.Fatal("Go and Python canonical bytes differ")
			}
			if digest(got) != result["digest"] {
				t.Fatal("Go and Python SHA-256 digests differ")
			}
		})
	}
}
