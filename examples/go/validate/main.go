package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

var schemaNames = map[string]string{
	"bundle":                 "bundle",
	"dataset-manifest":       "dataset-manifest",
	"envelope":               "envelope",
	"handoff":                "handoff",
	"origin":                 "origin",
	"record-declaration":     "record-declaration",
	"record-inclusion-proof": "record-inclusion-proof",
	"statement":              "statement",
	"transform":              "transform",
	"trust-policy":           "trust-policy",
	"verification-report":    "verification-report",
}

type offlineLoader struct{}

func (offlineLoader) Load(url string) (any, error) {
	return nil, fmt.Errorf("network schema loading is disabled: %s", url)
}

func validate(schemaDir, kind string, document []byte) error {
	schemaName, ok := schemaNames[kind]
	if !ok {
		return fmt.Errorf("unknown document kind %q", kind)
	}
	versionDirectory := filepath.Base(filepath.Clean(schemaDir))
	if versionDirectory != "v0.2" && versionDirectory != "v0.3" {
		return fmt.Errorf("unsupported schema directory %q", versionDirectory)
	}
	schemaID := fmt.Sprintf(
		"https://usemakoto.dev/schema/%s/%s.schema.json",
		versionDirectory,
		schemaName,
	)
	compiler := jsonschema.NewCompiler()
	compiler.UseLoader(offlineLoader{})
	paths, err := filepath.Glob(filepath.Join(schemaDir, "*.schema.json"))
	if err != nil {
		return fmt.Errorf("list schemas: %w", err)
	}
	if len(paths) == 0 {
		return errors.New("no schemas found")
	}
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if err != nil {
			return fmt.Errorf("read schema %s: %w", path, err)
		}
		var header map[string]any
		if err := json.Unmarshal(raw, &header); err != nil {
			return fmt.Errorf("decode schema %s: %w", path, err)
		}
		id, ok := header["$id"].(string)
		if !ok {
			return fmt.Errorf("schema %s has no $id", path)
		}
		resource, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
		if err != nil {
			return fmt.Errorf("parse schema %s: %w", path, err)
		}
		if err := compiler.AddResource(id, resource); err != nil {
			return fmt.Errorf("register schema %s: %w", path, err)
		}
	}
	schema, err := compiler.Compile(schemaID)
	if err != nil {
		return fmt.Errorf("compile %s schema: %w", kind, err)
	}
	value, err := jsonschema.UnmarshalJSON(bytes.NewReader(document))
	if err != nil {
		return fmt.Errorf("decode document: %w", err)
	}
	if err := schema.Validate(value); err != nil {
		return fmt.Errorf("validate %s: %w", kind, err)
	}
	return nil
}

func run(args []string) error {
	if len(args) != 3 {
		return errors.New("usage: validate SCHEMA_DIR KIND DOCUMENT")
	}
	document, err := os.ReadFile(args[2])
	if err != nil {
		return fmt.Errorf("read document: %w", err)
	}
	return validate(args[0], args[1], document)
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
