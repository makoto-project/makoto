package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strconv"
)

func pae(payloadType string, payload []byte) []byte {
	return []byte("DSSEv1 " + strconv.Itoa(len([]byte(payloadType))) + " " +
		payloadType + " " + strconv.Itoa(len(payload)) + " " + string(payload))
}

func keyID(publicKey ed25519.PublicKey) (string, error) {
	spki, err := x509.MarshalPKIXPublicKey(publicKey)
	if err != nil {
		return "", fmt.Errorf("encode public key: %w", err)
	}
	sum := sha256.Sum256(spki)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

func signEnvelope(payloadType string, payload []byte, privateKey ed25519.PrivateKey) (map[string]any, error) {
	id, err := keyID(privateKey.Public().(ed25519.PublicKey))
	if err != nil {
		return nil, err
	}
	signature := ed25519.Sign(privateKey, pae(payloadType, payload))
	return map[string]any{
		"payloadType": payloadType,
		"payload":     base64.StdEncoding.EncodeToString(payload),
		"signatures": []any{map[string]any{
			"keyid": id,
			"sig":   base64.StdEncoding.EncodeToString(signature),
		}},
	}, nil
}

func canonicalBase64(value string) ([]byte, error) {
	decoded, err := base64.StdEncoding.Strict().DecodeString(value)
	if err != nil || base64.StdEncoding.EncodeToString(decoded) != value {
		return nil, errors.New("value is not canonical base64")
	}
	return decoded, nil
}

func verifyEnvelope(envelope map[string]any, publicKeys map[string]ed25519.PublicKey) error {
	payloadType, ok := envelope["payloadType"].(string)
	if !ok {
		return errors.New("payloadType is not a string")
	}
	payloadText, ok := envelope["payload"].(string)
	if !ok {
		return errors.New("payload is not a string")
	}
	payload, err := canonicalBase64(payloadText)
	if err != nil {
		return fmt.Errorf("decode payload: %w", err)
	}
	signatures, ok := envelope["signatures"].([]any)
	if !ok || len(signatures) == 0 {
		return errors.New("signatures is not a nonempty array")
	}
	for index, value := range signatures {
		signature, ok := value.(map[string]any)
		if !ok {
			return fmt.Errorf("signature %d is not an object", index)
		}
		id, idOK := signature["keyid"].(string)
		sigText, sigOK := signature["sig"].(string)
		if !idOK || !sigOK {
			return fmt.Errorf("signature %d fields are malformed", index)
		}
		publicKey, ok := publicKeys[id]
		if !ok {
			return fmt.Errorf("signature %d uses unknown key %s", index, id)
		}
		sig, err := canonicalBase64(sigText)
		if err != nil {
			return fmt.Errorf("decode signature %d: %w", index, err)
		}
		if !ed25519.Verify(publicKey, pae(payloadType, payload), sig) {
			return fmt.Errorf("signature %d is invalid", index)
		}
	}
	return nil
}

func loadPolicyKeys(path string) (map[string]ed25519.PublicKey, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read policy: %w", err)
	}
	var policy map[string]any
	if err := json.Unmarshal(raw, &policy); err != nil {
		return nil, fmt.Errorf("decode policy: %w", err)
	}
	keys, ok := policy["keys"].(map[string]any)
	if !ok {
		return nil, errors.New("policy keys is not an object")
	}
	publicKeys := make(map[string]ed25519.PublicKey, len(keys))
	for id, value := range keys {
		key, ok := value.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("policy key %s is not an object", id)
		}
		encoded, ok := key["publicKey"].(string)
		if !ok {
			return nil, fmt.Errorf("policy key %s has no publicKey", id)
		}
		spki, err := canonicalBase64(encoded)
		if err != nil {
			return nil, fmt.Errorf("decode policy key %s: %w", id, err)
		}
		parsed, err := x509.ParsePKIXPublicKey(spki)
		if err != nil {
			return nil, fmt.Errorf("parse policy key %s: %w", id, err)
		}
		publicKey, ok := parsed.(ed25519.PublicKey)
		if !ok {
			return nil, fmt.Errorf("policy key %s is not Ed25519", id)
		}
		computedID, err := keyID(publicKey)
		if err != nil {
			return nil, err
		}
		if computedID != id {
			return nil, fmt.Errorf("policy key ID %s does not match key bytes", id)
		}
		publicKeys[id] = publicKey
	}
	return publicKeys, nil
}

func run(args []string) error {
	if len(args) == 3 && args[0] == "verify" {
		raw, err := os.ReadFile(args[1])
		if err != nil {
			return fmt.Errorf("read envelope: %w", err)
		}
		var envelope map[string]any
		if err := json.Unmarshal(raw, &envelope); err != nil {
			return fmt.Errorf("decode envelope: %w", err)
		}
		publicKeys, err := loadPolicyKeys(args[2])
		if err != nil {
			return err
		}
		if err := verifyEnvelope(envelope, publicKeys); err != nil {
			return err
		}
		fmt.Println("valid")
		return nil
	}
	if len(args) != 2 || args[0] != "sign" {
		return errors.New("usage: dsse sign PAYLOAD | dsse verify ENVELOPE POLICY")
	}
	payload, err := os.ReadFile(args[1])
	if err != nil {
		return fmt.Errorf("read payload: %w", err)
	}
	_, privateKey, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return fmt.Errorf("generate key: %w", err)
	}
	envelope, err := signEnvelope("application/vnd.in-toto+json", payload, privateKey)
	if err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(envelope)
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
