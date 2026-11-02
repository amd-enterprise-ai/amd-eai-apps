// Copyright © Advanced Micro Devices, Inc., or its affiliates.
//
// SPDX-License-Identifier: MIT

// Package authz implements a body-aware ext_authz HTTP backend for the AI gateway.
//
// The standard OpenAI client contract carries the model in the JSON body with no routing
// headers, so Envoy AI Gateway only resolves the model/backend after its ext_proc reads the
// body — which is after native per-route apiKeyAuth has already run. That leaves the
// header-less path unauthenticated (a request with no key or a bogus key would otherwise be
// served). Envoy Gateway's extAuth (with bodyToExtAuth) closes the gap by calling this
// handler, which authorizes on the body using the SAME membership the per-backend
// SecurityPolicies use: a key Secret bound to a model carries the
// apikey.eai.amd.com/bound-<workload-id> label. Keys stay in Secrets; nothing is baked into
// config.
//
// This handler backs two Envoy Gateway SecurityPolicy families, served on two DIFFERENT ports so the
// handler is told which family a request belongs to by the port its ext_authz check arrives on (set
// by the matching policy's backendRef) rather than by inferring it from the client-controlled URL:
//
//  1. AI-gateway (ai.<domain>, /v1/..., bodyToExtAuth) on AuthzPort — ServeHTTP: a supplement to the
//     native header path, authorizing header-less (model-in-body) and keyless-model requests on the
//     body, since a header-carrying request matches a per-backend SecurityPolicy that overrides the
//     gateway-level extAuth and never reaches here. Lasts until Envoy AI Gateway supports body-path
//     client auth.
//  2. Workloads (workloads.<domain>, /{namespace}/{workload-id}/..., no body) on WorkloadsAuthzPort —
//     ServeWorkloads: the sole authenticator for the workloads serving route, authorizing on the
//     path's workload-id against the key's bound-<workload-id> membership, deny-by-default.
//
// The handler also serves GET /v1/models: because it already runs in the request path ahead of the
// AI gateway's extProc, it returns a key-scoped model list (via package models) directly, instead
// of letting the request through to Envoy AI Gateway's built-in unfiltered list. This is done here
// rather than with a dedicated /v1/models route because attaching a foreign route to the
// AI-gateway-managed Gateway destabilises its extProc filter placement and breaks inference.
package authz

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"mime/multipart"
	"net/http"
	"strings"

	"github.com/go-logr/logr"
	"github.com/silogen/ai-gateway-discovery/internal/aigateway"
	"github.com/silogen/ai-gateway-discovery/internal/apikey"
	"github.com/silogen/ai-gateway-discovery/internal/common"
	"github.com/silogen/ai-gateway-discovery/internal/config"
	"github.com/silogen/ai-gateway-discovery/internal/models"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"sigs.k8s.io/controller-runtime/pkg/client"
)

// bodyLimit is the ceiling this handler reads a request body at. It tracks the same value the
// catch-all SecurityPolicy renders into bodyToExtAuth.maxRequestBytes — see
// common.DefaultBodyAuthMaxRequestBytes. Nothing guarantees the two agree: this handler is a plain
// ClusterIP any in-cluster pod can reach directly, and the gateway-scoped policy lives in another
// repo, so a request larger than this arrives here whether or not Envoy meant to allow it. Over the
// limit is answered with 413 rather than a truncated parse. Falls back to the default when the
// config leaves the field unset.
func (h *Handler) bodyLimit() int64 {
	if h.Config.BodyAuthMaxRequestBytes > 0 {
		return int64(h.Config.BodyAuthMaxRequestBytes)
	}
	return int64(common.DefaultBodyAuthMaxRequestBytes)
}

// secretListGVK matches how the reconciler watches Secrets (unstructured), so reads here hit
// the same manager cache informer rather than spinning up a second one.
var secretListGVK = schema.GroupVersionKind{Version: "v1", Kind: "SecretList"}

// Handler authorizes header-less inference requests on their JSON body. It is served as an
// Envoy Gateway extAuth (HTTP) backend and reads from the controller manager's cache.
type Handler struct {
	Client client.Client
	Config *config.ControllerConfig
	Log    logr.Logger
}

