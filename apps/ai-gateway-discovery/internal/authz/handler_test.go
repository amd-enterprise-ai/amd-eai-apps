// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

package authz

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/go-logr/logr"
	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"github.com/silogen/ai-gateway-discovery/internal/common"
	"github.com/silogen/ai-gateway-discovery/internal/config"
	"github.com/silogen/ai-gateway-discovery/internal/models"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"
)

const (
	ns        = "proj"
	managedK  = "app.kubernetes.io/managed-by"
	managedV  = "ai-gateway-discovery"
	modelAnno = "aim.eai.amd.com/model-id"

	modelA = "google/gemma-3-1b-it"
	wlA    = "wl-aaaa"
	keyA   = "amd_key_for_model_a"
	cidA   = "token-proj-alpha"

	modelB = "openai/gpt-oss-20b"
	wlB    = "wl-bbbb"
	keyB   = "amd_key_for_model_b"
	cidB   = "token-proj-bravo"
)

var secretGVK = schema.GroupVersionKind{Version: "v1", Kind: "Secret"}

func testScheme() *runtime.Scheme {
	s := runtime.NewScheme()
	for _, gvk := range []schema.GroupVersionKind{aigateway.InferenceServiceGVK, secretGVK} {
		s.AddKnownTypeWithName(gvk, &unstructured.Unstructured{})
		listGVK := gvk
		listGVK.Kind += "List"
		s.AddKnownTypeWithName(listGVK, &unstructured.UnstructuredList{})
	}
	return s
}

// keySecret is a per-key Secret bound to a model via its bound-<workload-id> label, with the
// key value base64-encoded under the client-id data key (as the API stores it).
func keySecret(name, workloadID, clientID, keyValue string) *unstructured.Unstructured {
	o := &unstructured.Unstructured{}
	o.SetGroupVersionKind(secretGVK)
	o.SetNamespace(ns)
	o.SetName(name)
	o.SetLabels(map[string]string{
		aigateway.APIKeyLabel:            "true",
		aigateway.BoundLabel(workloadID): "true",
	})
	_ = unstructured.SetNestedField(o.Object, base64.StdEncoding.EncodeToString([]byte(keyValue)), "data", clientID)
	return o
}

func inferenceService(name, model, workloadID string) *unstructured.Unstructured {
	o := &unstructured.Unstructured{}
	o.SetGroupVersionKind(aigateway.InferenceServiceGVK)
	o.SetNamespace(ns)
	o.SetName(name)
	o.SetLabels(map[string]string{managedK: managedV, common.DefaultWorkloadIDLabel: workloadID})
	o.SetAnnotations(map[string]string{modelAnno: model})
	return o
}

func newHandler(objs ...client.Object) *Handler {
	c := fake.NewClientBuilder().WithScheme(testScheme()).WithObjects(objs...).Build()
	return &Handler{
		Client: c,
		Log:    logr.Discard(),
		Config: &config.ControllerConfig{
			ManagedLabelName:    managedK,
			ManagedLabelValue:   managedV,
			ModelNameAnnotation: modelAnno,
			WorkloadIDLabel:     common.DefaultWorkloadIDLabel,
		},
	}
}

// fleet: two backends, each with one bound key.
func fleet() []client.Object {
	return []client.Object{
		inferenceService("is-a", modelA, wlA),
		inferenceService("is-b", modelB, wlB),
		keySecret("apikey-1", wlA, cidA, keyA),
		keySecret("apikey-2", wlB, cidB, keyB),
	}
}

