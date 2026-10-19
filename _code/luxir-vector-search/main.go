package main

// Hybrid search over the same Algolia ecommerce data as the hello-world
// post: a lexical simple_query, a kNN over the embedding_v field, and the
// two fused with reciprocal rank fusion. The engine is Luxir 0.1.0 over
// gRPC; the query vector comes from the Zig embedder in this directory.

import (
	"bufio"
	"bytes"
	"context"
	"embed"
	"encoding/json"
	"flag"
	"fmt"
	"html/template"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"luxir-vector-search/luxirpb"
)

const (
	collection = "products"
	pageSize   = 12
	// Default candidate pool per source. The docs are explicit that a
	// document outside a source's limit cannot contribute to the fusion.
	defaultPool = 200
)

type product struct {
	ID         string
	Title      string
	Desc       string
	Brand      string
	Categories []string
	Price      float64
	Reviews    int
	Image      string
	Score      float64
}

type bucket struct {
	Val   string
	Count int
}

type facetView struct {
	Label  string
	Count  int
	Active bool
	URL    string
}

type chip struct {
	Label string
	URL   string
}

type modeOption struct {
	Key   string
	Label string
	URL   string
}

// state is everything the URL carries. Mode picks the ranking, Pool sizes
// each source's candidate window.
type state struct {
	Q          string
	Brands     []string
	Categories []string
	Prices     []string
	Sort       string
	Mode       string
	Pool       int
	Page       int
}

func (s state) withCategory(v string) string {
	s.Categories = []string{v}
	s.Page = 1
	return s.href()
}

func (s state) withoutCategory(v string) string {
	s.Categories = toggleVal(s.Categories, v)
	s.Page = 1
	return s.href()
}

func parseState(r *http.Request) state {
	q := r.URL.Query()
	page, _ := strconv.Atoi(q.Get("page"))
	if page < 1 {
		page = 1
	}
	pool, err := strconv.Atoi(q.Get("pool"))
	if err != nil || pool <= 0 {
		pool = defaultPool
	}
	return state{
		Q:          q.Get("q"),
		Brands:     q["brand"],
		Categories: q["category"],
		Prices:     q["price"],
		Sort:       sortParam(q.Get("sort")),
		Mode:       modeParam(q.Get("mode")),
		Pool:       pool,
		Page:       page,
	}
}

func sortParam(v string) string {
	if _, ok := sortSpecs[v]; ok {
		return v
	}
	return ""
}

func modeParam(v string) string {
	switch v {
	case "words", "vectors", "hybrid":
		return v
	}
	return "hybrid"
}

var sortSpecs = map[string]*luxirpb.SortSpec{
	"price_asc":    {Expr: "price_f", Dir: luxirpb.SortSpec_ASC},
	"price_desc":   {Expr: "price_f", Dir: luxirpb.SortSpec_DESC},
	"reviews_desc": {Expr: "reviews_i", Dir: luxirpb.SortSpec_DESC},
}

var sortOptions = []struct{ key, label string }{
	{"", "Relevance"},
	{"price_asc", "Price ↑"},
	{"price_desc", "Price ↓"},
	{"reviews_desc", "Most reviewed"},
}

// poolOptions is the recall knob: how many ranked documents each source
// contributes before the two lists are fused.
var poolOptions = []int{20, 50, 200, 500}

var priceBuckets = []struct {
	Label    string
	Min, Max *float64
}{
	{"Under $50", nil, ptr(50)},
	{"$50 to $100", ptr(50), ptr(100)},
	{"$100 to $300", ptr(100), ptr(300)},
	{"$300 & up", ptr(300), nil},
}

func ptr(v float64) *float64 { return &v }

func toggleVal(list []string, v string) []string {
	out := []string{}
	for _, item := range list {
		if item != v {
			out = append(out, item)
		}
	}
	if len(out) == len(list) {
		out = append(out, v)
	}
	return out
}

func contains(list []string, v string) bool {
	for _, item := range list {
		if item == v {
			return true
		}
	}
	return false
}

func (s state) toggle(field, v string) string {
	s.Page = 1
	switch field {
	case "brand":
		s.Brands = toggleVal(s.Brands, v)
	case "category":
		s.Categories = toggleVal(s.Categories, v)
	case "price":
		s.Prices = toggleVal(s.Prices, v)
	case "sort":
		s.Sort = v
	case "mode":
		s.Mode = v
	case "pool":
		s.Pool, _ = strconv.Atoi(v)
	}
	return s.href()
}

