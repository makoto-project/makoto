package makoto

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
	t.Parallel()
	canonical, err := CanonicalJSON(map[string]any{"z": 1, "a": "誠"})
	if err != nil {
		t.Fatal(err)
	}
	if got, want := string(canonical), `{"a":"誠","z":1}`; got != want {
		t.Fatalf("canonical JSON = %q, want %q", got, want)
	}
	if got, want := SHA256Bytes(canonical), "9dcdad6bcf0b1eb43e24b39fcabe5e88a7e334426043297549e60c9ffbc6f9a1"; got != want {
		t.Fatalf("digest = %s, want %s", got, want)
	}
	if _, err := CanonicalJSON(map[string]any{"notFinite": json.Number("NaN")}); err == nil {
		t.Fatal("CanonicalJSON accepted a non-JSON number")
	}
}

func TestCanonicalizationMatchesPython(t *testing.T) {
	uv, err := exec.LookPath("uv")
	if err != nil {
		t.Skip("uv is not installed; skipping Python cross-implementation comparison")
	}
	repositoryRoot := filepath.Clean("..")
	fixtures := []string{
		"demos/v0.2-end-to-end/generated/positive-bundle/bundle.json",
		"demos/v0.2-end-to-end/generated/receiver/policy.json",
		"demos/v0.2-end-to-end/generated/reports/positive.json",
	}
	python := `
import base64
import json
import sys
from pathlib import Path
from makoto.canonical import canonical_json
from makoto.digest import sha256_bytes

value = json.loads(Path(sys.argv[1]).read_bytes())
canonical = canonical_json(value)
print(json.dumps({
    "canonical": base64.b64encode(canonical).decode("ascii"),
    "digest": sha256_bytes(canonical),
}))
`
	for _, fixture := range fixtures {
		fixture := fixture
		t.Run(filepath.Base(fixture), func(t *testing.T) {
			raw, readErr := os.ReadFile(filepath.Join(repositoryRoot, fixture))
			if readErr != nil {
				t.Fatal(readErr)
			}
			goCanonical, canonicalErr := Canonicalize(raw)
			if canonicalErr != nil {
				t.Fatal(canonicalErr)
			}
			command := exec.Command(
				uv,
				"run",
				"python",
				"-c",
				python,
				fixture,
			)
			command.Dir = repositoryRoot
			output, commandErr := command.Output()
			if commandErr != nil {
				t.Fatalf("run Python canonicalizer: %v", commandErr)
			}
			var result struct {
				Canonical string `json:"canonical"`
				Digest    string `json:"digest"`
			}
			if err := json.Unmarshal(output, &result); err != nil {
				t.Fatalf("decode Python result: %v", err)
			}
			pythonCanonical, err := base64.StdEncoding.DecodeString(result.Canonical)
			if err != nil {
				t.Fatalf("decode Python canonical bytes: %v", err)
			}
			if !bytes.Equal(goCanonical, pythonCanonical) {
				t.Fatal("Go and Python canonical bytes differ")
			}
			if got := SHA256Bytes(goCanonical); got != result.Digest {
				t.Fatalf("Go digest %s differs from Python digest %s", got, result.Digest)
			}
		})
	}
}
