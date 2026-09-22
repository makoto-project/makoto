package makoto

// Nested Makoto objects preserve unknown fields even though the current v0.2
// schemas reject them. This lets a caller inspect, edit, and write a newer
// document without silently deleting data before choosing whether to accept it.

var digestFields = []string{"sha256"}

func (v *Digest) UnmarshalJSON(data []byte) error {
	type plain Digest
	return unmarshalWithUnknown(data, (*plain)(v), digestFields, &v.UnknownFields)
}

func (v Digest) MarshalJSON() ([]byte, error) {
	type plain Digest
	return marshalWithUnknown(plain(v), digestFields, v.UnknownFields)
}

var subjectFields = []string{"name", "digest"}

func (v *Subject) UnmarshalJSON(data []byte) error {
	type plain Subject
	return unmarshalWithUnknown(data, (*plain)(v), subjectFields, &v.UnknownFields)
}

func (v Subject) MarshalJSON() ([]byte, error) {
	type plain Subject
	return marshalWithUnknown(plain(v), subjectFields, v.UnknownFields)
}

var eventFields = []string{"id", "occurredAt"}

func (v *Event) UnmarshalJSON(data []byte) error {
	type plain Event
	return unmarshalWithUnknown(data, (*plain)(v), eventFields, &v.UnknownFields)
}

func (v Event) MarshalJSON() ([]byte, error) {
	type plain Event
	return marshalWithUnknown(plain(v), eventFields, v.UnknownFields)
}

var profileReferenceFields = []string{
	"id", "digest", "closureDigest", "target", "subjectName", "mediaType",
	"critical", "resources",
}

func (v *ProfileReference) UnmarshalJSON(data []byte) error {
	type plain ProfileReference
	return unmarshalWithUnknown(
		data,
		(*plain)(v),
		profileReferenceFields,
		&v.UnknownFields,
	)
}

func (v ProfileReference) MarshalJSON() ([]byte, error) {
	type plain ProfileReference
	return marshalWithUnknown(plain(v), profileReferenceFields, v.UnknownFields)
}

var originSourceFields = []string{
	"kind", "uri", "name", "mediaType", "retrievedAt", "version",
}

func (v *OriginSource) UnmarshalJSON(data []byte) error {
	type plain OriginSource
	return unmarshalWithUnknown(data, (*plain)(v), originSourceFields, &v.UnknownFields)
}

func (v OriginSource) MarshalJSON() ([]byte, error) {
	type plain OriginSource
	return marshalWithUnknown(plain(v), originSourceFields, v.UnknownFields)
}

var toolFields = []string{"name", "uri", "version", "digest"}

func (v *Tool) UnmarshalJSON(data []byte) error {
	type plain Tool
	return unmarshalWithUnknown(data, (*plain)(v), toolFields, &v.UnknownFields)
}

func (v Tool) MarshalJSON() ([]byte, error) {
	type plain Tool
	return marshalWithUnknown(plain(v), toolFields, v.UnknownFields)
}

var operationFields = []string{"type", "name", "tool", "parametersDigest"}

func (v *Operation) UnmarshalJSON(data []byte) error {
	type plain Operation
	return unmarshalWithUnknown(data, (*plain)(v), operationFields, &v.UnknownFields)
}

func (v Operation) MarshalJSON() ([]byte, error) {
	type plain Operation
	return marshalWithUnknown(plain(v), operationFields, v.UnknownFields)
}

var provenanceFields = []string{"statementDigest", "subjectName", "entryName"}

func (v *Provenance) UnmarshalJSON(data []byte) error {
	type plain Provenance
	return unmarshalWithUnknown(data, (*plain)(v), provenanceFields, &v.UnknownFields)
}

func (v Provenance) MarshalJSON() ([]byte, error) {
	type plain Provenance
	return marshalWithUnknown(plain(v), provenanceFields, v.UnknownFields)
}

var transformInputFields = []string{"name", "digest", "provenance"}

func (v *TransformInput) UnmarshalJSON(data []byte) error {
	type plain TransformInput
	return unmarshalWithUnknown(
		data,
		(*plain)(v),
		transformInputFields,
		&v.UnknownFields,
	)
}

func (v TransformInput) MarshalJSON() ([]byte, error) {
	type plain TransformInput
	return marshalWithUnknown(plain(v), transformInputFields, v.UnknownFields)
}

var signatureFields = []string{"keyid", "sig"}

func (v *Signature) UnmarshalJSON(data []byte) error {
	type plain Signature
	return unmarshalWithUnknown(data, (*plain)(v), signatureFields, &v.UnknownFields)
}

func (v Signature) MarshalJSON() ([]byte, error) {
	type plain Signature
	return marshalWithUnknown(plain(v), signatureFields, v.UnknownFields)
}

var handoffArtifactFields = []string{"name", "digest", "head", "mediaType"}