func (s state) href() string {
	q := url.Values{}
	if s.Q != "" {
		q.Set("q", s.Q)
	}
	for _, v := range s.Brands {
		q.Add("brand", v)
	}
	for _, v := range s.Categories {
		q.Add("category", v)
	}
	for _, v := range s.Prices {
		q.Add("price", v)
	}
	if s.Sort != "" {
		q.Set("sort", s.Sort)
	}
	if s.Mode != "hybrid" {
		q.Set("mode", s.Mode)
	}
	if s.Pool != defaultPool {
		q.Set("pool", strconv.Itoa(s.Pool))
	}
	if s.Page > 1 {
		q.Set("page", strconv.Itoa(s.Page))
	}
	if len(q) == 0 {
		return "/"
	}
	return "/?" + q.Encode()
}

// --- query vector ---

// embedder is a long-lived child process. The Zig binary loads the 54 MB model
// and the 30 000-entry WordPiece vocabulary once, then answers one NDJSON line
// per line. Spawning it per query cost 120 ms of startup to do 0.9 ms of work;
// here the query vector costs about a millisecond.
type embedder struct {
	bin       string
	dir       string
	threads   string
	maxTokens string

	mu     sync.Mutex
	cmd    *exec.Cmd
	stdin  io.WriteCloser
	stdout *bufio.Reader
	stderr *bytes.Buffer
}

// start launches the child. The embedder reads nothing from stdin until the
// model is loaded, so the first request doubles as the readiness probe.
func (e *embedder) start() error {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.startLocked()
}

func (e *embedder) args() []string {
	return []string{
		"--model", filepath.Join(e.dir, "model.onnx"),
		"--tokenizer", filepath.Join(e.dir, "tokenizer.json"),
		"--threads", e.threads,
		"--max-tokens", e.maxTokens,
		"--server",
	}
}

func (e *embedder) startLocked() error {
	cmd := exec.Command(e.bin, e.args()...)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	stderr := &bytes.Buffer{}
	cmd.Stderr = stderr
	if err := cmd.Start(); err != nil {
		return err
	}
	e.cmd, e.stdin, e.stdout, e.stderr = cmd, stdin, bufio.NewReader(stdout), stderr
	return nil
}

func (e *embedder) killLocked() {
	if e.stdin != nil {
		e.stdin.Close()
	}
	if e.cmd != nil {
		e.cmd.Process.Kill()
		e.cmd.Wait()
	}
	e.cmd, e.stdin, e.stdout = nil, nil, nil
}

func (e *embedder) close() {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.killLocked()
}

// embed sends one document and reads back the same document with its vector.
func (e *embedder) embed(text string) ([]float32, error) {
	if strings.TrimSpace(text) == "" {
		return nil, nil
	}
	e.mu.Lock()
	defer e.mu.Unlock()

	if e.cmd == nil {
		if err := e.startLocked(); err != nil {
			return nil, err
		}
	}
	vec, err := e.roundTrip(text)
	if err == nil {
		return vec, nil
	}

	// The child died or closed its pipes. Replace it and retry once, so a
	// crashed embedder costs one request instead of the process.
	e.killLocked()
	if restartErr := e.startLocked(); restartErr != nil {
		return nil, err
	}
	return e.roundTrip(text)
}

func (e *embedder) roundTrip(text string) ([]float32, error) {
	line, err := json.Marshal(map[string]string{"title_t": text})
	if err != nil {
		return nil, err
	}
	if _, err := e.stdin.Write(append(line, '\n')); err != nil {
		return nil, e.wrap(err)
	}
	resp, err := e.stdout.ReadBytes('\n')
	if err != nil {
		return nil, e.wrap(err)
	}
	var doc struct {
		Embedding []float32 `json:"embedding_v"`
	}
	if err := json.Unmarshal(resp, &doc); err != nil {
		return nil, e.wrap(err)
	}
	return doc.Embedding, nil
}

func (e *embedder) wrap(err error) error {
	return fmt.Errorf("%s: %w: %s", e.bin, err, strings.TrimSpace(e.stderr.String()))
}