func TestAuthorize(t *testing.T) {
	h := newHandler(fleet()...)
	ctx := context.Background()

	tests := []struct {
		name                string
		model, backend, key string
		wantOK              bool
		wantClientID        string
		wantWorkload        string
	}{
		{"backend id + authorized key", "", wlA, keyA, true, cidA, wlA},
		{"backend id + wrong key", "", wlA, keyB, false, "", ""},
		{"model only + authorized key", modelA, "", keyA, true, cidA, wlA},
		{"model only + key for a different model", modelB, "", keyA, false, "", ""},
		{"model only + its own key", modelB, "", keyB, true, cidB, wlB},
		{"unknown model", "no/such-model", "", keyA, false, "", ""},
		{"unknown backend", "", "wl-nope", keyA, false, "", ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cid, wl, ok := h.authorize(ctx, tt.model, tt.backend, tt.key)
			if ok != tt.wantOK {
				t.Fatalf("authorize ok = %v, want %v", ok, tt.wantOK)
			}
			if ok && cid != tt.wantClientID {
				t.Fatalf("authorize clientID = %q, want %q", cid, tt.wantClientID)
			}
			if ok && wl != tt.wantWorkload {
				t.Fatalf("authorize workloadID = %q, want %q", wl, tt.wantWorkload)
			}
		})
	}
}

// doMultipart posts a body with an explicit Content-Type, which is how a real audio request
// arrives once the SecurityPolicy forwards content-type. Passing an empty contentType models the
// policy failing to forward it.
func doMultipart(t *testing.T, h *Handler, authHeader, contentType, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/audio/transcriptions", strings.NewReader(body))
	if authHeader != "" {
		req.Header.Set("Authorization", authHeader)
	}
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	return rr
}

// multipartBody builds a form body with the given field pairs plus a file part, using boundary.
func multipartBody(boundary string, fields ...string) string {
	var sb strings.Builder
	for i := 0; i < len(fields); i += 2 {
		sb.WriteString("--" + boundary + "\r\n")
		sb.WriteString(`Content-Disposition: form-data; name="` + fields[i] + `"` + "\r\n\r\n")
		sb.WriteString(fields[i+1] + "\r\n")
	}
	sb.WriteString("--" + boundary + "\r\n")
	sb.WriteString(`Content-Disposition: form-data; name="file"; filename="a.wav"` + "\r\n\r\n")
	sb.WriteString("RIFFxxxxWAVE\r\n")
	sb.WriteString("--" + boundary + "--\r\n")
	return sb.String()
}

