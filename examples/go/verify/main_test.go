package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func repoRoot() string {
	return filepath.Clean(filepath.Join("..", "..", ".."))
}

func TestReferenceVerifierAcceptsPositiveBundle(t *testing.T) {
	uv, err := exec.LookPath("uv")
	if err != nil {
		t.Skip("uv is not installed; skipping Python reference-verifier example")
	}
	args := []string{
		"demos/v0.2-end-to-end/generated/positive-bundle",
		"--policy", "demos/v0.2-end-to-end/generated/receiver/policy.json",
		"--schema-catalog", "demos/v0.2-end-to-end/generated/receiver/catalog.json",
		"--expected-manifest", "sha256:b83a5cd1870b8ce1f2931650611f0a19deed0796c0f262e4632efc17981f695c",
		"--expected-head", "sha256:962be71738a0146642d27c87fba3c7338b0f2bb764b113b16867bb4808b11977",
		"--expected-artifact", "demos/v0.2-end-to-end/generated/receiver/expected-artifact.json",
		"--evaluation-time", "2026-09-16T16:00:00Z",
	}
	got, err := verifyBundle(uv, repoRoot(), args)
	if err != nil {
		t.Fatal(err)
	}
	if got["decision"] != "allow" {
		t.Fatalf("decision = %v, want allow", got["decision"])
	}
	wantRaw, err := os.ReadFile(filepath.Join(repoRoot(), "demos", "v0.2-end-to-end", "generated", "reports", "positive.json"))
	if err != nil {
		t.Fatal(err)
	}
	var want map[string]any
	if err := json.Unmarshal(wantRaw, &want); err != nil {
		t.Fatal(err)
	}
	if want["decision"] != "allow" {
		t.Fatal("checked-in positive report does not allow the fixture")
	}
	if !jsonEqual(got["manifestDigest"], want["manifestDigest"]) {
		t.Fatal("reference verifier manifest digest differs from checked-in report")
	}
	if !jsonEqual(got["actualHeads"], want["actualHeads"]) {
		t.Fatal("reference verifier heads differ from checked-in report")
	}
}

func jsonEqual(left, right any) bool {
	leftJSON, leftErr := json.Marshal(left)
	rightJSON, rightErr := json.Marshal(right)
	return leftErr == nil && rightErr == nil && string(leftJSON) == string(rightJSON)
}

func TestNegativeExpectationsDecodeAsGenericJSON(t *testing.T) {
	pattern := filepath.Join(repoRoot(), "testdata", "v0.2", "negative", "*", "expected-report.json")
	paths, err := filepath.Glob(pattern)
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) != 7 {
		t.Fatalf("found %d negative expectations, want 7", len(paths))
	}
	for _, path := range paths {
		path := path
		t.Run(filepath.Base(filepath.Dir(path)), func(t *testing.T) {
			raw, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			var expectation map[string]any
			if err := json.Unmarshal(raw, &expectation); err != nil {
				t.Fatal(err)
			}
			if expectation["decision"] != "deny" {
				t.Fatalf("decision = %v, want deny", expectation["decision"])
			}
			codes, ok := expectation["requiredErrorCodes"].([]any)
			primaryError, primaryOK := expectation["primaryError"].(string)
			if !ok || len(codes) == 0 || !primaryOK || primaryError == "" {
				t.Fatal("negative expectation does not identify its failure")
			}
		})
	}
}