// embedBatch is the bulk path: one child, many lines. It streams the enriched
// NDJSON out so the caller can pipe it straight into the indexer. Documents
// get a larger token budget than a query does.
func (e *embedder) embedBatch(path string, out io.Writer) error {
	in, err := os.Open(path)
	if err != nil {
		return err
	}
	defer in.Close()

	args := []string{
		"--model", filepath.Join(e.dir, "model.onnx"),
		"--tokenizer", filepath.Join(e.dir, "tokenizer.json"),
		"--threads", e.threads,
		"--max-tokens", "256",
		"--fields", "title_t,description_t",
	}
	cmd := exec.Command(e.bin, args...)
	cmd.Stdin = in
	cmd.Stdout = out
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

// --- gRPC engine client ---

var searcher luxirpb.SearcherClient

func connectEngine(addr string) error {
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return err
	}
	searcher = luxirpb.NewSearcherClient(conn)
	return nil
}

// search sends one SearchRequest and folds the response stream back into one
// logical response.
func search(req *luxirpb.SearchRequest) (*luxirpb.SearchResponse, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	stream, err := searcher.Search(ctx)
	if err != nil {
		return nil, err
	}
	if err := stream.Send(req); err != nil {
		return nil, err
	}
	if err := stream.CloseSend(); err != nil {
		return nil, err
	}
	first, err := stream.Recv()
	if err != nil {
		return nil, err
	}
	if first.GetError() != nil {
		e := first.GetError()
		return nil, fmt.Errorf("luxir %v (%s): %s", e.GetKind(), e.GetCode(), e.GetMessage())
	}
	last := first
	for last.GetMore() {
		next, err := stream.Recv()
		if err != nil {
			return nil, err
		}
		if next.GetError() != nil {
			e := next.GetError()
			return nil, fmt.Errorf("luxir %v (%s): %s", e.GetKind(), e.GetCode(), e.GetMessage())
		}
		for name, v := range last.GetOps() {
			if dl := v.GetDocs(); dl != nil && len(dl.GetDocs()) > 0 {
				if nl := next.GetOps()[name].GetDocs(); nl != nil {
					nl.Docs = append(dl.GetDocs(), nl.GetDocs()...)
					if nl.Found == nil {
						nl.Found = dl.Found
					}
				}
			}
		}
		last = next
	}
	return last, nil
}

func valStr(s string) *luxirpb.Val  { return &luxirpb.Val{Kind: &luxirpb.Val_S{S: s}} }
func valNum(v float64) *luxirpb.Val { return &luxirpb.Val{Kind: &luxirpb.Val_D{D: v}} }

func valStrings(list []string) *luxirpb.Val {
	return &luxirpb.Val{Kind: &luxirpb.Val_ArrS{ArrS: &luxirpb.ArrStr{V: list}}}
}

func selectedVal(list []string) *luxirpb.Val {
	switch len(list) {
	case 0:
		return nil
	case 1:
		return valStr(list[0])
	default:
		return valStrings(list)
	}
}

func prefixQuery(field, prefix string) *luxirpb.Query {
	return &luxirpb.Query{Kind: &luxirpb.Query_Prefix{Prefix: &luxirpb.PrefixQuery{Field: field, Prefix: prefix}}}
}

func anyOfQuery(field string, values []string) *luxirpb.Query {
	return &luxirpb.Query{Kind: &luxirpb.Query_AnyOf{AnyOf: &luxirpb.AnyOfQuery{Field: field, Values: valStrings(values)}}}
}

var resultFields = []string{"id", "title_t", "brand_name", "price_f", "image_s"}

// lexicalQuery is the BM25 source: the same simple_query the first post used.
func lexicalQuery(q string) *luxirpb.Query {
	return &luxirpb.Query{Kind: &luxirpb.Query_SimpleQuery{SimpleQuery: &luxirpb.SimpleQuery{
		Q:      q,
		Fields: []string{"title_t", "description_t", "brand_name"},
	}}}
}

// knnQuery is the semantic source. A vector field is only searchable when the
// schema names a metric, which the converter does not do; the field arrives
// as a plain _v column and is searchable all the same.
func knnQuery(q []float32, k int) *luxirpb.Query {
	return &luxirpb.Query{Kind: &luxirpb.Query_Knn{Knn: &luxirpb.KnnQuery{
		Field: "embedding_v",
		Query: &luxirpb.Vector{Kind: &luxirpb.Vector_F32{F32: &luxirpb.ArrFloat{V: q}}},
		K:     int32(k),
	}}}
}