// TestServeHTTP_Multipart covers the audio path: the model is a form field, not a JSON key.
//
// The dual-boundary case is the important one. RFC 2046 §5.1.1 makes a reader discard everything
// before the first real boundary, so a body that opens with a decoy document under a made-up
// boundary parses differently here than it does downstream unless the boundary comes from
// Content-Type. Authorizing on the decoy while the served request names another model is a
// cross-model bypass, so the handler must read the real parts and deny.
func TestServeHTTP_Multipart(t *testing.T) {
	h := newHandler(fleet()...)
	const ct = "multipart/form-data; boundary=REAL"

	// A decoy document under a fake boundary, then the real one naming a model keyA cannot use.
	dualBoundary := multipartBody("FAKE", "model", modelA) + multipartBody("REAL", "model", modelB)

	// An allowed model part, then a part whose header line has no colon (Go's reader errors on it),
	// then a forbidden model part. A break-on-any-error parse would authorize modelA and never see
	// the second model; failing closed must deny before authorizing on a body it could not finish.
	malformedBetweenModels := "--REAL\r\n" +
		`Content-Disposition: form-data; name="model"` + "\r\n\r\n" +
		modelA + "\r\n" +
		"--REAL\r\n" +
		"not-a-header-line\r\n\r\n" +
		"--REAL\r\n" +
		`Content-Disposition: form-data; name="model"` + "\r\n\r\n" +
		modelB + "\r\n" +
		"--REAL--\r\n"

	// A part named "model" that carries a filename is a file upload, not a scalar. Its bytes (an
	// allowed model id here) must not be read as the model, so nothing names a model and the request
	// is denied — reading it would authorize on content the server treats as a file.
	fileNamedModel := "--REAL\r\n" +
		`Content-Disposition: form-data; name="model"; filename="m.bin"` + "\r\n\r\n" +
		modelA + "\r\n" +
		"--REAL--\r\n"

	// A scalar model part and a file part sharing the name "model": two occurrences, so ambiguous.
	// Authorizing on the scalar while a lenient downstream parser could read the file part is exactly
	// the divergence the duplicate guard closes, so it must deny rather than authorize modelA.
	scalarAndFileModel := "--REAL\r\n" +
		`Content-Disposition: form-data; name="model"` + "\r\n\r\n" +
		modelA + "\r\n" +
		"--REAL\r\n" +
		`Content-Disposition: form-data; name="model"; filename="m.bin"` + "\r\n\r\n" +
		modelB + "\r\n" +
		"--REAL--\r\n"

	// A scalar model field one byte past the cap. LimitReader would truncate it to maxFormFieldBytes
	// and authorize the prefix while the downstream parser reads the whole value; failing closed
	// denies instead.
	oversizedModel := multipartBody("REAL", "model", strings.Repeat("a", maxFormFieldBytes+1))

	// A part named "model" with an explicit but empty filename. Part.FileName() normalizes this to
	// "" just as it does an absent filename, but the filename parameter is present, so downstream
	// parsers treat it as a file part. Its allowed-model bytes must not be read as the model.
	emptyFilenameModel := "--REAL\r\n" +
		`Content-Disposition: form-data; name="model"; filename=""` + "\r\n\r\n" +
		modelA + "\r\n" +
		"--REAL--\r\n"

	// An allowed model part read cleanly, then a boundary and a header block cut off before its
	// blank line and before any closing "--REAL--". Go's reader reports io.EOF, not a parse error,
	// so without a close-delimiter requirement the loop would break and authorize modelA on a body
	// the sender never finished. The missing close must make it deny.
	truncatedAfterModel := "--REAL\r\n" +
		`Content-Disposition: form-data; name="model"` + "\r\n\r\n" +
		modelA + "\r\n" +
		"--REAL\r\n" +
		"Content-Disposition: form-data;"

	// A false close marker "--REAL--X" in the ignored preamble, then a real model part, then a header
	// block truncated before its blank line — which ends the body on a clean io.EOF with no real
	// "--REAL--". A substring close check would match the embedded "--REAL--" and authorize modelA;
	// the line-scoped check sees only a non-delimiter line ("--REAL--X") and denies. The trailing "X"
	// is what makes it content Go reads past rather than a delimiter.
	falseCloseMarker := "preamble\r\n" +
		"--REAL--X\r\n" +
		"--REAL\r\n" +
		`Content-Disposition: form-data; name="model"` + "\r\n\r\n" +
		modelA + "\r\n" +
		"--REAL\r\n" +
		"Content-Disposition: form-data;"

	// A CRLF body whose preamble carries a bare-LF "--REAL--" marker, then a real model part and a
	// truncated tail (clean io.EOF, no real close). A boundary needs a preceding CRLF, so Go reads
	// the LF-only marker as content; a close check keyed on any "\n" would accept it and authorize
	// modelA. The delimiter must be at the body start or after CRLF to deny this.
	lfOnlyCloseMarker := "preamble\n" +
		"--REAL--\n" +
		"--REAL\r\n" +
		`Content-Disposition: form-data; name="model"` + "\r\n\r\n" +
		modelA + "\r\n" +
		"--REAL\r\n" +
		"Content-Disposition: form-data;"

	// Close-looking lines before the first delimiter are preamble to the reader, which skips them
	// and goes on to read the model part; they say nothing about where the message ended. Each of
	// these fronts the truncated fixture above, so none may turn its denial into an authorization.
	preambleCloseAtStart := "--REAL--\n" + truncatedAfterModel
	preambleCloseWithSpace := "--REAL-- \n" + truncatedAfterModel
	preambleCloseCRLFThenLF := "x\r\n--REAL--\n" + truncatedAfterModel

	// A well-formed body delimited with bare LFs throughout. Go's reader latches LF mode from the
	// first delimiter and parses it, so the close check must accept it too rather than assume CRLF.
	lfDelimitedBody := "--REAL\n" +
		`Content-Disposition: form-data; name="model"` + "\n\n" +
		modelA + "\n" +
		"--REAL--\n"

	// modelA with its "/" quoted-printable encoded. NextPart would decode it back to modelA and
	// authorize; a form-data parser reads the literal bytes, so the part has no single value.
	quotedPrintableModel := "--REAL\r\n" +
		`Content-Disposition: form-data; name="model"` + "\r\n" +
		"Content-Transfer-Encoding: quoted-printable\r\n\r\n" +
		strings.Replace(modelA, "/", "=2F", 1) + "\r\n" +
		"--REAL--\r\n"

	// The same model part with the header present but empty, and with an empty header followed by a
	// real one. Header.Get reads "" for both, so only a presence check refuses them.
	cteModel := func(headers string) string {
		return "--REAL\r\n" +
			`Content-Disposition: form-data; name="model"` + "\r\n" +
			headers + "\r\n" +
			modelA + "\r\n" +
			"--REAL--\r\n"
	}
	emptyCTEModel := cteModel("Content-Transfer-Encoding:\r\n")
	repeatedCTEModel := cteModel("Content-Transfer-Encoding:\r\nContent-Transfer-Encoding: quoted-printable\r\n")

	tests := []struct {
		name        string
		contentType string
		body        string
		wantCode    int
		wantBackend string
	}{
		{"authorized model as a form field", ct, multipartBody("REAL", "model", modelA), http.StatusOK, wlA},
		{"model the key is not bound to", ct, multipartBody("REAL", "model", modelB), http.StatusUnauthorized, ""},
		{"no model field at all", ct, multipartBody("REAL", "response_format", "json"), http.StatusForbidden, ""},
		// A duplicated scalar is refused rather than resolved: the value authorized here and the
		// value the upstream serves can differ (parsers disagree on which occurrence wins), so a
		// pick would let the client authorize modelA while modelB is served. Detection is on the
		// part's presence, so an empty-then-named pair — which a first-non-empty-wins guard would
		// collapse to the named value — is refused too.
		{"duplicated model field is refused", ct, multipartBody("REAL", "model", modelA, "model", modelB), http.StatusBadRequest, ""},
		{"empty then named model field is refused", ct, multipartBody("REAL", "model", "", "model", modelA), http.StatusBadRequest, ""},
		{"duplicated backend field is refused", ct, multipartBody("REAL", "backend", wlA, "backend", wlB), http.StatusBadRequest, ""},
		// A parse failure is not an end-of-body: authorizing on the parts read before it would
		// decide on bytes the code could not finish reading, which a recovering downstream parser
		// could diverge from. The hidden second model part is exactly that divergence.
		{"malformed part between model fields is refused", ct, malformedBetweenModels, http.StatusBadRequest, ""},
		// A file part named "model" is not a scalar value: its bytes must not be authorized as the
		// model, so nothing names a model and the request is denied.
		{"file part named model is ignored", ct, fileNamedModel, http.StatusForbidden, ""},
		{"scalar and file model parts are ambiguous", ct, scalarAndFileModel, http.StatusBadRequest, ""},
		{"oversized model field is refused", ct, oversizedModel, http.StatusBadRequest, ""},
		// filename="" is a file part downstream even though Part.FileName() reports "", so its bytes
		// must not be read as the model.
		{"model part with empty filename is ignored", ct, emptyFilenameModel, http.StatusForbidden, ""},
		// Without Content-Type the body is not multipart as far as this handler is concerned; it
		// falls through to the JSON path and is rejected rather than parsed by a guessed boundary.
		{"content-type not forwarded", "", multipartBody("REAL", "model", modelA), http.StatusBadRequest, ""},
		{"decoy preamble under a fake boundary", ct, dualBoundary, http.StatusUnauthorized, ""},
		// A body cut mid-header-block reports io.EOF, but without the closing "--REAL--" it was never
		// finished, so it is denied as malformed rather than authorized on the parts read before the
		// cut — whether or not a complete part was read first.
		{"truncated body", ct, "--REAL\r\nContent-Disposition: form-data;", http.StatusBadRequest, ""},
		{"truncated tail after a model part", ct, truncatedAfterModel, http.StatusBadRequest, ""},
		// A false close marker in file content must not satisfy the close-delimiter check.
		{"false close marker in file content", ct, falseCloseMarker, http.StatusBadRequest, ""},
		// A bare-LF "--REAL--" is not a real delimiter (boundaries need a preceding CRLF), so it must
		// not satisfy the close check either.
		{"lf-only close marker is not a delimiter", ct, lfOnlyCloseMarker, http.StatusBadRequest, ""},
		{"close marker at body start is preamble", ct, preambleCloseAtStart, http.StatusBadRequest, ""},
		{"close marker with trailing space is preamble", ct, preambleCloseWithSpace, http.StatusBadRequest, ""},
		{"crlf-preceded lf-terminated close is preamble", ct, preambleCloseCRLFThenLF, http.StatusBadRequest, ""},
		{"lf-delimited body is accepted", ct, lfDelimitedBody, http.StatusOK, wlA},
		// The authorized value is the bytes on the wire: no transfer decoding and no trimming.
		{"quoted-printable model part is refused", ct, quotedPrintableModel, http.StatusBadRequest, ""},
		{"empty transfer-encoding header is refused", ct, emptyCTEModel, http.StatusBadRequest, ""},
		{"repeated transfer-encoding header is refused", ct, repeatedCTEModel, http.StatusBadRequest, ""},
		{"whitespace-padded model is not trimmed", ct, multipartBody("REAL", "model", " "+modelA+" "), http.StatusUnauthorized, ""},
		// Only multipart/form-data is parsed as form fields; another multipart subtype falls through
		// to the JSON path and is denied rather than authorized from its "model" part.
		{"non-form multipart subtype falls through", "multipart/mixed; boundary=REAL", multipartBody("REAL", "model", modelA), http.StatusBadRequest, ""},
		// RFC 2046 caps a boundary at 70 characters. At the cap a well-formed body authorizes; one
		// past it is not treated as multipart and falls through to the JSON path, which denies.
		{"boundary at the 70-byte cap", "multipart/form-data; boundary=" + strings.Repeat("b", 70), multipartBody(strings.Repeat("b", 70), "model", modelA), http.StatusOK, wlA},
		{"boundary over the 70-byte cap", "multipart/form-data; boundary=" + strings.Repeat("b", 71), multipartBody(strings.Repeat("b", 71), "model", modelA), http.StatusBadRequest, ""},
		{"very long boundary", "multipart/form-data; boundary=" + strings.Repeat("b", 5000), multipartBody(strings.Repeat("b", 5000), "model", modelA), http.StatusBadRequest, ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := doMultipart(t, h, "Bearer "+keyA, tt.contentType, tt.body)
			if rr.Code != tt.wantCode {
				t.Fatalf("code = %d, want %d (body %q)", rr.Code, tt.wantCode, rr.Body.String())
			}
			if got := rr.Header().Get("x-ai-eg-backend"); got != tt.wantBackend {
				t.Fatalf("x-ai-eg-backend = %q, want %q", got, tt.wantBackend)
			}
		})
	}
}