type inferenceBody struct {
	Model   string `json:"model"`
	Backend string `json:"backend"`
}

// ServeHTTP is the ai-gateway (ai.<domain>) authorizer: it authorizes header-less/body-only requests
// on the request body and serves GET /v1/models. It is reached via the gateway-scoped and per-model
// catch-all SecurityPolicies, which target AuthzPort. Workloads requests never reach here — they
// target WorkloadsAuthzPort and are handled by ServeWorkloads. The two families are told apart by
// which port the ext_authz check arrived on (set by the matching policy's backendRef), not by the
// request path — a client on ai.<domain> controls its URL, so any path-based classifier is forgeable,
// but it cannot choose the port.
func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	key := bearerToken(r.Header.Get("Authorization"))
	// Establish membership before reading anything. The body is buffered whole, so a caller that
	// reaches the read makes this pod allocate up to the full ceiling; checking only for a present
	// header would leave that reachable by anyone sending an arbitrary bearer token. Membership
	// needs no body: authorize with an empty model and backend resolves to every managed backend,
	// so it answers "is this key bound to anything at all" and nothing more. The per-model decision
	// still happens below, once the body names one.
	if key == "" {
		h.reply(w, http.StatusUnauthorized, "missing api key", "", "")
		return
	}
	if _, _, ok := h.authorize(r.Context(), "", "", key); !ok {
		h.reply(w, http.StatusUnauthorized, "key not authorized", "", "")
		return
	}

	// One byte past the limit distinguishes "ended naturally" from "cut short"; io.LimitReader
	// truncates silently, so without it an oversized body reaches json.Unmarshal cut mid-object and
	// is rejected as malformed rather than as too large.
	limit := h.bodyLimit()
	body, err := io.ReadAll(io.LimitReader(r.Body, limit+1))
	if err != nil {
		h.reply(w, http.StatusBadRequest, "cannot read body", "", "")
		return
	}
	if int64(len(body)) > limit {
		h.reply(w, http.StatusRequestEntityTooLarge, "request body too large", "", "")
		return
	}
	// The body is optional. An inference request carries a JSON body naming a model; a
	// metadata request (e.g. GET /v1/models) carries none. Only parse a body when one is
	// present — a bodyless request is authorized on the key alone, the same way native
	// apiKeyAuth (and cluster-auth before it) gate these routes: validate the credential,
	// never require a body.
	var b inferenceBody
	if len(bytes.TrimSpace(body)) > 0 {
		// Not every OpenAI endpoint posts JSON. /v1/audio/transcriptions and the other audio
		// endpoints post multipart/form-data, where the model is a form field rather than a JSON
		// key. Unmarshalling those as JSON fails on the leading "--" of the boundary, so a
		// transcription request used to be rejected here before it could be authorized at all.
		fields, isMultipart, parseErr := parseMultipartBody(body, r.Header.Get("Content-Type"))
		switch {
		case parseErr != nil:
			// A duplicated model/backend part, or a body Go could not parse to completion: either
			// way the value authorized here could differ from the one the upstream resolves, so
			// refuse rather than authorize a guess. parseErr's text is the deny reason.
			h.reply(w, http.StatusBadRequest, parseErr.Error(), "", "")
			return
		case isMultipart:
			b = fields
		default:
			if err := json.Unmarshal(body, &b); err != nil {
				h.reply(w, http.StatusBadRequest, "invalid json body", "", "")
				return
			}
		}
		// A present body must name a model (or backend) — a malformed inference request.
		if b.Model == "" && b.Backend == "" {
			h.reply(w, http.StatusForbidden, "no model in request body", "", "")
			return
		}
	}
	// GET /v1/models: return the key-scoped model list directly instead of allowing the request
	// through to Envoy AI Gateway's built-in (unfiltered) list. See replyModels for why this is a
	// 203 rather than a 200.
	if isModelsRequest(r) {
		// The membership gate above already rejected a key bound to no deployed model, which is
		// what this route needs before returning any list.
		list, err := models.Build(r.Context(), h.Client, h.Config, key)
		if err != nil {
			h.Log.Error(err, "building models list")
			h.reply(w, http.StatusInternalServerError, "internal error", "", "")
			return
		}
		h.replyModels(w, list)
		return
	}
	// For a bodyless request (model and backend empty) authorize resolves to every managed
	// backend, so any valid bound key is accepted — enough to list models on /v1/models.
	clientID, workloadID, ok := h.authorize(r.Context(), b.Model, b.Backend, key)
	if !ok {
		h.reply(w, http.StatusUnauthorized, "key not authorized for this model", "", "")
		return
	}
	// Forward the resolved backend (workload id) so the ext_proc can stamp aim_service_id on the
	// header-less path — the gateway itself can't resolve it from (EDS) endpoint metadata.
	// Exact for single-backend models; approximate when several backends share a model name
	// (authorize picks the key's bound workload, which may differ from the EPP-routed one).
	h.reply(w, http.StatusOK, "ok", clientID, workloadID)
}

