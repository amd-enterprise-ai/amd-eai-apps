// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Package apikey holds the primitives for tying a presented bearer key back to the per-key Secret
// that authorizes it. Both the ext_authz authorization path and the /v1/models listing reason about
// the same membership (a key Secret carries the raw key base64-encoded under its client-id data key,
// and one apikey.eai.amd.com/bound-<workload-id> label per model it may use), so the matching logic
// lives here once.
package apikey

import (
	"encoding/base64"
	"strings"
)

// Bearer extracts the raw key from an Authorization header value, tolerating the "Bearer " scheme
// prefix (case-insensitive) and returning "" when absent.
func Bearer(header string) string {
	if len(header) >= 7 && strings.EqualFold(header[:7], "bearer ") {
		return strings.TrimSpace(header[7:])
	}
	return strings.TrimSpace(header)
}

// MatchClientID reports whether the raw key appears (base64-encoded, as ESO materializes it) among
// the values of a key Secret's data map, returning the matching client id (the data key,
// token-<ns>-<key>) when it does. An entry that is not valid base64 is skipped rather than failing
// the whole match.
func MatchClientID(data map[string]string, key string) (string, bool) {
	for clientID, encoded := range data {
		raw, err := base64.StdEncoding.DecodeString(encoded)
		if err != nil {
			continue
		}
		if string(raw) == key {
			return clientID, true
		}
	}
	return "", false
}