// TestServeHTTP_MultipartDenyReason pins which deny reason reaches the client. The reasons share a
// 400, so the status alone cannot tell an over-cap field from a malformed body.
func TestServeHTTP_MultipartDenyReason(t *testing.T) {
	h := newHandler(fleet()...)
	const ct = "multipart/form-data; boundary=REAL"

	tests := []struct {
		name string
		body string
		want error
	}{
		{"over-cap field", multipartBody("REAL", "model", strings.Repeat("a", maxFormFieldBytes+1)), errFieldTooLarge},
		{"duplicated field", multipartBody("REAL", "model", modelA, "model", modelB), errAmbiguousMultipart},
		{"truncated body", "--REAL\r\nContent-Disposition: form-data;", errMalformedMultipart},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := doMultipart(t, h, "Bearer "+keyA, ct, tt.body)
			if rr.Code != http.StatusBadRequest || rr.Body.String() != tt.want.Error() {
				t.Fatalf("got %d %q, want 400 %q", rr.Code, rr.Body.String(), tt.want.Error())
			}
		})
	}
}

func do(t *testing.T, h *Handler, authHeader, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(body))
	if authHeader != "" {
		req.Header.Set("Authorization", authHeader)
	}
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	return rr
}

func TestServeHTTP(t *testing.T) {
	h := newHandler(fleet()...)
	bodyA := `{"model":"` + modelA + `","messages":[{"role":"user","content":"hi"}]}`

	tests := []struct {
		name        string
		auth, body  string
		wantCode    int
		wantCID     string // expected x-api-key-id on allow
		wantBackend string // expected x-ai-eg-backend (resolved workload) on allow
	}{
		{"no key", "", bodyA, http.StatusUnauthorized, "", ""},
		{"bogus key", "Bearer bogus", bodyA, http.StatusUnauthorized, "", ""},
		{"valid key for model", "Bearer " + keyA, bodyA, http.StatusOK, cidA, wlA},
		{"valid key wrong model", "Bearer " + keyA, `{"model":"` + modelB + `"}`, http.StatusUnauthorized, "", ""},
		{"no model", "Bearer " + keyA, `{"messages":[]}`, http.StatusForbidden, "", ""},
		{"invalid json", "Bearer " + keyA, `not json`, http.StatusBadRequest, "", ""},
		{"exact backend id", "Bearer " + keyB, `{"model":"` + modelB + `","backend":"` + wlB + `"}`, http.StatusOK, cidB, wlB},
		// Bodyless metadata request (e.g. GET /v1/models): authorized on the key alone.
		{"empty body valid key", "Bearer " + keyA, "", http.StatusOK, cidA, wlA},
		{"empty body no key", "", "", http.StatusUnauthorized, "", ""},
		{"empty body bogus key", "Bearer bogus", "", http.StatusUnauthorized, "", ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := do(t, h, tt.auth, tt.body)
			if rr.Code != tt.wantCode {
				t.Fatalf("status = %d, want %d (body %q)", rr.Code, tt.wantCode, rr.Body.String())
			}
			if got := rr.Header().Get(aigateway.ClientIDHeader); got != tt.wantCID {
				t.Fatalf("%s = %q, want %q", aigateway.ClientIDHeader, got, tt.wantCID)
			}
			if got := rr.Header().Get(aigateway.BackendHeader); got != tt.wantBackend {
				t.Fatalf("%s = %q, want %q", aigateway.BackendHeader, got, tt.wantBackend)
			}
		})
	}
}

