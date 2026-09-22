package makoto

import (
	"bytes"
	"embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"path"
	"strings"
	"sync"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

//go:embed schemas/v0.2/*.json
var embeddedSchemas embed.FS

// DocumentKind identifies one Makoto v0.2 core schema.
type DocumentKind string

const (
	KindStatement          DocumentKind = "statement"
	KindOrigin             DocumentKind = "origin"
	KindTransform          DocumentKind = "transform"
	KindEnvelope           DocumentKind = "envelope"
	KindHandoff            DocumentKind = "handoff"
	KindDatasetManifest    DocumentKind = "dataset-manifest"
	KindBundle             DocumentKind = "bundle"
	KindTrustPolicy        DocumentKind = "trust-policy"
	KindVerificationReport DocumentKind = "verification-report"
)

var schemaIDs = map[DocumentKind]string{
	KindStatement:          "https://usemakoto.dev/schema/v0.2/statement.schema.json",
	KindOrigin:             "https://usemakoto.dev/schema/v0.2/origin.schema.json",
	KindTransform:          "https://usemakoto.dev/schema/v0.2/transform.schema.json",
	KindEnvelope:           "https://usemakoto.dev/schema/v0.2/envelope.schema.json",
	KindHandoff:            "https://usemakoto.dev/schema/v0.2/handoff.schema.json",
	KindDatasetManifest:    "https://usemakoto.dev/schema/v0.2/dataset-manifest.schema.json",
	KindBundle:             "https://usemakoto.dev/schema/v0.2/bundle.schema.json",
	KindTrustPolicy:        "https://usemakoto.dev/schema/v0.2/trust-policy.schema.json",
	KindVerificationReport: "https://usemakoto.dev/schema/v0.2/verification-report.schema.json",
}

type rejectingLoader struct{}

func (rejectingLoader) Load(url string) (any, error) {
	return nil, fmt.Errorf("external schema loading is disabled: %s", url)
}

var (
	compileOnce sync.Once
	compiled    map[DocumentKind]*jsonschema.Schema
	compileErr  error
)

func compileSchemas() (map[DocumentKind]*jsonschema.Schema, error) {
	compileOnce.Do(func() {
		compiler := jsonschema.NewCompiler()
		compiler.UseLoader(rejectingLoader{})
		matches, err := fs.Glob(embeddedSchemas, "schemas/v0.2/*.schema.json")
		if err != nil {
			compileErr = fmt.Errorf("list embedded schemas: %w", err)
			return
		}
		for _, name := range matches {
			data, readErr := embeddedSchemas.ReadFile(name)
			if readErr != nil {
				compileErr = fmt.Errorf("read embedded schema %s: %w", name, readErr)
				return
			}
			var header struct {
				ID string `json:"$id"`
			}
			if unmarshalErr := json.Unmarshal(data, &header); unmarshalErr != nil {
				compileErr = fmt.Errorf("read schema ID %s: %w", name, unmarshalErr)
				return
			}
			document, parseErr := jsonschema.UnmarshalJSON(bytes.NewReader(data))
			if parseErr != nil {
				compileErr = fmt.Errorf("parse embedded schema %s: %w", name, parseErr)
				return
			}
			if addErr := compiler.AddResource(header.ID, document); addErr != nil {
				compileErr = fmt.Errorf("register embedded schema %s: %w", name, addErr)
				return
			}
		}
		compiled = make(map[DocumentKind]*jsonschema.Schema, len(schemaIDs))
		for kind, schemaID := range schemaIDs {
			schema, err := compiler.Compile(schemaID)
			if err != nil {
				compileErr = fmt.Errorf("compile %s schema: %w", kind, err)
				return
			}
			compiled[kind] = schema
		}
	})
	return compiled, compileErr
}

// ValidateJSON validates raw JSON against one embedded Makoto v0.2 schema.
func ValidateJSON(kind DocumentKind, data []byte) error {
	schemas, err := compileSchemas()
	if err != nil {
		return err
	}
	schema, ok := schemas[kind]
	if !ok {
		return fmt.Errorf("unknown Makoto document kind %q", kind)
	}
	instance, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("parse %s JSON: %w", kind, err)
	}
	if err := schema.Validate(instance); err != nil {
		return fmt.Errorf("validate %s: %w", kind, err)
	}
	return nil
}

func validateDocument(kind DocumentKind, value any) error {
	data, err := json.Marshal(value)
	if err != nil {
		return fmt.Errorf("marshal %s for validation: %w", kind, err)
	}
	return ValidateJSON(kind, data)
}

func (s Statement) Validate() error          { return validateDocument(KindStatement, s) }
func (p OriginPredicate) Validate() error    { return validateDocument(KindOrigin, p) }
func (p TransformPredicate) Validate() error { return validateDocument(KindTransform, p) }
func (e Envelope) Validate() error           { return validateDocument(KindEnvelope, e) }
func (m HandoffManifest) Validate() error    { return validateDocument(KindHandoff, m) }
func (m DatasetManifest) Validate() error {
	return validateDocument(KindDatasetManifest, m)
}
func (b Bundle) Validate() error      { return validateDocument(KindBundle, b) }
func (p TrustPolicy) Validate() error { return validateDocument(KindTrustPolicy, p) }
func (r VerificationReport) Validate() error {
	return validateDocument(KindVerificationReport, r)
}

// EmbeddedSchema returns a copy of one embedded schema file. Name may be a
// document kind such as "bundle" or a file name such as "catalog.json".
func EmbeddedSchema(name string) ([]byte, error) {
	fileName := name
	if !strings.HasSuffix(fileName, ".json") {
		fileName += ".schema.json"
	}
	data, err := embeddedSchemas.ReadFile(path.Join("schemas/v0.2", fileName))
	if err != nil {
		return nil, fmt.Errorf("read embedded schema %s: %w", name, err)
	}
	return bytes.Clone(data), nil
}
