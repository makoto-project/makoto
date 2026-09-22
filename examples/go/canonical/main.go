package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"

	"github.com/gowebpki/jcs"
)

func canonicalize(raw []byte) ([]byte, error) {
	canonical, err := jcs.Transform(raw)
	if err != nil {
		return nil, fmt.Errorf("canonicalize JSON: %w", err)
	}
	return canonical, nil
}

func digest(raw []byte) string {
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:])
}

func run(args []string) error {
	if len(args) != 1 {
		return errors.New("usage: canonical DOCUMENT")
	}
	raw, err := os.ReadFile(args[0])
	if err != nil {
		return fmt.Errorf("read document: %w", err)
	}
	canonical, err := canonicalize(raw)
	if err != nil {
		return err
	}
	fmt.Println(digest(canonical))
	_, err = os.Stdout.Write(append(canonical, '\n'))
	return err
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