func (v *HandoffArtifact) UnmarshalJSON(data []byte) error {
	type plain HandoffArtifact
	return unmarshalWithUnknown(
		data,
		(*plain)(v),
		handoffArtifactFields,
		&v.UnknownFields,
	)
}

func (v HandoffArtifact) MarshalJSON() ([]byte, error) {
	type plain HandoffArtifact
	return marshalWithUnknown(plain(v), handoffArtifactFields, v.UnknownFields)
}

var requiredProfileFields = []string{
	"head", "id", "digest", "closureDigest", "target", "subjectName",
	"mediaType", "scope",
}

func (v *RequiredProfile) UnmarshalJSON(data []byte) error {
	type plain RequiredProfile
	return unmarshalWithUnknown(
		data,
		(*plain)(v),
		requiredProfileFields,
		&v.UnknownFields,
	)
}

func (v RequiredProfile) MarshalJSON() ([]byte, error) {
	type plain RequiredProfile
	return marshalWithUnknown(plain(v), requiredProfileFields, v.UnknownFields)
}

var datasetEntryFields = []string{"name", "digest", "size", "mediaType"}

func (v *DatasetEntry) UnmarshalJSON(data []byte) error {
	type plain DatasetEntry
	return unmarshalWithUnknown(data, (*plain)(v), datasetEntryFields, &v.UnknownFields)
}

func (v DatasetEntry) MarshalJSON() ([]byte, error) {
	type plain DatasetEntry
	return marshalWithUnknown(plain(v), datasetEntryFields, v.UnknownFields)
}

var bundleAttestationFields = []string{"statementDigest", "path"}

func (v *BundleAttestation) UnmarshalJSON(data []byte) error {
	type plain BundleAttestation
	return unmarshalWithUnknown(
		data,
		(*plain)(v),
		bundleAttestationFields,
		&v.UnknownFields,
	)
}

func (v BundleAttestation) MarshalJSON() ([]byte, error) {
	type plain BundleAttestation
	return marshalWithUnknown(plain(v), bundleAttestationFields, v.UnknownFields)
}

var bundleArtifactFields = []string{
	"statementDigest", "subjectName", "digest", "path",
}

func (v *BundleArtifact) UnmarshalJSON(data []byte) error {
	type plain BundleArtifact
	return unmarshalWithUnknown(
		data,
		(*plain)(v),
		bundleArtifactFields,
		&v.UnknownFields,
	)
}

func (v BundleArtifact) MarshalJSON() ([]byte, error) {
	type plain BundleArtifact
	return marshalWithUnknown(plain(v), bundleArtifactFields, v.UnknownFields)
}

var bundleDatasetEntryFields = []string{
	"manifestStatementDigest", "manifestSubjectName", "entryName", "digest", "path",
}

func (v *BundleDatasetEntry) UnmarshalJSON(data []byte) error {
	type plain BundleDatasetEntry
	return unmarshalWithUnknown(
		data,
		(*plain)(v),
		bundleDatasetEntryFields,
		&v.UnknownFields,
	)
}

func (v BundleDatasetEntry) MarshalJSON() ([]byte, error) {
	type plain BundleDatasetEntry
	return marshalWithUnknown(plain(v), bundleDatasetEntryFields, v.UnknownFields)
}

var policyKeyFields = []string{"type", "publicKey", "label", "validFrom", "validUntil"}

func (v *PolicyKey) UnmarshalJSON(data []byte) error {
	type plain PolicyKey
	return unmarshalWithUnknown(data, (*plain)(v), policyKeyFields, &v.UnknownFields)
}

func (v PolicyKey) MarshalJSON() ([]byte, error) {
	type plain PolicyKey
	return marshalWithUnknown(plain(v), policyKeyFields, v.UnknownFields)
}

var policyRuleFields = []string{
	"id", "predicateTypes", "sourceKinds", "sourceUris", "operationTypes",
	"authorizedKeyIds", "minimumSignatures", "profileConstraints",
}

func (v *PolicyRule) UnmarshalJSON(data []byte) error {
	type plain PolicyRule
	return unmarshalWithUnknown(data, (*plain)(v), policyRuleFields, &v.UnknownFields)
}

func (v PolicyRule) MarshalJSON() ([]byte, error) {
	type plain PolicyRule
	return marshalWithUnknown(plain(v), policyRuleFields, v.UnknownFields)
}

var handoffRuleFields = []string{
	"authorizedKeyIds", "minimumSignatures", "requireExpectedManifest",
	"requireExpectedHead", "requireExpectedArtifacts", "requireRecipient",
	"requireNonce", "allowReplayableHandoff", "maxAgeSeconds",
	"maxFutureSkewSeconds",
}

func (v *HandoffRule) UnmarshalJSON(data []byte) error {
	type plain HandoffRule
	return unmarshalWithUnknown(data, (*plain)(v), handoffRuleFields, &v.UnknownFields)
}

func (v HandoffRule) MarshalJSON() ([]byte, error) {
	type plain HandoffRule
	return marshalWithUnknown(plain(v), handoffRuleFields, v.UnknownFields)
}