// selectionFilters turns the checked facets into one shared filter list.
// Putting it on the fusion (not on each source) means Luxir computes it once
// per segment and applies it inside both ranked lists.
func selectionFilters(s state) []*luxirpb.Filter {
	var out []*luxirpb.Filter
	add := func(q *luxirpb.Query) { out = append(out, &luxirpb.Filter{Query: q}) }
	if len(s.Categories) > 0 {
		add(anyOfQuery("category_names", s.Categories))
	}
	if len(s.Brands) > 0 {
		add(anyOfQuery("brand_name", s.Brands))
	}
	for _, b := range priceBuckets {
		if !contains(s.Prices, b.Label) {
			continue
		}
		r := &luxirpb.RangeQuery{Field: "price_f"}
		if b.Min != nil {
			r.Gte = valNum(*b.Min)
		}
		if b.Max != nil {
			r.Lt = valNum(*b.Max)
		}
		add(&luxirpb.Query{Kind: &luxirpb.Query_Range{Range: r}})
	}
	return out
}

// facetOps builds the sidebar. `selected` is what makes guided navigation work
// in a TopDocs, but Luxir rejects it on a facet nested inside a Fusion:
// "selected is only supported on facets directly inside TopDocs.ops". Under
// the fusion the selection has to come from the fusion's own filter, which is
// what selectionFilters builds. So the hybrid path passes false and keeps the
// counts, dropping the selection bookkeeping.
func facetOps(s state, allowSelected bool) map[string]*luxirpb.SearchOp {
	limit6 := int64(6)
	buckets := []*luxirpb.QueryBucket{}
	for _, b := range priceBuckets {
		r := &luxirpb.RangeQuery{Field: "price_f"}
		if b.Min != nil {
			r.Gte = valNum(*b.Min)
		}
		if b.Max != nil {
			r.Lt = valNum(*b.Max)
		}
		buckets = append(buckets, &luxirpb.QueryBucket{
			Name:  b.Label,
			Query: &luxirpb.Query{Kind: &luxirpb.Query_Range{Range: r}},
		})
	}

	var catSel, brandSel, priceSel *luxirpb.Val
	if allowSelected {
		catSel, brandSel, priceSel = selectedVal(s.Categories), selectedVal(s.Brands), selectedVal(s.Prices)
	}

	return map[string]*luxirpb.SearchOp{
		"categories": {Kind: &luxirpb.SearchOp_FieldFacet{FieldFacet: &luxirpb.FieldFacet{
			Field: "category_names", Limit: &limit6, Selected: catSel, Missing: true,
		}}},
		"brands": {Kind: &luxirpb.SearchOp_FieldFacet{FieldFacet: &luxirpb.FieldFacet{
			Field: "brand_name", Limit: &limit6, Selected: brandSel, Missing: true,
		}}},
		"prices": {Kind: &luxirpb.SearchOp_QueryFacet{QueryFacet: &luxirpb.QueryFacet{
			Buckets: buckets, Selected: priceSel,
		}}},
		"avg_price": {Kind: &luxirpb.SearchOp_ExprOp{ExprOp: &luxirpb.ExprOp{Expr: "avg(price_f)"}}},
	}
}