// ServeWorkloads is the workloads-route (workloads.<domain>/{namespace}/{workload-id}/...)
// authorizer. It is served on WorkloadsAuthzPort, which only the workloads SecurityPolicy targets, so
// every request here is by construction a workloads request — the port is set by that policy's
// backendRef, not by the client, so this cannot be reached by forging a URL on ai.<domain>. It
// authorizes the path's workload-id against the key's bound-<workload-id> membership; no body is read.
// Deny-by-default (absent/unbound key rejected) — it is the sole authenticator for the workloads
// route, which rides the shared https gateway with no default-deny backstop.
func (h *Handler) ServeWorkloads(w http.ResponseWriter, r *http.Request) {
	workloadID, ok := workloadIDFromPath(r.URL.Path)
	if !ok {
		h.reply(w, http.StatusForbidden, "cannot resolve workload from path", "", "")
		return
	}
	key := bearerToken(r.Header.Get("Authorization"))
	if key == "" {
		h.reply(w, http.StatusUnauthorized, "missing api key", "", "")
		return
	}
	clientID, _, authorized := h.authorize(r.Context(), "", workloadID, key)
	if !authorized {
		h.reply(w, http.StatusUnauthorized, "key not authorized for this workload", "", "")
		return
	}
	h.reply(w, http.StatusOK, "ok", clientID, workloadID)
}

// authorize returns the matched key's client id and the workload id it authorized against
// when the presented key is bound to the requested model/backend. An explicit backend (workload
// id) names one model exactly; a
// model-only request (no backend id) resolves to every backend serving that model, and the
// key must be authorized for at least one of them.
//
// Membership is the bound-<workload-id> label alone, matched cluster-wide — the same loose
// check every caller uses. On the ai-gateway path this handler is a supplement for the header-less
// (model-in-body) and empty request paths; header-carrying requests there are authorized natively by
// the per-backend SecurityPolicy (which overrides the gateway-level extAuth) and never reach here.
// On the workloads path the caller passes the path's workload-id as backend, so this is the sole
// authenticator.
func (h *Handler) authorize(ctx context.Context, model, backend, key string) (string, string, bool) {
	for _, workloadID := range h.targetWorkloadIDs(ctx, model, backend) {
		list := &unstructured.UnstructuredList{}
		list.SetGroupVersionKind(secretListGVK)
		// Match the api-key contract label as well as the bound-<workload-id> membership label, so
		// only Secrets that are actually AIWB API keys count — otherwise a tenant able to create
		// Secrets could mint a "key" by labelling an arbitrary Secret bound to a workload.
		if err := h.Client.List(ctx, list, client.MatchingLabels{
			aigateway.BoundLabel(workloadID): "true",
			aigateway.APIKeyLabel:            "true",
		}); err != nil {
			h.Log.Error(err, "listing bound key secrets", "workloadID", workloadID)
			continue
		}
		for i := range list.Items {
			data, found, err := unstructured.NestedStringMap(list.Items[i].Object, "data")
			if !found || err != nil {
				continue
			}
			if clientID, ok := apikey.MatchClientID(data, key); ok {
				return clientID, workloadID, true
			}
		}
	}
	return "", "", false
}

