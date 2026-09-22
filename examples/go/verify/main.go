package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
)

func verifyBundle(uv, workingDirectory string, args []string) (map[string]any, error) {
	commandArgs := append([]string{"run", "makoto", "verify", "bundle"}, args...)
	commandArgs = append(commandArgs, "--json")
	command := exec.Command(uv, commandArgs...)
	command.Dir = workingDirectory
	var stderr bytes.Buffer
	command.Stderr = &stderr
	output, err := command.Output()
	if err != nil {
		return nil, fmt.Errorf("makoto verify bundle: %w: %s", err, stderr.String())
	}
	var report map[string]any
	if err := json.Unmarshal(output, &report); err != nil {
		return nil, fmt.Errorf("decode verification report: %w", err)
	}
	return report, nil
}

func run(args []string) error {
	if len(args) == 0 {
		return errors.New("usage: verify BUNDLE --policy POLICY [OPTIONS]")
	}
	uv, err := exec.LookPath("uv")
	if err != nil {
		return errors.New("uv is required to run the Python reference verifier")
	}
	report, err := verifyBundle(uv, ".", args)
	if err != nil {
		return err
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	return encoder.Encode(report)
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