// srpRequest builds one of three shapes.
//
// words   — a single top_docs with a simple_query, the lexical-only control.
// vectors — a single top_docs with a knn, the semantic-only control.
// hybrid  — a fusion whose two sources each get their own query and limit,
//
//	merged by reciprocal rank fusion. The facets hang off the
//	fusion, so they count the union of both ranked lists.
func srpRequest(s state, qvec []float32) *luxirpb.SearchRequest {
	limit := int64(pageSize)
	if s.Page > 1 {
		limit = int64(pageSize * s.Page)
	}
	sort := []*luxirpb.SortSpec(nil)
	if s.Sort != "" {
		sort = []*luxirpb.SortSpec{sortSpecs[s.Sort]}
	}

	switch s.Mode {
	case "words":
		q := lexicalQuery(s.Q)
		if s.Q == "" {
			q = &luxirpb.Query{Kind: &luxirpb.Query_All{All: true}}
		}
		return &luxirpb.SearchRequest{
			Collection: collection,
			Ops: map[string]*luxirpb.SearchOp{"q": {Kind: &luxirpb.SearchOp_TopDocs{TopDocs: &luxirpb.TopDocs{
				Query:          q,
				Filter:         selectionFilters(s),
				Limit:          &limit,
				Offset:         int64((s.Page - 1) * pageSize),
				GetNumber:      true,
				GetScores:      true,
				Fields:         resultFields,
				DocumentFormat: luxirpb.DocFormat_ROWS,
				Sort:           sort,
				Ops:            facetOps(s, true),
			}}}},
		}

	case "vectors":
		q := knnQuery(qvec, s.Pool)
		if len(qvec) == 0 {
			q = &luxirpb.Query{Kind: &luxirpb.Query_All{All: true}}
		}
		return &luxirpb.SearchRequest{
			Collection: collection,
			Ops: map[string]*luxirpb.SearchOp{"q": {Kind: &luxirpb.SearchOp_TopDocs{TopDocs: &luxirpb.TopDocs{
				Query:          q,
				Filter:         selectionFilters(s),
				Limit:          &limit,
				Offset:         int64((s.Page - 1) * pageSize),
				GetNumber:      true,
				GetScores:      true,
				Fields:         resultFields,
				DocumentFormat: luxirpb.DocFormat_ROWS,
				Sort:           sort,
				Ops:            facetOps(s, true),
			}}}},
		}
	}

	pool := int64(s.Pool)
	rd := int32(60)

	words := lexicalQuery(s.Q)
	if s.Q == "" {
		words = &luxirpb.Query{Kind: &luxirpb.Query_All{All: true}}
	}
	sources := map[string]*luxirpb.TopDocs{
		"words": {
			Query:          words,
			Limit:          &pool,
			Fields:         resultFields,
			DocumentFormat: luxirpb.DocFormat_ROWS,
		},
	}
	// Without a query there is no vector, and a knn with an empty one is
	// rejected, so the landing page is a single lexical source.
	if len(qvec) > 0 {
		sources["vectors"] = &luxirpb.TopDocs{
			Query:          knnQuery(qvec, s.Pool),
			Limit:          &pool,
			Fields:         resultFields,
			DocumentFormat: luxirpb.DocFormat_ROWS,
		}
	}
	return &luxirpb.SearchRequest{
		Collection: collection,
		Ops: map[string]*luxirpb.SearchOp{"q": {Kind: &luxirpb.SearchOp_Fusion{Fusion: &luxirpb.Fusion{
			Sources: sources,
			Filter:  selectionFilters(s),
			Method:  &luxirpb.Fusion_Rrf{Rrf: &luxirpb.RrfFusion{K: rd}},
			Limit:   &limit,
			Offset:  int64((s.Page - 1) * pageSize),
			// found counts the union of the two source windows, so it is the
			// honest number only while the pool is wider than the page.
			GetNumber:      true,
			GetScores:      true,
			Fields:         resultFields,
			DocumentFormat: luxirpb.DocFormat_ROWS,
			Ops:            facetOps(s, false),
		}}}},
	}
}

func rowProduct(m *luxirpb.Map) product {
	f := m.GetFields()
	p := product{
		ID:    f["id"].GetS(),
		Title: f["title_t"].GetS(),
		Desc:  f["description_t"].GetS(),
		Brand: f["brand_name"].GetS(),
		Image: f["image_s"].GetS(),
	}
	switch v := f["price_f"].GetKind().(type) {
	case *luxirpb.Val_D:
		p.Price = v.D
	case *luxirpb.Val_F:
		p.Price = float64(v.F)
	case *luxirpb.Val_I:
		p.Price = float64(v.I)
	}
	switch v := f["_score_"].GetKind().(type) {
	case *luxirpb.Val_D:
		p.Score = v.D
	case *luxirpb.Val_F:
		p.Score = float64(v.F)
	}
	p.Reviews = int(f["reviews_i"].GetI())
	if a := f["category_names"].GetArrS(); a != nil {
		p.Categories = a.GetV()
	}
	return p
}

func docList(resp *luxirpb.SearchResponse, name string) *luxirpb.DocList {
	return resp.GetOps()[name].GetDocs()
}

func rows(dl *luxirpb.DocList) []product {
	if dl == nil {
		return nil
	}
	out := make([]product, 0, len(dl.GetDocs()))
	for _, m := range dl.GetDocs() {
		out = append(out, rowProduct(m))
	}
	return out
}

