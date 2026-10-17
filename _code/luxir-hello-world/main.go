package main

import (
	"context"
	"embed"
	"flag"
	"fmt"
	"html/template"
	"log"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"luxir-hello-world/luxirpb"
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

type state struct {
	Q          string
	Brands     []string
	Categories []string
	Prices     []string
	Sort       string
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
	return state{
		Q:          q.Get("q"),
		Brands:     q["brand"],
		Categories: q["category"],
		Prices:     q["price"],
		Sort:       sortParam(q.Get("sort")),
		Page:       page,
	}
}

func sortParam(v string) string {
	if _, ok := sortSpecs[v]; ok {
		return v
	}
	return ""
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
	if s.Page > 1 {
		q.Set("page", strconv.Itoa(s.Page))
	}
	if len(q) == 0 {
		return "/"
	}
	return "/?" + q.Encode()
}

const pageSize = 12

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
// logical response. Small requests arrive in a single batch; the loop keeps
// document rows from earlier batches and takes facets and counts from the last.
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

func srpRequest(s state) *luxirpb.SearchRequest {
	query := &luxirpb.Query{Kind: &luxirpb.Query_All{All: true}}
	if s.Q != "" {
		query = &luxirpb.Query{Kind: &luxirpb.Query_SimpleQuery{SimpleQuery: &luxirpb.SimpleQuery{
			Q:      s.Q,
			Fields: []string{"title_t", "description_t", "brand_name"},
		}}}
	}
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
	limit6 := int64(6)
	td := &luxirpb.TopDocs{
		Query:          query,
		Limit:          func() *int64 { v := int64(pageSize); return &v }(),
		GetNumber:      true,
		Fields:         []string{"id", "title_t", "brand_name", "price_f", "image_s"},
		DocumentFormat: luxirpb.DocFormat_ROWS,
		Sort:           nil,
	}
	if s.Sort != "" {
		td.Sort = []*luxirpb.SortSpec{sortSpecs[s.Sort]}
	}
	if s.Page > 1 {
		td.Offset = int64((s.Page - 1) * pageSize)
	}
	td.Ops = map[string]*luxirpb.SearchOp{
		"categories": {Kind: &luxirpb.SearchOp_FieldFacet{FieldFacet: &luxirpb.FieldFacet{
			Field: "category_names", Limit: &limit6, Selected: selectedVal(s.Categories), Missing: true,
		}}},
		"brands": {Kind: &luxirpb.SearchOp_FieldFacet{FieldFacet: &luxirpb.FieldFacet{
			Field: "brand_name", Limit: &limit6, Selected: selectedVal(s.Brands), Missing: true,
		}}},
		"prices": {Kind: &luxirpb.SearchOp_QueryFacet{QueryFacet: &luxirpb.QueryFacet{
			Buckets: buckets, Selected: selectedVal(s.Prices),
		}}},
		"avg_price": {Kind: &luxirpb.SearchOp_ExprOp{ExprOp: &luxirpb.ExprOp{Expr: "avg(price_f)"}}},
	}
	return &luxirpb.SearchRequest{
		Collection: "products",
		Ops:        map[string]*luxirpb.SearchOp{"q": {Kind: &luxirpb.SearchOp_TopDocs{TopDocs: td}}},
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

type srpResponse struct {
	Found int
	Docs  []product
	Ops   struct {
		Brands     []bucket
		Categories []bucket
		Prices     []bucket
		AvgPrice   *float64
	}
}

type srpView struct {
	State      state
	Resp       srpResponse
	TookMS     float64
	Brands     []facetView
	Categories []facetView
	Prices     []facetView
	Sorts      []facetView
	Chips      []chip
	ClearURL   string
	Prev, Next string
	LastPage   int
}

func buildView(s state) (srpView, error) {
	start := time.Now()
	resp, err := search(srpRequest(s))
	tookMS := float64(time.Since(start).Microseconds()) / 1000
	if err != nil {
		return srpView{}, err
	}
	qdl := docList(resp, "q")
	var v srpView
	v.State, v.TookMS = s, tookMS
	v.Resp.Found = int(qdl.GetFound())
	v.Resp.Docs = rows(qdl)
	subs := qdl.GetOps()
	v.Resp.Ops.Brands = facetBuckets(resp, subs, "brands")
	v.Resp.Ops.Categories = facetBuckets(resp, subs, "categories")
	v.Resp.Ops.Prices = facetBuckets(resp, subs, "prices")
	v.Resp.Ops.AvgPrice = metricFloat(subs, "avg_price")
	for _, c := range v.Resp.Ops.Categories {
		v.Categories = append(v.Categories, facetView{c.Val, c.Count, contains(s.Categories, c.Val), s.withCategory(c.Val)})
	}
	for _, b := range v.Resp.Ops.Brands {
		v.Brands = append(v.Brands, facetView{b.Val, b.Count, contains(s.Brands, b.Val), s.toggle("brand", b.Val)})
	}
	counted := map[string]int{}
	for _, b := range v.Resp.Ops.Prices {
		counted[b.Val] = b.Count
	}
	for _, p := range priceBuckets {
		v.Prices = append(v.Prices, facetView{p.Label, counted[p.Label], contains(s.Prices, p.Label), s.toggle("price", p.Label)})
	}
	for _, o := range sortOptions {
		v.Sorts = append(v.Sorts, facetView{o.label, 0, s.Sort == o.key, s.toggle("sort", o.key)})
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
	v.LastPage = (v.Resp.Found + pageSize - 1) / pageSize
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
		Collection: "products",
		Ops: map[string]*luxirpb.SearchOp{
			"products": {Kind: &luxirpb.SearchOp_TopDocs{TopDocs: &luxirpb.TopDocs{
				Query:          prefixQuery("title_t", q),
				Limit:          &limit5,
				Fields:         []string{"id", "title_t", "brand_name", "price_f", "image_s"},
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

func pdpViewFor(id string) (pdpView, error) {
	fields := []string{"id", "title_t", "description_t", "brand_name", "price_f", "reviews_i", "image_s", "category_names"}
	limit4 := int64(4)
	resp, err := search(&luxirpb.SearchRequest{
		Collection: "products",
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
	relatedQuery := func(categoryOrBrand bool) map[string]*luxirpb.SearchOp {
		q := &luxirpb.Query{Kind: &luxirpb.Query_Boolean{Boolean: &luxirpb.BooleanQuery{
			Prohibited: []*luxirpb.Query{anyOfQuery("id", []string{p.ID})},
		}}}
		b := q.GetBoolean()
		if categoryOrBrand && len(p.Categories) > 0 {
			b.Required = []*luxirpb.Query{anyOfQuery("category_names", p.Categories)}
		} else if !categoryOrBrand && p.Brand != "" {
			b.Required = []*luxirpb.Query{anyOfQuery("brand_name", []string{p.Brand})}
		} else {
			return nil
		}
		return map[string]*luxirpb.SearchOp{"q": {Kind: &luxirpb.SearchOp_TopDocs{TopDocs: &luxirpb.TopDocs{
			Query:          q,
			Limit:          &limit4,
			Fields:         []string{"id", "title_t", "brand_name", "price_f", "image_s"},
			DocumentFormat: luxirpb.DocFormat_ROWS,
		}}}}
	}
	for _, byCategory := range []bool{true, false} {
		ops := relatedQuery(byCategory)
		if ops == nil {
			continue
		}
		related, err := search(&luxirpb.SearchRequest{Collection: "products", Ops: ops})
		if err != nil {
			log.Println("related search:", err)
			break
		}
		v.Related = rows(docList(related, "q"))
		if len(v.Related) > 0 {
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

func index(w http.ResponseWriter, r *http.Request) {
	v, err := buildView(parseState(r))
	if err != nil {
		writeErr(w, err)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	name := "page"
	// Live htmx swaps get the fragment. A history restore (HX-History-Restore-Request)
	// replaces the whole document and must receive the full page.
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
	flag.Parse()
	if err := connectEngine(*grpcAddr); err != nil {
		log.Fatal(err)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /", noStore(index))
	mux.HandleFunc("GET /typeahead", noStore(typeahead))
	mux.HandleFunc("GET /product/{id}", noStore(productPage))
	log.Println("listening on", *httpAddr)
	log.Fatal(http.ListenAndServe(*httpAddr, mux))
}