// targetWorkloadIDs resolves the request to the workload ids whose bound keys may authorize
// it: the explicit backend id when present (taken as-is — it names one exact model), otherwise
// every managed InferenceService serving the named model (model names can collide across
// backends, so this may be more than one). An empty model (a bodyless metadata request like
// /v1/models) resolves to every managed backend, so any valid bound key authorizes it.
func (h *Handler) targetWorkloadIDs(ctx context.Context, model, backend string) []string {
	if backend != "" {
		return []string{backend}
	}
	list := &unstructured.UnstructuredList{}
	listGVK := aigateway.InferenceServiceGVK
	listGVK.Kind += "List"
	list.SetGroupVersionKind(listGVK)
	if err := h.Client.List(ctx, list, client.MatchingLabels{h.Config.ManagedLabelName: h.Config.ManagedLabelValue}); err != nil {
		h.Log.Error(err, "listing inference services", "model", model)
		return nil
	}
	seen := map[string]struct{}{}
	ids := make([]string, 0, len(list.Items))
	for i := range list.Items {
		is := &list.Items[i]
		if model != "" && is.GetAnnotations()[h.Config.ModelNameAnnotation] != model {
			continue
		}
		workloadID := is.GetLabels()[h.Config.WorkloadIDLabel]
		if workloadID == "" {
			continue
		}
		if _, dup := seen[workloadID]; dup {
			continue
		}
		seen[workloadID] = struct{}{}
		ids = append(ids, workloadID)
	}
	return ids
}

func (h *Handler) reply(w http.ResponseWriter, code int, msg, clientID, backendID string) {
	if clientID != "" {
		// Forwarded upstream via extAuth headersToBackend for per-key metrics attribution.
		w.Header().Set(aigateway.ClientIDHeader, clientID)
	}
	if backendID != "" {
		// Forwarded upstream via extAuth headersToBackend so the ext_proc stamps aim_service_id
		// on the header-less path, where the gateway can't resolve the backend from EDS metadata.
		w.Header().Set(aigateway.BackendHeader, backendID)
	}
	w.WriteHeader(code)
	_, _ = io.WriteString(w, msg)
}

// maxFormFieldBytes caps a single multipart form field this handler will read. The fields it
// wants (model, backend) are short identifiers.
//
// This does not bound the handler's memory: ServeHTTP has already buffered the whole request body,
// up to bodyLimit, before any parsing happens, so the file bytes of an audio upload are in memory
// regardless. What skipping the file part avoids is a second copy of them.
const maxFormFieldBytes = 4 * 1024

// Deny reasons parseMultipartBody returns for a multipart body the handler will not authorize. All
// map to 400: a duplicated scalar part, a body Go could not parse or read to completion, and a
// scalar field larger than maxFormFieldBytes. Their text is the client-facing response, so it must
// stay free of internal detail.
var (
	errAmbiguousMultipart = errors.New("ambiguous multipart body")
	errMalformedMultipart = errors.New("malformed multipart body")
	errFieldTooLarge      = errors.New("multipart field too large")
)

