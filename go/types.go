package makoto

import (
	"encoding/json"
	"io"
)

// Digest is the Makoto v0.2 SHA-256 digest object.
type Digest struct {
	SHA256        string                     `json:"sha256"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// Subject is one in-toto Statement v1 subject.
type Subject struct {
	Name          string                     `json:"name"`
	Digest        Digest                     `json:"digest"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// Event identifies when a producer observed or performed an operation.
type Event struct {
	ID            string                     `json:"id"`
	OccurredAt    string                     `json:"occurredAt"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// ProfileReference pins an organizational schema profile.
type ProfileReference struct {
	ID            string                     `json:"id"`
	Digest        Digest                     `json:"digest"`
	ClosureDigest Digest                     `json:"closureDigest"`
	Target        string                     `json:"target"`
	SubjectName   *string                    `json:"subjectName,omitempty"`
	MediaType     *string                    `json:"mediaType,omitempty"`
	Critical      bool                       `json:"critical"`
	Resources     json.RawMessage            `json:"resources"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// Statement is the in-toto Statement v1 wrapper used by Makoto v0.2.
// Predicate remains raw JSON so callers can decode it as OriginPredicate or
// TransformPredicate without losing private extension fields.
type Statement struct {
	Type          string                     `json:"_type"`
	Subject       []Subject                  `json:"subject"`
	PredicateType string                     `json:"predicateType"`
	Predicate     json.RawMessage            `json:"predicate"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

var statementFields = []string{"_type", "subject", "predicateType", "predicate"}

func (s *Statement) UnmarshalJSON(data []byte) error {
	type plain Statement
	return unmarshalWithUnknown(data, (*plain)(s), statementFields, &s.UnknownFields)
}

func (s Statement) MarshalJSON() ([]byte, error) {
	type plain Statement
	return marshalWithUnknown(plain(s), statementFields, s.UnknownFields)
}

func DecodeStatement(r io.Reader) (*Statement, error) {
	var value Statement
	if err := decodeOne(r, &value); err != nil {
		return nil, err
	}
	return &value, nil
}

// OriginSource describes where an artifact was first observed.
type OriginSource struct {
	Kind          string                     `json:"kind"`
	URI           string                     `json:"uri,omitempty"`
	Name          string                     `json:"name,omitempty"`
	MediaType     string                     `json:"mediaType,omitempty"`
	RetrievedAt   string                     `json:"retrievedAt,omitempty"`
	Version       string                     `json:"version,omitempty"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// OriginPredicate is the Makoto v0.2 origin predicate.
type OriginPredicate struct {
	SchemaVersion string                     `json:"schemaVersion"`
	Event         Event                      `json:"event"`
	Source        OriginSource               `json:"source"`
	Profiles      *[]ProfileReference        `json:"profiles,omitempty"`
	Extensions    map[string]json.RawMessage `json:"extensions,omitempty"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

var originFields = []string{"schemaVersion", "event", "source", "profiles", "extensions"}

func (p *OriginPredicate) UnmarshalJSON(data []byte) error {
	type plain OriginPredicate
	return unmarshalWithUnknown(data, (*plain)(p), originFields, &p.UnknownFields)
}

func (p OriginPredicate) MarshalJSON() ([]byte, error) {
	type plain OriginPredicate
	return marshalWithUnknown(plain(p), originFields, p.UnknownFields)
}

func DecodeOriginPredicate(r io.Reader) (*OriginPredicate, error) {
	var value OriginPredicate
	if err := decodeOne(r, &value); err != nil {
		return nil, err
	}
	return &value, nil
}

// Tool identifies software used by a transformation.
type Tool struct {
	Name          string                     `json:"name,omitempty"`
	URI           string                     `json:"uri,omitempty"`
	Version       string                     `json:"version,omitempty"`
	Digest        *Digest                    `json:"digest,omitempty"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// Operation identifies the transformation operation.
type Operation struct {
	Type             string                     `json:"type"`
	Name             string                     `json:"name,omitempty"`
	Tool             *Tool                      `json:"tool,omitempty"`
	ParametersDigest *Digest                    `json:"parametersDigest,omitempty"`
	UnknownFields    map[string]json.RawMessage `json:"-"`
}

// Provenance links a transformation input to its predecessor statement.
type Provenance struct {
	StatementDigest Digest                     `json:"statementDigest"`
	SubjectName     string                     `json:"subjectName"`
	EntryName       string                     `json:"entryName,omitempty"`
	UnknownFields   map[string]json.RawMessage `json:"-"`
}

// TransformInput is one input to a transformation.
type TransformInput struct {
	Name          string                     `json:"name"`
	Digest        Digest                     `json:"digest"`
	Provenance    Provenance                 `json:"provenance"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// TransformPredicate is the Makoto v0.2 transformation predicate.
type TransformPredicate struct {
	SchemaVersion string                     `json:"schemaVersion"`
	Event         Event                      `json:"event"`
	Operation     Operation                  `json:"operation"`
	Inputs        []TransformInput           `json:"inputs"`
	Profiles      *[]ProfileReference        `json:"profiles,omitempty"`
	Extensions    map[string]json.RawMessage `json:"extensions,omitempty"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

var transformFields = []string{
	"schemaVersion", "event", "operation", "inputs", "profiles", "extensions",
}

func (p *TransformPredicate) UnmarshalJSON(data []byte) error {
	type plain TransformPredicate
	return unmarshalWithUnknown(data, (*plain)(p), transformFields, &p.UnknownFields)
}

func (p TransformPredicate) MarshalJSON() ([]byte, error) {
	type plain TransformPredicate
	return marshalWithUnknown(plain(p), transformFields, p.UnknownFields)
}

func DecodeTransformPredicate(r io.Reader) (*TransformPredicate, error) {
	var value TransformPredicate
	if err := decodeOne(r, &value); err != nil {
		return nil, err
	}
	return &value, nil
}

// Signature is one DSSE signature entry.
type Signature struct {
	KeyID         string                     `json:"keyid"`
	Sig           string                     `json:"sig"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// Envelope is a DSSE envelope.
type Envelope struct {
	PayloadType   string                     `json:"payloadType"`
	Payload       string                     `json:"payload"`
	Signatures    []Signature                `json:"signatures"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

var envelopeFields = []string{"payloadType", "payload", "signatures"}

func (e *Envelope) UnmarshalJSON(data []byte) error {
	type plain Envelope
	return unmarshalWithUnknown(data, (*plain)(e), envelopeFields, &e.UnknownFields)
}

func (e Envelope) MarshalJSON() ([]byte, error) {
	type plain Envelope
	return marshalWithUnknown(plain(e), envelopeFields, e.UnknownFields)
}

func DecodeEnvelope(r io.Reader) (*Envelope, error) {
	var value Envelope
	if err := decodeOne(r, &value); err != nil {
		return nil, err
	}
	return &value, nil
}

// HandoffArtifact names a final artifact declared by a handoff.
type HandoffArtifact struct {
	Name          string                     `json:"name"`
	Digest        Digest                     `json:"digest"`
	Head          Digest                     `json:"head"`
	MediaType     string                     `json:"mediaType,omitempty"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// RequiredProfile is a required final-artifact profile.
type RequiredProfile struct {
	Head          *Digest                    `json:"head,omitempty"`
	ID            string                     `json:"id"`
	Digest        Digest                     `json:"digest"`
	ClosureDigest Digest                     `json:"closureDigest"`
	Target        string                     `json:"target"`
	SubjectName   string                     `json:"subjectName"`
	MediaType     string                     `json:"mediaType"`
	Scope         string                     `json:"scope"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// HandoffManifest is the signed Makoto v0.2 handoff payload.
type HandoffManifest struct {
	Version          string                     `json:"version"`
	BundleID         string                     `json:"bundleId"`
	IssuedAt         string                     `json:"issuedAt"`
	Recipient        string                     `json:"recipient,omitempty"`
	Roots            []Digest                   `json:"roots"`
	Heads            []Digest                   `json:"heads"`
	Statements       []Digest                   `json:"statements"`
	Artifacts        []HandoffArtifact          `json:"artifacts"`
	RequiredProfiles []RequiredProfile          `json:"requiredProfiles"`
	Nonce            string                     `json:"nonce,omitempty"`
	UnknownFields    map[string]json.RawMessage `json:"-"`
}

var handoffFields = []string{
	"version", "bundleId", "issuedAt", "recipient", "roots", "heads",
	"statements", "artifacts", "requiredProfiles", "nonce",
}

func (m *HandoffManifest) UnmarshalJSON(data []byte) error {
	type plain HandoffManifest
	return unmarshalWithUnknown(data, (*plain)(m), handoffFields, &m.UnknownFields)
}

func (m HandoffManifest) MarshalJSON() ([]byte, error) {
	type plain HandoffManifest
	return marshalWithUnknown(plain(m), handoffFields, m.UnknownFields)
}

func DecodeHandoffManifest(r io.Reader) (*HandoffManifest, error) {
	var value HandoffManifest
	if err := decodeOne(r, &value); err != nil {
		return nil, err
	}
	return &value, nil
}

// DatasetEntry is one logical file in a dataset manifest.
type DatasetEntry struct {
	Name          string                     `json:"name"`
	Digest        Digest                     `json:"digest"`
	Size          *int64                     `json:"size,omitempty"`
	MediaType     string                     `json:"mediaType,omitempty"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// DatasetManifest binds logical entry names to exact bytes.
type DatasetManifest struct {
	Version       string                     `json:"version"`
	Entries       []DatasetEntry             `json:"entries"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

var datasetManifestFields = []string{"version", "entries"}

func (m *DatasetManifest) UnmarshalJSON(data []byte) error {
	type plain DatasetManifest
	return unmarshalWithUnknown(
		data,
		(*plain)(m),
		datasetManifestFields,
		&m.UnknownFields,
	)
}

func (m DatasetManifest) MarshalJSON() ([]byte, error) {
	type plain DatasetManifest
	return marshalWithUnknown(plain(m), datasetManifestFields, m.UnknownFields)
}

func DecodeDatasetManifest(r io.Reader) (*DatasetManifest, error) {
	var value DatasetManifest
	if err := decodeOne(r, &value); err != nil {
		return nil, err
	}
	return &value, nil
}

// BundleAttestation locates one statement envelope in a bundle.
type BundleAttestation struct {
	StatementDigest Digest                     `json:"statementDigest"`
	Path            string                     `json:"path"`
	UnknownFields   map[string]json.RawMessage `json:"-"`
}

// BundleArtifact locates one ordinary artifact in a bundle.
type BundleArtifact struct {
	StatementDigest Digest                     `json:"statementDigest"`
	SubjectName     string                     `json:"subjectName"`
	Digest          Digest                     `json:"digest"`
	Path            string                     `json:"path"`
	UnknownFields   map[string]json.RawMessage `json:"-"`
}

// BundleDatasetEntry locates one partition artifact in a bundle.
type BundleDatasetEntry struct {
	ManifestStatementDigest Digest                     `json:"manifestStatementDigest"`
	ManifestSubjectName     string                     `json:"manifestSubjectName"`
	EntryName               string                     `json:"entryName"`
	Digest                  Digest                     `json:"digest"`
	Path                    string                     `json:"path"`
	UnknownFields           map[string]json.RawMessage `json:"-"`
}

// Bundle is the portable Makoto v0.2 bundle index.
type Bundle struct {
	Version        string                     `json:"version"`
	Manifest       string                     `json:"manifest"`
	Attestations   []BundleAttestation        `json:"attestations"`
	Artifacts      []BundleArtifact           `json:"artifacts"`
	DatasetEntries *[]BundleDatasetEntry      `json:"datasetEntries,omitempty"`
	SchemaCatalog  string                     `json:"schemaCatalog,omitempty"`
	UnknownFields  map[string]json.RawMessage `json:"-"`
}

var bundleFields = []string{
	"version", "manifest", "attestations", "artifacts", "datasetEntries", "schemaCatalog",
}

func (b *Bundle) UnmarshalJSON(data []byte) error {
	type plain Bundle
	return unmarshalWithUnknown(data, (*plain)(b), bundleFields, &b.UnknownFields)
}

func (b Bundle) MarshalJSON() ([]byte, error) {
	type plain Bundle
	return marshalWithUnknown(plain(b), bundleFields, b.UnknownFields)
}

func DecodeBundle(r io.Reader) (*Bundle, error) {
	var value Bundle
	if err := decodeOne(r, &value); err != nil {
		return nil, err
	}
	return &value, nil
}

// PolicyKey is an Ed25519 verification key from a consumer trust policy.
type PolicyKey struct {
	Type          string                     `json:"type"`
	PublicKey     string                     `json:"publicKey"`
	Label         string                     `json:"label,omitempty"`
	ValidFrom     string                     `json:"validFrom,omitempty"`
	ValidUntil    string                     `json:"validUntil,omitempty"`
	UnknownFields map[string]json.RawMessage `json:"-"`
}

// PolicyRule authorizes keys for a set of Makoto claims.
type PolicyRule struct {
	ID                 string                     `json:"id"`
	PredicateTypes     []string                   `json:"predicateTypes"`
	SourceKinds        []string                   `json:"sourceKinds,omitempty"`
	SourceURIs         []string                   `json:"sourceUris,omitempty"`
	OperationTypes     []string                   `json:"operationTypes,omitempty"`
	AuthorizedKeyIDs   []string                   `json:"authorizedKeyIds"`
	MinimumSignatures  int                        `json:"minimumSignatures"`
	ProfileConstraints []json.RawMessage          `json:"profileConstraints,omitempty"`
	UnknownFields      map[string]json.RawMessage `json:"-"`
}

// HandoffRule controls receiver acceptance of a signed handoff manifest.
type HandoffRule struct {
	AuthorizedKeyIDs         []string                   `json:"authorizedKeyIds"`
	MinimumSignatures        int                        `json:"minimumSignatures"`
	RequireExpectedManifest  bool                       `json:"requireExpectedManifest"`
	RequireExpectedHead      bool                       `json:"requireExpectedHead"`
	RequireExpectedArtifacts bool                       `json:"requireExpectedArtifacts"`
	RequireRecipient         bool                       `json:"requireRecipient"`
	RequireNonce             bool                       `json:"requireNonce"`
	AllowReplayableHandoff   bool                       `json:"allowReplayableHandoff"`
	MaxAgeSeconds            *int64                     `json:"maxAgeSeconds,omitempty"`
	MaxFutureSkewSeconds     *int64                     `json:"maxFutureSkewSeconds,omitempty"`
	UnknownFields            map[string]json.RawMessage `json:"-"`
}

// TrustPolicy is the receiver-owned Makoto v0.2 trust policy.
type TrustPolicy struct {
	Version             string                     `json:"version"`
	Keys                map[string]PolicyKey       `json:"keys"`
	Rules               []PolicyRule               `json:"rules"`
	Handoff             HandoffRule                `json:"handoff"`
	RequiredProfiles    []RequiredProfile          `json:"requiredProfiles"`
	VerificationSummary json.RawMessage            `json:"verificationSummary,omitempty"`
	Limits              map[string]int64           `json:"limits"`
	UnknownFields       map[string]json.RawMessage `json:"-"`
}

var trustPolicyFields = []string{
	"version", "keys", "rules", "handoff", "requiredProfiles", "verificationSummary", "limits",
}

func (p *TrustPolicy) UnmarshalJSON(data []byte) error {
	type plain TrustPolicy
	return unmarshalWithUnknown(data, (*plain)(p), trustPolicyFields, &p.UnknownFields)
}

func (p TrustPolicy) MarshalJSON() ([]byte, error) {
	type plain TrustPolicy
	return marshalWithUnknown(plain(p), trustPolicyFields, p.UnknownFields)
}

func DecodeTrustPolicy(r io.Reader) (*TrustPolicy, error) {
	var value TrustPolicy
	if err := decodeOne(r, &value); err != nil {
		return nil, err
	}
	return &value, nil
}

// VerificationReport is the stable Makoto v0.2 receiver report. Detailed
// records remain raw JSON because their schema is diagnostic-code dependent.
type VerificationReport struct {
	ReportVersion          string                     `json:"reportVersion"`
	Decision               string                     `json:"decision"`
	ReportTruncated        bool                       `json:"reportTruncated"`
	PrimaryError           json.RawMessage            `json:"primaryError"`
	BundleID               string                     `json:"bundleId"`
	EvaluationTime         string                     `json:"evaluationTime"`
	PolicyDigest           Digest                     `json:"policyDigest"`
	PolicyDigestEncoding   string                     `json:"policyDigestEncoding"`
	CoreCatalogDigest      Digest                     `json:"coreCatalogDigest"`
	ManifestDigest         json.RawMessage            `json:"manifestDigest"`
	ExpectedManifestDigest json.RawMessage            `json:"expectedManifestDigest"`
	Handoff                json.RawMessage            `json:"handoff"`
	ExpectedHeads          []Digest                   `json:"expectedHeads"`
	ActualHeads            []Digest                   `json:"actualHeads"`
	ExpectedArtifacts      []json.RawMessage          `json:"expectedArtifacts"`
	ExpectedRecipient      json.RawMessage            `json:"expectedRecipient"`
	ActualRecipient        json.RawMessage            `json:"actualRecipient"`
	RecipientStatus        string                     `json:"recipientStatus"`
	ExpectedNonce          json.RawMessage            `json:"expectedNonce"`
	ActualNonce            json.RawMessage            `json:"actualNonce"`
	NonceStatus            string                     `json:"nonceStatus"`
	Roots                  []Digest                   `json:"roots"`
	Summary                json.RawMessage            `json:"summary"`
	Statements             []json.RawMessage          `json:"statements"`
	Profiles               []json.RawMessage          `json:"profiles"`
	Artifacts              []json.RawMessage          `json:"artifacts"`
	UnindexedEnvelopes     []json.RawMessage          `json:"unindexedEnvelopes"`
	QuarantinedStatements  []json.RawMessage          `json:"quarantinedStatements"`
	DatasetEntries         []json.RawMessage          `json:"datasetEntries"`
	UnreferencedFiles      []json.RawMessage          `json:"unreferencedFiles"`
	Checks                 []json.RawMessage          `json:"checks"`
	Warnings               []json.RawMessage          `json:"warnings"`
	Errors                 []json.RawMessage          `json:"errors"`
	Tool                   json.RawMessage            `json:"tool"`
	UnknownFields          map[string]json.RawMessage `json:"-"`
}

var verificationReportFields = []string{
	"reportVersion", "decision", "reportTruncated", "primaryError", "bundleId",
	"evaluationTime", "policyDigest", "policyDigestEncoding", "coreCatalogDigest",
	"manifestDigest", "expectedManifestDigest", "handoff", "expectedHeads",
	"actualHeads", "expectedArtifacts", "expectedRecipient", "actualRecipient",
	"recipientStatus", "expectedNonce", "actualNonce", "nonceStatus", "roots",
	"summary", "statements", "profiles", "artifacts", "unindexedEnvelopes",
	"quarantinedStatements", "datasetEntries", "unreferencedFiles", "checks",
	"warnings", "errors", "tool",
}

func (r *VerificationReport) UnmarshalJSON(data []byte) error {
	type plain VerificationReport
	return unmarshalWithUnknown(
		data,
		(*plain)(r),
		verificationReportFields,
		&r.UnknownFields,
	)
}

func (r VerificationReport) MarshalJSON() ([]byte, error) {
	type plain VerificationReport
	return marshalWithUnknown(plain(r), verificationReportFields, r.UnknownFields)
}

func DecodeVerificationReport(r io.Reader) (*VerificationReport, error) {
	var value VerificationReport
	if err := decodeOne(r, &value); err != nil {
		return nil, err
	}
	return &value, nil
}