func facetBuckets(resp *luxirpb.SearchResponse, qops map[string]*luxirpb.Val, name string) []bucket {
	var fr *luxirpb.FacetResult
	if qops != nil {
		fr = qops[name].GetFacet()
	} else {
		fr = resp.GetOps()[name].GetFacet()
	}
	if fr == nil {
		return nil
	}
	ids := fr.GetBucketIds().GetColS().GetV()
	var out []bucket
	for i, id := range ids {
		b := bucket{Val: id}
		if i < len(fr.GetCounts()) {
			b.Count = int(fr.GetCounts()[i])
		}
		out = append(out, b)
	}
	return out
}

func metricFloat(ops map[string]*luxirpb.Val, name string) *float64 {
	v, ok := ops[name]
	if !ok || v == nil {
		return nil
	}
	switch k := v.GetKind().(type) {
	case *luxirpb.Val_D:
		return &k.D
	case *luxirpb.Val_F:
		d := float64(k.F)
		return &d
	case *luxirpb.Val_I:
		d := float64(k.I)
		return &d
	}
	return nil
}

// --- views ---

type srpView struct {
	State      state
	Found      int
	Docs       []product
	AvgPrice   *float64
	TookMS     float64
	EmbedMS    float64
	Brands     []facetView
	Categories []facetView
	Prices     []facetView
	Sorts      []facetView
	Modes      []modeOption
	Pools      []facetView
	Chips      []chip
	ClearURL   string
	Prev, Next string
	LastPage   int
}

func buildView(s state, emb *embedder) (srpView, error) {
	var v srpView

	// The query vector is the one thing a semantic search cannot skip. With the
	// embedder kept warm it is a millisecond; it was 120 when the model was
	// reloaded per request.
	embedStart := time.Now()
	qvec, err := emb.embed(s.Q)
	if err != nil {
		return v, fmt.Errorf("embed: %w", err)
	}
	embedMS := float64(time.Since(embedStart).Microseconds()) / 1000

	start := time.Now()
	resp, err := search(srpRequest(s, qvec))
	if err != nil {
		return v, err
	}
	tookMS := float64(time.Since(start).Microseconds()) / 1000

	qdl := docList(resp, "q")
	v.State, v.TookMS, v.EmbedMS = s, tookMS, embedMS
	v.Found = int(qdl.GetFound())
	v.Docs = rows(qdl)
	subs := qdl.GetOps()
	v.AvgPrice = metricFloat(subs, "avg_price")

	cats := facetBuckets(resp, subs, "categories")
	brands := facetBuckets(resp, subs, "brands")
	prices := facetBuckets(resp, subs, "prices")

	for _, c := range cats {
		v.Categories = append(v.Categories, facetView{c.Val, c.Count, contains(s.Categories, c.Val), s.withCategory(c.Val)})
	}
	for _, b := range brands {
		v.Brands = append(v.Brands, facetView{b.Val, b.Count, contains(s.Brands, b.Val), s.toggle("brand", b.Val)})
	}
	counted := map[string]int{}
	for _, b := range prices {
		counted[b.Val] = b.Count
	}
	for _, p := range priceBuckets {
		v.Prices = append(v.Prices, facetView{p.Label, counted[p.Label], contains(s.Prices, p.Label), s.toggle("price", p.Label)})
	}
	for _, o := range sortOptions {
		v.Sorts = append(v.Sorts, facetView{o.label, 0, s.Sort == o.key, s.toggle("sort", o.key)})
	}
	for _, m := range []struct{ key, label string }{{"words", "Words"}, {"vectors", "Vectors"}, {"hybrid", "Hybrid"}} {
		v.Modes = append(v.Modes, modeOption{m.key, m.label, s.toggle("mode", m.key)})
	}
	for _, p := range poolOptions {
		v.Pools = append(v.Pools, facetView{strconv.Itoa(p), 0, s.Pool == p, s.toggle("pool", strconv.Itoa(p))})
	}
	for _, c := range s.Categories {
		v.Chips = append(v.Chips, chip{c, s.withoutCategory(c)})
	}
	for _, b := range s.Brands {
		v.Chips = append(v.Chips, chip{b, s.toggle("brand", b)})
	}
	for _, p := range s.Prices {
		v.Chips = append(v.Chips, chip{p, s.toggle("price", p)})
	}
	clear := s
	clear.Brands, clear.Categories, clear.Prices, clear.Page = nil, nil, nil, 1
	v.ClearURL = clear.href()
	v.LastPage = (v.Found + pageSize - 1) / pageSize
	if s.Page > 1 {
		back := s
		back.Page--
		v.Prev = back.href()
	}
	if s.Page < v.LastPage {
		next := s
		next.Page++
		v.Next = next.href()
	}
	return v, nil
}