// parseMultipartBody extracts the model/backend form fields from a multipart/form-data body,
// reporting whether the body was multipart at all. Audio endpoints (/v1/audio/transcriptions and
// friends) post the model as a form field, so this is the equivalent of the JSON path for them.
//
// The boundary comes from Content-Type and from nowhere else. It must not be recovered from the
// body: RFC 2046 §5.1.1 requires a reader to discard everything before the first real boundary
// delimiter, so a body opening with a decoy document under a made-up boundary parses one way here
// and another way in every compliant parser downstream. A client could then be authorized for the
// model named in the decoy while the request that proceeds names a different one. Deciding
// authorization on a parse the client can decouple from everyone else's is the bug this guard
// exists to prevent. Without the header the body is simply not multipart as far as this handler is
// concerned, and it falls through to the JSON path, which denies.
//
// The file part is skipped rather than copied: only the short scalar fields are consumed, so
// authorizing a large upload costs no memory beyond the body ServeHTTP has already buffered. The
// body itself is still held in full, up to bodyLimit.
//
// A model or backend part appearing twice is refused, not resolved. Downstream parsers disagree on
// which occurrence a served request uses — Starlette/FastAPI take the last — so any pick here lets
// the client decouple the value this guard authorizes from the value the server is asked to serve.
// Detecting it on the part's presence (not its value) also rejects an empty-then-nonempty pair,
// which a value-based guard would silently collapse to the second value, and treats a "model"/
// "backend" part carrying a filename as an occurrence too — its bytes are a file the server never
// reads as the model, but pairing it with a scalar of the same name is the same ambiguity. Parts
// named anything else (the audio upload included) are neither read nor counted.
//
// A parse or field-read error is a refusal, not an end-of-body: breaking on any error would let a
// client hide a second model part behind a part Go refuses to parse, and authorize on the prefix
// read so far — deciding on bytes this code could not finish reading, which a downstream parser that
// recovers past the break would then diverge from.
//
// io.EOF ends the loop, but it is not on its own proof the body was complete: Go returns io.EOF both
// at the closing "--boundary--" delimiter and when the body is cut mid-header-block, so the parts
// read before a truncated tail would otherwise be authorized on a body the sender never finished.
// After the loop, the closing delimiter must therefore be present, or the body is refused. Together
// these make authorization decide only on a fully-delimited body, and mirror the JSON path, which
// rejects a malformed body outright.
//
// isMultipart reports whether the body was multipart at all (a non-multipart body falls through to
// the JSON path, which denies). parseErr is non-nil when the body must be denied — a duplicated
// scalar part (errAmbiguousMultipart), a parse/read failure (errMalformedMultipart), or an over-cap
// field (errFieldTooLarge); when set, the returned fields are empty.
func parseMultipartBody(body []byte, contentType string) (fields inferenceBody, isMultipart bool, parseErr error) {
	boundary, ok := multipartBoundary(contentType)
	if !ok {
		return inferenceBody{}, false, nil
	}
	reader := multipart.NewReader(bytes.NewReader(body), boundary)
	var b inferenceBody
	var modelSeen, backendSeen bool
	for {
		// NextRawPart, not NextPart: NextPart transparently decodes a quoted-printable
		// Content-Transfer-Encoding, which would authorize a value other than the bytes on the wire
		// that a form-data parser reads.
		part, err := reader.NextRawPart()
		if errors.Is(err, io.EOF) {
			break // no more parts — or a truncated tail, which the close-delimiter check below denies
		}
		if err != nil {
			return inferenceBody{}, true, errMalformedMultipart
		}
		// A part carrying a filename is a file upload, not a scalar value — even when its form name
		// is "model"/"backend". Its bytes are never read as the model: authorizing on the first 4 KiB
		// of an upload would decide on content the server resolves as a file, not the model. But it
		// still counts as an occurrence, so a "model"/"backend" name appearing both as a scalar and
		// as a file part is refused as ambiguous rather than silently authorized on the scalar — the
		// divergence stays closed whatever the downstream parser makes of the file part.
		scalar := !hasFilenameParam(part)
		// RFC 7578 forbids Content-Transfer-Encoding on form-data parts, and parsers disagree on
		// whether to honour it, so a scalar model/backend part carrying one has no single value. The
		// header's presence decides, not Get's value: Get returns only the first occurrence and ""
		// for an empty one, so an empty header, or an empty one followed by "quoted-printable",
		// would slip past a value check.
		_, hasCTE := part.Header["Content-Transfer-Encoding"]
		if scalar && hasCTE && (part.FormName() == "model" || part.FormName() == "backend") {
			_ = part.Close()
			return inferenceBody{}, true, errMalformedMultipart
		}
		switch part.FormName() {
		case "model":
			if modelSeen {
				_ = part.Close()
				return inferenceBody{}, true, errAmbiguousMultipart
			}
			modelSeen = true
			if scalar {
				b.Model, err = readFormField(part)
			}
		case "backend":
			if backendSeen {
				_ = part.Close()
				return inferenceBody{}, true, errAmbiguousMultipart
			}
			backendSeen = true
			if scalar {
				b.Backend, err = readFormField(part)
			}
		}
		_ = part.Close()
		if errors.Is(err, errFieldTooLarge) {
			return inferenceBody{}, true, errFieldTooLarge
		}
		if err != nil {
			return inferenceBody{}, true, errMalformedMultipart
		}
	}
	// The loop exited on io.EOF, which Go also returns for a body cut mid-header-block. Require a
	// real closing "--boundary--" delimiter so a truncated body is denied rather than authorized on
	// the parts read before the cut. hasCloseDelimiter mirrors the reader's latched newline and only
	// looks past the first delimiter, so preamble lines, file-part content like "--boundary--X", and
	// markers with the wrong newline cannot fake completeness.
	if !hasCloseDelimiter(body, boundary) {
		return inferenceBody{}, true, errMalformedMultipart
	}
	return b, true, nil
}