// doWorkloadsReq issues an ext_authz check against the workloads handler (ServeWorkloads, served on
// the dedicated workloads port). The workloads route names the workload in the path.
func doWorkloadsReq(t *testing.T, h *Handler, method, path, authHeader, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	if authHeader != "" {
		req.Header.Set("Authorization", authHeader)
	}
	rr := httptest.NewRecorder()
	h.ServeWorkloads(rr, req)
	return rr
}

// TestServeWorkloads covers the workloads serving route (/{ns}/{workload-id}/...): the handler
// authorizes on the path's workload-id against the key's bound membership, deny-by-default.
func TestServeWorkloads(t *testing.T) {
	h := newHandler(fleet()...)
	pathA := "/" + ns + "/" + wlA + "/v1/chat/completions"
	bodyA := `{"model":"` + modelA + `","messages":[{"role":"user","content":"hi"}]}`

	tests := []struct {
		name                     string
		method, path, auth, body string
		wantCode                 int
		wantCID                  string
		wantBackend              string // x-ai-eg-backend (the resolved workload) forwarded on allow
	}{
		{"valid bound key", http.MethodPost, pathA, "Bearer " + keyA, bodyA, http.StatusOK, cidA, wlA},
		{"no key", http.MethodPost, pathA, "", bodyA, http.StatusUnauthorized, "", ""},
		{"bogus key", http.MethodPost, pathA, "Bearer bogus", bodyA, http.StatusUnauthorized, "", ""},
		{"key bound to a different workload", http.MethodPost, pathA, "Bearer " + keyB, bodyA, http.StatusUnauthorized, "", ""},
		// /v1/models under a workload path is authorized and passed through (200), not answered with
		// the ai-gateway key-scoped list (203).
		{"workloads /v1/models valid key", http.MethodGet, "/" + ns + "/" + wlA + "/v1/models", "Bearer " + keyA, "", http.StatusOK, cidA, wlA},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := doWorkloadsReq(t, h, tt.method, tt.path, tt.auth, tt.body)
			if rr.Code != tt.wantCode {
				t.Fatalf("status = %d, want %d (body %q)", rr.Code, tt.wantCode, rr.Body.String())
			}
			if got := rr.Header().Get(aigateway.ClientIDHeader); got != tt.wantCID {
				t.Fatalf("%s = %q, want %q", aigateway.ClientIDHeader, got, tt.wantCID)
			}
			if got := rr.Header().Get(aigateway.BackendHeader); got != tt.wantBackend {
				t.Fatalf("%s = %q, want %q", aigateway.BackendHeader, got, tt.wantBackend)
			}
		})
	}
}