type taView struct {
	Q        string
	Products []product
	Brands   []facetView
	Cats     []facetView
}

func taRequest(q string) *luxirpb.SearchRequest {
	limit5 := int64(5)
	limit3 := int64(3)
	return &luxirpb.SearchRequest{
		Collection: collection,
		Ops: map[string]*luxirpb.SearchOp{
			"products": {Kind: &luxirpb.SearchOp_TopDocs{TopDocs: &luxirpb.TopDocs{
				Query:          prefixQuery("title_t", q),
				Limit:          &limit5,
				Fields:         resultFields,
				DocumentFormat: luxirpb.DocFormat_ROWS,
			}}},
			"brands": {
				Kind:   &luxirpb.SearchOp_FieldFacet{FieldFacet: &luxirpb.FieldFacet{Field: "brand_name", Limit: &limit3}},
				Domain: &luxirpb.Domain{Query: prefixQuery("brand_name", q)},
			},
			"categories": {
				Kind:   &luxirpb.SearchOp_FieldFacet{FieldFacet: &luxirpb.FieldFacet{Field: "category_names", Limit: &limit3}},
				Domain: &luxirpb.Domain{Query: prefixQuery("category_names", q)},
			},
		},
	}
}

func taViewFor(q string) (taView, error) {
	resp, err := search(taRequest(q))
	if err != nil {
		return taView{}, err
	}
	v := taView{Q: q, Products: rows(docList(resp, "products"))}
	for _, b := range facetBuckets(resp, nil, "brands") {
		v.Brands = append(v.Brands, facetView{Label: b.Val, Count: b.Count, URL: "/?brand=" + url.QueryEscape(b.Val)})
	}
	for _, b := range facetBuckets(resp, nil, "categories") {
		v.Cats = append(v.Cats, facetView{Label: b.Val, Count: b.Count, URL: "/?category=" + url.QueryEscape(b.Val)})
	}
	return v, nil
}

type pdpView struct {
	P           product
	BrandURL    string
	Category    string
	CategoryURL string
	Related     []product
}

// pdpViewFor keeps the boolean "same category, not me" query for the related
// row, and swaps the kNN in as a fallback: a category with one product in it
// returns nothing, and the nearest neighbours always return something.
func pdpViewFor(id string) (pdpView, error) {
	fields := []string{"id", "title_t", "description_t", "brand_name", "price_f", "reviews_i", "image_s", "category_names"}
	resp, err := search(&luxirpb.SearchRequest{
		Collection: collection,
		Ops: map[string]*luxirpb.SearchOp{"q": {Kind: &luxirpb.SearchOp_TopDocs{TopDocs: &luxirpb.TopDocs{
			Query:          anyOfQuery("id", []string{id}),
			Fields:         fields,
			DocumentFormat: luxirpb.DocFormat_ROWS,
		}}}},
	})
	if err != nil {
		return pdpView{}, err
	}
	docs := rows(docList(resp, "q"))
	if len(docs) == 0 {
		return pdpView{}, fmt.Errorf("product not found")
	}
	p := docs[0]
	v := pdpView{P: p, BrandURL: "/?brand=" + url.QueryEscape(p.Brand)}
	if len(p.Categories) > 0 {
		v.Category = p.Categories[0]
		v.CategoryURL = "/?category=" + url.QueryEscape(v.Category)
	}

	limit4 := int64(4)
	base := func(q *luxirpb.Query) *luxirpb.SearchRequest {
		return &luxirpb.SearchRequest{Collection: collection, Ops: map[string]*luxirpb.SearchOp{
			"q": {Kind: &luxirpb.SearchOp_TopDocs{TopDocs: &luxirpb.TopDocs{
				Query:          q,
				Limit:          &limit4,
				Fields:         resultFields,
				DocumentFormat: luxirpb.DocFormat_ROWS,
			}}},
		}}
	}
	byCategory := &luxirpb.Query{Kind: &luxirpb.Query_Boolean{Boolean: &luxirpb.BooleanQuery{
		Required:   []*luxirpb.Query{anyOfQuery("category_names", p.Categories)},
		Prohibited: []*luxirpb.Query{anyOfQuery("id", []string{p.ID})},
	}}}
	byBrand := &luxirpb.Query{Kind: &luxirpb.Query_Boolean{Boolean: &luxirpb.BooleanQuery{
		Required:   []*luxirpb.Query{anyOfQuery("brand_name", []string{p.Brand})},
		Prohibited: []*luxirpb.Query{anyOfQuery("id", []string{p.ID})},
	}}}
	for _, q := range []*luxirpb.Query{byCategory, byBrand} {
		related, err := search(base(q))
		if err != nil {
			log.Println("related search:", err)
			break
		}
		if v.Related = rows(docList(related, "q")); len(v.Related) > 0 {
			break
		}
	}
	return v, nil
}