// hasCloseDelimiter reports whether Go's multipart reader would have ended body at a real close
// delimiter rather than at a truncated tail. It mirrors the reader's state machine instead of
// scanning for the delimiter anywhere:
//
//   - The newline the reader uses is latched from the first boundary delimiter line, exactly as
//     isBoundaryDelimiterLine does: "--boundary" plus optional spaces/tabs, ending in CRLF, or in a
//     bare LF (which switches the reader to LF mode).
//   - Only a close after that first delimiter counts. Before it the reader is skipping preamble, so
//     a "--boundary--" line there is not where the message ended.
//   - The close must be that newline followed by "--boundary--", then optional spaces/tabs, then
//     that same newline or end of body — isFinalBoundary's rule. A bare LF in a CRLF body, a CRLF in
//     an LF body, or a trailing byte ("--boundary--X") makes it content, not a close.
//
// After the first delimiter, any sequence meeting that rule ends the part the reader is in (its
// scan stops at newline + "--boundary") and is then accepted as the final boundary, so the reader
// cannot have read past one; with none present, the io.EOF came from a truncated body.
func hasCloseDelimiter(body []byte, boundary string) bool {
	nl, afterFirst, ok := firstDelimiterLine(body, boundary)
	if !ok {
		return false
	}
	marker := append(append([]byte{}, nl...), "--"+boundary+"--"...)
	// Start at the first delimiter line's own newline, so a close directly after it is found too.
	search := body[afterFirst-len(nl):]
	for off := 0; ; {
		i := bytes.Index(search[off:], marker)
		if i < 0 {
			return false
		}
		rest := bytes.TrimLeft(search[off+i+len(marker):], " \t")
		if len(rest) == 0 || bytes.HasPrefix(rest, nl) {
			return true
		}
		off += i + len(marker)
	}
}

// firstDelimiterLine finds the first line the multipart reader would accept as a boundary
// delimiter, returning the newline it latches from it and the offset just past that line.
func firstDelimiterLine(body []byte, boundary string) (nl []byte, end int, ok bool) {
	dash := []byte("--" + boundary)
	for off := 0; off < len(body); {
		end := len(body)
		if i := bytes.IndexByte(body[off:], '\n'); i >= 0 {
			end = off + i + 1
		}
		if line := body[off:end]; bytes.HasPrefix(line, dash) {
			switch rest := bytes.TrimLeft(line[len(dash):], " \t"); {
			case bytes.Equal(rest, []byte("\r\n")):
				return []byte("\r\n"), end, true
			case bytes.Equal(rest, []byte("\n")):
				return []byte("\n"), end, true
			}
		}
		off = end
	}
	return nil, 0, false
}

// readFormField reads a scalar form field, failing closed if it exceeds maxFormFieldBytes rather
// than silently keeping the prefix. io.LimitReader stops at the cap with a normal EOF, so reading
// exactly the cap could not tell a field that fit from one truncated at the boundary: the handler
// would authorize the prefix while the downstream parser reads the whole value — the parser
// divergence this guard exists to prevent. Reading one byte past the cap makes the overflow
// observable, and an over-cap field is denied.
//
// The value is returned exactly as sent, untrimmed: the downstream form parser and the JSON path
// both keep surrounding whitespace, so trimming here would authorize "m" while " m " is served.
func readFormField(part *multipart.Part) (string, error) {
	value, err := io.ReadAll(io.LimitReader(part, maxFormFieldBytes+1))
	if err != nil {
		return "", err
	}
	if len(value) > maxFormFieldBytes {
		return "", errFieldTooLarge
	}
	return string(value), nil
}