// A Secret bound to the workload but WITHOUT the api-key contract label must not authorize —
// otherwise a tenant able to create Secrets could mint a key by labelling an arbitrary Secret with
// the bound-<workload-id> label. Guards the APIKeyLabel filter in authorize().
func TestServeWorkloads_RequiresAPIKeyLabel(t *testing.T) {
	rogue := keySecret("rogue", wlA, "token-proj-rogue", "rogue-key-value")
	lbls := rogue.GetLabels()
	delete(lbls, aigateway.APIKeyLabel) // bound-<wlA> stays; drop the api-key contract label
	rogue.SetLabels(lbls)
	h := newHandler(rogue)

	rr := doWorkloadsReq(t, h, http.MethodPost, "/"+ns+"/"+wlA+"/v1/chat/completions", "Bearer rogue-key-value", "")
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401 — a Secret without the api-key label must not authorize", rr.Code)
	}
}

// A workloads path too short to name /{namespace}/{workload-id} is refused, deny-by-default.
func TestServeWorkloads_UnresolvablePath(t *testing.T) {
	h := newHandler(fleet()...)
	rr := doWorkloadsReq(t, h, http.MethodGet, "/onlyoneseg", "Bearer "+keyA, "")
	if rr.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want 403 for an unresolvable workloads path", rr.Code)
	}
}

