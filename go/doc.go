// Package makoto reads, writes, validates, canonicalizes, hashes, signs, and
// verifies Makoto v0.2 documents.
//
// This package does not implement receiver graph, policy, profile, assurance,
// or VSA evaluation. Those operations remain in the Python reference verifier.
package makoto

const (
	Version                = "0.2"
	StatementType          = "https://in-toto.io/Statement/v1"
	OriginPredicateType    = "https://usemakoto.dev/predicate/v0.2/origin"
	TransformPredicateType = "https://usemakoto.dev/predicate/v0.2/transform"
	StatementPayloadType   = "application/vnd.in-toto+json"
	HandoffPayloadType     = "application/vnd.makoto.handoff.v0.2+json"
)