// hasFilenameParam reports whether the part's Content-Disposition carries a filename parameter,
// which marks it a file upload downstream even when the parameter is empty (filename=""). It is not
// the same as Part.FileName() != "": FileName normalizes both an absent filename and filename="" to
// "", so a present-but-empty filename would slip through a value check and be read as a scalar,
// diverging from every downstream parser that treats it as a file. Presence of the parameter, not
// its value, is what decides.
func hasFilenameParam(part *multipart.Part) bool {
	_, params, err := mime.ParseMediaType(part.Header.Get("Content-Disposition"))
	if err != nil {
		return false
	}
	_, ok := params["filename"]
	return ok
}

// multipartBoundary returns the boundary declared by Content-Type, and whether the request is a
// form-data body this handler should parse as scalar fields. Only "multipart/form-data" qualifies:
// the audio endpoints post that subtype and the downstream server reads its parts as form fields.
// Other multipart/* subtypes (mixed, byteranges, …) are not form-data downstream, so treating their
// parts as a "model" field would authorize on something the server never reads that way — the
// divergence this guard prevents. They fall through to the JSON path, which denies. The
// SecurityPolicies that route bodies here list content-type in headersToExtAuth so the header
// actually arrives; see BuildCatchAllExtAuthSecurityPolicy.
func multipartBoundary(contentType string) (string, bool) {
	if contentType == "" {
		return "", false
	}
	mediaType, params, err := mime.ParseMediaType(contentType)
	if err != nil || mediaType != "multipart/form-data" {
		return "", false
	}
	// RFC 2046 §5.1.1 limits a boundary to 1–70 characters, the same limit Go's
	// multipart.Writer.SetBoundary enforces. Content-Type is client-controlled, so a longer one is
	// not treated as multipart rather than left to however the reader happens to cope with it.
	boundary := params["boundary"]
	return boundary, boundary != "" && len(boundary) <= maxBoundaryLen
}

const maxBoundaryLen = 70

// bearerToken extracts the raw key from an Authorization header value. Thin alias over
// apikey.Bearer so the authorization path and the models path parse the credential identically.
func bearerToken(header string) string {
	return apikey.Bearer(header)
}

// isModelsRequest reports whether the ext_authz call is for GET /v1/models. Envoy forwards the
// original method and path on the check request, so both are available here. The path is matched by
// suffix (tolerating any prefix the gateway may prepend) after trimming a single trailing slash, so
// "/v1/models/" is intercepted too and cannot fall through to the AI gateway's unfiltered list.
func isModelsRequest(r *http.Request) bool {
	if r.Method != http.MethodGet {
		return false
	}
	return strings.HasSuffix(strings.TrimSuffix(r.URL.Path, "/"), "/v1/models")
}

// workloadIDFromPath extracts the workload id from a workloads serving-route path of shape
// /{namespace}/{workload-id}/... (the aim-engine pathTemplate). It is only called by ServeWorkloads,
// i.e. for requests that already arrived on the workloads ext_authz port, so it does not need to
// distinguish ai-gateway paths — the port did that. It returns ("", false) for a path too short to
// carry a workload id.
func workloadIDFromPath(path string) (string, bool) {
	segs := strings.Split(strings.Trim(path, "/"), "/")
	// After trimming slashes, segs[0] is only empty for the empty path (caught by len < 2). The
	// segs[1] == "" guard is meaningful: e.g. "/ns//rest" → ["ns","","rest"].
	if len(segs) < 2 || segs[1] == "" {
		return "", false
	}
	return segs[1], true
}

// replyModels returns the key-scoped model list to the client.
//
// Envoy's ext_authz treats a literal 200 as "allow — continue to the next filter", which is exactly
// what lets /v1/models fall through to the AI gateway's built-in unfiltered list today. Any other
// status makes Envoy relay this auth response — status, headers, and body — straight to the client
// and stop. So we cannot emit a literal 200; 203 (Non-Authoritative Information — the response was
// transformed by a proxy, which is literally the case) is a success the OpenAI SDKs accept while
// signalling Envoy to short-circuit. The JSON body is the filtered list.
func (h *Handler) replyModels(w http.ResponseWriter, list models.List) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusNonAuthoritativeInfo) // 203
	if err := json.NewEncoder(w).Encode(list); err != nil {
		h.Log.Error(err, "encoding models response")
	}
}