// TestServeHTTP_AuthorizesBodyNotPath is the regression guard for the cross-workload bypass: the
// ai-gateway handler (ServeHTTP) must authorize on the request BODY, never on the request path — even
// when the path names a workload the caller IS bound to. A key bound to workload A must not reach
// model B by putting A's id in the path and B's model in the body. (Workloads auth lives on a
// separate port; ServeHTTP never classifies by path, so the path segment is irrelevant here.)
func TestServeHTTP_AuthorizesBodyNotPath(t *testing.T) {
	h := newHandler(fleet()...)
	// Path names workload A (keyA is bound to it); body names model B (keyA is NOT bound to it).
	req := httptest.NewRequest(http.MethodPost, "/"+ns+"/"+wlA+"/v1/chat/completions",
		strings.NewReader(`{"model":"`+modelB+`"}`))
	req.Header.Set("Authorization", "Bearer "+keyA)
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401 — key A must not reach model B by naming workload A in the path (body %q)", rr.Code, rr.Body.String())
	}
}

// workloadIDFromPath is only reached via the workloads port, so it is a pure /{ns}/{workload-id}/...
// parser — it does not classify ai-gateway paths (the port already did). The workload id is segment 2
// verbatim, whatever its shape.
func TestWorkloadIDFromPath(t *testing.T) {
	tests := []struct {
		path   string
		wantID string
		wantOK bool
	}{
		{"/proj/wl-aaaa/v1/chat/completions", "wl-aaaa", true},
		{"/proj/wl-aaaa/v1/models", "wl-aaaa", true},
		{"/proj/wl-aaaa", "wl-aaaa", true},
		{"/proj/wl-aaaa/", "wl-aaaa", true}, // trailing slash tolerated
		// Workload id is taken verbatim regardless of shape (UUID or not).
		{"/proj/123e4567-e89b-12d3-a456-426614174000/v1/chat/completions", "123e4567-e89b-12d3-a456-426614174000", true},
		{"/proj//rest", "", false}, // empty workload-id segment
		{"/onlyone", "", false},
		{"/", "", false},
		{"", "", false},
	}
	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			id, ok := workloadIDFromPath(tt.path)
			if ok != tt.wantOK || id != tt.wantID {
				t.Fatalf("workloadIDFromPath(%q) = (%q, %v), want (%q, %v)", tt.path, id, ok, tt.wantID, tt.wantOK)
			}
		})
	}
}

