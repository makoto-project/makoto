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

var schemaIDs = map[string]string{
	"bundle":              "https://usemakoto.dev/schema/v0.2/bundle.schema.json",
	"dataset-manifest":    "https://usemakoto.dev/schema/v0.2/dataset-manifest.schema.json",
	"envelope":            "https://usemakoto.dev/schema/v0.2/envelope.schema.json",
	"handoff":             "https://usemakoto.dev/schema/v0.2/handoff.schema.json",
	"origin":              "https://usemakoto.dev/schema/v0.2/origin.schema.json",
	"statement":           "https://usemakoto.dev/schema/v0.2/statement.schema.json",
	"transform":           "https://usemakoto.dev/schema/v0.2/transform.schema.json",
	"trust-policy":        "https://usemakoto.dev/schema/v0.2/trust-policy.schema.json",
	"verification-report": "https://usemakoto.dev/schema/v0.2/verification-report.schema.json",
}

type offlineLoader struct{}

func (offlineLoader) Load(url string) (any, error) {
	return nil, fmt.Errorf("network schema loading is disabled: %s", url)
}

func validate(schemaDir, kind string, document []byte) error {
	schemaID, ok := schemaIDs[kind]
	if !ok {
		return fmt.Errorf("unknown document kind %q", kind)
	}
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
