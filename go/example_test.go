package makoto_test

import (
	"bytes"
	"fmt"
	"log"
	"strings"

	makoto "github.com/makoto-project/makoto/go"
)

func Example_readValidateWrite() {
	input := strings.NewReader(`{
  "version": "0.2",
  "manifest": "manifest.dsse.json",
  "attestations": [],
  "artifacts": []
}`)
	bundle, err := makoto.DecodeBundle(input)
	if err != nil {
		log.Fatal(err)
	}
	if err := bundle.Validate(); err != nil {
		log.Fatal(err)
	}
	var output bytes.Buffer
	if err := makoto.Encode(&output, bundle); err != nil {
		log.Fatal(err)
	}
	fmt.Println(bundle.Version, output.Len() > 0)
	// Output: 0.2 true
}