// getModels issues a GET /v1/models ext_authz check with the given bearer and returns the recorder.
func getModels(t *testing.T, h *Handler, authHeader string) *httptest.ResponseRecorder {
	t.Helper()
	return getModelsPath(t, h, "/v1/models", authHeader)
}

// getModelsPath issues a GET ext_authz check for an arbitrary path with the given bearer.
func getModelsPath(t *testing.T, h *Handler, path, authHeader string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	if authHeader != "" {
		req.Header.Set("Authorization", authHeader)
	}
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	return rr
}

// GET /v1/models returns a 203 with the key-scoped model list (203 short-circuits Envoy's built-in
// unfiltered list); an unknown/missing key is rejected before any list is produced.
func TestServeHTTP_Models(t *testing.T) {
	h := newHandler(fleet()...)

	t.Run("valid key gets its models, filtered", func(t *testing.T) {
		rr := getModels(t, h, "Bearer "+keyA)
		if rr.Code != http.StatusNonAuthoritativeInfo {
			t.Fatalf("status = %d, want 203 (body %q)", rr.Code, rr.Body.String())
		}
		if ct := rr.Header().Get("Content-Type"); ct != "application/json" {
			t.Errorf("content-type = %q, want application/json", ct)
		}
		var list models.List
		if err := json.Unmarshal(rr.Body.Bytes(), &list); err != nil {
			t.Fatalf("decode: %v (body %q)", err, rr.Body.String())
		}
		if len(list.Data) != 1 || list.Data[0].ID != modelA {
			t.Fatalf("models = %+v, want only %q", list.Data, modelA)
		}
	})

	t.Run("no key -> 401", func(t *testing.T) {
		if rr := getModels(t, h, ""); rr.Code != http.StatusUnauthorized {
			t.Fatalf("status = %d, want 401", rr.Code)
		}
	})

	t.Run("bogus key -> 401, no list", func(t *testing.T) {
		rr := getModels(t, h, "Bearer bogus")
		if rr.Code != http.StatusUnauthorized {
			t.Fatalf("status = %d, want 401", rr.Code)
		}
	})

	// A trailing slash must still be intercepted; otherwise the request falls through to the AI
	// gateway's built-in unfiltered list, defeating the per-key scoping.
	t.Run("trailing slash is intercepted", func(t *testing.T) {
		rr := getModelsPath(t, h, "/v1/models/", "Bearer "+keyA)
		if rr.Code != http.StatusNonAuthoritativeInfo {
			t.Fatalf("status = %d, want 203 (body %q)", rr.Code, rr.Body.String())
		}
	})
}

func TestBearerToken(t *testing.T) {
	cases := map[string]string{
		"Bearer abc":  "abc",
		"bearer abc":  "abc",
		"BEARER  abc": "abc",
		"abc":         "abc",
		"":            "",
		"Bearer ":     "",
	}
	for in, want := range cases {
		if got := bearerToken(in); got != want {
			t.Errorf("bearerToken(%q) = %q, want %q", in, got, want)
		}
	}
}