var tmpl = template.Must(template.New("").Funcs(template.FuncMap{
	"price": func(v float64) string { return fmt.Sprintf("$%.2f", v) },
	"join":  strings.Join,
}).ParseFS(tmplFS, "templates/*.html"))

func writeErr(w http.ResponseWriter, err error) {
	http.Error(w, err.Error(), http.StatusBadGateway)
}

func noStore(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		h(w, r)
	}
}

var embedBin *embedder

func index(w http.ResponseWriter, r *http.Request) {
	v, err := buildView(parseState(r), embedBin)
	if err != nil {
		writeErr(w, err)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	name := "page"
	if r.Header.Get("HX-Request") != "" && r.Header.Get("HX-History-Restore-Request") != "true" {
		name = "srp"
	}
	if err := tmpl.ExecuteTemplate(w, name, v); err != nil {
		log.Println(err)
	}
}

func typeahead(w http.ResponseWriter, r *http.Request) {
	q := strings.TrimSpace(r.URL.Query().Get("q"))
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if len(q) < 2 {
		return
	}
	v, err := taViewFor(q)
	if err != nil {
		writeErr(w, err)
		return
	}
	if err := tmpl.ExecuteTemplate(w, "typeahead", v); err != nil {
		log.Println(err)
	}
}

func productPage(w http.ResponseWriter, r *http.Request) {
	v, err := pdpViewFor(r.PathValue("id"))
	if err != nil {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := tmpl.ExecuteTemplate(w, "product", v); err != nil {
		log.Println(err)
	}
}

//go:embed templates/*.html
var tmplFS embed.FS

func main() {
	grpcAddr := flag.String("luxir-grpc", "localhost:9401", "Luxir gRPC address")
	httpAddr := flag.String("addr", ":8080", "listen address")
	embedPath := flag.String("embed", "embedder/zig-out/bin/embed", "path to the Zig embedder")
	embedThreads := flag.String("embed-threads", "6", "ONNX Runtime intra-op threads for query vectors")
	embedDir := flag.String("embed-dir", "embedder", "directory holding model.onnx and tokenizer.json")
	embedMaxTokens := flag.String("embed-max-tokens", "64", "token budget for a query vector")
	bulkIn := flag.String("bulk-in", "", "embed this NDJSON file to stdout with vectors, then exit")
	flag.Parse()

	embedBin = &embedder{
		bin:       *embedPath,
		dir:       *embedDir,
		threads:   *embedThreads,
		maxTokens: *embedMaxTokens,
	}

	// Bulk mode: read a file, write the same file with vectors, exit. It needs
	// no engine, which is what makes it usable as an ingest step.
	if *bulkIn != "" {
		if err := embedBin.embedBatch(*bulkIn, os.Stdout); err != nil {
			log.Fatal(err)
		}
		return
	}

	if err := connectEngine(*grpcAddr); err != nil {
		log.Fatal(err)
	}
	if err := embedBin.start(); err != nil {
		log.Fatal(err)
	}
	defer embedBin.close()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /", noStore(index))
	mux.HandleFunc("GET /typeahead", noStore(typeahead))
	mux.HandleFunc("GET /product/{id}", noStore(productPage))
	log.Println("listening on", *httpAddr)
	log.Fatal(http.ListenAndServe(*httpAddr, mux))
}
